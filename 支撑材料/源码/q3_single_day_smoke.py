"""Q3 预测-调整-执行-结算的最小单日 smoke。"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.q2_replay import daily_price, load_window_actuals, prior_from_attachment1
from core.q3_replay import run_day


def main() -> int:
    day = date(2025, 2, 1)
    actuals = load_window_actuals(date(2025, 1, 1), day)
    prior = prior_from_attachment1(date(2025, 1, 1))
    vintages = data_io.load_forecast_vintages()
    price = daily_price()
    plan, records, result = run_day(day, 6000.0, actuals, prior, vintages, price)
    checks = {
        "144_slots": len(records) == 144,
        "physical_audit": result["physical_audit"].ok,
        "four_versions_after_18": len(plan.versions[143]) == 4,
        "executed_slot_not_rewritten": len(plan.versions[0]) == 1,
        "finite_cost": result["total_cost"] > 0,
        "ledger_identity": abs(
            result["total_cost"] - result["initial_contract_cost"] - result["up_cost"]
            + result["down_credit"] - result["emergency_cost"]
        ) < 1e-6,
        "soc_continuous": all(abs(a.soc_end-b.soc_start) < 1e-6 for a,b in zip(records, records[1:])),
    }
    payload = {
        "scope": "Q3 one-day forecast-driven smoke; 2025-02-01; soc0=6000",
        "summary": {"total": len(checks), "passed": sum(checks.values()), "failed": len(checks)-sum(checks.values())},
        "checks": checks,
        "metrics": {k: v for k, v in result.items() if isinstance(v, (int, float))},
    }
    out = ROOT / "experiments/q3_single_day_smoke_results.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
