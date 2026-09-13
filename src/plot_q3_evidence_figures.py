"""Generate two paper-ready Q3 evidence figures from frozen formal outputs.

This script is deliberately read-only with respect to the formal outputs.  It
only writes two PNG files under ``paper/figures``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, MultipleLocator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from core.figure_style import configure_chinese_font  # noqa: E402

Q2_DAILY = ROOT / "outputs" / "q2" / "q2_daily_summary.csv"
Q3_ABLATION = ROOT / "outputs" / "q3" / "q3_update_ablation.json"
Q3_DISPATCH = ROOT / "outputs" / "q3" / "q3_dispatch.csv"
FIGURE_DIR = ROOT / "paper" / "figures"

BENEFIT_FIGURE = FIGURE_DIR / "q3_two_stage_benefit.png"
TYPICAL_DAY_FIGURE = FIGURE_DIR / "q3_typical_day_dispatch_20250923.png"
TYPICAL_DAY = "2025-09-23"


BLUE = "#0072B2"
SKY = "#56B4E9"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"
PURPLE = "#CC79A7"
GRAY = "#666666"


def load_cost_levels() -> tuple[float, float, float]:
    q2 = pd.read_csv(Q2_DAILY)
    required_q2 = {"date", "cost_total"}
    if not required_q2.issubset(q2.columns):
        raise ValueError(f"Q2日汇总缺少字段：{sorted(required_q2 - set(q2.columns))}")
    if len(q2) != 334 or q2["date"].duplicated().any():
        raise ValueError("Q2正式日汇总应包含334个不重复日期。")
    q2_total = float(q2["cost_total"].sum())

    payload = json.loads(Q3_ABLATION.read_text(encoding="utf-8"))
    configs = payload["configurations"]
    q3_midnight = float(configs["00"]["total_cost"])
    q3_all = float(configs["00+06+12+18"]["total_cost"])

    if not q2_total > q3_midnight > q3_all:
        raise ValueError("两台阶费用应满足 Q2 > Q3仅0点 > Q3四时点。")
    if abs((q2_total - q3_midnight) + (q3_midnight - q3_all) - (q2_total - q3_all)) > 1e-6:
        raise AssertionError("两台阶收益未能闭合到总收益。")
    return q2_total, q3_midnight, q3_all


def plot_two_stage_benefit() -> None:
    q2_total, q3_midnight, q3_all = load_cost_levels()
    values = np.array([q2_total, q3_midnight, q3_all]) / 1e4
    labels = ["问题二\n历史光伏预测", "问题三仅0点\n附件3预报", "问题三四时点\n日内滚动更新"]
    colors = [GRAY, SKY, GREEN]

    fig, ax = plt.subplots(figsize=(9.2, 5.2), constrained_layout=True)
    bars = ax.bar(np.arange(3), values, width=0.58, color=colors, edgecolor="white", linewidth=1.2)
    ax.set_ylabel("全年总购电费（万元）")
    ax.set_title(
        f"问题三费用改善的两台阶分解（合计节省 {(q2_total - q3_all) / 1e4:.2f} 万元）",
        pad=12,
        fontweight="bold",
    )
    ax.set_xticks(np.arange(3), labels)
    ax.set_ylim(1500, 1725)
    ax.yaxis.set_major_locator(MultipleLocator(50))
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.7, alpha=0.75)
    ax.set_axisbelow(True)

    for bar, raw_value in zip(bars, (q2_total, q3_midnight, q3_all)):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 8,
            f"{raw_value / 1e4:.2f}",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    reductions = (q2_total - q3_midnight, q3_midnight - q3_all)
    for left, reduction in enumerate(reductions):
        y = min(values[left], values[left + 1]) + 20
        ax.annotate(
            "",
            xy=(left + 0.68, y),
            xytext=(left + 0.32, y),
            arrowprops={"arrowstyle": "->", "color": RED, "lw": 1.8},
        )
        reason = "0点预报来源改善" if left == 0 else "增加6/12/18点更新"
        ax.text(
            left + 0.5,
            y + 6,
            f"{reason}\n节省 {reduction / 1e4:.2f} 万元",
            ha="center",
            va="bottom",
            color=RED,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.88, "pad": 1.5},
        )

    ax.text(
        0.985,
        0.97,
        "注：纵轴截断以突出费用差异",
        transform=ax.transAxes,
        ha="right",
        va="top",
        color="#555555",
        fontsize=8.5,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 1.0},
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(BENEFIT_FIGURE, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def load_typical_day() -> pd.DataFrame:
    required = {
        "date",
        "slot",
        "load_actual",
        "pv_available",
        "initial_contract",
        "final_contract",
        "grid_emergency",
        "charge_actual",
        "discharge_actual",
        "soc_start",
        "soc_end",
    }
    dispatch = pd.read_csv(Q3_DISPATCH, usecols=lambda column: column in required)
    missing = required - set(dispatch.columns)
    if missing:
        raise ValueError(f"Q3逐槽结果缺少字段：{sorted(missing)}")
    day = dispatch.loc[dispatch["date"] == TYPICAL_DAY].sort_values("slot").copy()
    if len(day) != 144 or day["slot"].tolist() != list(range(144)):
        raise ValueError(f"{TYPICAL_DAY} 应恰有连续的144个槽位。")
    numeric = sorted(required - {"date"})
    if not np.isfinite(day[numeric].to_numpy(dtype=float)).all():
        raise ValueError("典型日数据包含非有限值。")
    day["hour"] = (day["slot"].to_numpy(dtype=float) + 1.0) / 6.0
    day["net_load"] = day["load_actual"] - day["pv_available"]
    return day


def add_release_markers(ax: plt.Axes, show_labels: bool = False) -> None:
    for hour in (0, 6, 12, 18):
        ax.axvline(hour, color="#777777", linestyle="--", linewidth=0.8, alpha=0.75, zorder=0)
        if show_labels:
            ax.text(
                hour + (0.15 if hour == 0 else 0),
                0.97,
                f"{hour}:00发布",
                transform=ax.get_xaxis_transform(),
                ha="left" if hour == 0 else "center",
                va="top",
                color="#555555",
                fontsize=8.5,
            )
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.65, alpha=0.75)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def plot_typical_day_dispatch() -> None:
    day = load_typical_day()
    x = day["hour"].to_numpy(dtype=float)

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(11.0, 8.6),
        sharex=True,
        gridspec_kw={"height_ratios": [1.25, 0.9, 0.9]},
        constrained_layout=True,
    )
    fig.suptitle("2025年9月23日典型日滚动调度机制", fontsize=14, fontweight="bold")

    ax = axes[0]
    ax.plot(x, day["net_load"], color=BLUE, linewidth=2.0, label="实际净负荷")
    ax.step(x, day["initial_contract"], where="mid", color=GRAY, linewidth=1.35, linestyle="--", label="0点初始合同购电")
    ax.step(x, day["final_contract"], where="mid", color=GREEN, linewidth=1.65, label="最终合同购电")
    ax.bar(x, day["grid_emergency"], width=0.15, color=RED, alpha=0.75, label="紧急购电")
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_ylabel("每10分钟电量（kWh）")
    ax.legend(ncol=4, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.01))
    add_release_markers(ax, show_labels=True)

    ax = axes[1]
    ax.bar(x, day["charge_actual"], width=0.15, color=SKY, alpha=0.9, label="实际充电")
    ax.bar(x, -day["discharge_actual"], width=0.15, color=ORANGE, alpha=0.9, label="实际放电（向下）")
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_ylabel("每10分钟电量（kWh）")
    ax.set_title("储能充放电")
    ax.legend(ncol=2, frameon=False, loc="upper right")
    add_release_markers(ax)

    ax = axes[2]
    soc_x = np.concatenate(([0.0], x))
    soc = np.concatenate(([float(day.iloc[0]["soc_start"])], day["soc_end"].to_numpy(dtype=float)))
    ax.plot(soc_x, soc, color=PURPLE, linewidth=2.0, label="实际SOC")
    ax.axhline(1200, color="#999999", linestyle=":", linewidth=1.0, label="SOC上下限")
    ax.axhline(10800, color="#999999", linestyle=":", linewidth=1.0)
    ax.fill_between(soc_x, 1200, 10800, color="#EEEEEE", alpha=0.35, zorder=-2)
    ax.set_ylabel("储电量（kWh）")
    ax.set_xlabel("时刻")
    ax.set_title("储能状态")
    ax.legend(frameon=False, loc="upper right")
    add_release_markers(ax)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{int(value):02d}:00"))

    fig.savefig(TYPICAL_DAY_FIGURE, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    configure_chinese_font()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    plot_two_stage_benefit()
    plot_typical_day_dispatch()
    print(BENEFIT_FIGURE.relative_to(ROOT))
    print(TYPICAL_DAY_FIGURE.relative_to(ROOT))


if __name__ == "__main__":
    main()
