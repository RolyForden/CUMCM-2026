"""第二问历史基线的因果性测试，不选择最终预测器。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q2_forecast import (
    forecast_cold_start,
    forecast_lag_day,
    forecast_same_weekday,
    validate_forecast_causality,
)
from core.slot_adapter import build_day_slots


def synthetic_history(start: date, days: int) -> pd.DataFrame:
    rows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        for slot in build_day_slots(day):
            rows.append(
                {
                    "slot": slot.slot_id,
                    "valid_time": slot.interval_start,
                    "observed_at": slot.interval_end,
                    "load_actual": float(1000 + 10 * offset + slot.slot_id),
                    "pv_actual": float(max(0, slot.slot_id - 30)),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    checks: list[dict] = []

    def check(name: str, passed: bool, actual: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": str(actual)})

    target = date(2025, 2, 1)
    decision = datetime(2025, 2, 1, 0, 0)
    history = synthetic_history(date(2025, 1, 1), 31)
    history = history[history.observed_at <= decision].copy()

    d7 = forecast_lag_day(history, target, decision, 7)
    validate_forecast_causality(d7)
    check("七天前基线给出完整144槽", len(d7) == 144, len(d7))
    check(
        "七天前基线没有读取未来",
        d7.source_max_observed_at.max() <= decision,
        d7.source_max_observed_at.max(),
    )

    weekday = forecast_same_weekday(history, target, decision, weeks=4, decay=0.8)
    validate_forecast_causality(weekday)
    check("同星期衰减基线给出完整144槽", len(weekday) == 144, len(weekday))
    check(
        "同星期衰减基线没有读取未来",
        weekday.source_max_observed_at.max() <= decision,
        weekday.source_max_observed_at.max(),
    )

    d1_rejected = False
    try:
        forecast_lag_day(history, target, decision, 1)
    except ValueError:
        d1_rejected = True
    check(
        "凌晨决策时昨天同刻末槽尚未观测则拒绝末槽偷看",
        d1_rejected,
        d1_rejected,
    )

    future = history.copy()
    future.loc[future.index[0], "observed_at"] = decision + timedelta(minutes=10)
    future_rejected = False
    try:
        forecast_lag_day(future, target, decision, 7)
    except ValueError:
        future_rejected = True
    check("历史输入混入未来观测时拒绝", future_rejected, future_rejected)

    prior = pd.DataFrame(
        {
            "slot": list(range(144)),
            "load_forecast": [2000.0] * 144,
            "pv_forecast": [100.0] * 144,
        }
    )
    jan1 = forecast_cold_start(
        pd.DataFrame(), prior, date(2025, 1, 1), datetime(2025, 1, 1)
    )
    validate_forecast_causality(jan1)
    check(
        "一月一日无历史时完整使用典型日先验",
        len(jan1) == 144
        and set(jan1.method) == {"cold-start:attachment1-prior"}
        and (jan1.load_forecast == 2000.0).all(),
        jan1.method.value_counts().to_dict(),
    )

    jan2_decision = datetime(2025, 1, 2)
    jan1_history = synthetic_history(date(2025, 1, 1), 1)
    jan1_history = jan1_history[jan1_history.observed_at <= jan2_decision].copy()
    jan2 = forecast_cold_start(jan1_history, prior, date(2025, 1, 2), jan2_decision)
    validate_forecast_causality(jan2)
    check(
        "一月二日已观测槽用历史且未完成末槽用先验",
        jan2.iloc[0].method == "cold-start:available-history-slot-mean"
        and jan2.iloc[143].method == "cold-start:attachment1-prior"
        and jan2.source_max_observed_at.max() <= jan2_decision,
        jan2.method.value_counts().to_dict(),
    )

    failed = [item for item in checks if not item["passed"]]
    payload = {
        "scope": "Q2 forecast candidates and causality only; no final model selected",
        "summary": {"total": len(checks), "passed": len(checks) - len(failed), "failed": len(failed)},
        "results": checks,
    }
    output = ROOT / "experiments" / "q2_forecast_candidate_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
