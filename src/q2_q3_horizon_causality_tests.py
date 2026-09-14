"""Independent regression tests for Q2/Q3 multi-day horizon causality."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import q2_replay, q3_replay
from core.q2_replay import Strategy, Terminal, build_forecast, plan_day
from core.q3_forecast import expand_issue_forecast
from core.slot_adapter import build_day_slots


OUTPUT = ROOT / "experiments/q2_q3_horizon_causality_results.json"


def _prior() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "slot": np.arange(144),
            "load_forecast": np.full(144, 600.0),
            "pv_forecast": np.full(144, 100.0),
        }
    )


def _actuals(start: date, end: date) -> pd.DataFrame:
    rows = []
    current = start
    day_index = 0
    while current <= end:
        for slot in build_day_slots(current):
            rows.append(
                {
                    "date": current,
                    "slot": slot.slot_id,
                    "valid_time": slot.interval_start,
                    "observed_at": slot.interval_end,
                    "load_actual": 1000.0 + 10.0 * day_index + slot.slot_id / 1000.0,
                    "pv_actual": 200.0 + day_index + slot.slot_id / 10000.0,
                }
            )
        current += timedelta(days=1)
        day_index += 1
    return pd.DataFrame(rows)


def _vintages(issue: datetime) -> pd.DataFrame:
    rows = [
        {
            "issue_time": issue - timedelta(hours=6),
            "valid_time": issue,
            "lead_hour": 6,
            "pv_forecast": 321.0,
        }
    ]
    rows.extend(
        {
            "issue_time": issue,
            "valid_time": issue + timedelta(hours=lead),
            "lead_hour": lead,
            "pv_forecast": 400.0 + lead,
        }
        for lead in range(1, 25)
    )
    return pd.DataFrame(rows)


def main() -> int:
    checks: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    prior = _prior()
    price = np.full(144, 0.5)

    # Jan-1: all seven target days must share the one real 00:00 decision.
    jan1 = date(2025, 1, 1)
    jan_actuals = _actuals(jan1, jan1 + timedelta(days=6))
    captured_q2: list[tuple[date, datetime | None]] = []
    original_build = q2_replay.build_forecast

    def capture_q2(strategy, actuals, prior_frame, target_day, decision_time=None):
        captured_q2.append((target_day, decision_time))
        return original_build(strategy, actuals, prior_frame, target_day, decision_time)

    with patch.object(q2_replay, "build_forecast", side_effect=capture_q2):
        solution = plan_day(
            Strategy("D-7", "point"),
            Terminal("rolling", 7),
            jan_actuals,
            prior,
            price,
            jan1,
            6000.0,
        )
    jan1_decision = datetime(2025, 1, 1)
    record(
        "Q2 Jan-1 rolling horizon uses one real decision time",
        len(captured_q2) == 7 and all(d == jan1_decision for _, d in captured_q2),
        repr(captured_q2),
    )
    record(
        "Q2 Jan-1 cold start remains feasible without future actuals",
        np.isfinite(solution.grid).all(),
        f"status={solution.status}",
    )

    # Formal-period frontier: target day 7 slot 143's D-7 source ends ten
    # minutes after the decision, so it must use D-14 (Jan-25) instead.
    decision = datetime(2025, 2, 1)
    formal_actuals = _actuals(date(2025, 1, 1), date(2025, 2, 8))
    target_day = date(2025, 2, 7)
    forecast = build_forecast(
        Strategy("D-7", "point"),
        formal_actuals,
        prior,
        target_day,
        decision_time=decision,
    )
    frontier = forecast.iloc[143]
    source_time = build_day_slots(target_day)[143].interval_start - timedelta(days=14)
    expected = formal_actuals.set_index("valid_time").loc[source_time]
    record(
        "Q2 seventh-day slot143 falls back from unavailable D-7 to D-14",
        frontier["method"] == "D-7-fallback:D-14"
        and abs(float(frontier.load_forecast) - float(expected.load_actual)) < 1e-12,
        f"method={frontier['method']}, source={source_time.isoformat()}",
    )
    record(
        "Q2 formal horizon sources do not exceed real decision time",
        bool((forecast.source_max_observed_at <= decision).all())
        and bool((forecast.issue_time == decision).all()),
        f"max_source={forecast.source_max_observed_at.max()}, issue={decision}",
    )

    # Q3 18:00: all fallback forecasts share the actual issue time, while the
    # Attachment-3 interpolation for the following day is unchanged.
    q3_day = date(2025, 2, 1)
    issue = datetime(2025, 2, 1, 18)
    q3_actuals = _actuals(date(2025, 1, 1), date(2025, 2, 8))
    vintages = _vintages(issue)
    captured_q3: list[tuple[date, datetime | None]] = []
    original_day_forecast = q3_replay._day_forecast

    def capture_q3(actuals, prior_frame, target_day, decision_time=None):
        captured_q3.append((target_day, decision_time))
        return original_day_forecast(actuals, prior_frame, target_day, decision_time)

    with patch.object(q3_replay, "_day_forecast", side_effect=capture_q3):
        _, _, horizon_pv = q3_replay._horizon(
            q3_day, 18, 107, q3_actuals, prior, vintages, price
        )
    record(
        "Q3 18:00 horizon fallback uses one real issue time",
        len(captured_q3) == 7 and all(d == issue for _, d in captured_q3),
        repr(captured_q3),
    )
    next_target = datetime(2025, 2, 2, 12)
    expected_pv = expand_issue_forecast(vintages, issue, [next_target], method="linear")
    # Current-day slots 107..143 occupy 37 positions.  On the next target day,
    # 12:00 is slot 71 under scheme A.
    actual_pv_kw = float(horizon_pv[37 + 71] * 6.0)
    record(
        "Q3 Attachment-3 cross-midnight interpolation is unchanged",
        abs(actual_pv_kw - float(expected_pv.pv_forecast.iloc[0])) < 1e-12,
        f"expected={float(expected_pv.pv_forecast.iloc[0])}, actual={actual_pv_kw}",
    )

    payload = {
        "scope": "Q2/Q3 multi-day horizon causal information-set regression",
        "summary": {
            "total": len(checks),
            "passed": sum(row["passed"] for row in checks),
            "failed": sum(not row["passed"] for row in checks),
        },
        "checks": checks,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
