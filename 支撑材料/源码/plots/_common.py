"""论文图脚本共用工具：正式产物路径、加载器与闭合校验。

只读正式产物；任何数值异常都在这里抛出，避免把错误数据带进论文图。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.figure_style import (  # noqa: E402
    PALETTE,
    clean_spines,
    configure_chinese_font,
    grid,
    save_figure,
)

FIGDIR = ROOT / "paper" / "figures"
OUT = ROOT / "outputs"

# 正式口径数值（用于断言，不作为绘图数据源）
Q1_TOTAL_COST = 35126.94858938963
Q1_TOTAL_GRID = 59482.69899811735
Q2_TOTAL_COST = 16886077.669584937
Q2_NORMAL_COST = 12190821.026133068
Q2_EMERGENCY_COST = 4695256.643451871
Q2_EMERGENCY_KWH = 1199863.4471374485
Q3_TOTAL_COST = 15805751.774900615
Q3_EMERGENCY_KWH = 809227.1359076473
Q3_SAVING = 1080325.8946843222
Q4_2_TOTAL_COST = 17743324.87892995
Q4_3_TOTAL_COST = 16606095.443703488

TOL = 1.0  # 元；正式值与显示值之间允许的分钱级舍入差


def require(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def close_to(value: float, expected: float, tol: float = TOL) -> None:
    require(abs(value - expected) <= tol, f"数值 {value:.6f} 与正式值 {expected:.6f} 不符")


def load_q1_dispatch() -> pd.DataFrame:
    df = pd.read_csv(OUT / "q1_scheme_a" / "q1_dispatch.csv")
    require(len(df) == 144, "Q1 逐槽结果应为 144 行")
    close_to(df.grid_contract.sum(), Q1_TOTAL_GRID, 1e-6)
    close_to((df.price * df.grid_contract).sum(), Q1_TOTAL_COST, 1e-6)
    return df


def load_q2_daily() -> pd.DataFrame:
    df = pd.read_csv(OUT / "q2" / "q2_daily_summary.csv", parse_dates=["date"])
    require(len(df) == 334, "Q2 正式日汇总应为 334 天")
    close_to(df.cost_total.sum(), Q2_TOTAL_COST, 1e-3)
    close_to(df.cost_normal.sum(), Q2_NORMAL_COST, 1e-3)
    close_to(df.cost_emergency.sum(), Q2_EMERGENCY_COST, 1e-3)
    close_to(df.grid_emergency_kwh.sum(), Q2_EMERGENCY_KWH, 1e-3)
    return df


def load_q3_daily() -> pd.DataFrame:
    df = pd.read_csv(OUT / "q3" / "q3_daily_summary.csv", parse_dates=["date"])
    require(len(df) == 334, "Q3 正式日汇总应为 334 天")
    close_to(df.total_cost.sum(), Q3_TOTAL_COST, 1e-3)
    close_to(df.emergency_kwh.sum(), Q3_EMERGENCY_KWH, 1e-3)
    return df


def load_q3_ablation() -> dict:
    payload = json.loads((OUT / "q3" / "q3_update_ablation.json").read_text(encoding="utf-8"))
    return payload["configurations"]


def load_q4_monthly() -> pd.DataFrame:
    df = pd.read_csv(OUT / "q4" / "q4_monthly_costs.csv")
    require(len(df) == 11, "Q4 月度费用应为 11 个月（2 月至 12 月）")
    close_to(df.q4_2_cost.sum(), Q4_2_TOTAL_COST, 1e-3)
    close_to(df.q4_3_cost.sum(), Q4_3_TOTAL_COST, 1e-3)
    return df


def month_labels(months) -> list[str]:
    return [f"{int(m)}月" for m in months]


def thousands(value: float, decimals: int = 2) -> str:
    """论文现有千位格式：12 190 821.03（空格分隔）。"""
    return f"{value:,.{decimals}f}".replace(",", " ")


def thin_line(ax, x, y, color, label=None, **kw):
    return ax.plot(x, y, color=color, linewidth=1.0, label=label, **kw)


def trend_line(ax, x, y, color, label=None, **kw):
    return ax.plot(x, y, color=color, linewidth=2.1, label=label, **kw)


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1, center=True).mean()


__all__ = [
    "PALETTE",
    "FIGDIR",
    "OUT",
    "ROOT",
    "clean_spines",
    "configure_chinese_font",
    "grid",
    "save_figure",
    "require",
    "close_to",
    "load_q1_dispatch",
    "load_q2_daily",
    "load_q3_daily",
    "load_q3_ablation",
    "load_q4_monthly",
    "month_labels",
    "thousands",
    "thin_line",
    "trend_line",
    "rolling_mean",
    "np",
    "pd",
]
