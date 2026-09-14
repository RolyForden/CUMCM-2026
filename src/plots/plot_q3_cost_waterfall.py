"""F5 问题三相对问题二的费用改善来源分解（瀑布图）。

数据：outputs/q3/q3_update_ablation.json 各档 total_cost（正式消融结果），
基准取 outputs/q2/q2_daily_summary.csv 的全年总费用。
输出：paper/figures/q3_cost_waterfall.pdf / .png

0:00 阶段同时包含预报来源与初始计划变化，单独成阶，不与日内追加更新合并。
18:00 阶段变化极小（+2.90 元），以文本标注真实数值，不做视觉夸大。
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
    load_q3_ablation,
    np,
    save_figure,
)

EXPECT = {
    "00": 16350694.803204868,
    "00+06": 16008998.896033239,
    "00+06+12": 15805748.8763911,
    "00+06+12+18": 15805751.774900634,
}


def main() -> None:
    configure_chinese_font()
    q2_total = float(load_q2_daily().cost_total.sum())
    cfgs = load_q3_ablation()
    for key, expected in EXPECT.items():
        close_to(float(cfgs[key]["total_cost"]), expected, 1e-3)

    levels = [
        ("问题二基准", q2_total, "base"),
        ("0:00 附件3预报\n＋初始计划", float(cfgs["00"]["total_cost"]), "step"),
        ("加入 6:00\n更新", float(cfgs["00+06"]["total_cost"]), "step"),
        ("加入 12:00\n更新", float(cfgs["00+06+12"]["total_cost"]), "step"),
        ("加入 18:00\n更新", float(cfgs["00+06+12+18"]["total_cost"]), "step"),
        ("问题三最终", float(cfgs["00+06+12+18"]["total_cost"]), "total"),
    ]

    n = len(levels)
    fig, ax = plt.subplots(figsize=(7.8, 4.6), constrained_layout=True)

    # 逐阶计算浮动柱位置
    prev = q2_total
    xs = np.arange(n)
    for i, (label, value, kind) in enumerate(levels):
        if kind == "base":
            bottom, height = 0.0, value
            color = PALETTE["q2"]
        elif kind == "total":
            bottom, height = 0.0, value
            color = PALETTE["q3"]
        else:
            delta = value - prev
            bottom = value if delta < 0 else prev
            height = abs(delta)
            color = PALETTE["saving"] if delta < 0 else PALETTE["loss"]
        ax.bar(i, height / 1e4, bottom=bottom / 1e4, width=0.62, color=color,
               edgecolor="white", linewidth=0.8, zorder=3)
        if kind == "step":
            delta = value - prev
            top = max(bottom + height, prev)
            ax.text(i, top / 1e4 + 1.2,
                    f"−{abs(delta)/1e4:.2f}" if delta < 0 else f"+{abs(delta)/1e4:.4f}",
                    ha="center", va="bottom", fontsize=8.5,
                    color="#8B0000" if delta > 0 else PALETTE["saving"],
                    fontweight="bold")
        prev = value

    # 连接线
    for i in range(1, n):
        _, prev_val, prev_kind = levels[i - 1]
        _, cur_val, _ = levels[i]
        y = (prev_val if levels[i][2] != "base" else cur_val) / 1e4
        if levels[i - 1][2] != "base":
            y = prev_val / 1e4
        ax.plot([i - 1 + 0.31, i - 0.31], [y, y], color="#999999",
                linewidth=0.9, linestyle="--", zorder=2)

    ax.text(0, q2_total / 1e4 + 1.2, f"{q2_total/1e4:.2f}", ha="center", va="bottom",
            fontsize=9, fontweight="bold", color=PALETTE["q2"])
    ax.text(n - 1, levels[-1][1] / 1e4 + 1.2, f"{levels[-1][1]/1e4:.2f}", ha="center",
            va="bottom", fontsize=9, fontweight="bold", color=PALETTE["q3"])

    ax.set_xticks(xs, [lab for lab, _, _ in levels])
    ax.set_ylabel("全年总购电费（万元）")
    lo = min(v for _, v, _ in levels) / 1e4
    hi = max(v for _, v, _ in levels) / 1e4
    ax.set_ylim(lo - 12, hi + 8)
    ax.text(0.985, 0.04, "注：纵轴截断以突出费用差异；18:00 阶段真实变化仅 +2.90 元（红色）。",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.2, color="#555555")
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q3_cost_waterfall")
    print("wrote", out["pdf"].name)
    print("闭合校验：Q2 %.2f → 00 %.2f → +06 %.2f → +12 %.2f → +18 %.2f，合计节省 %.2f 元" % (
        q2_total, levels[1][1], levels[2][1], levels[3][1], levels[4][1], q2_total - levels[-1][1]))


if __name__ == "__main__":
    main()
