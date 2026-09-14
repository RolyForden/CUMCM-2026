"""F3 问题二各月正常合同费用与紧急购电费用构成。

数据：outputs/q2/q2_daily_summary.csv，按自然月求和。
输出：paper/figures/q2_monthly_cost.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from _common import (
    FIGDIR,
    PALETTE,
    clean_spines,
    close_to,
    configure_chinese_font,
    grid,
    load_q2_daily,
    month_labels,
    np,
    save_figure,
)

Q2_NORMAL = 12190821.026133068
Q2_EMERGENCY = 4695256.643451871


def main() -> None:
    configure_chinese_font()
    df = load_q2_daily()
    df = df.assign(month=df.date.dt.month)
    normal = df.groupby("month").cost_normal.sum()
    emergency = df.groupby("month").cost_emergency.sum()
    close_to(normal.sum(), Q2_NORMAL, 1e-3)
    close_to(emergency.sum(), Q2_EMERGENCY, 1e-3)

    months = normal.index.to_numpy()
    x = np.arange(len(months))
    n = normal.to_numpy() / 1e4
    e = emergency.to_numpy() / 1e4

    fig, ax = plt.subplots(figsize=(7.4, 4.2), constrained_layout=True)
    ax.bar(x, n, width=0.66, color=PALETTE["grid"], label="正常合同购电费")
    ax.bar(x, e, width=0.66, bottom=n, color=PALETTE["emergency"], label="紧急购电费")

    for xi, ni, ei in zip(x, n, e):
        share = 100.0 * ei / (ni + ei)
        ax.text(xi, ni + ei + 6, f"{share:.0f}%", ha="center", va="bottom",
                fontsize=8, color=PALETTE["emergency"])

    ax.set_xticks(x, month_labels(months))
    ax.set_xlabel("月份")
    ax.set_ylabel("月度费用（万元）")
    ax.set_ylim(0, 230)
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.11), columnspacing=1.8)
    ax.text(0.985, 0.96, "柱顶：当月紧急购电费占比", transform=ax.transAxes,
            ha="right", va="top", fontsize=8.2, color="#555555")
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q2_monthly_cost")
    print("wrote", out["pdf"].name)
    print("闭合校验：全年 %.2f 元（正常 %.2f + 紧急 %.2f）" % (
        (normal.sum() + emergency.sum()), normal.sum(), emergency.sum()))


if __name__ == "__main__":
    main()
