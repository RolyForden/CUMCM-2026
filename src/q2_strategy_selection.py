"""第二问策略的顺序选择：只用过去数据选，未来数据评价。

方法地图 §3.3 与交接说明第三步要求：不得先看全年结果再挑方法。本脚本对
每个候选各跑一次完整全年回放（2025-01-01 至 12-31），得到逐日实际总费用
轨迹；然后在每个重新选择时点，只用该时点以前已经完成的日期的累计实际总
费用比较候选，选出最低者用于后续段。

因果等价性：选择发生在段边界，只读取候选在边界之前的累计费用；因为两个
候选各自是一条确定轨迹，"用边界前累计值比较"与"每段独立重放"在点预测+
固定终端口径下给出同一选择，且不引入未来信息。

冻结参数：重新选择频率每 30 天；终端 rolling-7d（D011）；候选网格为预测
方法 {D-7, same-weekday-4-decay-0.8} × 保守等级 {point, 0.7, 0.8, 0.9}。
首段没有已完成评价日，固定用默认先验 D-7/point。

输出选定序列、各时点候选排名和候选全年费用；不写 result2。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import itertools
import json
from pathlib import Path
import sys
import time

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
DEFAULT = "D-7/point"
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


def cumulative(rows: list[dict]) -> dict[str, float]:
    running = 0.0
    out: dict[str, float] = {}
    for row in rows:
        if row["date"] >= EVAL_START.isoformat():
            running += row["cost_total"]
            out[row["date"]] = running
    return out


def main() -> int:
    t0 = time.time()
    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    price = daily_price()

    traj: dict[str, dict[str, float]] = {}
    full_year: dict[str, float] = {}
    for method, level in itertools.product(METHODS, LEVELS):
        key = f"{method}/{level}"
        row = replay(
            Strategy(method, level), TERMINAL, actuals, prior, price,
            START, EVAL_START, EVAL_END,
        )
        traj[key] = cumulative(row["daily"])
        full_year[key] = float(sum(d["cost_total"] for d in row["daily"]))
        print(f"{key:>34} 全年总费={full_year[key]:12.0f} ({time.time() - t0:.0f}s)", flush=True)

    # 段边界
    seg_starts = []
    cursor = EVAL_START
    while cursor <= EVAL_END:
        seg_starts.append(cursor)
        cursor += timedelta(days=REBALANCE_DAYS)

    selections = []
    for i, seg_start in enumerate(seg_starts):
        seg_end = (
            seg_starts[i + 1] - timedelta(days=1) if i + 1 < len(seg_starts) else EVAL_END
        )
        completed = seg_start - timedelta(days=1)
        if completed < EVAL_START:
            selections.append({
                "decision_time": datetime.combine(seg_start, datetime.min.time()).isoformat(),
                "compared_through": None,
                "applies_to": [seg_start.isoformat(), seg_end.isoformat()],
                "chosen": DEFAULT,
                "ranking": None,
                "note": "首段无历史，使用固定默认先验",
            })
            continue
        scores = {k: series.get(completed.isoformat(), 0.0) for k, series in traj.items()}
        best = min(scores, key=lambda k: scores[k])
        selections.append({
            "decision_time": datetime.combine(seg_start, datetime.min.time()).isoformat(),
            "compared_through": completed.isoformat(),
            "applies_to": [seg_start.isoformat(), seg_end.isoformat()],
            "chosen": best,
            "ranking": sorted(scores.items(), key=lambda kv: kv[1]),
        })

    chosen_counts: dict[str, int] = {}
    for item in selections:
        chosen_counts[item["chosen"]] = chosen_counts.get(item["chosen"], 0) + 1

    payload = {
        "scope": "walk-forward selection; past-only; rolling-7d terminal (D011)",
        "rebalance_days": REBALANCE_DAYS,
        "grid": [f"{m}/{l}" for m, l in itertools.product(METHODS, LEVELS)],
        "selections": selections,
        "chosen_counts": chosen_counts,
        "candidate_full_year_cost": full_year,
    }
    output = ROOT / "experiments" / "q2_strategy_selection_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"chosen_counts": chosen_counts}, ensure_ascii=False))
    print(json.dumps({"candidate_full_year_cost": full_year}, ensure_ascii=False, indent=2))
    print(f"总耗时 {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
