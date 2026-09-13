"""Q3 纯合成账本测试。

边界：
- 不读取附件3；
- 不调用预测适配器；
- 不做滚动窗口；
- 只验证多次改计划如何收费。
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from core.q3_ledger import Q3PlanVersion, settle_q3_slot, settle_q4_slot_with_price_split


OUT = ROOT / "experiments" / "q3_ledger_synthetic_results.json"


@dataclass
class Check:
    name: str
    passed: bool
    expected: str
    actual: str


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def versions(*quantities: float) -> list[Q3PlanVersion]:
    base = datetime(2025, 2, 1, 0, 0)
    return [
        Q3PlanVersion(
            target_slot=60,
            issue_time=base + timedelta(hours=6 * i),
            version=i,
            quantity=q,
        )
        for i, q in enumerate(quantities)
    ]


def expect_value_error(fn) -> str:
    try:
        fn()
    except ValueError as exc:
        return type(exc).__name__
    return "not rejected"


def run_checks() -> list[Check]:
    checks: list[Check] = []

    no_adjust = settle_q3_slot(versions(100.0), target_price=1.0)
    checks.append(Check(
        "Q3-ledger-no-adjust",
        close(no_adjust.total_cost, 100.0)
        and close(no_adjust.initial_contract_cost, 100.0)
        and close(no_adjust.adjustment_cashflow, 0.0)
        and close(no_adjust.final_quantity, 100.0),
        "total=100, initial=100, adjustment=0, q_final=100",
        f"total={no_adjust.total_cost}, initial={no_adjust.initial_contract_cost}, adjustment={no_adjust.adjustment_cashflow}, q_final={no_adjust.final_quantity}",
    ))

    up = settle_q3_slot(versions(100.0, 120.0), target_price=1.0)
    checks.append(Check(
        "Q3-ledger-up-only",
        close(up.total_cost, 130.0)
        and close(up.adjustment_cashflow, 30.0)
        and close(up.adjustments[0].increase, 20.0),
        "100 + 1.5*(120-100) = 130",
        f"total={up.total_cost}, adjustment={up.adjustment_cashflow}, increase={up.adjustments[0].increase}",
    ))

    down = settle_q3_slot(versions(100.0, 80.0), target_price=1.0)
    checks.append(Check(
        "Q3-ledger-down-only",
        close(down.total_cost, 90.0)
        and close(down.adjustment_cashflow, -10.0)
        and close(down.adjustments[0].decrease, 20.0),
        "100 - 0.5*(100-80) = 90",
        f"total={down.total_cost}, adjustment={down.adjustment_cashflow}, decrease={down.adjustments[0].decrease}",
    ))

    back_and_forth = settle_q3_slot(versions(100.0, 80.0, 100.0), target_price=1.0)
    checks.append(Check(
        "Q3-ledger-100-80-100",
        close(back_and_forth.total_cost, 120.0)
        and close(back_and_forth.adjustment_cashflow, 20.0),
        "100 - 10 + 30 = 120",
        f"total={back_and_forth.total_cost}, adjustment={back_and_forth.adjustment_cashflow}",
    ))

    reject_duplicate = expect_value_error(
        lambda: settle_q3_slot(
            versions(100.0, 80.0, 100.0),
            target_price=1.0,
            q_final_contract_charge=100.0,
        )
    )
    checks.append(Check(
        "Q3-ledger-reject-q-final-double-charge",
        reject_duplicate == "ValueError",
        "ValueError",
        reject_duplicate,
    ))

    reject_history_edit = expect_value_error(
        lambda: settle_q3_slot(
            versions(100.0, 90.0),
            target_price=1.0,
            executed_before_version=0,
        )
    )
    checks.append(Check(
        "Q3-ledger-reject-executed-slot-edit",
        reject_history_edit == "ValueError",
        "ValueError",
        reject_history_edit,
    ))

    optimizer_view, accountant_view = settle_q4_slot_with_price_split(
        versions(100.0, 120.0),
        price_forecast_for_optimizer=2.0,
        price_actual_for_accountant=3.0,
    )
    checks.append(Check(
        "Q4-ledger-price-forecast-vs-actual",
        close(optimizer_view.total_cost, 260.0)
        and close(accountant_view.total_cost, 390.0),
        "optimizer=260 with forecast price 2; accountant=390 with actual price 3",
        f"optimizer={optimizer_view.total_cost}, accountant={accountant_view.total_cost}",
    ))

    emergency = settle_q3_slot(versions(100.0), target_price=2.0, grid_emergency=5.0)
    checks.append(Check(
        "Q3-ledger-emergency-separated",
        close(emergency.initial_contract_cost, 200.0)
        and close(emergency.emergency_cost, 50.0)
        and close(emergency.total_cost, 250.0),
        "normal=2*100=200, emergency=5*2*5=50, total=250",
        f"normal={emergency.initial_contract_cost}, emergency={emergency.emergency_cost}, total={emergency.total_cost}",
    ))

    reject_bad_version = expect_value_error(
        lambda: settle_q3_slot(
            [
                Q3PlanVersion(60, datetime(2025, 2, 1, 0, 0), 0, 100.0),
                Q3PlanVersion(60, datetime(2025, 2, 1, 12, 0), 2, 120.0),
            ],
            target_price=1.0,
        )
    )
    checks.append(Check(
        "Q3-ledger-reject-version-gap",
        reject_bad_version == "ValueError",
        "ValueError",
        reject_bad_version,
    ))

    return checks


def main() -> int:
    checks = run_checks()
    result = {
        "status": "PASS" if all(c.passed for c in checks) else "FAIL",
        "scope": "Q3 pure synthetic settlement ledger only; no attachment 3, no forecast adapter, no rolling window",
        "summary": {
            "total": len(checks),
            "passed": sum(1 for c in checks if c.passed),
            "failed": sum(1 for c in checks if not c.passed),
        },
        "results": [asdict(c) for c in checks],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["summary"], "output": str(OUT)}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
