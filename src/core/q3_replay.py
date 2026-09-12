"""Q3 四时点确定性 MPC 的计划、执行与版本账本。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from core import accountant, data_io
from core.executor import ExecRecord, estimate_bridge_soc, execute_q2
from core.lp_kernel import LpInputs, solve_lp
from core.q2_replay import Strategy, build_forecast
from core.q3_forecast import expand_issue_forecast
from core.q3_ledger import Q3PlanVersion, settle_q3_slot
from core.q3_optimizer import solve_adjustment_lp
from core.slot_adapter import build_day_slots


UPDATE_SLOT = {0: 0, 6: 35, 12: 71, 18: 107}
SEGMENT_END = {0: 35, 6: 71, 12: 107, 18: 143}
Q2_STRATEGY = Strategy("D-7", "point")
ROLLING_FUTURE_DAYS = 6


@dataclass
class Q3DayPlan:
    day: date
    initial_grid: np.ndarray
    grid: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    versions: dict[int, list[Q3PlanVersion]]


def _day_forecast(actuals: pd.DataFrame, prior: pd.DataFrame, day: date) -> pd.DataFrame:
    return build_forecast(Q2_STRATEGY, actuals, prior, day)


def _horizon(
    day: date,
    issue_hour: int,
    start_slot: int,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    vintages: pd.DataFrame,
    price: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    slots = build_day_slots(day)
    base = _day_forecast(actuals, prior, day)
    fallback = {
        slot.interval_start: float(base.iloc[slot.slot_id].pv_forecast)
        for slot in slots
    }
    issue = datetime.combine(day, datetime.min.time()) + timedelta(hours=issue_hour)
    current_targets = [s.interval_start for s in slots[start_slot:]]
    expanded = expand_issue_forecast(
        vintages, issue, current_targets, method="linear", fallback=fallback
    )
    loads = [base.load_forecast.to_numpy(dtype=float)[start_slot:] / 6.0]
    pvs = [expanded.pv_forecast.to_numpy(dtype=float) / 6.0]
    prices = [price[start_slot:]]
    for k in range(1, ROLLING_FUTURE_DAYS + 1):
        future = _day_forecast(actuals, prior, day + timedelta(days=k))
        loads.append(future.load_forecast.to_numpy(dtype=float) / 6.0)
        pvs.append(future.pv_forecast.to_numpy(dtype=float) / 6.0)
        prices.append(price)
    return np.concatenate(prices), np.concatenate(loads), np.concatenate(pvs)


def make_initial_plan(
    day: date,
    soc0: float,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    vintages: pd.DataFrame,
    price: np.ndarray,
) -> Q3DayPlan:
    hp, hl, hv = _horizon(day, 0, 0, actuals, prior, vintages, price)
    solution = solve_lp(LpInputs(price=hp, load=hl, pv_available=hv, soc0=soc0, soc_final=soc0))
    if not np.isfinite(solution.grid).all():
        raise AssertionError(f"{day} Q3 0:00初始计划不可行: {solution.message}")
    issue = datetime.combine(day, datetime.min.time())
    initial = solution.grid[:144].copy()
    versions = {
        t: [Q3PlanVersion(t, issue, 0, float(initial[t]))]
        for t in range(144)
    }
    return Q3DayPlan(
        day=day,
        initial_grid=initial,
        grid=initial.copy(),
        charge=solution.charge[:144].copy(),
        discharge=solution.discharge[:144].copy(),
        versions=versions,
    )


def update_plan(
    plan: Q3DayPlan,
    issue_hour: int,
    soc_now: float,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    vintages: pd.DataFrame,
    price: np.ndarray,
) -> None:
    start = UPDATE_SLOT[issue_hour]
    hp, hl, hv = _horizon(plan.day, issue_hour, start, actuals, prior, vintages, price)
    remaining = 144 - start
    solution = solve_adjustment_lp(
        price=hp,
        load=hl,
        pv_available=hv,
        soc0=soc_now,
        previous_contract=plan.grid[start:].copy(),
        adjusted_slots=remaining,
        soc_final=soc_now,
    )
    if not np.isfinite(solution.grid).all():
        raise AssertionError(f"{plan.day} {issue_hour}:00调整计划不可行: {solution.message}")
    issue = datetime.combine(plan.day, datetime.min.time()) + timedelta(hours=issue_hour)
    for local, slot in enumerate(range(start, 144)):
        version = len(plan.versions[slot])
        plan.versions[slot].append(Q3PlanVersion(slot, issue, version, float(solution.grid[local])))
    plan.grid[start:] = solution.grid[:remaining]
    plan.charge[start:] = solution.charge[:remaining]
    plan.discharge[start:] = solution.discharge[:remaining]


def _execute_range(
    plan: Q3DayPlan,
    truth: pd.DataFrame,
    price: np.ndarray,
    lo: int,
    hi: int,
    soc0: float,
    issue_hour: int,
) -> list[ExecRecord]:
    slots = build_day_slots(plan.day)
    return execute_q2(
        grid_contract=plan.grid[lo:hi],
        price=price[lo:hi],
        load_actual=truth.load_actual.to_numpy(dtype=float)[lo:hi] / 6.0,
        pv_available=truth.pv_actual.to_numpy(dtype=float)[lo:hi] / 6.0,
        charge_planned=plan.charge[lo:hi],
        discharge_planned=plan.discharge[lo:hi],
        soc0=soc0,
        starts=[s.interval_start for s in slots[lo:hi]],
        ends=[s.interval_end for s in slots[lo:hi]],
        slot_ids=list(range(lo, hi)),
        plan_issue_time=datetime.combine(plan.day, datetime.min.time()) + timedelta(hours=issue_hour),
    )


def settle_day(plan: Q3DayPlan, records: list[ExecRecord], price: np.ndarray) -> dict:
    physical = accountant.audit(records, require_q1_semantics=False)
    if not physical.ok:
        raise AssertionError(f"{plan.day} Q3物理审计失败: {physical.violations[:5]}")
    by_slot = {r.slot: r for r in records}
    ledgers = [
        settle_q3_slot(plan.versions[t], target_price=float(price[t]),
                       grid_emergency=float(by_slot[t].grid_emergency))
        for t in range(144)
    ]
    up_qty = sum(a.increase for row in ledgers for a in row.adjustments)
    down_qty = sum(a.decrease for row in ledgers for a in row.adjustments)
    up_cost = sum(1.5 * row.target_price * a.increase for row in ledgers for a in row.adjustments)
    down_credit = sum(0.5 * row.target_price * a.decrease for row in ledgers for a in row.adjustments)
    initial_cost = sum(row.initial_contract_cost for row in ledgers)
    emergency_cost = sum(row.emergency_cost for row in ledgers)
    return {
        "physical_audit": physical,
        "initial_contract_cost": float(initial_cost),
        "up_cost": float(up_cost),
        "down_credit": float(down_credit),
        "adjustment_cashflow": float(up_cost-down_credit),
        "emergency_cost": float(emergency_cost),
        "total_cost": float(initial_cost+up_cost-down_credit+emergency_cost),
        "increase_kwh": float(up_qty),
        "decrease_kwh": float(down_qty),
        "emergency_kwh": float(sum(r.grid_emergency for r in records)),
        "unused_kwh": float(sum(r.grid_unused for r in records)),
        "ledgers": ledgers,
    }


def run_day(
    day: date,
    soc0: float,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    vintages: pd.DataFrame,
    price: np.ndarray,
    *,
    update_hours: tuple[int, ...] = (6, 12, 18),
) -> tuple[Q3DayPlan, list[ExecRecord], dict]:
    """独立单日 smoke 用；完整执行144槽，不处理次日0:00先计划的桥接顺序。"""
    plan = make_initial_plan(day, soc0, actuals, prior, vintages, price)
    truth = actuals[actuals.date == day].sort_values("slot")
    if len(truth) != 144:
        raise ValueError(f"{day}实际数据不是144槽")
    records: list[ExecRecord] = []
    cursor = 0
    soc = soc0
    for hour in (6, 12, 18):
        boundary = UPDATE_SLOT[hour]
        part = _execute_range(plan, truth, price, cursor, boundary, soc, 0 if cursor == 0 else update_hours[update_hours.index(hour)-1] if hour in update_hours and update_hours.index(hour)>0 else 0)
        records.extend(part)
        if part:
            soc = part[-1].soc_end
        cursor = boundary
        if hour in update_hours:
            update_plan(plan, hour, soc, actuals, prior, vintages, price)
    part = _execute_range(plan, truth, price, cursor, 144, soc, max(update_hours) if update_hours else 0)
    records.extend(part)
    result = settle_day(plan, records, price)
    return plan, records, result


def replay(
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    vintages: pd.DataFrame,
    price: np.ndarray,
    start: date,
    evaluation_start: date,
    evaluation_end: date,
    *,
    update_hours: tuple[int, ...] = (6, 12, 18),
    collect_records: bool = False,
    progress=None,
) -> dict:
    """按D009顺序回放Q3：午夜先制定新计划，再执行旧计划末槽。"""
    if evaluation_start < start or evaluation_end < evaluation_start:
        raise ValueError("Q3评价窗口错误")
    plan = make_initial_plan(start, 6000.0, actuals, prior, vintages, price)
    actual_soc_start = 6000.0
    daily = []
    all_records: list[dict] = []
    all_versions: list[dict] = []
    day = start
    while day <= evaluation_end:
        truth = actuals[actuals.date == day].sort_values("slot")
        if len(truth) != 144:
            raise ValueError(f"{day}实际数据不是144槽")
        records: list[ExecRecord] = []
        cursor = 0
        soc = actual_soc_start
        current_issue = 0
        for hour in (6, 12, 18):
            boundary = UPDATE_SLOT[hour]
            part = _execute_range(plan, truth, price, cursor, boundary, soc, current_issue)
            records.extend(part)
            if part:
                soc = part[-1].soc_end
            cursor = boundary
            if hour in update_hours:
                update_plan(plan, hour, soc, actuals, prior, vintages, price)
                current_issue = hour
        part = _execute_range(plan, truth, price, cursor, 143, soc, current_issue)
        records.extend(part)
        if part:
            soc = part[-1].soc_end

        next_plan = None
        if day < evaluation_end:
            next_day = day + timedelta(days=1)
            estimated = estimate_bridge_soc(soc, plan.charge[143], plan.discharge[143])
            next_plan = make_initial_plan(next_day, estimated, actuals, prior, vintages, price)

        bridge = _execute_range(plan, truth, price, 143, 144, soc, current_issue)
        records.extend(bridge)
        settled = settle_day(plan, records, price)
        audit = settled.pop("physical_audit")
        row = {
            "date": day.isoformat(),
            "actual_soc_start": float(actual_soc_start),
            "actual_soc_end": float(records[-1].soc_end),
            "soc_min": float(audit.soc_min),
            "soc_max": float(audit.soc_max),
            "max_residual": float(audit.max_residual),
            "audit_ok": bool(audit.ok),
            **{k: v for k, v in settled.items() if k != "ledgers"},
        }
        daily.append(row)

        if collect_records and day >= evaluation_start:
            for rec in records:
                all_records.append(
                    {
                        "date": day.isoformat(),
                        "slot": rec.slot,
                        "interval_start": rec.interval_start.isoformat(),
                        "interval_end": rec.interval_end.isoformat(),
                        "price": rec.price,
                        "load_actual": rec.load,
                        "pv_available": rec.pv_available,
                        "pv_used": rec.pv_used,
                        "pv_curtail": rec.pv_curtail,
                        "initial_contract": float(plan.initial_grid[rec.slot]),
                        "final_contract": rec.grid_contract,
                        "grid_delivered": rec.grid_delivered,
                        "grid_unused": rec.grid_unused,
                        "grid_emergency": rec.grid_emergency,
                        "charge_planned": rec.charge_planned,
                        "charge_actual": rec.charge,
                        "discharge_planned": rec.discharge_planned,
                        "discharge_actual": rec.discharge,
                        "soc_start": rec.soc_start,
                        "soc_end": rec.soc_end,
                    }
                )
            for slot, versions in plan.versions.items():
                for version in versions:
                    all_versions.append(
                        {
                            "date": day.isoformat(),
                            "slot": slot,
                            "version": version.version,
                            "issue_time": version.issue_time.isoformat(),
                            "quantity": version.quantity,
                        }
                    )
        if progress is not None:
            progress(day, row)
        actual_soc_start = records[-1].soc_end
        if next_plan is not None:
            plan = next_plan
        day += timedelta(days=1)

    evaluated = [r for r in daily if r["date"] >= evaluation_start.isoformat()]
    result = {
        "update_hours": list(update_hours),
        "replay_days": len(daily),
        "evaluation_days": len(evaluated),
        "initial_contract_cost": float(sum(r["initial_contract_cost"] for r in evaluated)),
        "up_cost": float(sum(r["up_cost"] for r in evaluated)),
        "down_credit": float(sum(r["down_credit"] for r in evaluated)),
        "adjustment_cashflow": float(sum(r["adjustment_cashflow"] for r in evaluated)),
        "emergency_cost": float(sum(r["emergency_cost"] for r in evaluated)),
        "total_cost": float(sum(r["total_cost"] for r in evaluated)),
        "increase_kwh": float(sum(r["increase_kwh"] for r in evaluated)),
        "decrease_kwh": float(sum(r["decrease_kwh"] for r in evaluated)),
        "emergency_kwh": float(sum(r["emergency_kwh"] for r in evaluated)),
        "unused_kwh": float(sum(r["unused_kwh"] for r in evaluated)),
        "infeasible_days": sum(not r["audit_ok"] for r in evaluated),
        "soc_min": float(min(r["soc_min"] for r in evaluated)),
        "soc_max": float(max(r["soc_max"] for r in evaluated)),
        "soc_end_final": evaluated[-1]["actual_soc_end"],
        "daily": daily,
    }
    if collect_records:
        result["records"] = all_records
        result["versions"] = all_versions
    return result
