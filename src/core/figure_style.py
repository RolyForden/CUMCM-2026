"""论文图共用的中文字体与字号配置。

所有论文图脚本调用 configure_chinese_font()，保证六张图的字体、
单位与打印字号一致，且不依赖用户个人路径。
"""

from __future__ import annotations

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
        }
    )
