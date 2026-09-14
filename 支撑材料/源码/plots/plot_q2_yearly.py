"""F2 问题二全年逐日费用与紧急购电变化。

数据：outputs/q2/q2_daily_summary.csv（正式评价期 2025-02-01 至 2025-12-31，334 天）。
输出：paper/figures/q2_yearly_series.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, MonthLocator

from _common import (
    FIGDIR,
    PALETTE,
    clean_spines,
    configure_chinese_font,
    grid,
    load_q2_daily,
    rolling_mean,
    save_figure,
)

WINDOW = 14


def main() -> None:
    configure_chinese_font()
    df = load_q2_daily().sort_values("date").reset_index(drop=True)
    total = df.cost_total.to_numpy(dtype=float)
    emg = df.grid_emergency_kwh.to_numpy(dtype=float)
    trend_cost = rolling_mean(df.cost_total, WINDOW).to_numpy(dtype=float)
    trend_emg = rolling_mean(df.grid_emergency_kwh, WINDOW).to_numpy(dtype=float)

    fig, axes = plt.subplots(
        2, 1, figsize=(7.4, 5.6), sharex=True,
        gridspec_kw={"hspace": 0.16}, constrained_layout=True,
    )

    # (a) 每日总购电费用
    ax = axes[0]
    ax.plot(df.date, total / 1e4, color=PALETTE["q2"], linewidth=0.8,
            alpha=0.55, label="逐日总费用")
    ax.plot(df.date, trend_cost / 1e4, color=PALETTE["grid"], linewidth=2.2,
            label=f"{WINDOW}日滚动均值")
    ax.set_ylabel("每日总购电费（万元）")
    ax.annotate("(a) 每日总购电费用", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.15), columnspacing=1.8)
    grid(ax)
    clean_spines(ax)

    # (b) 每日紧急购电量
    ax = axes[1]
    idx = int(df.grid_emergency_kwh.idxmax())
    peak_date = df.date.iloc[idx]
    peak_val = emg[idx]
    ax.plot(df.date, emg / 1e3, color=PALETTE["emergency"], linewidth=0.8,
            alpha=0.55, label="逐日紧急购电量")
    ax.plot(df.date, trend_emg / 1e3, color=PALETTE["emergency"], linewidth=2.2,
            alpha=0.95, label=f"{WINDOW}日滚动均值")
    ax.plot([peak_date], [peak_val / 1e3], marker="v", color="#8B0000", markersize=7,
            zorder=5)
    ax.annotate(
        f"最高 {peak_date.strftime('%m-%d')}\n{peak_val / 1e3:.1f} 千kWh",
        xy=(peak_date, peak_val / 1e3), xytext=(peak_date, peak_val / 1e3 + 6.5),
        ha="center", fontsize=8.5, color="#8B0000",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.2},
        arrowprops={"arrowstyle": "-", "color": "#8B0000", "lw": 0.9},
    )
    ax.set_ylabel("每日紧急购电量（千kWh）")
    ax.set_xlabel("日期（2025年）")
    ax.annotate("(b) 每日紧急购电量", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.15), columnspacing=1.8)
    grid(ax)
    clean_spines(ax)
    ax.xaxis.set_major_locator(MonthLocator())
    ax.xaxis.set_major_formatter(DateFormatter("%m月"))
    for lbl in ax.get_xticklabels():
        lbl.set_fontsize(8.5)
        lbl.set_rotation(0)

    out = save_figure(fig, FIGDIR, "q2_yearly_series")
    print("wrote", out["pdf"].name)
    print("闭合校验：总费用 %.2f 元，紧急购电量 %.2f kWh，最高日 %s %.2f kWh" % (
        df.cost_total.sum(), df.grid_emergency_kwh.sum(),
        peak_date.strftime("%Y-%m-%d"), peak_val))


if __name__ == "__main__":
    main()
