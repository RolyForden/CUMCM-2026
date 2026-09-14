"""F10 问题一参数敏感性与输入稳健性 / 主模型与替代模型验证。

数据：
  outputs/q1_validation/q1_sensitivity.csv
  outputs/q1_validation/q1_robustness.csv
  outputs/q1_validation/q1_alternative_comparison.csv
输出：
  paper/figures/q1_sensitivity_robustness.pdf / .png
  paper/figures/q1_alternative_validation.pdf / .png
"""

from __future__ import annotations

import matplotlib.pyplot as plt

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

VAL = OUT / "q1_validation"


def plot_sensitivity_robustness() -> None:
    sens = pd.read_csv(VAL / "q1_sensitivity.csv", encoding="utf-8-sig")
    rob = pd.read_csv(VAL / "q1_robustness.csv", encoding="utf-8-sig")

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 4.2), constrained_layout=True)

    ax = axes[0]
    data = sens[(sens.scenario != "base")
                & (sens.cost_change_vs_base_pct.abs() > 1e-6)].copy()
    data = data.sort_values("cost_change_vs_base_pct")
    colors = [PALETTE["loss"] if v > 0 else PALETTE["saving"]
              for v in data.cost_change_vs_base_pct]
    ypos = np.arange(len(data))
    ax.barh(ypos, data.cost_change_vs_base_pct, color=colors, alpha=0.9, height=0.62)
    ax.axvline(0, color="#333333", linewidth=0.9)
    ax.set_yticks(ypos, data.scenario, fontsize=8.2)
    ax.set_xlabel("费用相对基准变化（%）")
    for yi, v in zip(ypos, data.cost_change_vs_base_pct):
        ax.text(v + (0.06 if v >= 0 else -0.06), yi, f"{v:+.2f}",
                ha="left" if v >= 0 else "right", va="center", fontsize=7.6)
    ax.set_xlim(-4.6, 4.6)
    ax.annotate("(a) 参数敏感性", xy=(0.02, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    grid(ax, axis="x")
    clean_spines(ax)

    ax = axes[1]
    levels = sorted(rob.noise_level_pct.unique())
    groups = [rob.loc[rob.noise_level_pct == lv, "cost_yuan"].to_numpy() for lv in levels]
    bp = ax.boxplot(groups, tick_labels=[f"{lv:g}%" for lv in levels], showmeans=True,
                    patch_artist=True, widths=0.55,
                    medianprops={"color": "#B22222", "linewidth": 1.5},
                    meanprops={"marker": "D", "markerfacecolor": "white",
                               "markeredgecolor": "#333333", "markersize": 4},
                    boxprops={"linewidth": 1.0},
                    flierprops={"marker": "o", "markersize": 2.6, "alpha": 0.35,
                                "markeredgecolor": "none"})
    for patch in bp["boxes"]:
        patch.set_facecolor(PALETTE["grid"])
        patch.set_alpha(0.4)
    base = float(sens.loc[sens.scenario == "base", "cost_yuan"].iloc[0])
    ax.axhline(base, color=PALETTE["saving"], linestyle="--", linewidth=1.2,
               label=f"基准 {base:,.0f} 元".replace(",", " "))
    ax.set_xlabel("负荷与光伏相关扰动幅度")
    ax.set_ylabel("最优费用（元）")
    ax.annotate("(b) 输入稳健性", xy=(0.02, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(frameon=False, loc="lower left", fontsize=8.2)
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q1_sensitivity_robustness")
    print("wrote", out["pdf"].name)


def plot_alternative() -> None:
    alt = pd.read_csv(VAL / "q1_alternative_comparison.csv", encoding="utf-8-sig")
    main_grid = alt.main_grid_kwh.to_numpy(dtype=float)
    alt_grid = alt.alternative_grid_kwh.to_numpy(dtype=float)
    main_soc = np.concatenate(([6000.0], alt.main_soc_end_kwh.to_numpy(dtype=float)))
    alt_soc = np.concatenate(([6000.0], alt.alternative_soc_end_kwh.to_numpy(dtype=float)))

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 4.0), constrained_layout=True)

    ax = axes[0]
    ax.scatter(main_grid, alt_grid, s=15, alpha=0.65, color=PALETTE["grid"],
               edgecolors="none")
    bound = float(max(main_grid.max(), alt_grid.max())) * 1.05
    ax.plot([0, bound], [0, bound], color="#333333", linestyle="--", linewidth=1.1,
            label="y = x")
    ax.set_xlabel("主 LP 购电量（kWh）")
    ax.set_ylabel("显式互斥 MILP 购电量（kWh）")
    ax.set_xlim(0, bound)
    ax.set_ylim(0, bound)
    ax.annotate("(a) 逐槽购电量一致性", xy=(0.03, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.text(0.97, 0.06,
            "同价时段存在多重最优，\n个别槽购电量可不同，费用/总量一致。",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.8,
            color="#555555",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 1.2})
    ax.legend(frameon=False, loc="lower right", fontsize=8.4, bbox_to_anchor=(1.0, 0.28))
    grid(ax)
    ax.set_aspect("equal", adjustable="box")
    clean_spines(ax)

    ax = axes[1]
    n = np.arange(main_soc.size)
    ax.plot(n, main_soc, color=PALETTE["soc"], linewidth=1.9, label="主 LP")
    ax.plot(n, alt_soc, color=PALETTE["discharge"], linewidth=1.5, linestyle="--",
            alpha=0.85, label="显式互斥 MILP")
    ax.axhline(1200, color="#999999", linestyle=":", linewidth=0.9)
    ax.axhline(10800, color="#999999", linestyle=":", linewidth=0.9,
               label="SOC 上下限")
    ax.set_xlabel("槽位索引")
    ax.set_ylabel("储电量（kWh）")
    ax.set_ylim(0, 12000)
    ax.annotate("(b) 储电量轨迹", xy=(0.03, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(frameon=False, loc="upper right", fontsize=8.4)
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q1_alternative_validation")
    print("wrote", out["pdf"].name)
    max_soc_gap = float(np.max(np.abs(main_soc - alt_soc)))
    print("闭合校验：两条 SOC 轨迹最大差 %.3e kWh" % max_soc_gap)


def main() -> None:
    configure_chinese_font()
    plot_sensitivity_robustness()
    plot_alternative()


if __name__ == "__main__":
    main()
