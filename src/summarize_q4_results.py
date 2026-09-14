"""从已通过独立核验的第四问产物生成论文数字和图。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from core.figure_style import configure_chinese_font  # noqa: E402

OUT = ROOT / "outputs/q4"
FIG = ROOT / "paper/figures/q4_cost_comparison.png"


def main() -> int:
    validation = json.loads((OUT / "q4_validation.json").read_text(encoding="utf-8"))
    if validation["summary"]["failed"]:
        raise AssertionError("第四问独立核验未全过，拒绝生成论文数字")
    q42 = pd.read_csv(OUT / "q4_2_dispatch.csv")
    q43 = pd.read_csv(OUT / "q4_3_dispatch.csv")
    d42 = pd.read_csv(OUT / "q4_2_daily_summary.csv", parse_dates=["date"])
    d43 = pd.read_csv(OUT / "q4_3_daily_summary.csv", parse_dates=["date"])
    versions = pd.read_csv(OUT / "q4_3_versions.csv")
    oracle = json.loads((OUT / "q4_oracle_benchmark.json").read_text(encoding="utf-8"))

    def version_deltas(group: pd.DataFrame) -> tuple[float, float]:
        values = group.sort_values("version").quantity.to_numpy(float)
        delta = np.diff(values)
        return float(np.maximum(delta, 0).sum()), float(np.maximum(-delta, 0).sum())

    deltas = [version_deltas(group) for _, group in versions.groupby(["date", "slot"])]
    up_qty = float(sum(row[0] for row in deltas))
    down_qty = float(sum(row[1] for row in deltas))
    total42 = float(d42.cost_total.sum())
    total43 = float(d43.total_cost_actual.sum())
    saving = total42 - total43
    result = {
        "evaluation_days": 334,
        "price_method": "same-weekday-weighted",
        "q4_2": {
            "cost_normal": float(d42.cost_normal.sum()),
            "cost_emergency": float(d42.cost_emergency.sum()),
            "cost_total": total42,
            "emergency_kwh": float(q42.grid_emergency.sum()),
            "grid_unused_kwh": float(q42.grid_unused.sum()),
            "price_forecast_mae": float((q42.price_forecast - q42.price_actual).abs().mean()),
            "price_forecast_rmse": float(np.sqrt(np.mean((q42.price_forecast - q42.price_actual) ** 2))),
        },
        "q4_3": {
            "initial_contract_cost": float(d43.initial_contract_cost_actual.sum()),
            "adjustment_cashflow": float(d43.adjustment_cashflow_actual.sum()),
            "emergency_cost": float(d43.emergency_cost_actual.sum()),
            "cost_total": total43,
            "adjustment_up_kwh": up_qty,
            "adjustment_down_kwh": down_qty,
            "emergency_kwh": float(q43.grid_emergency.sum()),
            "grid_unused_kwh": float(q43.grid_unused.sum()),
            "price_forecast_mae_final_vintage": float((q43.price_forecast - q43.price_actual).abs().mean()),
        },
        "q4_3_vs_q4_2": {
            "saving": saving,
            "saving_percent": 100.0 * saving / total42,
            "emergency_reduction_kwh": float(q42.grid_emergency.sum() - q43.grid_emergency.sum()),
            "emergency_reduction_percent": 100.0 * float(q42.grid_emergency.sum() - q43.grid_emergency.sum()) / float(q42.grid_emergency.sum()),
        },
        "oracle": oracle,
        "independent_validation": validation["summary"],
    }
    (OUT / "q4_paper_tables.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    m42 = d42.assign(month=d42.date.dt.month).groupby("month").cost_total.sum()
    m43 = d43.assign(month=d43.date.dt.month).groupby("month").total_cost_actual.sum()
    monthly = pd.DataFrame({"q4_2_cost": m42, "q4_3_cost": m43})
    monthly["saving"] = monthly.q4_2_cost - monthly.q4_3_cost
    monthly.to_csv(OUT / "q4_monthly_costs.csv")
    x = np.arange(len(monthly))
    width = 0.38
    configure_chinese_font()
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.bar(x - width / 2, monthly.q4_2_cost / 1e6, width, label="第二问式：每日计划")
    ax.bar(x + width / 2, monthly.q4_3_cost / 1e6, width, label="第三问式：日内更新")
    ax.set_xticks(x, [f"{month}月" for month in monthly.index])
    ax.set_xlabel("月份")
    ax.set_ylabel("实际结算费用（百万元）")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=220)
    plt.close(fig)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
