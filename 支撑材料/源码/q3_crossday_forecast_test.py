"""Regression test that an intraday Q3 vintage is not truncated at midnight."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.q2_replay import daily_price, prior_from_attachment1
from core.q3_forecast import expand_issue_forecast
from core.q3_replay import _horizon
from core.slot_adapter import build_day_slots


def main() -> int:
    day = date(2025, 2, 1)
    issue = datetime(2025, 2, 1, 18)
    cache = pd.read_csv(
        ROOT / "experiments/q3_actuals_cache.csv",
        parse_dates=["valid_time", "observed_at", "date"],
    )
    cache["date"] = cache.date.dt.date
    vintages = data_io.load_forecast_vintages()
    _, _, horizon_pv = _horizon(
        day,
        18,
        107,
        cache,
        prior_from_attachment1(date(2025, 1, 1)),
        vintages,
        daily_price(),
    )

    # 37 current-day slots precede the next day's 144-slot block.
    next_slots = build_day_slots(day + timedelta(days=1))
    target_slot = 71
    target = next_slots[target_slot].interval_start
    expected = expand_issue_forecast(vintages, issue, [target], method="linear")
    actual = float(horizon_pv[37 + target_slot] * 6.0)
    checks = {
        "seven_day_horizon_length": len(horizon_pv) == 37 + 6 * 144,
        "cross_midnight_value_from_current_vintage": abs(
            actual - float(expected.pv_forecast.iloc[0])
        ) < 1e-9,
        "cross_midnight_source_is_not_fallback": expected.source.iloc[0] == "linear",
        "source_issue_is_causal": expected.source_issue_max.iloc[0] <= issue,
    }
    payload = {
        "scope": "Q3 18:00 vintage retained after midnight",
        "target_time": target.isoformat(),
        "expected_kw": float(expected.pv_forecast.iloc[0]),
        "actual_kw": actual,
        "summary": {
            "total": len(checks),
            "passed": sum(checks.values()),
            "failed": len(checks) - sum(checks.values()),
        },
        "checks": checks,
    }
    out = ROOT / "experiments/q3_crossday_forecast_test.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
