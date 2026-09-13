"""F9 波动电价下两条策略的逐月实际结算费用。

数据：outputs/q4/q4_monthly_costs.csv（由 q4_2/q4_3 日汇总按月聚合）。
输出：paper/figures/q4_cost_comparison.pdf / .png

全部费用均使用真实波动价格结算，不用预测价替代账单。
"""

from __future__ import annotations

import matplotlib.pyplot as plt

from _common import (
    FIGDIR,
    PALETTE,
    clean_spines,
    configure_chinese_font,
    grid,
    load_q4_monthly,
    month_labels,
    np,
    save_figure,
)


def main() -> None:
    configure_chinese_font()
    m = load_q4_monthly()
    months = m.month.to_numpy()
    x = np.arange(len(months))
    w = 0.38

    fig, ax = plt.subplots(figsize=(7.4, 4.2), constrained_layout=True)
    ax.bar(x - w / 2, m.q4_2_cost / 1e4, width=w, color=PALETTE["q4_2"],
           label="第二问式：每日计划")
    ax.bar(x + w / 2, m.q4_3_cost / 1e4, width=w, color=PALETTE["q4_3"],
           label="第三问式：日内更新")

    saving = (m.q4_2_cost - m.q4_3_cost).to_numpy() / 1e4
    for xi, s in zip(x, saving):
        if abs(s) < 0.6:
            continue
        ax.text(xi, max(m.q4_2_cost.iloc[xi], m.q4_3_cost.iloc[xi]) / 1e4 + 4,
                f"−{abs(s):.1f}", ha="center", va="bottom", fontsize=7.6,
                color=PALETTE["saving"] if s > 0 else "#8B0000")

    ax.set_xticks(x, month_labels(months))
    ax.set_xlabel("月份")
    ax.set_ylabel("月度实际结算费用（万元）")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.5, 1.11), columnspacing=1.6)
    ax.text(0.02, 0.96, "柱顶：第三问式相对第二问式的节省（万元）；2 月为负",
            transform=ax.transAxes, ha="left", va="top", fontsize=8.0, color="#555555")
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q4_cost_comparison")
    print("wrote", out["pdf"].name)
    print("闭合校验：第二问式 %.2f 元，第三问式 %.2f 元" % (
        m.q4_2_cost.sum(), m.q4_3_cost.sum()))


if __name__ == "__main__":
    main()
