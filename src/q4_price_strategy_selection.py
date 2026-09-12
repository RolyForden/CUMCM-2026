"""只用一月顺序窗口选择第四问正式电价预测方法。"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.data_io import load_forecast_vintages
from core.q2_replay import prior_from_attachment1
from core.q4_energy import make_q42_energy_provider, make_q43_energy_provider
from core.q4_price import load_attachment4_prices
from core.q4_replay import replay_q42, replay_q43


ACTUAL_CACHE = ROOT / "experiments/q2_actuals_cache.csv"
OUTPUT = ROOT / "experiments/q4_price_strategy_selection.json"
REPORT = ROOT / "research/C_Q4_price_strategy_selection.md"
START = date(2025, 1, 1)
EVAL_START = date(2025, 1, 15)
END = date(2025, 1, 30)
METHODS = ("D-7", "same-weekday-weighted")


def load_actuals() -> pd.DataFrame:
    if not ACTUAL_CACHE.exists():
        raise FileNotFoundError("缺少已验证的第二问实际数据缓存")
    frame = pd.read_csv(
        ACTUAL_CACHE, parse_dates=["date", "valid_time", "observed_at"]
    )
    frame["date"] = frame["date"].dt.date
    return frame


def main() -> int:
    t0 = time.time()
    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    prices = load_attachment4_prices()
    vintages = load_forecast_vintages()
    q42_energy = make_q42_energy_provider(actuals, prior)
    q43_energy = make_q43_energy_provider(actuals, prior, vintages)
    rows = []
    for method in METHODS:
        q42 = replay_q42(
            actuals, prices, q42_energy, START, END,
            evaluation_start=EVAL_START, price_method=method, collect_records=False,
        )
        q43 = replay_q43(
            actuals, prices, q43_energy, START, END,
            evaluation_start=EVAL_START, price_method=method, collect_records=False,
        )
        rows.append({
            "method": method,
            "q4_2_cost_actual": q42["cost_total"],
            "q4_3_cost_actual": q43["total_cost_actual"],
            "combined_actual_cost": q42["cost_total"] + q43["total_cost_actual"],
            "evaluation_days": q42["evaluation_days"],
        })
    winner = min(rows, key=lambda row: row["combined_actual_cost"])["method"]
    payload = {
        "selection_window": "2025-01-15..2025-01-30",
        "information_rule": "每次优化仅使用当时可得价格；真实价格只做事后结算",
        "candidates": rows,
        "selected_method": winner,
        "selection_rule": "两条正式分支的一月实际结算费之和最小",
        "elapsed_seconds": time.time() - t0,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 第四问电价预测方法冻结实验",
        "",
        "只使用 2025 年 1 月 15 日至 30 日的顺序回放选择方法；2 月至 12 月没有参与选型。",
        "优化时只用当时可得的历史电价，真实电价只在事后核算费用。",
        "",
        "| 方法 | 第二问式费用（元） | 第三问式费用（元） | 合计（元） |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['method']} | {row['q4_2_cost_actual']:.6f} | "
            f"{row['q4_3_cost_actual']:.6f} | {row['combined_actual_cost']:.6f} |"
        )
    lines += [
        "",
        f"主方法冻结为 **{winner}**。选择标准是两条分支合计实际费用最低；复杂度只在费用近似相同时用于取舍。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
