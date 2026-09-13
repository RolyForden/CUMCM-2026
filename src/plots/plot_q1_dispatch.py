"""F1 问题一典型日购电—光伏—储能协同调度图。

数据：outputs/q1_scheme_a/q1_dispatch.csv（正式 144 槽结果，逐槽原始值）。
输出：paper/figures/q1_dispatch.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator

from _common import (
    PALETTE,
    FIGDIR,
    clean_spines,
    configure_chinese_font,
    grid,
    load_q1_dispatch,
    save_figure,
    np,
)

SOC_MIN = 1200.0
SOC_MAX = 10800.0
SOC_INIT = 6000.0


def hour_axis(ax) -> None:
    ax.set_xlim(0, 24)
    ax.xaxis.set_major_locator(MultipleLocator(3))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):02d}:00"))


def main() -> None:
    configure_chinese_font()
    df = load_q1_dispatch()
    x = (df.slot.to_numpy(dtype=float) + 1.0) / 6.0  # 槽结束时刻（小时）
    soc_x = np.concatenate(([0.0], x))
    soc = np.concatenate(([df.soc_start.iloc[0]], df.soc_end.to_numpy(dtype=float)))

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(7.2, 7.4),
        sharex=True,
        gridspec_kw={"height_ratios": [1.25, 0.85, 0.85], "hspace": 0.18},
        constrained_layout=True,
    )

    # (a) 供需与购电调度
    ax = axes[0]
    ax.fill_between(x, 0, df.pv_used.to_numpy(dtype=float), step="mid",
                    color=PALETTE["pv"], alpha=0.22, linewidth=0)
    ax.plot(x, df.pv_used, color=PALETTE["pv"], linewidth=1.5, label="实际消纳光伏")
    ax.plot(x, df.load, color=PALETTE["load"], linewidth=1.8, label="负荷")
    ax.step(x, df.grid_contract, where="mid", color=PALETTE["grid"],
            linewidth=1.8, label="计划购电")
    ax.axhline(0, color="#333333", linewidth=0.7, zorder=0)
    ax.set_ylabel("电量（kWh/10min）")
    ax.annotate("(a) 供需与购电调度", xy=(0.012, 0.94), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=3, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.16), columnspacing=1.4)
    grid(ax)
    clean_spines(ax)

    axp = ax.twinx()
    axp.step(x, df.price, where="mid", color=PALETTE["price"], linewidth=1.0,
             alpha=0.85, linestyle="--")
    axp.set_ylabel("电价（元/kWh）", color=PALETTE["price"])
    axp.tick_params(axis="y", colors=PALETTE["price"])
    axp.yaxis.set_major_locator(MultipleLocator(0.2))
    axp.set_ylim(0.2, 1.35)
    clean_spines(axp, keep=())
    for lbl in axp.get_yticklabels():
        lbl.set_fontsize(8.5)

    # (b) 储能充放电（正=充电，负=放电）
    ax = axes[1]
    ax.bar(x, df.charge, width=0.155, color=PALETTE["charge"], alpha=0.92, label="充电")
    ax.bar(x, -df.discharge, width=0.155, color=PALETTE["discharge"], alpha=0.92,
           label="放电")
    ax.axhline(0, color="#333333", linewidth=0.7)
    ax.set_ylabel("功率电量（kWh/10min）")
    ax.annotate("(b) 储能充放电", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.16), columnspacing=1.6)
    grid(ax)
    clean_spines(ax)

    # (c) SOC
    ax = axes[2]
    ax.fill_between(soc_x, SOC_MIN, SOC_MAX, color=PALETTE["band"], alpha=0.5, zorder=-2)
    ax.plot(soc_x, soc, color=PALETTE["soc"], linewidth=2.0, label="储电量 SOC")
    ax.axhline(SOC_MAX, color="#999999", linestyle=":", linewidth=1.0)
    ax.axhline(SOC_MIN, color="#999999", linestyle=":", linewidth=1.0, label="SOC 上下限")
    ax.axhline(SOC_INIT, color="#BBBBBB", linestyle="-.", linewidth=0.9,
               label="初始/终端 6000")
    ax.set_ylim(0, 12000)
    ax.yaxis.set_major_locator(MultipleLocator(3000))
    ax.set_ylabel("储电量（kWh）")
    ax.set_xlabel("时刻")
    ax.annotate("(c) 储能状态 SOC", xy=(0.012, 0.93), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=3, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.18), columnspacing=1.4)
    grid(ax)
    clean_spines(ax)
    hour_axis(ax)

    out = save_figure(fig, FIGDIR, "q1_dispatch")
    print("wrote", out["pdf"].relative_to(FIGDIR.parent.parent), out["png"].name)
    print("闭合校验：购电费 %.3f 元，购电量 %.3f kWh" % (
        (df.price * df.grid_contract).sum(), df.grid_contract.sum()))


if __name__ == "__main__":
    main()
