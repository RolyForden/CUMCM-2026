"""第二问终端库存处理对照实验。

比较三种终端口径在完整回放期上的费用、紧急购电、不可行次数、边界停留
和库存轨迹，供人类裁决全年正式口径。默认用点预测策略，不与保守程度选择
耦合；输出交人类后，正式全年回放在冻结口径下运行。

不自行选定终端方案，也不写入 result2。
"""

from __future__ import annotations

from datetime import date, datetime
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


def load_actuals() -> pd.DataFrame:
    """全窗口实际值；首次读取慢，缓存为 CSV 以便重复实验。"""
    if CACHE.exists():
        cached = pd.read_csv(CACHE, parse_dates=["valid_time", "observed_at", "date"])
        cached["date"] = cached["date"].dt.date
        if (
            cached["date"].min() == START
            and cached["date"].max() == EVAL_END
            and cached["slot"].nunique() == 144
        ):
            return cached
    actuals = load_window_actuals(START, EVAL_END)
    actuals.to_csv(CACHE, index=False)
    return actuals


def summarize(row: dict) -> dict:
    keys = (
        "terminal",
        "terminal_mode",
        "terminal_param",
        "cost_normal",
        "cost_emergency",
        "cost_total",
        "grid_emergency_kwh",
        "grid_unused_kwh",
        "charge_shortfall_kwh",
        "discharge_shortfall_kwh",
        "infeasible_days",
        "days_soc_end_at_max",
        "days_soc_end_at_min",
        "days_touching_max",
        "days_touching_min",
        "soc_end_mean",
        "soc_end_median",
        "soc_min_overall",
        "soc_max_overall",
        "soc_end_final",
        "all_audits_ok",
        "evaluation_days",
    )
    out = {k: row[k] for k in keys}
    # 每月末库存轨迹，用于判断长期边界停留
    monthly = {}
    for day_row in row["daily"]:
        if day_row["date"] >= EVAL_START.isoformat():
            monthly[day_row["date"]] = day_row["actual_soc_end"]
    out["soc_at_month_ends"] = {
        d: v for d, v in monthly.items() if d.endswith("-01") or d.endswith("-31") or d[-5:] in ("02-28",)
    }
    return out


def main() -> int:
    t0 = time.time()
    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    price = daily_price()
    print(f"实际值 {len(actuals)} 行，加载 {time.time() - t0:.1f}s", flush=True)

    configs = [
        Terminal("plan_eq"),
        Terminal("terminal_value", 0.0),
        Terminal("terminal_value", 0.4),
        Terminal("terminal_value", 0.8),
        Terminal("terminal_value", 1.2),
        Terminal("rolling", 3),
        Terminal("rolling", 7),
    ]
    strategy = Strategy("D-7", "point")
    results = []
    for term in configs:
        t1 = time.time()
        row = replay(
            strategy, term, actuals, prior, price, START, EVAL_START, EVAL_END
        )
        results.append(row)
        print(
            f"{term.label():>20}  总费={row['cost_total']:12.2f}  "
            f"紧急={row['grid_emergency_kwh']:10.1f}  "
            f"边界天={row['days_at_boundary']:3d}  "
            f"不可行={row['infeasible_days']:2d}  "
            f"期末库存={row['soc_end_final']:8.1f}  "
            f"{time.time() - t1:.1f}s",
            flush=True,
        )

    payload = {
        "scope": "terminal inventory handling comparison; point forecast; no result2 written",
        "strategy": {"method": strategy.method, "level": strategy.level},
        "evaluation": {"start": EVAL_START.isoformat(), "end": EVAL_END.isoformat()},
        "summary": [summarize(row) for row in results],
        "daily": {row["terminal"]: row["daily"] for row in results},
    }
    output = ROOT / "experiments" / "q2_terminal_comparison_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": payload["summary"]}, ensure_ascii=False, indent=2))
    print(f"总耗时 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
