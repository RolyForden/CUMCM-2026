"""第四问价格层短测试与一月顺序候选比较。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q4_price import forecast_prices_as_of, load_attachment4_prices
from core.slot_adapter import build_day_slots


def main() -> int:
    checks: list[dict] = []

    def check(name: str, passed: bool, actual: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": str(actual)})

    actual = load_attachment4_prices()
    check("附件4读取为365乘144长表", len(actual) == 365 * 144, len(actual))
    check("附件4目标时刻唯一", actual.target_time.nunique() == len(actual), actual.target_time.nunique())

    jan1_targets = [slot.interval_start for slot in build_day_slots(date(2025, 1, 1))]
    jan1 = forecast_prices_as_of(actual, datetime(2025, 1, 1), jan1_targets, "D-7")
    check("一月一日完整使用附件1先验", set(jan1.method) == {"cold-start:attachment1-prior"}, jan1.method.value_counts().to_dict())

    jan2_targets = [slot.interval_start for slot in build_day_slots(date(2025, 1, 2))]
    jan2 = forecast_prices_as_of(actual, datetime(2025, 1, 2), jan2_targets, "D-7")
    check(
        "一月二日只用已观测同槽均值且末槽回退先验",
        jan2.iloc[0].method == "cold-start:observed-slot-mean"
        and jan2.iloc[143].method == "cold-start:attachment1-prior"
        and jan2.source_observed_at.max() <= datetime(2025, 1, 2),
        jan2.method.value_counts().to_dict(),
    )

    decision = datetime(2025, 2, 1)
    horizon_targets = [
        slot.interval_start
        for offset in range(7)
        for slot in build_day_slots(date(2025, 2, 1) + timedelta(days=offset))
    ]
    d7 = forecast_prices_as_of(actual, decision, horizon_targets, "D-7")
    check("七日视野一次生成1008槽", len(d7) == 7 * 144, len(d7))
    check("七日视野全部沿用真实决策时刻", d7.issue_time.nunique() == 1 and d7.issue_time.iloc[0] == decision, d7.issue_time.unique())
    check("七日视野没有未来来源", d7.source_observed_at.max() <= decision, d7.source_observed_at.max())
    check("七天来源不可用时按十四天等同周回退", d7.method.str.contains("fallback-D-14").any(), d7.method.value_counts().to_dict())

    slot143_target = build_day_slots(date(2025, 2, 1))[143].interval_start
    slot143 = forecast_prices_as_of(actual, decision, [slot143_target], "D-7").iloc[0]
    check(
        "槽143按次日零点处理且来源已经完整观测",
        slot143.target_time == datetime(2025, 2, 2)
        and slot143.source_time == pd.Timestamp(datetime(2025, 1, 26))
        and slot143.source_observed_at <= decision,
        {"target": str(slot143.target_time), "source": str(slot143.source_time)},
    )

    d1_rejected = False
    try:
        forecast_prices_as_of(actual, decision, [slot143_target], "D-1")
    except ValueError:
        d1_rejected = True
    check("昨天同刻末槽来源尚未发生时明确拒绝", d1_rejected, d1_rejected)

    future_target = build_day_slots(date(2025, 2, 3))[0].interval_start
    future_rejected = False
    try:
        forecast_prices_as_of(actual, decision, [future_target], "D-1")
    except ValueError:
        future_rejected = True
    check("多日视野不得把未来目标日当新决策时刻", future_rejected, future_rejected)

    weekday = forecast_prices_as_of(actual, decision, horizon_targets, "same-weekday-weighted")
    check("同星期加权生成完整七日视野", len(weekday) == 1008, len(weekday))
    check("同星期加权没有未来来源", weekday.source_observed_at.max() <= decision, weekday.source_observed_at.max())

    comparison: dict[str, dict] = {}
    for method in ("D-1", "D-7", "same-weekday-weighted"):
        predicted: list[float] = []
        observed: list[float] = []
        covered_days: set[str] = set()
        full_days = 0
        for offset in range(14, 30):
            target_day = date(2025, 1, 1) + timedelta(days=offset)
            day_decision = datetime.combine(target_day, datetime.min.time())
            day_actual = actual[actual.target_time.isin([s.interval_start for s in build_day_slots(target_day)])]
            evaluation_rows = day_actual.copy()
            if method == "D-1":
                # 午夜决策时，方案A末槽的一天前来源到00:10才观测完成。
                evaluation_rows = evaluation_rows[
                    evaluation_rows.target_time.dt.time != datetime.min.time()
                ]
            day_forecast = forecast_prices_as_of(
                actual,
                day_decision,
                evaluation_rows.target_time.tolist(),
                method,
            )
            predicted.extend(day_forecast.price_forecast.astype(float).tolist())
            observed.extend(evaluation_rows.price_actual.astype(float).tolist())
            day_count = len(day_forecast)
            if day_count:
                covered_days.add(target_day.isoformat())
            if day_count == 144:
                full_days += 1
        errors = np.asarray(predicted) - np.asarray(observed)
        comparison[method] = {
            "mae": float(np.mean(np.abs(errors))),
            "rmse": float(np.sqrt(np.mean(errors ** 2))),
            "predicted_slots": len(predicted),
            "days_with_any_coverage": len(covered_days),
            "full_144_slot_days": full_days,
            "evaluation_days": "2025-01-15..2025-01-30",
        }
    check("一月顺序比较覆盖三个候选", set(comparison) == {"D-1", "D-7", "same-weekday-weighted"}, comparison)
    check("一月候选比较未使用二月至十二月", all(item["evaluation_days"].endswith("2025-01-30") for item in comparison.values()), comparison)

    failed = [item for item in checks if not item["passed"]]
    payload = {
        "scope": "Q4 price layer only; no optimizer and no full-year replay",
        "summary": {"total": len(checks), "passed": len(checks) - len(failed), "failed": len(failed)},
        "january_sequential_comparison": comparison,
        "results": checks,
    }
    output = ROOT / "experiments/q4_price_test_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
