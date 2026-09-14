"""N3 点预测展开与一次加载回归测试。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.q3_forecast import expand_issue_forecast
from core.slot_adapter import build_day_slots


def main() -> int:
    checks = []
    def check(name: str, passed: bool, actual: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "actual": str(actual)})

    all_rows = data_io.load_forecast_vintages()
    check("附件3记录完整", len(all_rows) == 35040, len(all_rows))
    check(
        "点预测有效时刻",
        bool(((all_rows.valid_time - all_rows.issue_time).dt.total_seconds() / 3600 == all_rows.lead_hour).all()),
        "valid_time=issue+lead",
    )
    before = data_io._load_forecast_vintages_cached.cache_info()
    data_io.forecast_vintage_as_of(datetime(2025, 2, 1, 6))
    after = data_io._load_forecast_vintages_cached.cache_info()
    check("工作簿缓存命中", after.hits > before.hits, after)

    issue = datetime(2025, 2, 1, 6)
    targets = [issue + timedelta(minutes=10 * i) for i in range(37)]
    expanded = expand_issue_forecast(all_rows, issue, targets, method="linear")
    check("单次更新覆盖至下一发布点", len(expanded) == 37 and expanded.pv_forecast.notna().all(), len(expanded))
    check(
        "无后发批次泄漏",
        bool(expanded.source_issue_max.dropna().le(issue).all()),
        expanded.source_issue_max.max(),
    )
    current = all_rows[(all_rows.issue_time == issue) & (all_rows.lead_hour.isin([1, 2]))]
    f1, f2 = current.sort_values("lead_hour").pv_forecast.to_numpy()
    midpoint = expand_issue_forecast(
        all_rows, issue, [issue + timedelta(hours=1, minutes=30)], method="linear"
    ).pv_forecast.iloc[0]
    check("整点间线性插值", abs(midpoint - (f1 + f2) / 2) < 1e-9, midpoint)

    slots = build_day_slots(date(2025, 2, 1))
    schedule = [(0, 0, 35), (6, 35, 71), (12, 71, 107), (18, 107, 144)]
    covered = []
    for hour, lo, hi in schedule:
        decision = datetime(2025, 2, 1, hour)
        part = expand_issue_forecast(
            all_rows, decision, [s.interval_start for s in slots[lo:hi]], method="linear"
        )
        covered.extend(range(lo, hi))
        check(f"{hour:02d}:00批次覆盖", len(part) == hi - lo, len(part))
    check("四批次不重不漏覆盖144槽", covered == list(range(144)), (len(covered), len(set(covered))))

    # 只用1月选择点到区间方法；2-12月保留为正式评价期。
    actual_frames = [data_io.attachment2_pv(date(2025, 1, 1) + timedelta(days=i)) for i in range(31)]
    actual = pd.concat(actual_frames).set_index("valid_time")["value"]
    errors = {"linear": [], "previous": []}
    for i in range(31):
        day = date(2025, 1, 1) + timedelta(days=i)
        day_slots = build_day_slots(day)
        for hour, lo, hi in schedule:
            decision = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour)
            targets_part = [s.interval_start for s in day_slots[lo:hi]]
            for method in errors:
                try:
                    pred = expand_issue_forecast(all_rows, decision, targets_part, method=method)
                except ValueError:
                    # Jan 1 00:00 lacks a previous-day anchor; it is a declared cold-start gap.
                    continue
                errors[method].extend((pred.pv_forecast.to_numpy() - actual.loc[targets_part].to_numpy()).tolist())
    metrics = {
        method: {
            "n": len(values),
            "mae_kw": float(np.mean(np.abs(values))),
            "rmse_kw": float(np.sqrt(np.mean(np.square(values)))),
        }
        for method, values in errors.items()
    }
    check("1月线性插值优于前值保持", metrics["linear"]["mae_kw"] < metrics["previous"]["mae_kw"], metrics)

    failed = [c for c in checks if not c["passed"]]
    payload = {
        "scope": "N3 point forecast expansion; January-only method choice",
        "summary": {"total": len(checks), "passed": len(checks) - len(failed), "failed": len(failed)},
        "january_metrics": metrics,
        "results": checks,
    }
    out = ROOT / "experiments/q3_forecast_mapping_results.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": payload["summary"], "january_metrics": metrics}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
