"""F4 问题三不同日内发布时点下光伏预报绝对误差分布。

样本定义（可复现、公平口径，见 figure_data_manifest.md）：
对每个正式评价日与发布时点 r ∈ {0,6,12,18}，起始槽 s_r ∈ {0,35,71,107}，
取该时点之后当天尚未执行的全部有效时段（槽 s_r…143）；用该时点可获得的
附件3预报版本按正式线性展开口径得到预报值，与实际光伏真值比较：
    absolute_error = |forecast_pv - actual_pv|   （单位 kW）

预报展开调用 core.q3_forecast.expand_issue_forecast，与回放器使用同一接口，
不做任何自建近似。真值取自正式逐槽结果 outputs/q3/q3_dispatch.csv 的 pv_available。

注意：不同发布时点的剩余窗口长度不同，本图反映各发布时点在实际滚动决策中
可获得预报的误差分布，不等价于同一 lead time 预测器优劣比较。
离群点不删除，按标准箱线图规则（1.5×IQR）绘制，α 调低。

输出：paper/figures/q3_forecast_error.pdf / .png
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import matplotlib.pyplot as plt

from _common import (
    FIGDIR,
    PALETTE,
    OUT,
    ROOT,
    clean_spines,
    configure_chinese_font,
    grid,
    np,
    pd,
    save_figure,
)

sys_path = str(ROOT / "src")
import sys  # noqa: E402

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from core import data_io  # noqa: E402
from core.q3_forecast import expand_issue_forecast  # noqa: E402
from core.slot_adapter import build_day_slots  # noqa: E402

RELEASES = [(0, 0), (6, 35), (12, 71), (18, 107)]
EVAL_START = date(2025, 2, 1)
EVAL_END = date(2025, 12, 31)


def build_errors() -> dict[int, np.ndarray]:
    vintages = data_io.load_forecast_vintages()
    q3 = pd.read_csv(OUT / "q3" / "q3_dispatch.csv", usecols=["date", "slot", "pv_available"])
    if len(q3) != 334 * 144:
        raise AssertionError(f"Q3 逐槽结果行数 {len(q3)} != 334*144")
    q3["actual_kw"] = q3["pv_available"] * 6.0
    day_actual = {
        d: g.set_index("slot")["actual_kw"].to_dict() for d, g in q3.groupby("date")
    }

    collected: dict[int, list[float]] = {r: [] for r, _ in RELEASES}
    day = EVAL_START
    while day <= EVAL_END:
        slots = build_day_slots(day)
        actual_by_slot = day_actual[day.isoformat()]
        for release_hour, start_slot in RELEASES:
            issue = datetime.combine(day, datetime.min.time()) + timedelta(hours=release_hour)
            targets = [s.interval_start for s in slots[start_slot:]]
            expanded = expand_issue_forecast(vintages, issue, targets, method="linear")
            forecast = expanded.pv_forecast.to_numpy(dtype=float)
            actual = np.array(
                [actual_by_slot[s.slot_id] for s in slots[start_slot:]], dtype=float
            )
            collected[release_hour].append(np.abs(forecast - actual))
        day += timedelta(days=1)
    return {r: np.concatenate(v) for r, v in collected.items()}


def main() -> None:
    configure_chinese_font()
    errors = build_errors()

    order = [0, 6, 12, 18]
    data = [errors[h] for h in order]

    stats = []
    for h, arr in zip(order, data):
        day_frac = float(np.mean(arr > 0))  # 非零误差占比，反映窗口内白天时段比例
        stats.append(
            dict(
                release=f"{h}:00",
                samples=int(arr.size),
                mae=float(arr.mean()),
                median=float(np.median(arr)),
                q1=float(np.percentile(arr, 25)),
                q3=float(np.percentile(arr, 75)),
                zero_frac=float(np.mean(arr == 0.0)),
                nonzero_frac=day_frac,
            )
        )
    print("误差统计（单位 kW）：")
    for row in stats:
        print(
            f"  {row['release']}  样本 {row['samples']:>6d}  MAE {row['mae']:7.2f}  "
            f"中位AE {row['median']:7.2f}  IQR [{row['q1']:.2f}, {row['q3']:.2f}]  "
            f"精确零占比 {row['zero_frac']:.3f}"
        )

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 4.4), constrained_layout=True)
    colors = [PALETTE["grid"], PALETTE["pv"], PALETTE["price"], PALETTE["emergency"]]
    labels = [f"{h}:00\nn={s['samples']}" for h, s in zip(order, stats)]

    ax = axes[0]
    bp = ax.boxplot(
        data, tick_labels=labels, showfliers=True, widths=0.55, patch_artist=True,
        medianprops={"color": "#B22222", "linewidth": 1.6},
        boxprops={"linewidth": 1.0},
        whiskerprops={"linewidth": 1.0},
        capprops={"linewidth": 1.0},
        flierprops={"marker": "o", "markersize": 2.6, "markerfacecolor": "#555555",
                    "markeredgecolor": "none", "alpha": 0.25},
    )
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.42)
    ax.set_ylabel("绝对误差 |预报−实际|（kW）")
    ax.set_xlabel("日内发布时点（样本量 n=剩余窗口槽数）")
    ax.annotate("(a) 绝对误差分布", xy=(0.012, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.text(0.985, 0.60, "18:00 窗口覆盖 18:00–24:00，白天时段少，\n多数槽预报与实际均为零。",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.0, color="#555555",
            bbox={"facecolor": "white", "edgecolor": "#DDDDDD", "alpha": 0.9, "pad": 1.8})
    grid(ax)
    clean_spines(ax)

    ax = axes[1]
    x = np.arange(len(order))
    ax.bar(x - 0.19, [s["mae"] for s in stats], width=0.36, color="#8C8C8C", label="MAE")
    ax.bar(x + 0.19, [s["median"] for s in stats], width=0.36,
           color=PALETTE["pv"], alpha=0.85, label="中位绝对误差")
    for xi, s in zip(x, stats):
        ax.text(xi - 0.19, s["mae"] + 3, f"{s['mae']:.0f}", ha="center", va="bottom",
                fontsize=8)
        ax.text(xi + 0.19, s["median"] + 3, f"{s['median']:.0f}", ha="center", va="bottom",
                fontsize=8)
    ax.set_xticks(x, [f"{h}:00" for h in order])
    ax.set_xlabel("日内发布时点")
    ax.set_ylabel("误差（kW）")
    ax.set_ylim(0, max(s["mae"] for s in stats) * 1.18)
    ax.annotate("(b) MAE 与中位绝对误差", xy=(0.012, 0.95), xycoords="axes fraction",
                fontsize=10.5, fontweight="bold", va="top")
    ax.legend(ncol=2, frameon=False, loc="upper center",
              bbox_to_anchor=(0.55, 1.0))
    grid(ax)
    clean_spines(ax)

    out = save_figure(fig, FIGDIR, "q3_forecast_error")
    print("wrote", out["pdf"].name)
    print("样本量随发布时点递减（剩余窗口缩短），" "图中误差变化不等于经济收益，见 F5/F6。")


if __name__ == "__main__":
    main()
