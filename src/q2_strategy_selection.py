"""第二问策略的顺序选择：只用过去数据选，未来数据评价。

方法地图 §3.3/交接说明第三步要求：不得先看全年结果再挑最好的方法。本脚本
按固定频率（每 rebalance_days 天）在一次重新选择时点，只用该时点以前已经
完成的日期比较候选，选出历史实际总费用最低的候选，再将它用于后续尚未发生
的日期。

候选网格：预测方法 × 保守等级。每个候选在"选择窗口"内独立回放，用核算器
复算的实际总费用排序；选中者进入下一段。全部选择频率与候选网格在报告中
固定后，才允许在正式全年回放里复用选定结果。

不写入 result2；终端口径需先由人类裁决，这里以 plan_eq 为例跑通流程。
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
WARMUP_END = date(2025, 1, 31)
EVAL_START = date(2025, 2, 1)
EVAL_END = date(2025, 12, 31)
CACHE = ROOT / "experiments" / "q2_actuals_cache.csv"

METHODS = ("D-7", "same-weekday-4-decay-0.8")
LEVELS = ("point", "0.7", "0.8", "0.9")


def load_actuals() -> pd.DataFrame:
    if CACHE.exists():
        cached = pd.read_csv(CACHE, parse_dates=["valid_time", "observed_at", "date"])
        cached["date"] = cached["date"].dt.date
        if cached["date"].min() == START and cached["date"].max() == EVAL_END:
            return cached
    actuals = load_window_actuals(START, EVAL_END)
    actuals.to_csv(CACHE, index=False)
    return actuals


def segment_cost(
    strategy: Strategy,
    terminal: Terminal,
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    price: np.ndarray,
    seg_start: date,
    seg_end: date,
) -> dict:
    """在 [seg_start, seg_end] 上评估一个候选。

    为保证所选候选在同一起点比较，回放从 START（含1月预热）开始，
    但只汇总 [seg_start, seg_end] 的费用；每个候选拥有各自初值一致的
    一月推进，起点差异来自各自策略在1月的实际库存轨迹。
    """
    row = replay(strategy, terminal, actuals, prior, price, START, seg_start, seg_end)
    return {
        "method": strategy.method,
        "level": strategy.level,
        "cost_total": row["cost_total"],
        "cost_normal": row["cost_normal"],
        "cost_emergency": row["cost_emergency"],
        "grid_emergency_kwh": row["grid_emergency_kwh"],
        "infeasible_days": row["infeasible_days"],
        "all_audits_ok": row["all_audits_ok"],
        "soc_start": row["daily"][0]["actual_soc_start"] if row["daily"] else None,
    }


def main() -> int:
    t0 = time.time()
    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    price = daily_price()
    terminal = Terminal("plan_eq")  # 终端口径待人类裁决，流程演示用
    rebalance_days = 30

    grid = [Strategy(m, l) for m, l in itertools.product(METHODS, LEVELS)]
    # 选择窗口从 WARMUP_END 后开始，每个窗口用之前已完成日期比较
    selections: list[dict] = []
    cum_start = EVAL_START
    while cum_start <= EVAL_END:
        cum_end = min(cum_start + timedelta(days=rebalance_days - 1), EVAL_END)
        # 用"到目前为止已完成"的日期比较候选：回放到 cum_end，汇总 [EVAL_START, cum_end]
        scored = []
        for strategy in grid:
            row = segment_cost(
                strategy, terminal, actuals, prior, price, EVAL_START, cum_end
            )
            scored.append(row)
        best = min(scored, key=lambda r: r["cost_total"])
        selections.append(
            {
                "decision_time": datetime.combine(cum_start, datetime.min.time()).isoformat(),
                "window": [EVAL_START.isoformat(), cum_end.isoformat()],
                "chosen": {"method": best["method"], "level": best["level"]},
                "chosen_cost_total": best["cost_total"],
                "candidates": scored,
            }
        )
        print(
            f"选择时点 {cum_start}: 选中 {best['method']}/{best['level']} "
            f"窗口费用 {best['cost_total']:.2f} ({time.time() - t0:.0f}s)",
            flush=True,
        )
        cum_start = cum_end + timedelta(days=1)

    payload = {
        "scope": "walk-forward strategy selection; past-only selection; plan_eq terminal (pending human decision)",
        "rebalance_days": rebalance_days,
        "grid": [{"method": s.method, "level": s.level} for s in grid],
        "selections": selections,
    }
    output = ROOT / "experiments" / "q2_strategy_selection_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    chosen_counts: dict[str, int] = {}
    for item in selections:
        key = f"{item['chosen']['method']}/{item['chosen']['level']}"
        chosen_counts[key] = chosen_counts.get(key, 0) + 1
    print(json.dumps({"chosen_counts": chosen_counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
