"""第二问通用顺序回放框架。

把"预测候选 × 保守等级 × 终端库存处理"参数化，供终端库存对照实验和
正式全年回放共用。回放严格遵循 D009：每天00:00先用已知库存和旧计划末
槽动作估计00:10库存并制定次日计划，再执行旧计划末槽。

本模块不选择最终方案；终端库存口径必须由人类裁决后再定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from core import accountant, data_io
from core.executor import estimate_bridge_soc, execute_q2
from core.lp_kernel import LpInputs, LpSolution, solve_lp
from core.q2_conservative import conservative_plan_forecast
from core.q2_forecast import forecast_cold_start
from core.slot_adapter import build_day_slots

def load_window_actuals(start: date, end: date) -> pd.DataFrame:
    """读取 [start, end] 的实际负荷与光伏，供执行器和预测器使用。

    执行器逐槽读取；预测器只能看到 observed_at <= 决策时刻 的子集
    （由 build_forecast 内部过滤），本函数本身不做时间截断。
    """
    frames = []
    day = start
    while day <= end:
        load = data_io.attachment2_load(day).rename(columns={"value": "load_actual"})
        pv = data_io.attachment2_pv(day).rename(columns={"value": "pv_actual"})
        frame = load[["date", "slot", "valid_time", "observed_at", "load_actual"]]
        frame = frame.merge(
            pv[["date", "slot", "pv_actual"]], on=["date", "slot"], validate="one_to_one"
        )
        frames.append(frame)
        day += timedelta(days=1)
    out = pd.concat(frames, ignore_index=True)
    if out["valid_time"].duplicated().any():
        raise ValueError("实际数据 valid_time 重复")
    return out


def prior_from_attachment1(day: date) -> pd.DataFrame:
    """附件1典型日先验（冷启动用）。"""
    return data_io.build_q1_inputs(day, datetime.combine(day, datetime.min.time()))[
        ["slot", "load_forecast", "pv_forecast"]
    ]


def daily_price() -> np.ndarray:
    """附件1的144点日内电价曲线（每天重复）。"""
    return data_io.build_q1_inputs(date(2025, 1, 1), datetime(2025, 1, 1))[
        "price"
    ].to_numpy(dtype=float)


COLD_START_END = date(2025, 1, 7)
TERMINAL_MODES = ("plan_eq", "terminal_value", "rolling")
EventObserver = Callable[[dict], None]


@dataclass(frozen=True)
class Strategy:
    """预测与保守程度的选择。"""

    method: str = "D-7"
    level: str = "point"
    lookback_days: int = 21


@dataclass(frozen=True)
class Terminal:
    """终端库存处理口径。

    mode='plan_eq'：每日计划首尾库存相等（E144_plan = E0_plan）。
    mode='terminal_value'：终端自由，对 E144 赋 param 元/kWh 的价值。
    mode='rolling'：param 天滚动视野，期末回到起始库存，只执行第一天。
    """

    mode: str = "plan_eq"
    param: float = 0.0

    def label(self) -> str:
        if self.mode == "plan_eq":
            return "plan-eq"
        if self.mode == "terminal_value":
            return f"terminal-value-{self.param:g}"
        if self.mode == "rolling":
            return f"rolling-{int(self.param)}d"
        raise ValueError(f"未知终端模式: {self.mode}")


def build_forecast(
    strategy: Strategy,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    day: date,
) -> pd.DataFrame:
    decision = datetime.combine(day, datetime.min.time())
    history = actuals[actuals["observed_at"] <= decision].copy()
    if day <= COLD_START_END:
        return forecast_cold_start(history, prior, day, decision)
    return conservative_plan_forecast(
        strategy.method, history, day, decision, strategy.level, strategy.lookback_days
    )


def plan_day(
    strategy: Strategy,
    terminal: Terminal,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    price: np.ndarray,
    day: date,
    soc0: float,
) -> LpSolution:
    if terminal.mode == "rolling":
        horizon = int(terminal.param)
        if horizon < 1:
            raise ValueError("滚动视野必须为正整数")
        loads, pvs = [], []
        for k in range(horizon):
            forecast = build_forecast(strategy, actuals, prior, day + timedelta(days=k))
            loads.append(forecast.load_forecast.to_numpy(dtype=float) / 6.0)
            pvs.append(forecast.pv_forecast.to_numpy(dtype=float) / 6.0)
        solution = solve_lp(
            LpInputs(
                price=np.tile(price, horizon),
                load=np.concatenate(loads),
                pv_available=np.concatenate(pvs),
                soc0=soc0,
                soc_final=soc0,
            )
        )
        # 只保留第一天，作为当天要执行的计划。
        return LpSolution(
            grid=solution.grid[:144],
            pv_used=solution.pv_used[:144],
            pv_curtail=solution.pv_curtail[:144],
            charge=solution.charge[:144],
            discharge=solution.discharge[:144],
            soc=solution.soc[:145],
            cost=solution.cost,
            objective=solution.objective,
            primary_optimum=solution.primary_optimum,
            status=solution.status,
            message=solution.message,
            solver=solution.solver,
        )

    forecast = build_forecast(strategy, actuals, prior, day)
    load = forecast.load_forecast.to_numpy(dtype=float) / 6.0
    pv = forecast.pv_forecast.to_numpy(dtype=float) / 6.0
    if terminal.mode == "plan_eq":
        return solve_lp(
            LpInputs(price=price, load=load, pv_available=pv, soc0=soc0, soc_final=soc0)
        )
    if terminal.mode == "terminal_value":
        return solve_lp(
            LpInputs(
                price=price,
                load=load,
                pv_available=pv,
                soc0=soc0,
                soc_final=None,
                terminal_value=terminal.param,
            )
        )
    raise ValueError(f"未知终端模式: {terminal.mode}")


def replay(
    strategy: Strategy,
    terminal: Terminal,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    price: np.ndarray,
    start: date,
    evaluation_start: date,
    evaluation_end: date,
    observer: EventObserver | None = None,
) -> dict:
    """从 start 顺序回放到 evaluation_end，汇总 evaluation_start 起的指标。"""
    if evaluation_start < start or evaluation_end < evaluation_start:
        raise ValueError("评价窗口必须落在回放区间内且顺序正确")

    day = start
    estimated_soc = 6000.0
    plan = plan_day(strategy, terminal, actuals, prior, price, day, estimated_soc)
    actual_soc_at_slot0 = 6000.0
    daily: list[dict] = []
    observations: list[dict] = []

    def emit(event: dict) -> None:
        observations.append(event)
        if observer is not None:
            observer(event)

    while day <= evaluation_end:
        truth = actuals[actuals["date"] == day].sort_values("slot")
        if len(truth) != 144:
            raise ValueError(f"{day}实际数据不是144槽")
        slots = build_day_slots(day)
        if not np.isfinite(plan.grid).all():
            raise AssertionError(f"{terminal.label()} {day} 计划求解失败: {plan.message}")
        common = dict(plan_issue_time=datetime.combine(day, datetime.min.time()))

        first = execute_q2(
            grid_contract=plan.grid[:143],
            price=price[:143],
            load_actual=truth.load_actual.to_numpy(dtype=float)[:143] / 6.0,
            pv_available=truth.pv_actual.to_numpy(dtype=float)[:143] / 6.0,
            charge_planned=plan.charge[:143],
            discharge_planned=plan.discharge[:143],
            soc0=actual_soc_at_slot0,
            starts=[s.interval_start for s in slots[:143]],
            ends=[s.interval_end for s in slots[:143]],
            slot_ids=list(range(143)),
            **common,
        )
        soc_at_midnight = first[-1].soc_end

        next_plan = None
        next_estimated_soc = None
        if day < evaluation_end:
            next_day = day + timedelta(days=1)
            next_estimated_soc = estimate_bridge_soc(
                soc_at_midnight, plan.charge[143], plan.discharge[143]
            )
            next_plan = plan_day(
                strategy, terminal, actuals, prior, price, next_day, next_estimated_soc
            )
            if not np.isfinite(next_plan.grid).all():
                raise AssertionError(
                    f"{terminal.label()} {next_day} 计划求解失败: {next_plan.message}"
                )
            if abs(float(next_plan.soc[0]) - float(next_estimated_soc)) > 1e-6:
                raise AssertionError(f"{next_day} 新计划起点未等于00:10估计库存")
            emit(
                {
                    "event": "plan_made",
                    "day": day.isoformat(),
                    "next_plan_day": next_day.isoformat(),
                    "next_plan_soc_start": float(next_estimated_soc),
                    "planned_slot143_charge": float(plan.charge[143]),
                    "planned_slot143_discharge": float(plan.discharge[143]),
                }
            )

        bridge = execute_q2(
            grid_contract=plan.grid[143:],
            price=price[143:],
            load_actual=truth.load_actual.to_numpy(dtype=float)[143:] / 6.0,
            pv_available=truth.pv_actual.to_numpy(dtype=float)[143:] / 6.0,
            charge_planned=plan.charge[143:],
            discharge_planned=plan.discharge[143:],
            soc0=soc_at_midnight,
            starts=[slots[143].interval_start],
            ends=[slots[143].interval_end],
            slot_ids=[143],
            **common,
        )
        records = first + bridge
        audit = accountant.audit(records, require_q1_semantics=False)
        if not audit.ok:
            raise AssertionError(f"{terminal.label()} {day} 核算失败: {audit.violations[:5]}")

        daily.append(
            {
                "date": day.isoformat(),
                "terminal": terminal.label(),
                "strategy_method": strategy.method,
                "strategy_level": strategy.level,
                "actual_soc_start": float(actual_soc_at_slot0),
                "actual_soc_end": float(records[-1].soc_end),
                "cost_normal": audit.cost_normal,
                "cost_emergency": audit.cost_emergency,
                "cost_total": audit.cost_total,
                "grid_emergency_kwh": float(sum(r.grid_emergency for r in records)),
                "grid_unused_kwh": float(sum(r.grid_unused for r in records)),
                "charge_shortfall_kwh": float(sum(r.charge_shortfall for r in records)),
                "discharge_shortfall_kwh": float(sum(r.discharge_shortfall for r in records)),
                "soc_min_seen": float(audit.soc_min),
                "soc_max_seen": float(audit.soc_max),
                "soc_end_at_max": bool(records[-1].soc_end >= 10800.0 - 1e-3),
                "soc_end_at_min": bool(records[-1].soc_end <= 1200.0 + 1e-3),
                "audit_ok": audit.ok,
            }
        )
        emit(
            {
                "event": "day_completed",
                "day": day.isoformat(),
                "max_residual": float(audit.max_residual),
                "simultaneous_charge_discharge": int(audit.simultaneous_charge_discharge),
                "audit_ok": bool(audit.ok),
            }
        )

        actual_soc_at_slot0 = records[-1].soc_end
        if next_plan is not None:
            plan = next_plan
            estimated_soc = float(next_estimated_soc)
        day += timedelta(days=1)

    evaluated = [
        row for row in daily if evaluation_start.isoformat() <= row["date"] <= evaluation_end.isoformat()
    ]
    return {
        "strategy": {"method": strategy.method, "level": strategy.level},
        "terminal": terminal.label(),
        "terminal_mode": terminal.mode,
        "terminal_param": terminal.param,
        "replay_days": len(daily),
        "evaluation_days": len(evaluated),
        "cost_normal": float(sum(row["cost_normal"] for row in evaluated)),
        "cost_emergency": float(sum(row["cost_emergency"] for row in evaluated)),
        "cost_total": float(sum(row["cost_total"] for row in evaluated)),
        "grid_emergency_kwh": float(sum(row["grid_emergency_kwh"] for row in evaluated)),
        "grid_unused_kwh": float(sum(row["grid_unused_kwh"] for row in evaluated)),
        "charge_shortfall_kwh": float(sum(row["charge_shortfall_kwh"] for row in evaluated)),
        "discharge_shortfall_kwh": float(sum(row["discharge_shortfall_kwh"] for row in evaluated)),
        "infeasible_days": sum(1 for row in evaluated if not row["audit_ok"]),
        "days_soc_end_at_max": sum(1 for row in evaluated if row["soc_end_at_max"]),
        "days_soc_end_at_min": sum(1 for row in evaluated if row["soc_end_at_min"]),
        "days_touching_max": sum(
            1 for row in evaluated if row["soc_max_seen"] >= 10800.0 - 1e-3
        ),
        "days_touching_min": sum(
            1 for row in evaluated if row["soc_min_seen"] <= 1200.0 + 1e-3
        ),
        "soc_end_mean": (
            float(sum(row["actual_soc_end"] for row in evaluated)) / len(evaluated)
            if evaluated
            else None
        ),
        "soc_end_median": (
            float(sorted(row["actual_soc_end"] for row in evaluated)[len(evaluated) // 2])
            if evaluated
            else None
        ),
        "soc_end_final": evaluated[-1]["actual_soc_end"] if evaluated else None,
        "soc_min_overall": float(min(row["soc_min_seen"] for row in evaluated)),
        "soc_max_overall": float(max(row["soc_max_seen"] for row in evaluated)),
        "all_audits_ok": all(row["audit_ok"] for row in evaluated),
        "daily": daily,
        "observations": observations,
    }
