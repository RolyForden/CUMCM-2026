"""紧急购电时段合并规则的独立测试。

交接说明要求：合并相邻非零紧急购电槽，并特别检查跨午夜边界。这里用构造
记录直接测试合并逻辑，不运行整年回放。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generate_q2_result import merge_emergency_intervals
from core.slot_adapter import build_day_slots


RESULTS: list[dict] = []


def check(name: str, passed: bool, actual: object) -> None:
    RESULTS.append({"name": name, "passed": bool(passed), "actual": str(actual)})


def make_records(day: date, emergency_by_slot: dict[int, float]) -> list[dict]:
    slots = build_day_slots(day)
    out = []
    for k in range(144):
        out.append(
            {
                "date": day.isoformat(),
                "slot": k,
                "grid_contract": 0.0,
                "grid_emergency": float(emergency_by_slot.get(k, 0.0)),
                "charge": 0.0,
                "discharge": 0.0,
                "soc_start": 6000.0,
                "soc_end": 6000.0,
                "interval_start": slots[k].interval_start.isoformat(),
                "interval_end": slots[k].interval_end.isoformat(),
            }
        )
    return out


def main() -> int:
    day = date(2025, 3, 1)

    # 连续三槽合并为一段，中间断开则分成两段
    recs = make_records(day, {10: 30.0, 11: 40.0, 12: 50.0, 20: 60.0})
    merged = merge_emergency_intervals(day, recs)
    check(
        "相邻非零槽合并为一段、断开处分开",
        len(merged) == 2
        and merged[0]["quantity"] == 120.0
        and merged[0]["start"] == "01:50"
        and merged[0]["end_label"] == "02:20"
        and merged[1]["quantity"] == 60.0,
        [(m["start"], m["end_label"], m["quantity"]) for m in merged],
    )

    # 跨午夜：槽142（23:50-24:00）+ 槽143（次日00:00-00:10）必须合并为一段
    cross = make_records(day, {142: 70.0, 143: 80.0})
    merged_cross = merge_emergency_intervals(day, cross)
    check(
        "槽142与槽143跨午夜合并为一段",
        len(merged_cross) == 1
        and merged_cross[0]["slot_first"] == 142
        and merged_cross[0]["slot_last"] == 143
        and merged_cross[0]["quantity"] == 150.0
        and merged_cross[0]["start"] == "23:50"
        and merged_cross[0]["end_label"] == "00:10+1",
        merged_cross[0] if merged_cross else None,
    )

    # 只有槽143时，起点也必须标为次日 00:00+1
    only143 = make_records(day, {143: 25.0})
    merged_143 = merge_emergency_intervals(day, only143)
    check(
        "仅槽143时起点标为00:00+1",
        len(merged_143) == 1
        and merged_143[0]["start"] == "00:00+1"
        and merged_143[0]["end_label"] == "00:10+1"
        and merged_143[0]["quantity"] == 25.0,
        merged_merged := merged_143[0] if merged_143 else None,
    )

    # 无紧急购电则无区间
    none_recs = make_records(day, {})
    check("无紧急购电时不产生区间", len(merge_emergency_intervals(day, none_recs)) == 0, 0)

    # 全天连续非零则合并为唯一一段 00:10-00:10+1
    all_day = make_records(day, {k: 1.0 for k in range(144)})
    merged_all = merge_emergency_intervals(day, all_day)
    check(
        "全天连续非零合并为唯一一段",
        len(merged_all) == 1
        and merged_all[0]["start"] == "00:10"
        and merged_all[0]["end_label"] == "00:10+1"
        and abs(merged_all[0]["quantity"] - 144.0) < 1e-9,
        merged_all[0] if merged_all else None,
    )

    failed = [item for item in RESULTS if not item["passed"]]
    payload = {
        "scope": "emergency purchase interval merging; cross-midnight boundary",
        "summary": {"total": len(RESULTS), "passed": len(RESULTS) - len(failed), "failed": len(failed)},
        "results": RESULTS,
    }
    output = ROOT / "experiments" / "q2_emergency_merge_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
