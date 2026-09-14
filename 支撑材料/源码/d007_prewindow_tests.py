"""D007 前置闸门反例与只读验证。

本脚本只做合成反例和附件3只读检查，不实现 Q2/Q3 正式流程，
不运行全年模型，不修改 data/raw。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.slot_adapter import build_day_slots


OUT = ROOT / "experiments" / "d007_prewindow_results.json"


@dataclass
class Check:
    name: str
    passed: bool
    expected: str
    actual: str


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def n1_execute_slot(
    *,
    load_actual: float,
    pv_available: float,
    grid_contract: float,
    charge: float,
    discharge_planned: float,
    price: float = 1.0,
) -> dict:
    """D007 N1 计划优先口径的单槽合成执行。

    过剩时的削减顺序：先弃光 -> 再减少合同交付形成 grid_unused -> 最后削减计划放电。
    等价的需求分配顺序：先保计划放电 -> 再保合同交付 -> 最后消纳光伏；
    不足时再用 emergency 补齐。
    """
    demand = load_actual + charge

    discharge_actual = min(discharge_planned, max(demand, 0.0))
    remaining = demand - discharge_actual

    grid_delivered = min(grid_contract, max(remaining, 0.0))
    grid_unused = grid_contract - grid_delivered
    remaining -= grid_delivered

    pv_used = min(pv_available, max(remaining, 0.0))
    pv_curtail = pv_available - pv_used
    remaining -= pv_used

    grid_emergency = max(remaining, 0.0)
    surplus_after_discharge = 0.0

    discharge_shortfall = discharge_planned - discharge_actual
    residual = (
        grid_delivered
        + grid_emergency
        + pv_used
        + discharge_actual
        - load_actual
        - charge
    )
    return {
        "load_actual": load_actual,
        "pv_available": pv_available,
        "pv_used": pv_used,
        "pv_curtail": pv_curtail,
        "grid_contract": grid_contract,
        "grid_delivered": grid_delivered,
        "grid_unused": grid_unused,
        "grid_emergency": grid_emergency,
        "charge": charge,
        "discharge_planned": discharge_planned,
        "discharge_actual": discharge_actual,
        "discharge_shortfall": discharge_shortfall,
        "discharge_clipped": discharge_shortfall > 1e-9,
        "surplus_after_discharge": surplus_after_discharge,
        "cost_normal": price * grid_contract,
        "cost_emergency": 5 * price * grid_emergency,
        "residual": residual,
    }


def q3_cashflow(versions: list[tuple[int, float]], target_price: float, executed_before: int | None = None) -> float:
    """D007 N2 逐次现金流。versions = [(version, quantity), ...]."""
    if not versions:
        raise ValueError("versions must not be empty")
    if executed_before is not None:
        for version, _ in versions:
            if version > executed_before:
                raise ValueError("attempt to modify an already executed slot")
    cost = target_price * versions[0][1]
    for (_, prev), (_, cur) in zip(versions, versions[1:]):
        increase = max(cur - prev, 0.0)
        decrease = max(prev - cur, 0.0)
        cost += 1.5 * target_price * increase - 0.5 * target_price * decrease
    return cost


def run_n1() -> list[Check]:
    checks: list[Check] = []

    zero = n1_execute_slot(load_actual=0, pv_available=0, grid_contract=0, charge=0, discharge_planned=10)
    checks.append(Check(
        "N1-zero-load-discharge-clipped",
        zero["discharge_clipped"] and close(zero["discharge_actual"], 0) and close(zero["discharge_shortfall"], 10),
        "planned discharge clipped to 0, shortfall=10",
        f"actual={zero['discharge_actual']}, shortfall={zero['discharge_shortfall']}",
    ))

    high_pv = n1_execute_slot(load_actual=10, pv_available=100, grid_contract=50, charge=0, discharge_planned=20)
    checks.append(Check(
        "N1-high-pv-contract-overage",
        close(high_pv["pv_curtail"], 100) and close(high_pv["grid_unused"], 50) and close(high_pv["discharge_actual"], 10) and close(high_pv["discharge_shortfall"], 10),
        "curtail=100, unused=50, discharge_actual=10, shortfall=10",
        f"curtail={high_pv['pv_curtail']}, unused={high_pv['grid_unused']}, discharge_actual={high_pv['discharge_actual']}, shortfall={high_pv['discharge_shortfall']}",
    ))

    severe = n1_execute_slot(load_actual=5, pv_available=0, grid_contract=100, charge=0, discharge_planned=50)
    checks.append(Check(
        "N1-severe-contract-overage",
        close(severe["grid_delivered"], 0) and close(severe["grid_unused"], 100) and close(severe["discharge_actual"], 5) and close(severe["discharge_shortfall"], 45),
        "delivered=0, unused=100, discharge_actual=5, discharge_shortfall=45",
        f"delivered={severe['grid_delivered']}, unused={severe['grid_unused']}, shortfall={severe['discharge_shortfall']}",
    ))

    shortage = n1_execute_slot(load_actual=100, pv_available=0, grid_contract=30, charge=0, discharge_planned=20, price=2)
    checks.append(Check(
        "N1-contract-shortage-emergency",
        close(shortage["grid_emergency"], 50) and close(shortage["cost_emergency"], 500),
        "emergency=50, emergency cost=5*2*50=500",
        f"emergency={shortage['grid_emergency']}, cost={shortage['cost_emergency']}",
    ))

    boundary = n1_execute_slot(load_actual=0, pv_available=0, grid_contract=0, charge=0, discharge_planned=833.3333333333)
    checks.append(Check(
        "N1-soc-boundary-proxy",
        boundary["discharge_clipped"] and close(boundary["discharge_actual"], 0),
        "near power limit planned discharge is clipped when no demand",
        f"actual={boundary['discharge_actual']}, clipped={boundary['discharge_clipped']}",
    ))
    return checks


def run_n2() -> list[Check]:
    checks: list[Check] = []
    cases = [
        ("N2-no-adjust", [(0, 100.0)], 100.0),
        ("N2-up-only", [(0, 100.0), (1, 120.0)], 130.0),
        ("N2-down-only", [(0, 100.0), (1, 80.0)], 90.0),
        ("N2-100-80-100", [(0, 100.0), (1, 80.0), (2, 100.0)], 120.0),
    ]
    for name, versions, expected in cases:
        actual = q3_cashflow(versions, target_price=1.0)
        checks.append(Check(name, close(actual, expected), str(expected), str(actual)))

    target_price_cost = q3_cashflow([(0, 100.0), (1, 120.0)], target_price=2.0)
    issue_price_wrong_cost = q3_cashflow([(0, 100.0), (1, 120.0)], target_price=1.0)
    checks.append(Check(
        "N2-target-slot-price",
        close(target_price_cost, 260.0) and not close(target_price_cost, issue_price_wrong_cost),
        "target price 2 gives 260, issue-price-like 1 would give 130",
        f"target={target_price_cost}, wrong={issue_price_wrong_cost}",
    ))

    plan_cost = q3_cashflow([(0, 100.0), (1, 80.0), (2, 100.0)], target_price=1.0)
    duplicated = plan_cost + 100.0
    checks.append(Check(
        "N2-no-q-final-double-charge",
        close(plan_cost, 120.0) and not close(duplicated, 120.0),
        "plan cashflow=120 and q_final charge would be duplicate",
        f"plan={plan_cost}, duplicated={duplicated}",
    ))

    try:
        q3_cashflow([(0, 100.0), (1, 90.0)], target_price=1.0, executed_before=0)
        illegal_ok = False
        detail = "not rejected"
    except ValueError as exc:
        illegal_ok = True
        detail = type(exc).__name__
    checks.append(Check("N2-reject-history-edit", illegal_ok, "ValueError", detail))

    forecast_price = 2.0
    actual_price = 3.0
    opt_cost = q3_cashflow([(0, 100.0), (1, 120.0)], target_price=forecast_price)
    settlement_cost = q3_cashflow([(0, 100.0), (1, 120.0)], target_price=actual_price)
    checks.append(Check(
        "N2-q4-price-forecast-vs-actual",
        close(opt_cost, 260.0) and close(settlement_cost, 390.0),
        "optimizer uses forecast price, accountant uses actual price",
        f"opt={opt_cost}, settlement={settlement_cost}",
    ))
    return checks


def run_n3() -> tuple[list[Check], dict]:
    decision = datetime(2025, 1, 1, 6, 0)
    vintages = data_io.forecast_vintage_as_of(decision)
    checks: list[Check] = []
    if vintages.empty:
        checks.append(Check("N3-vintage-not-empty", False, "non-empty", "empty"))
        return checks, {}

    deltas = (vintages["valid_time"] - vintages["issue_time"]).dt.total_seconds() / 3600
    max_delta_error = float((deltas - vintages["lead_hour"]).abs().max())
    checks.append(Check(
        "N3-valid-time-equals-issue-plus-lead",
        max_delta_error < 1e-12,
        "max delta error 0",
        str(max_delta_error),
    ))

    max_issue = vintages["issue_time"].max()
    checks.append(Check(
        "N3-issue-time-causal-cutoff",
        max_issue <= decision,
        f"<= {decision.isoformat()}",
        max_issue.isoformat(),
    ))

    slots = build_day_slots(date(2025, 1, 1))
    slot143_start = slots[143].interval_start
    issue0 = datetime.combine(date(2025, 1, 1), time(0, 0))
    h24_valid = issue0 + timedelta(hours=24)
    checks.append(Check(
        "N3-scheme-a-last-slot-h24-point",
        slot143_start == h24_valid,
        "slot143 start equals 0:00 issue h24 valid_time",
        f"slot143={slot143_start.isoformat()}, h24={h24_valid.isoformat()}",
    ))

    first_hour_start = issue0
    first_forecast_point = issue0 + timedelta(hours=1)
    checks.append(Check(
        "N3-first-hour-gap-documented",
        first_hour_start < first_forecast_point,
        "0:00-1:00 precedes first point forecast, needs redecision",
        f"first_hour_start={first_hour_start.isoformat()}, f1={first_forecast_point.isoformat()}",
    ))

    summary = {
        "decision_time": decision.isoformat(),
        "records": int(len(vintages)),
        "max_issue_time": max_issue.isoformat(),
        "max_valid_time": vintages["valid_time"].max().isoformat(),
        "max_delta_error_hours": max_delta_error,
        "slot143_start": slot143_start.isoformat(),
        "h24_valid_time": h24_valid.isoformat(),
    }
    return checks, summary


def main() -> int:
    n1 = run_n1()
    n2 = run_n2()
    n3, n3_summary = run_n3()
    checks = n1 + n2 + n3
    result = {
        "status": "PASS" if all(c.passed for c in checks) else "FAIL",
        "scope": "D007 prewindow synthetic checks; no Q2/Q3 window, no annual run",
        "summary": {
            "total": len(checks),
            "passed": sum(1 for c in checks if c.passed),
            "failed": sum(1 for c in checks if not c.passed),
        },
        "n3_summary": n3_summary,
        "results": [asdict(c) for c in checks],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["summary"], "output": str(OUT)}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
