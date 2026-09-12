"""Generate the two evidence panels used by the Q3 paper section."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    q2 = pd.read_csv(ROOT / "outputs/q2/q2_daily_summary.csv", parse_dates=["date"])
    q3 = pd.read_csv(ROOT / "outputs/q3/q3_daily_summary.csv", parse_dates=["date"])
    ablation = json.loads(
        (ROOT / "outputs/q3/q3_update_ablation.json").read_text(encoding="utf-8")
    )["configurations"]

    merged = q2[["date", "cost_total"]].merge(
        q3[["date", "total_cost"]], on="date", validate="one_to_one"
    )
    monthly = merged.set_index("date").resample("ME").sum()
    monthly["saving"] = monthly.cost_total - monthly.total_cost

    order = ["00", "00+06", "00+06+12", "00+06+12+18"]
    missing = [name for name in order if name not in ablation]
    if missing:
        raise ValueError(f"Q3 update ablation is incomplete: {missing}")

    plt.rcParams.update({"font.size": 10, "axes.unicode_minus": False})
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2))

    ax = axes[0]
    x = range(len(monthly))
    ax.plot(x, monthly.cost_total / 1e6, marker="o", label="Q2: 00:00 plan")
    ax.plot(x, monthly.total_cost / 1e6, marker="s", label="Q3: intraday updates")
    ax.set_xticks(list(x), [str(i) for i in range(2, 13)])
    ax.set_xlabel("Month")
    ax.set_ylabel("Monthly cost (million CNY)")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    ax.set_title("(a) Out-of-sample monthly cost")

    ax = axes[1]
    costs = [ablation[name]["total_cost"] / 1e6 for name in order]
    bars = ax.bar(range(4), costs, color=["#9aa0a6", "#5b8ff9", "#61a0a8", "#d48265"])
    ax.set_xticks(range(4), ["00", "+06", "+12", "+18"])
    ax.set_xlabel("Available forecast releases")
    ax.set_ylabel("Annual cost (million CNY)")
    ax.set_title("(b) Update-time ablation")
    ax.grid(axis="y", alpha=0.25)
    low = min(costs)
    ax.set_ylim(max(0, low - 0.35), max(costs) + 0.15)
    for bar, value in zip(bars, costs):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.015, f"{value:.3f}",
                ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    out = ROOT / "figures/q3_cost_and_updates.png"
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
