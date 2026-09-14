"""论文图共用的中文字体与字号配置。

所有论文图脚本调用 configure_chinese_font()，保证六张图的字体、
单位与打印字号一致，且不依赖用户个人路径。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager

CANDIDATES = (
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
)


def configure_chinese_font() -> None:
    """选择系统已安装的中文字体，统一图内字号与负号显示。"""
    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in CANDIDATES:
        if name in installed:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    else:
        raise RuntimeError("未找到可用中文字体，无法生成无乱码的论文图。")
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "font.size": 10.5,
            "axes.titlesize": 12,
            "axes.labelsize": 10.5,
            "legend.fontsize": 9,
            "xtick.labelsize": 9.5,
            "ytick.labelsize": 9.5,
            "figure.dpi": 150,
            "savefig.dpi": 320,
            "axes.grid": False,
            "axes.edgecolor": "#333333",
            "axes.linewidth": 0.9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


# ---------------------------------------------------------------------------
# 全文统一配色：同一物理量在四问中使用同一视觉语义。
# 颜色不单独承载信息，始终与线型/填充/正负方向配合使用。
# ---------------------------------------------------------------------------
PALETTE = {
    "load": "#333333",          # 负荷：深灰/黑
    "pv": "#009E73",            # 光伏：绿色系
    "grid": "#0072B2",          # 正常购电/合同电：蓝色系
    "emergency": "#D55E00",     # 紧急购电：橙红色系
    "soc": "#00838F",           # SOC：青色
    "price": "#7B6AA0",         # 电价：紫灰色
    "charge": "#4C72B0",        # 充电
    "discharge": "#DD8452",     # 放电
    "q2": "#666666",            # 问题二基准：中性灰
    "q3": "#009E73",            # 问题三：绿
    "q4_2": "#0072B2",          # 问题四第二问式
    "q4_3": "#009E73",          # 问题四第三问式
    "neutral": "#9AA0A6",
    "saving": "#009E73",
    "loss": "#D55E00",
    "band": "#E8E8E8",
}

GRID_LIGHT = "#DDDDDD"
RELEASE_LINE = "#777777"


def grid(ax, axis: str = "y") -> None:
    """浅色主要网格，置于数据之下。"""
    ax.grid(axis=axis, color=GRID_LIGHT, linewidth=0.65, alpha=0.8)
    ax.set_axisbelow(True)


def clean_spines(ax, keep=("left", "bottom")) -> None:
    for name, spine in ax.spines.items():
        spine.set_visible(name in keep)


def save_figure(fig, outdir, stem: str, *, dpi: int = 320) -> dict:
    """同时导出矢量 PDF 与高分辨率 PNG，返回两个路径。"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    pdf = outdir / f"{stem}.pdf"
    png = outdir / f"{stem}.png"
    fig.savefig(pdf, bbox_inches="tight", facecolor="white")
    fig.savefig(png, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {"pdf": pdf, "png": png}
