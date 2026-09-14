"""F7 2025 年 9 月 23 日问题三滚动调度机制。

数据：outputs/q3/q3_dispatch.csv 中 date == 2025-09-23 的逐槽正式记录。
输出：paper/figures/q3_typical_day_dispatch_20250923.pdf / .png

三面板：(a) 负荷/光伏/合同购电/紧急购电与发布时点；
(b) 储能充放电（充电为正、放电为负）；(c) SOC 与上下限。
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

DAY = "2025-09-23"
RELEASES = (6, 12, 18)
SOC_MIN, SOC_MAX = 1200.0, 10800.0


def load_day() -> pd.DataFrame:
    usecols = [
        "date", "slot", "soc_start", "load_actual", "pv_available",
        "initial_contract", "final_contract", "grid_emergency",
        "charge_actual", "discharge_actual", "soc_end",
    ]
    cols = pd.read_csv(OUT / "q3" / "q3_dispatch.csv", nrows=0).columns
    usecols = [c for c in usecols if c in cols]
    df = pd.read_csv(OUT / "q3" / "q3_dispatch.csv", usecols=usecols)
    day = df[df.date == DAY].sort_values("slot").reset_index(drop=True)
    if len(day) != 144 or day.slot.tolist() != list(range(144)):
        raise AssertionError(f"{DAY} 应恰有连续 144 槽")
    day["hour"] = (day.slot.to_numpy(dtype=float) + 1.0) / 6.0
    return day


def hour_fmt(value, _):
    return f"{int(value):02d}:00"


def add_releases(ax, label_text: bool) -> None:
    for h in RELEASES:
        ax.axvline(h, color="#999999", linestyle="--", linewidth=0.8,
                   alpha=0.8, zorder=0)
    if label_text:
        for h in RELEASES:
            ax.text(h, 0.02, f"{h}:00", transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=7.6, color="#555555",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.8, "pad": 0.8})


def main() -> None:
    configure_chinese_font()
    day = load_day()
    x = day.hour.to_numpy(dtype=float)

    fig, axes = plt.subplots(
        3, 1, figsize=(7.4, 7.6), sharex=True,
        gridspec_kw={"height_ratios": [1.3, 0.85, 0.85], "hspace": 0.16},
        constrained_layout=True,
    )

    # (a) 负荷、光伏、合同购电、紧急购电
    ax = axes[0]
    ax.fill_between(x, 0, day.pv_available, step="mid", color=PALETTE["pv"],
                    alpha=0.20, linewidth=0)
    ax.plot(x, day.pv_available, color=PALETTE["pv"], linewidth=1.4, label="光伏可用")
    ax.plot(x, day.load_actual, color=PALETTE["load"], linewidth=1.8, label="实际负荷")
    ax.step(x, day.initial_contract, where="mid", color="#AAAAAA", linewidth=1.2,
            linestyle="--", label="0:00 初始合同")
    ax.step(x, day.final_contract, where="mid", color=PALETTE["grid"], linewidth=1.8,
            label="最终合同购电")
    ax.bar(x, day.grid_emergency, width=0.15, color=PALETTE["emergency"], alpha=0.9,
           label="紧急购电")
    ax.axhline(0, color="#333333", linewidth=0.7, zorder=0)
    ax.set_ylabel("电量（kWh/10min）")
    ax.annotate("(a) 电网侧与负荷调度", xy=(0.012, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=3, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.20), columnspacing=1.2, handlelength=1.4)
    grid(ax)
    clean_spines(ax)
    add_releases(ax, label_text=True)

    # (b) 储能充放电（正=充电，负=放电）
    ax = axes[1]
    ax.bar(x, day.charge_actual, width=0.15, color=PALETTE["charge"], alpha=0.92,
           label="充电")
    ax.bar(x, -day.discharge_actual, width=0.15, color=PALETTE["discharge"], alpha=0.92,
           label="放电")
    ax.axhline(0, color="#333333", linewidth=0.7)
    ax.set_ylabel("充放电量（kWh/10min）")
    ax.annotate("(b) 储能动作", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.16), columnspacing=1.6)
    grid(ax)
    clean_spines(ax)
    add_releases(ax, label_text=False)

    # (c) SOC
    ax = axes[2]
    soc_x = np.concatenate(([0.0], x))
    soc = np.concatenate(([day.soc_start.iloc[0]], day.soc_end.to_numpy(float)))
    ax.fill_between(soc_x, SOC_MIN, SOC_MAX, color=PALETTE["band"], alpha=0.5, zorder=-2)
    ax.plot(soc_x, soc, color=PALETTE["soc"], linewidth=2.0, label="实际 SOC")
    ax.axhline(SOC_MAX, color="#999999", linestyle=":", linewidth=1.0, label="SOC 上下限")
    ax.axhline(SOC_MIN, color="#999999", linestyle=":", linewidth=1.0)
    ax.set_ylim(0, 12000)
    ax.yaxis.set_major_locator(MultipleLocator(3000))
    ax.set_ylabel("储电量（kWh）")
    ax.set_xlabel("时刻")
    ax.annotate("(c) 储能状态 SOC", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.16), columnspacing=1.6)
    grid(ax)
    clean_spines(ax)
    add_releases(ax, label_text=False)
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.xaxis.set_major_formatter(FuncFormatter(hour_fmt))

    out = save_figure(fig, FIGDIR, "q3_typical_day_dispatch_20250923")
    print("wrote", out["pdf"].name)
    print("闭合校验：9/23 最终合同 %.2f kWh，紧急购电 %.2f kWh，SOC [%.1f, %.1f]" % (
        day.final_contract.sum(), day.grid_emergency.sum(), float(soc.min()), float(soc.max())))


if __name__ == "__main__":
    main()
