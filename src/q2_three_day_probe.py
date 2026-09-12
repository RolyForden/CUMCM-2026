"""第二问三天连续窗口：一月预热后回放2月1日至3日。

比较七天前同刻与同星期日衰减平均。计划层暂用每日首尾库存相同，
仅用于D007允许的小窗口检查，不作为全年正式终端库存裁决。

回放全程记录观察者事实（决策时刻、预测器输入的信息边界、核算结果），
供 src/q2_three_day_acceptance.py 独立验收，不自行宣布验收通过。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Callable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import accountant, data_io
from core.executor import estimate_bridge_soc, execute_q2
from core.lp_kernel import LpInputs, solve_lp
from core.q2_forecast import forecast_cold_start, forecast_lag_day, forecast_same_weekday
from core.slot_adapter import build_day_slots

EventObserver = Callable[[dict], None]


START = date(2025, 1, 1)
PROBE_START = date(2025, 2, 1)
PROBE_END = date(2025, 2, 3)


def load_actuals() -> pd.DataFrame:
    frames = []
    day = START
    while day <= PROBE_END:
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


def make_forecast(
    method: str,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    day: date,
) -> pd.DataFrame:
    decision = datetime.combine(day, datetime.min.time())
    history = actuals[actuals["observed_at"] <= decision].copy()
    if day <= date(2025, 1, 7):
        return forecast_cold_start(history, prior, day, decision)
    if method == "D-7":
        return forecast_lag_day(history, day, decision, 7)
    if method == "same-weekday-4-decay-0.8":
        return forecast_same_weekday(history, day, decision, weeks=4, decay=0.8)
    raise ValueError(f"未知预测方法: {method}")


def plan_day(forecast: pd.DataFrame, price: np.ndarray, estimated_soc: float):
    return solve_lp(
        LpInputs(
            price=price,
            load=forecast.load_forecast.to_numpy(dtype=float) / 6.0,
            pv_available=forecast.pv_forecast.to_numpy(dtype=float) / 6.0,
            soc0=estimated_soc,
            soc_final=estimated_soc,
        )
    )


def simulate(
    method: str,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    price: np.ndarray,
    observer: EventObserver | None = None,
) -> dict:
    day = START
    estimated_soc = 6000.0
    forecast = make_forecast(method, actuals, prior, day)
    plan = plan_day(forecast, price, estimated_soc)
    actual_soc_at_slot0 = 6000.0
    daily = []
    observations: list[dict] = []

    def emit(event: dict) -> None:
        event = {"method": method, **event}
        observations.append(event)
        if observer is not None:
            observer(event)

    while day <= PROBE_END:
        truth = actuals[actuals["date"] == day].sort_values("slot")
        if len(truth) != 144:
            raise ValueError(f"{day}实际数据不是144槽")
        slots = build_day_slots(day)
        common = dict(
            plan_issue_time=datetime.combine(day, datetime.min.time()),
        )
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
        if day < PROBE_END:
            next_day = day + timedelta(days=1)
            next_decision = datetime.combine(next_day, datetime.min.time())
            next_history = actuals[actuals["observed_at"] <= next_decision].copy()
            next_estimated_soc = estimate_bridge_soc(
                soc_at_midnight, plan.charge[143], plan.discharge[143]
            )
            next_forecast = make_forecast(method, actuals, prior, next_day)
            next_plan = plan_day(next_forecast, price, next_estimated_soc)
            emit(
                {
                    "event": "plan_made",
                    "day": day.isoformat(),
                    "next_plan_day": next_day.isoformat(),
                    "decision_time": next_decision.isoformat(),
                    "forecast_input_max_observed_at": (
                        np.nan
                        if next_history.empty
                        else next_history["observed_at"].max().isoformat()
                    ),
                    "forecast_source_max_observed_at": (
                        np.nan
                        if not next_forecast["source_max_observed_at"].notna().any()
                        else next_forecast["source_max_observed_at"].max().isoformat()
                    ),
                    "planned_actions": [
                        {
                            "slot": 143,
                            "charge_kwh": float(plan.charge[143]),
                            "discharge_kwh": float(plan.discharge[143]),
                        }
                    ],
                    "next_plan_soc_start": float(next_estimated_soc),
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
            raise AssertionError(f"{method} {day}核算失败: {audit.violations[:5]}")
        emit(
            {
                "event": "day_completed",
                "day": day.isoformat(),
                "first_interval_start": first[0].interval_start.isoformat(),
                "bridge_interval_start": bridge[0].interval_start.isoformat(),
                "last_interval_end": records[-1].interval_end.isoformat(),
                "max_residual": float(audit.max_residual),
                "simultaneous_charge_discharge": int(
                    audit.simultaneous_charge_discharge
                ),
                "soc_min_seen": float(audit.soc_min),
                "soc_max_seen": float(audit.soc_max),
                "max_charge": float(max(r.charge for r in records)),
                "max_discharge": float(max(r.discharge for r in records)),
                "audit_ok": bool(audit.ok),
            }
        )

        daily.append(
            {
                "date": day.isoformat(),
                "plan_soc_start": float(estimated_soc),
                "actual_soc_start": float(actual_soc_at_slot0),
                "soc_at_midnight": float(soc_at_midnight),
                "actual_soc_end": float(records[-1].soc_end),
                "next_plan_estimated_soc": None if next_estimated_soc is None else float(next_estimated_soc),
                "cost_normal": audit.cost_normal,
                "cost_emergency": audit.cost_emergency,
                "cost_total": audit.cost_total,
                "grid_emergency_kwh": float(sum(r.grid_emergency for r in records)),
                "grid_unused_kwh": float(sum(r.grid_unused for r in records)),
                "charge_shortfall_kwh": float(sum(r.charge_shortfall for r in records)),
                "discharge_shortfall_kwh": float(sum(r.discharge_shortfall for r in records)),
                "charge_clipped_slots": sum(r.charge_clipped for r in records),
                "discharge_clipped_slots": sum(r.discharge_clipped for r in records),
                "audit_ok": audit.ok,
            }
        )
        actual_soc_at_slot0 = records[-1].soc_end
        if next_plan is not None:
            plan = next_plan
            estimated_soc = float(next_estimated_soc)
        day += timedelta(days=1)

    probe = [row for row in daily if PROBE_START.isoformat() <= row["date"] <= PROBE_END.isoformat()]
    return {
        "method": method,
        "warmup_days": 31,
        "probe_days": 3,
        "feb1_actual_soc_start": probe[0]["actual_soc_start"],
        "probe_cost_normal": float(sum(row["cost_normal"] for row in probe)),
        "probe_cost_emergency": float(sum(row["cost_emergency"] for row in probe)),
        "probe_cost_total": float(sum(row["cost_total"] for row in probe)),
        "probe_grid_emergency_kwh": float(sum(row["grid_emergency_kwh"] for row in probe)),
        "probe_grid_unused_kwh": float(sum(row["grid_unused_kwh"] for row in probe)),
        "probe_all_audits_ok": all(row["audit_ok"] for row in probe),
        "daily": daily,
        "observations": observations,
    }


def main() -> int:
    actuals = load_actuals()
    prior = data_io.build_q1_inputs(START, datetime(2025, 1, 1))[
        ["slot", "load_forecast", "pv_forecast"]
    ]
    price = data_io.build_q1_inputs(START, datetime(2025, 1, 1))["price"].to_numpy(dtype=float)
    results = [
        simulate("D-7", actuals, prior, price),
        simulate("same-weekday-4-decay-0.8", actuals, prior, price),
    ]
    payload = {
        "scope": "Jan warmup plus Feb 1-3 probe; temporary plan terminal equality",
        "results": results,
    }
    output = ROOT / "experiments" / "q2_three_day_probe_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scope": payload["scope"], "summary": [
        {k: v for k, v in row.items() if k != "daily" and k != "observations"} for row in results
    ]}, ensure_ascii=False, indent=2))
    return 0 if all(row["probe_all_audits_ok"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
