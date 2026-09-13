"""第四问隔离回放内核：预测价做计划，真实价做执行与结算。

本模块只复用第二、三问已经冻结的物理执行器和线性规划内核，不修改
原有回放器。所有价格预测均绑定真实决策时刻，并保存来源观测时间。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from core import accountant
from core.executor import ExecRecord, estimate_bridge_soc, execute_q2
from core.q3_ledger import Q3PlanVersion, settle_q3_slot
from core.q3_optimizer import solve_adjustment_lp, solve_standard_sparse
from core.slot_adapter import Slot, build_day_slots


UPDATE_SLOT = {0: 0, 6: 35, 12: 71, 18: 107}
ROLLING_DAYS = 7
PriceProvider = Callable[..., pd.DataFrame]
EnergyProvider = Callable[[datetime, Sequence[datetime]], pd.DataFrame]


@dataclass
class Q42DayPlan:
    day: date
    issue_time: datetime
    grid: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    price_meta: pd.DataFrame


@dataclass
class Q43DayPlan:
    day: date
    initial_grid: np.ndarray
    grid: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    versions: dict[int, list[Q3PlanVersion]]
    price_versions: dict[int, list[dict]]


def _default_price_provider(*args, **kwargs) -> pd.DataFrame:
    # 延迟导入，允许价格层与回放层并行开发，也避免模块循环导入。
    from core.q4_price import forecast_prices_as_of

    return forecast_prices_as_of(*args, **kwargs)


def _horizon_slots(day: date, start_slot: int) -> list[Slot]:
    if not 0 <= start_slot < 144:
        raise ValueError("start_slot 必须在0至143之间")
    rows: list[Slot] = []
    for offset in range(ROLLING_DAYS):
        slots = build_day_slots(day + timedelta(days=offset))
        rows.extend(slots[start_slot:] if offset == 0 else slots)
    return rows


def _forecast_prices(
    actual_prices: pd.DataFrame,
    decision_time: datetime,
    target_times: Sequence[datetime],
    *,
    method: str,
    price_provider: PriceProvider | None,
) -> pd.DataFrame:
    provider = price_provider or _default_price_provider
    frame = provider(actual_prices, decision_time, list(target_times), method=method).copy()
    required = {
        "issue_time", "target_time", "source_time", "source_observed_at",
        "price_forecast", "method",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"价格预测缺少字段: {sorted(missing)}")
    if len(frame) != len(target_times):
        raise ValueError("价格预测长度与目标槽不一致")
    if list(pd.to_datetime(frame["target_time"])) != list(pd.to_datetime(target_times)):
        raise ValueError("价格预测目标时刻顺序与请求不一致")
    issue = pd.to_datetime(frame["issue_time"])
    observed = pd.to_datetime(frame["source_observed_at"])
    if (issue != pd.Timestamp(decision_time)).any():
        raise ValueError("价格预测issue_time不是当前真实决策时刻")
    if (observed > pd.Timestamp(decision_time)).any():
        raise ValueError("价格预测使用了决策时刻之后才观测到的真实价格")
    values = frame["price_forecast"].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < -1e-9).any():
        raise ValueError("预测电价必须为有限非负数")
    return frame.reset_index(drop=True)


def _forecast_energy(
    provider: EnergyProvider,
    decision_time: datetime,
    target_times: Sequence[datetime],
) -> pd.DataFrame:
    frame = provider(decision_time, list(target_times)).copy()
    required = {"target_time", "load_forecast", "pv_forecast", "source_max_observed_at"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"能量预测缺少字段: {sorted(missing)}")
    if len(frame) != len(target_times):
        raise ValueError("能量预测长度与目标槽不一致")
    if list(pd.to_datetime(frame["target_time"])) != list(pd.to_datetime(target_times)):
        raise ValueError("能量预测目标时刻顺序与请求不一致")
    if (pd.to_datetime(frame["source_max_observed_at"]) > pd.Timestamp(decision_time)).any():
        raise ValueError("能量预测使用了真实决策时刻之后的数据")
    values = frame[["load_forecast", "pv_forecast"]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < -1e-9).any():
        raise ValueError("负荷和光伏预测必须为有限非负数")
    return frame.reset_index(drop=True)


def _actual_price_vector(actual_prices: pd.DataFrame, target_times: Sequence[datetime]) -> np.ndarray:
    required = {"target_time", "price_actual"}
    missing = required - set(actual_prices.columns)
    if missing:
        raise ValueError(f"真实价格缺少字段: {sorted(missing)}")
    rows = actual_prices.copy()
    rows["target_time"] = pd.to_datetime(rows["target_time"])
    if rows["target_time"].duplicated().any():
        raise ValueError("真实价格target_time重复")
    lookup = rows.set_index("target_time")["price_actual"]
    try:
        values = np.asarray([lookup.loc[pd.Timestamp(t)] for t in target_times], dtype=float)
    except KeyError as exc:
        raise ValueError(f"缺少目标槽真实价格: {exc}") from exc
    if not np.isfinite(values).all() or (values < -1e-9).any():
        raise ValueError("真实价格必须为有限非负数")
    return values


def _truth_for_day(actuals: pd.DataFrame, day: date) -> pd.DataFrame:
    truth = actuals[actuals["date"] == day].sort_values("slot")
    if len(truth) != 144 or truth["slot"].tolist() != list(range(144)):
        raise ValueError(f"{day}实际负荷与光伏不是唯一完整144槽")
    return truth


def make_q42_plan(
    day: date,
    soc0: float,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    *,
    price_method: str = "D-7",
    price_provider: PriceProvider | None = None,
) -> Q42DayPlan:
    """在当天0:00用同一个真实决策时刻生成七天计划，只返回第一天。"""
    decision = datetime.combine(day, datetime.min.time())
    slots = _horizon_slots(day, 0)
    targets = [s.interval_start for s in slots]
    energy = _forecast_energy(energy_provider, decision, targets)
    prices = _forecast_prices(
        actual_prices, decision, targets, method=price_method, price_provider=price_provider
    )
    solution = solve_standard_sparse(
        price=prices["price_forecast"].to_numpy(dtype=float),
        load=energy["load_forecast"].to_numpy(dtype=float) / 6.0,
        pv_available=energy["pv_forecast"].to_numpy(dtype=float) / 6.0,
        soc0=soc0,
        soc_final=soc0,
    )
    if not np.isfinite(solution.grid).all():
        raise AssertionError(f"{day} 第四问第二问计划不可行: {solution.message}")
    return Q42DayPlan(
        day=day,
        issue_time=decision,
        grid=solution.grid[:144].copy(),
        charge=solution.charge[:144].copy(),
        discharge=solution.discharge[:144].copy(),
        price_meta=prices.iloc[:144].copy(),
    )


def _execute(
    day: date,
    plan_grid: np.ndarray,
    plan_charge: np.ndarray,
    plan_discharge: np.ndarray,
    truth: pd.DataFrame,
    actual_prices: pd.DataFrame,
    lo: int,
    hi: int,
    soc0: float,
    issue_time: datetime,
) -> list[ExecRecord]:
    slots = build_day_slots(day)[lo:hi]
    prices = _actual_price_vector(actual_prices, [s.interval_start for s in slots])
    return execute_q2(
        grid_contract=plan_grid[lo:hi],
        price=prices,
        load_actual=truth["load_actual"].to_numpy(dtype=float)[lo:hi] / 6.0,
        pv_available=truth["pv_actual"].to_numpy(dtype=float)[lo:hi] / 6.0,
        charge_planned=plan_charge[lo:hi],
        discharge_planned=plan_discharge[lo:hi],
        soc0=soc0,
        starts=[s.interval_start for s in slots],
        ends=[s.interval_end for s in slots],
        slot_ids=list(range(lo, hi)),
        plan_issue_time=issue_time,
    )


def _record_row(day: date, rec: ExecRecord, price_meta: pd.Series) -> dict:
    return {
        "date": day.isoformat(),
        "slot": rec.slot,
        "interval_start": rec.interval_start.isoformat(),
        "interval_end": rec.interval_end.isoformat(),
        "decision_time": pd.Timestamp(price_meta["issue_time"]).isoformat(),
        "price_source_time": (
            None if pd.isna(price_meta.get("source_time"))
            else pd.Timestamp(price_meta["source_time"]).isoformat()
        ),
        "price_method": str(price_meta.get("method", "unknown")),
        "price_forecast": float(price_meta["price_forecast"]),
        "price_actual": float(rec.price),
        "price_source_observed_at": pd.Timestamp(price_meta["source_observed_at"]).isoformat(),
        "grid_contract": rec.grid_contract,
        "grid_delivered": rec.grid_delivered,
        "grid_unused": rec.grid_unused,
        "grid_emergency": rec.grid_emergency,
        "load_actual": rec.load,
        "pv_available": rec.pv_available,
        "pv_used": rec.pv_used,
        "pv_curtail": rec.pv_curtail,
        "charge_planned": rec.charge_planned,
        "charge_actual": rec.charge,
        "discharge_planned": rec.discharge_planned,
        "discharge_actual": rec.discharge,
        "soc_start": rec.soc_start,
        "soc_end": rec.soc_end,
        "normal_cost_actual": rec.normal_cost,
        "emergency_cost_actual": rec.emergency_cost,
    }


def replay_q42(
    actuals: pd.DataFrame,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    start: date,
    end: date,
    *,
    soc0: float = 6000.0,
    price_method: str = "D-7",
    price_provider: PriceProvider | None = None,
    collect_records: bool = True,
    evaluation_start: date | None = None,
    progress=None,
) -> dict:
    """按D009做第四问第二问顺序回放，包含午夜先计划、后执行旧末槽。"""
    if end < start:
        raise ValueError("回放结束日期不得早于开始日期")
    evaluation_start = evaluation_start or start
    if not start <= evaluation_start <= end:
        raise ValueError("评价起点必须落在回放区间内")
    day = start
    actual_soc = float(soc0)
    plan = make_q42_plan(
        day, actual_soc, actual_prices, energy_provider,
        price_method=price_method, price_provider=price_provider,
    )
    daily: list[dict] = []
    output: list[dict] = []
    while day <= end:
        truth = _truth_for_day(actuals, day)
        first = _execute(
            day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
            0, 143, actual_soc, plan.issue_time,
        )
        soc_midnight = first[-1].soc_end
        next_plan = None
        if day < end:
            estimated = estimate_bridge_soc(soc_midnight, plan.charge[143], plan.discharge[143])
            next_plan = make_q42_plan(
                day + timedelta(days=1), estimated, actual_prices, energy_provider,
                price_method=price_method, price_provider=price_provider,
            )
        bridge = _execute(
            day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
            143, 144, soc_midnight, plan.issue_time,
        )
        records = first + bridge
        audit = accountant.audit(records, require_q1_semantics=False)
        if not audit.ok:
            raise AssertionError(f"{day} 第四问第二问物理核算失败: {audit.violations[:5]}")
        daily.append({
            "date": day.isoformat(), "cost_normal": audit.cost_normal,
            "cost_emergency": audit.cost_emergency, "cost_total": audit.cost_total,
            "actual_soc_start": actual_soc, "actual_soc_end": records[-1].soc_end,
            "audit_ok": audit.ok,
        })
        if collect_records and day >= evaluation_start:
            output.extend(_record_row(day, rec, plan.price_meta.iloc[rec.slot]) for rec in records)
        if progress is not None:
            progress(day, daily[-1])
        actual_soc = records[-1].soc_end
        if next_plan is not None:
            plan = next_plan
        day += timedelta(days=1)
    evaluated = [r for r in daily if r["date"] >= evaluation_start.isoformat()]
    return {
        "mode": "Q4-2", "replay_days": len(daily),
        "evaluation_days": len(evaluated),
        "cost_normal": float(sum(r["cost_normal"] for r in evaluated)),
        "cost_emergency": float(sum(r["cost_emergency"] for r in evaluated)),
        "cost_total": float(sum(r["cost_total"] for r in evaluated)),
        "daily": daily, "records": output if collect_records else [], "versions": [],
        "price_sources": [
            {
                "issue_time": row["decision_time"],
                "target_time": row["interval_start"],
                "source_time": row["price_source_time"],
                "source_observed_at": row["price_source_observed_at"],
                "price_forecast": row["price_forecast"],
                "method": row["price_method"],
            }
            for row in output
        ],
    }


def _q43_horizon(
    day: date,
    issue_hour: int,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    price_method: str,
    price_provider: PriceProvider | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    decision = datetime.combine(day, datetime.min.time()) + timedelta(hours=issue_hour)
    slots = _horizon_slots(day, UPDATE_SLOT[issue_hour])
    targets = [s.interval_start for s in slots]
    return (
        _forecast_energy(energy_provider, decision, targets),
        _forecast_prices(actual_prices, decision, targets, method=price_method,
                         price_provider=price_provider),
    )


def make_q43_initial_plan(
    day: date,
    soc0: float,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    *,
    price_method: str = "D-7",
    price_provider: PriceProvider | None = None,
) -> Q43DayPlan:
    energy, prices = _q43_horizon(
        day, 0, actual_prices, energy_provider, price_method, price_provider
    )
    p = prices["price_forecast"].to_numpy(dtype=float)
    solution = solve_standard_sparse(
        price=p, load=energy["load_forecast"].to_numpy(dtype=float) / 6.0,
        pv_available=energy["pv_forecast"].to_numpy(dtype=float) / 6.0,
        soc0=soc0, soc_final=soc0,
    )
    if not np.isfinite(solution.grid).all():
        raise AssertionError(f"{day} 第四问第三问初始计划不可行: {solution.message}")
    issue = datetime.combine(day, datetime.min.time())
    initial = solution.grid[:144].copy()
    versions = {t: [Q3PlanVersion(t, issue, 0, float(initial[t]))] for t in range(144)}
    meta = {
        t: [{
            "issue_time": issue,
            "price_forecast": float(prices.iloc[t]["price_forecast"]),
            "source_time": prices.iloc[t]["source_time"],
            "source_observed_at": pd.Timestamp(prices.iloc[t]["source_observed_at"]).to_pydatetime(),
            "method": prices.iloc[t]["method"],
        }]
        for t in range(144)
    }
    return Q43DayPlan(day, initial, initial.copy(), solution.charge[:144].copy(),
                      solution.discharge[:144].copy(), versions, meta)


def update_q43_plan(
    plan: Q43DayPlan,
    issue_hour: int,
    soc_now: float,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    *,
    price_method: str = "D-7",
    price_provider: PriceProvider | None = None,
) -> None:
    if issue_hour not in (6, 12, 18):
        raise ValueError("第三问只允许在6、12、18时调整")
    start = UPDATE_SLOT[issue_hour]
    energy, prices = _q43_horizon(
        plan.day, issue_hour, actual_prices, energy_provider, price_method, price_provider
    )
    remaining = 144 - start
    p = prices["price_forecast"].to_numpy(dtype=float)
    solution = solve_adjustment_lp(
        price=p, load=energy["load_forecast"].to_numpy(dtype=float) / 6.0,
        pv_available=energy["pv_forecast"].to_numpy(dtype=float) / 6.0,
        soc0=soc_now, previous_contract=plan.grid[start:].copy(),
        adjusted_slots=remaining, soc_final=soc_now,
    )
    if not np.isfinite(solution.grid).all():
        raise AssertionError(f"{plan.day} {issue_hour}:00第四问第三问调整不可行")
    issue = datetime.combine(plan.day, datetime.min.time()) + timedelta(hours=issue_hour)
    for local, slot in enumerate(range(start, 144)):
        plan.versions[slot].append(
            Q3PlanVersion(slot, issue, len(plan.versions[slot]), float(solution.grid[local]))
        )
        plan.price_versions[slot].append({
            "issue_time": issue,
            "price_forecast": float(prices.iloc[local]["price_forecast"]),
            "source_time": prices.iloc[local]["source_time"],
            "source_observed_at": pd.Timestamp(
                prices.iloc[local]["source_observed_at"]
            ).to_pydatetime(),
            "method": prices.iloc[local]["method"],
        })
    plan.grid[start:] = solution.grid[:remaining]
    plan.charge[start:] = solution.charge[:remaining]
    plan.discharge[start:] = solution.discharge[:remaining]


def run_q43_day(
    day: date,
    soc0: float,
    actuals: pd.DataFrame,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    *,
    price_method: str = "D-7",
    price_provider: PriceProvider | None = None,
    update_hours: tuple[int, ...] = (6, 12, 18),
) -> tuple[Q43DayPlan, list[ExecRecord], dict]:
    """执行一个完整日；正式跨日生成器可在此接口上增加D009桥接。"""
    plan = make_q43_initial_plan(
        day, soc0, actual_prices, energy_provider,
        price_method=price_method, price_provider=price_provider,
    )
    truth = _truth_for_day(actuals, day)
    records: list[ExecRecord] = []
    cursor, soc, current_issue = 0, float(soc0), 0
    for hour in (6, 12, 18):
        boundary = UPDATE_SLOT[hour]
        part = _execute(
            day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
            cursor, boundary, soc,
            datetime.combine(day, datetime.min.time()) + timedelta(hours=current_issue),
        )
        records.extend(part)
        if part:
            soc = part[-1].soc_end
        cursor = boundary
        if hour in update_hours:
            update_q43_plan(
                plan, hour, soc, actual_prices, energy_provider,
                price_method=price_method, price_provider=price_provider,
            )
            current_issue = hour
    records.extend(_execute(
        day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
        cursor, 144, soc,
        datetime.combine(day, datetime.min.time()) + timedelta(hours=current_issue),
    ))
    audit = accountant.audit(records, require_q1_semantics=False)
    if not audit.ok:
        raise AssertionError(f"{day} 第四问第三问物理核算失败: {audit.violations[:5]}")
    actual = _actual_price_vector(actual_prices, [s.interval_start for s in build_day_slots(day)])
    by_slot = {r.slot: r for r in records}
    ledgers = [
        settle_q3_slot(plan.versions[t], target_price=float(actual[t]),
                       grid_emergency=float(by_slot[t].grid_emergency))
        for t in range(144)
    ]
    initial = sum(x.initial_contract_cost for x in ledgers)
    adjustment = sum(x.adjustment_cashflow for x in ledgers)
    emergency = sum(x.emergency_cost for x in ledgers)
    rows = []
    for rec in records:
        meta = plan.price_versions[rec.slot][-1]
        row = _record_row(day, rec, pd.Series(meta))
        row["initial_contract"] = float(plan.initial_grid[rec.slot])
        row["final_contract"] = float(rec.grid_contract)
        # Q4-3 的普通合同费只来自 0:00 初始版本。最终合同量的变化由
        # 版本现金流单独结算，不能把最终合同量再次当作普通购电收费。
        row["normal_cost_actual"] = float(rec.price) * float(plan.initial_grid[rec.slot])
        rows.append(row)
    version_rows = []
    for slot in range(144):
        for version, meta in zip(plan.versions[slot], plan.price_versions[slot]):
            version_rows.append({
                "date": day.isoformat(), "slot": slot, "version": version.version,
                "issue_time": version.issue_time.isoformat(), "quantity": version.quantity,
                "price_forecast": float(meta["price_forecast"]),
                "price_source_time": (
                    None if pd.isna(meta.get("source_time"))
                    else pd.Timestamp(meta["source_time"]).isoformat()
                ),
                "price_source_observed_at": pd.Timestamp(
                    meta["source_observed_at"]
                ).isoformat(),
                "price_method": str(meta.get("method", "unknown")),
            })
    result = {
        "physical_audit": audit,
        "initial_contract_cost_actual": float(initial),
        "adjustment_cashflow_actual": float(adjustment),
        "emergency_cost_actual": float(emergency),
        "total_cost_actual": float(initial + adjustment + emergency),
        "records": rows,
        "versions": version_rows,
        "ledgers": ledgers,
    }
    return plan, records, result


def _settle_q43_day(
    plan: Q43DayPlan,
    records: list[ExecRecord],
    actual_prices: pd.DataFrame,
) -> dict:
    audit = accountant.audit(records, require_q1_semantics=False)
    if not audit.ok:
        raise AssertionError(f"{plan.day} 第四问第三问物理核算失败: {audit.violations[:5]}")
    actual = _actual_price_vector(
        actual_prices, [s.interval_start for s in build_day_slots(plan.day)]
    )
    by_slot = {r.slot: r for r in records}
    ledgers = [
        settle_q3_slot(
            plan.versions[t], target_price=float(actual[t]),
            grid_emergency=float(by_slot[t].grid_emergency),
        )
        for t in range(144)
    ]
    initial = sum(x.initial_contract_cost for x in ledgers)
    adjustment = sum(x.adjustment_cashflow for x in ledgers)
    emergency = sum(x.emergency_cost for x in ledgers)
    record_rows = []
    for rec in records:
        meta = plan.price_versions[rec.slot][-1]
        row = _record_row(plan.day, rec, pd.Series(meta))
        row["initial_contract"] = float(plan.initial_grid[rec.slot])
        row["final_contract"] = float(rec.grid_contract)
        row["normal_cost_actual"] = float(rec.price) * float(plan.initial_grid[rec.slot])
        record_rows.append(row)
    version_rows = []
    for slot in range(144):
        for version, meta in zip(plan.versions[slot], plan.price_versions[slot]):
            version_rows.append({
                "date": plan.day.isoformat(), "slot": slot,
                "version": version.version, "issue_time": version.issue_time.isoformat(),
                "quantity": version.quantity,
                "price_forecast": float(meta["price_forecast"]),
                "price_source_time": (
                    None if pd.isna(meta.get("source_time"))
                    else pd.Timestamp(meta["source_time"]).isoformat()
                ),
                "price_source_observed_at": pd.Timestamp(
                    meta["source_observed_at"]
                ).isoformat(),
                "price_method": str(meta.get("method", "unknown")),
            })
    return {
        "physical_audit": audit,
        "initial_contract_cost_actual": float(initial),
        "adjustment_cashflow_actual": float(adjustment),
        "emergency_cost_actual": float(emergency),
        "total_cost_actual": float(initial + adjustment + emergency),
        "records": record_rows, "versions": version_rows, "ledgers": ledgers,
    }


def replay_q43(
    actuals: pd.DataFrame,
    actual_prices: pd.DataFrame,
    energy_provider: EnergyProvider,
    start: date,
    end: date,
    *,
    soc0: float = 6000.0,
    evaluation_start: date | None = None,
    price_method: str = "D-7",
    price_provider: PriceProvider | None = None,
    update_hours: tuple[int, ...] = (6, 12, 18),
    collect_records: bool = True,
    progress=None,
) -> dict:
    """第四问第三问顺序回放，包含四时点调整、D007账本和午夜桥接。"""
    evaluation_start = evaluation_start or start
    if not start <= evaluation_start <= end:
        raise ValueError("评价起点必须落在回放区间内")
    if any(hour not in (6, 12, 18) for hour in update_hours):
        raise ValueError("update_hours只能包含6、12、18")
    plan = make_q43_initial_plan(
        start, soc0, actual_prices, energy_provider,
        price_method=price_method, price_provider=price_provider,
    )
    actual_soc = float(soc0)
    day = start
    daily: list[dict] = []
    output_records: list[dict] = []
    output_versions: list[dict] = []
    while day <= end:
        truth = _truth_for_day(actuals, day)
        records: list[ExecRecord] = []
        cursor, soc, current_issue = 0, actual_soc, 0
        for hour in (6, 12, 18):
            boundary = UPDATE_SLOT[hour]
            part = _execute(
                day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
                cursor, boundary, soc,
                datetime.combine(day, datetime.min.time()) + timedelta(hours=current_issue),
            )
            records.extend(part)
            if part:
                soc = part[-1].soc_end
            cursor = boundary
            if hour in update_hours:
                update_q43_plan(
                    plan, hour, soc, actual_prices, energy_provider,
                    price_method=price_method, price_provider=price_provider,
                )
                current_issue = hour
        part = _execute(
            day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
            cursor, 143, soc,
            datetime.combine(day, datetime.min.time()) + timedelta(hours=current_issue),
        )
        records.extend(part)
        if part:
            soc = part[-1].soc_end

        next_plan = None
        if day < end:
            estimated = estimate_bridge_soc(soc, plan.charge[143], plan.discharge[143])
            next_plan = make_q43_initial_plan(
                day + timedelta(days=1), estimated, actual_prices, energy_provider,
                price_method=price_method, price_provider=price_provider,
            )
        records.extend(_execute(
            day, plan.grid, plan.charge, plan.discharge, truth, actual_prices,
            143, 144, soc,
            datetime.combine(day, datetime.min.time()) + timedelta(hours=current_issue),
        ))
        settled = _settle_q43_day(plan, records, actual_prices)
        audit = settled["physical_audit"]
        row = {
            "date": day.isoformat(), "actual_soc_start": actual_soc,
            "actual_soc_end": records[-1].soc_end,
            "initial_contract_cost_actual": settled["initial_contract_cost_actual"],
            "adjustment_cashflow_actual": settled["adjustment_cashflow_actual"],
            "emergency_cost_actual": settled["emergency_cost_actual"],
            "total_cost_actual": settled["total_cost_actual"], "audit_ok": audit.ok,
        }
        daily.append(row)
        if collect_records and day >= evaluation_start:
            output_records.extend(settled["records"])
            output_versions.extend(settled["versions"])
        if progress is not None:
            progress(day, row)
        actual_soc = records[-1].soc_end
        if next_plan is not None:
            plan = next_plan
        day += timedelta(days=1)

    evaluated = [r for r in daily if r["date"] >= evaluation_start.isoformat()]
    return {
        "mode": "Q4-3", "update_hours": list(update_hours),
        "replay_days": len(daily), "evaluation_days": len(evaluated),
        "initial_contract_cost_actual": float(sum(
            r["initial_contract_cost_actual"] for r in evaluated
        )),
        "adjustment_cashflow_actual": float(sum(
            r["adjustment_cashflow_actual"] for r in evaluated
        )),
        "emergency_cost_actual": float(sum(r["emergency_cost_actual"] for r in evaluated)),
        "total_cost_actual": float(sum(r["total_cost_actual"] for r in evaluated)),
        "daily": daily,
        "records": output_records if collect_records else [],
        "versions": output_versions if collect_records else [],
        "price_sources": [
            {
                "issue_time": row["decision_time"],
                "target_time": row["interval_start"],
                "source_time": row["price_source_time"],
                "source_observed_at": row["price_source_observed_at"],
                "price_forecast": row["price_forecast"],
                "method": row["price_method"],
            }
            for row in output_records
        ],
    }
