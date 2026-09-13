"""F6 问题二与问题三的月度费用及累计经济收益。

(a) Q2 与最终 Q3 的逐月实际总费用（万元）对比；
(b) Q3 相对 Q2 的全年累计节省曲线，逐日累计。

数据：outputs/q2/q2_daily_summary.csv（cost_total）、
      outputs/q3/q3_daily_summary.csv（total_cost）。
输出：paper/figures/q3_monthly_cumulative.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, MonthLocator

from _common import (
    FIGDIR,
    PALETTE,
    clean_spines,
    close_to,
    configure_chinese_font,
    grid,
    load_q2_daily,
    load_q3_daily,
    month_labels,
    np,
    save_figure,
)

Q3_SAVING = 1080325.8946843222


def main() -> None:
    configure_chinese_font()
    q2 = load_q2_daily().sort_values("date").reset_index(drop=True)
    q3 = load_q3_daily().sort_values("date").reset_index(drop=True)
    merged = q2[["date", "cost_total"]].merge(
        q3[["date", "total_cost"]], on="date", validate="one_to_one"
    )
    merged = merged.assign(month=merged.date.dt.month)
    m2 = merged.groupby("month").cost_total.sum()
    m3 = merged.groupby("month").total_cost.sum()
    saving = merged.cost_total - merged.total_cost
    cumulative = saving.cumsum()
    close_to(cumulative.iloc[-1], Q3_SAVING, 1e-3)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 4.0), constrained_layout=True)
    months = m2.index.to_numpy()

    # (a) 月度费用对比
    ax = axes[0]
    x = np.arange(len(months))
    ax.plot(x, m2.to_numpy() / 1e4, marker="o", markersize=4.6, linewidth=1.7,
            color=PALETTE["q2"], label="问题二")
    ax.plot(x, m3.to_numpy() / 1e4, marker="s", markersize=4.2, linewidth=1.7,
            color=PALETTE["q3"], label="问题三")
    ax.fill_between(x, m3.to_numpy() / 1e4, m2.to_numpy() / 1e4,
                    color=PALETTE["saving"], alpha=0.12, linewidth=0)
    ax.set_xticks(x, month_labels(months))
    ax.set_xlabel("月份")
    ax.set_ylabel("月度实际总费用（万元）")
    ax.annotate("(a) 月度费用对比", xy=(0.02, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.13), columnspacing=1.8)
    grid(ax)
    clean_spines(ax)

    # (b) 累计节省
    ax = axes[1]
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.plot(merged.date, cumulative / 1e4, color=PALETTE["saving"], linewidth=2.0,
            label="累计节省")
    ax.fill_between(merged.date, 0, cumulative / 1e4, color=PALETTE["saving"],
                    alpha=0.12, linewidth=0)
    final_d = merged.date.iloc[-1]
    final_v = cumulative.iloc[-1] / 1e4
    ax.plot([final_d], [final_v], marker="D", color="#8B0000", markersize=5.5, zorder=5)
    ax.annotate(
        f"全年累计节省 {final_v:.2f} 万元",
        xy=(final_d, final_v), xytext=(final_d, final_v + 14),
        ha="right", fontsize=8.4, color="#8B0000",
        arrowprops={"arrowstyle": "-", "color": "#8B0000", "lw": 0.9},
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.2},
    )
    ax.set_ylabel("累计节省（万元）")
    ax.set_xlabel("日期（2025年）")
    ax.annotate("(b) Q3 相对 Q2 累计节省", xy=(0.02, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.xaxis.set_major_locator(MonthLocator())
    ax.xaxis.set_major_formatter(DateFormatter("%m月"))
    for lbl in ax.get_xticklabels():
        lbl.set_fontsize(8.5)
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q3_monthly_cumulative")
    print("wrote", out["pdf"].name)
    drops = int((saving < 0).sum())
    print("闭合校验：累计节省末点 %.2f 元；单日节省为负的天数 %d（曲线局部下降）"
          % (cumulative.iloc[-1], drops))


if __name__ == "__main__":
    main()
