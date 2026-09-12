"""第二问策略的顺序选择：只用过去数据选，未来数据评价。

方法地图 §3.3 与交接说明第三步要求：不得先看全年结果再挑最好的方法。本
脚本让每个候选走一次完整全年回放（2025-01-01 至 12-31），但在每个重新
选择时点，只用该时点以前已经完成的日期比较候选，选出累计实际总费用最低
者，用于后续尚未发生的日期段。

因果等价性：每个候选全年只有一条库存轨迹，但选择在第 k 段使用的候选时，
只读取它在第 k 段起点之前的累计费用。因为选择发生在段边界，段内两种候选
的库存差异不影响选择时点的历史比较；这是"每段重新选择"的确定性实现，
不引入未来信息。

冻结参数（写入 report 后再看全年结果）：
- 重新选择频率：每 30 天一次；
- 候选网格：预测方法 {七天前同刻, 同星期日四周衰减平均} × 保守等级 {point, 0.7, 0.8, 0.9}；
- 终端口径：rolling-7d（D011 冻结）；
- 选择标准：选择时点以前已完成日期的累计实际总费用最低。

输出选定序列与各时点候选排名；不写入 result2。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import itertools
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q2_replay import (
    Strategy,
    Terminal,
    daily_price,
    load_window_actuals,
    prior_from_attachment1,
    replay,
)

START = date(2025, 1, 1)
EVAL_START = date(2025, 2, 1)
EVAL_END = date(2025, 12, 31)
CACHE = ROOT / "experiments" / "q2_actuals_cache.csv"

METHODS = ("D-7", "same-weekday-4-decay-0.8")
LEVELS = ("point", "0.7", "0.8", "0.9")
REBALANCE_DAYS = 30
TERMINAL = Terminal("rolling", 7)


def load_actuals() -> pd.DataFrame:
    if CACHE.exists():
        cached = pd.read_csv(CACHE, parse_dates=["valid_time", "observed_at", "date"])
        cached["date"] = cached["date"].dt.date
        if cached["date"].min() == START and cached["date"].max() == EVAL_END:
            return cached
    actuals = load_window_actuals(START, EVAL_END)
    actuals.to_csv(CACHE, index=False)
    return actuals


def cumulative_from(daily: list[dict]) -> dict[str, float]:
    """按日期累计实际总费用（含正常与紧急）。"""
    running = 0.0
    out: dict[str, float] = {}
    for row in daily:
        running += row["cost_total"]
        out[row["date"]] = running
    return out


def main() -> int:
    t0 = time.time()
    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    price = daily_price()

    # 每个候选一次全年回放
    candidate_daily: dict[str, list[dict]] = {}
    for method, level in itertools.product(METHODS, LEVELS):
        key = f"{method}/{level}"
        row = replay(
            Strategy(method, level), TERMINAL, actuals, prior, price, START, EVAL_START, EVAL_END
        )
        candidate_daily[key] = row["daily"]
        print(f"{key:>34} 全年总费={row['cost_total']:12.0f} ({time.time() - t0:.0f}s)", flush=True)

    # 段边界：每 REBALANCE_DAYS 天一个决策时点，只用此前已完成日期比较。
    # 第一段没有已完成日期，固定用参数网格中的简单基线 D-7/point 作默认先验。
    DEFAULT = "D-7/point"
    segment_starts = []
    cursor = EVAL_START
    while cursor <= EVAL_END:
        segment_starts.append(cursor)
        cursor = cursor + timedelta(days=REBALANCE_DAYS)

    cum = {key: cumulative_from(daily) for key, daily in candidate_daily.items()}
    selections = []
    for i, seg_start in enumerate(segment_starts):
        seg_end = (
            segment_starts[i + 1] - timedelta(days=1)
            if i + 1 < len(segment_starts)
            else EVAL_END
        )
        completed_through = seg_start - timedelta(days=1)
        if completed_through < EVAL_START:
            # 无任何已完成评价日：用固定默认，不作比较。
            selections.append(
                {
                    "decision_time": datetime.combine(seg_start, datetime.min.time()).isoformat(),
                    "compared_through": None,
                    "applies_to": [seg_start.isoformat(), seg_end.isoformat()],
                    "chosen": DEFAULT,
                    "ranking": None,
                    "note": "首段无历史，使用固定默认先验",
                }
            )
            continue
        # 只读取决策时点之前已完成日期的累计实际总费用
        scores = {
            key: series.get(completed_through.isoformat(), 0.0)
            for key, series in cum.items()
        }
        best = min(scores, key=lambda k: scores[k])
        selections.append(
            {
                "decision_time": datetime.combine(seg_start, datetime.min.time()).isoformat(),
                "compared_through": completed_through.isoformat(),
                "applies_to": [seg_start.isoformat(), seg_end.isoformat()],
                "chosen": best,
                "ranking": sorted(scores.items(), key=lambda kv: kv[1]),
            }
        )

    chosen_counts: dict[str, int] = {}
    for item in selections:
        chosen_counts[item["chosen"]] = chosen_counts.get(item["chosen"], 0) + 1

    payload = {
        "scope": "walk-forward selection; past-only; rolling-7d terminal (D011)",
        "rebalance_days": REBALANCE_DAYS,
        "grid": [f"{m}/{l}" for m, l in itertools.product(METHODS, LEVELS)],
        "selections": selections,
        "chosen_counts": chosen_counts,
        "candidate_full_year_cost": {
            key: float(sum(r["cost_total"] for r in daily)) for key, daily in candidate_daily.items()
        },
    }
    output = ROOT / "experiments" / "q2_strategy_selection_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"chosen_counts": chosen_counts}, ensure_ascii=False, indent=2))
    print(json.dumps({"candidate_full_year_cost": payload["candidate_full_year_cost"]}, ensure_ascii=False, indent=2))
    print(f"总耗时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
