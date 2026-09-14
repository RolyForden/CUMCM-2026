"""F8 波动电价下典型日预测价格与真实结算价格对比。

典型日选择规则（客观、可复现）：对正式评价期每个自然日计算当日真实价格
的标准差，取最接近全年中位数的一天。结果 2025-02-25。
数据：outputs/q4/q4_2_dispatch.csv（price_actual、price_forecast）。
输出：paper/figures/q4_price_forecast.pdf / .png

仅用于事后展示预测误差；正式计划优化只读取决策时点可获得的历史价格。
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator

from _common import (
    FIGDIR,
    OUT,
    PALETTE,
    clean_spines,
    configure_chinese_font,
    grid,
    np,
    pd,
    save_figure,
)

EVAL_START = "2025-02-01"
EVAL_END = "2025-12-31"


def pick_typical_day() -> tuple[str, float, float]:
    d = pd.read_csv(OUT / "q4" / "q4_2_dispatch.csv",
                    usecols=["date", "slot", "price_actual"])
    std_by_day = d.groupby("date").price_actual.std()
    median = float(std_by_day.median())
    day = (std_by_day - median).abs().idxmin()
    return str(day), median, float(std_by_day.loc[day])


def main() -> None:
    configure_chinese_font()
    day, median_std, day_std = pick_typical_day()

    d = pd.read_csv(OUT / "q4" / "q4_2_dispatch.csv",
                    usecols=["date", "slot", "price_actual", "price_forecast"])
    row = d[d.date == day].sort_values("slot").reset_index(drop=True)
    if len(row) != 144:
        raise AssertionError(f"{day} 应恰有 144 槽")
    x = (row.slot.to_numpy(dtype=float) + 1.0) / 6.0
    actual = row.price_actual.to_numpy(dtype=float)
    forecast = row.price_forecast.to_numpy(dtype=float)
    err = forecast - actual

    fig, axes = plt.subplots(
        2, 1, figsize=(7.4, 5.4), sharex=True,
        gridspec_kw={"height_ratios": [1.15, 0.85], "hspace": 0.14},
        constrained_layout=True,
    )

    # (a) 真实价 vs 0:00 因果预测价
    ax = axes[0]
    ax.plot(x, actual, color=PALETTE["load"], linewidth=1.9, label="真实结算价")
    ax.plot(x, forecast, color=PALETTE["grid"], linewidth=1.5, linestyle="--",
            label="0:00 因果预测价")
    ax.fill_between(x, actual, forecast, color=PALETTE["price"], alpha=0.12, linewidth=0)
    ax.set_ylabel("电价（元/kWh）")
    ax.yaxis.set_major_locator(MultipleLocator(0.2))
    ax.set_ylim(0, max(actual.max(), forecast.max()) * 1.15)
    ax.annotate("(a) 真实价与预测价", xy=(0.012, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.15), columnspacing=1.6)
    grid(ax)
    clean_spines(ax)

    # (b) 预测误差
    ax = axes[1]
    ax.axhline(0, color="#333333", linewidth=0.9)
    ax.bar(x, np.where(err >= 0, err, 0), width=0.155, color=PALETTE["loss"], alpha=0.85,
           label="高估（预测>真实）")
    ax.bar(x, np.where(err < 0, err, 0), width=0.155, color=PALETTE["grid"], alpha=0.85,
           label="低估（预测<真实）")
    ax.set_ylabel("预测误差（元/kWh）")
    ax.set_xlabel("时刻")
    mae = float(np.abs(err).mean())
    ax.annotate("(b) 预测误差", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.text(0.985, 0.05, f"当日 MAE = {mae:.4f} 元/kWh", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.2, color="#555555")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.16), columnspacing=1.6)
    grid(ax)
    clean_spines(ax)
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):02d}:00"))

    fig.suptitle(f"典型波动日 {day}（当日价格标准差 {day_std:.4f}，全年中位数 {median_std:.4f}）",
                 fontsize=10, y=1.04)
    out = save_figure(fig, FIGDIR, "q4_price_forecast")
    print("wrote", out["pdf"].name)
    print(f"典型日 {day}：标准差 {day_std:.4f} / 中位数 {median_std:.4f}，当日 MAE {mae:.4f} 元/kWh")


if __name__ == "__main__":
    main()
