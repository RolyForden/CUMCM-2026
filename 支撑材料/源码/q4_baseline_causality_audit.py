"""Q4-0：证明旧滚动视野是否把未来目标日误当成决策时刻。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from core.executor import execute_q2
from core.lp_kernel import LpInputs, solve_lp
from core.q2_forecast import forecast_cold_start
from core.q2_replay import Strategy, Terminal, daily_price, load_window_actuals, plan_day, prior_from_attachment1
from core.slot_adapter import build_day_slots


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments/q4_baseline_causality_audit.json"


def main() -> int:
    day = date(2025, 1, 1)
    outer_decision = datetime.combine(day, datetime.min.time())
    actuals = load_window_actuals(day, day + timedelta(days=6))
    prior = prior_from_attachment1(day)
    price = daily_price()

    current = plan_day(
        Strategy("D-7", "point"),
        Terminal("rolling", 7),
        actuals,
        prior,
        price,
        day,
        6000.0,
    )

    # 冻结复现整改前错误：把每个未来目标日零点误当成新的决策时刻。
    legacy_loads: list[np.ndarray] = []
    legacy_pvs: list[np.ndarray] = []
    for offset in range(7):
        target = day + timedelta(days=offset)
        wrong_decision = datetime.combine(target, datetime.min.time())
        wrong_history = actuals[actuals["observed_at"] <= wrong_decision].copy()
        forecast = forecast_cold_start(wrong_history, prior, target, wrong_decision)
        legacy_loads.append(forecast.load_forecast.to_numpy(dtype=float) / 6.0)
        legacy_pvs.append(forecast.pv_forecast.to_numpy(dtype=float) / 6.0)
    legacy = solve_lp(LpInputs(
        price=np.tile(price, 7), load=np.concatenate(legacy_loads),
        pv_available=np.concatenate(legacy_pvs), soc0=6000.0, soc_final=6000.0,
    ))

    # 独立参考：七天视野的所有目标日都只能使用真实决策时刻前的数据。
    history = actuals[actuals["observed_at"] <= outer_decision].copy()
    loads: list[np.ndarray] = []
    pvs: list[np.ndarray] = []
    for offset in range(7):
        target = day + timedelta(days=offset)
        forecast = forecast_cold_start(history, prior, target, outer_decision)
        loads.append(forecast.load_forecast.to_numpy(dtype=float) / 6.0)
        pvs.append(forecast.pv_forecast.to_numpy(dtype=float) / 6.0)
    corrected = solve_lp(
        LpInputs(
            price=np.tile(price, 7),
            load=np.concatenate(loads),
            pv_available=np.concatenate(pvs),
            soc0=6000.0,
            soc_final=6000.0,
        )
    )

    truth = actuals[actuals["date"] == day].sort_values("slot")
    slots = build_day_slots(day)

    def execute(grid: np.ndarray, charge: np.ndarray, discharge: np.ndarray):
        return execute_q2(
            grid_contract=grid[:144],
            price=price,
            load_actual=truth.load_actual.to_numpy(dtype=float) / 6.0,
            pv_available=truth.pv_actual.to_numpy(dtype=float) / 6.0,
            charge_planned=charge[:144],
            discharge_planned=discharge[:144],
            soc0=6000.0,
            starts=[slot.interval_start for slot in slots],
            ends=[slot.interval_end for slot in slots],
            slot_ids=list(range(144)),
            plan_issue_time=outer_decision,
        )

    legacy_records = execute(legacy.grid, legacy.charge, legacy.discharge)
    corrected_records = execute(corrected.grid, corrected.charge, corrected.discharge)
    grid_diff = float(np.max(np.abs(legacy.grid[:144] - corrected.grid[:144])))
    charge_diff = float(np.max(np.abs(legacy.charge[:144] - corrected.charge[:144])))
    soc_diff = float(legacy_records[-1].soc_end - corrected_records[-1].soc_end)
    current_diff = float(np.max(np.abs(current.grid - corrected.grid[:144])))
    result = {
        "scope": "Jan-1 rolling-7d causality audit; no formal result rewritten",
        "outer_decision": outer_decision.isoformat(),
        "legacy_first_day_grid_max_abs_diff_kwh": grid_diff,
        "legacy_first_day_charge_max_abs_diff_kwh": charge_diff,
        "legacy_actual_soc_end_kwh": float(legacy_records[-1].soc_end),
        "strict_actual_soc_end_kwh": float(corrected_records[-1].soc_end),
        "soc_end_difference_kwh": soc_diff,
        "future_information_changes_executed_plan": bool(grid_diff > 1e-7),
        "current_first_day_vs_strict_max_abs_diff_kwh": current_diff,
        "historical_defect_detected": bool(grid_diff > 1e-7),
        "current_fix_matches_strict_reference": bool(current_diff < 1e-7),
        "verdict": "PASS" if grid_diff > 1e-7 and current_diff < 1e-7 else "FAIL",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
