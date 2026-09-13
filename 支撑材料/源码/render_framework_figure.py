"""F0 四问统一建模框架图：由原始位图生成交付用 framework.pdf / framework.png。

来源：本图由作者提供的设计稿（位图）导入，不使用 TikZ 或任何数值数据，
不改动模型、正式结果或核算口径，可重复运行。

流程：读取原始位图 paper/figures/framework.png，
      另存为 300 dpi 的 framework.pdf（矢量容器 + 位图内容），保持与 PNG 同源。
输出：paper/figures/framework.pdf。

注：原始位图本身是图1 的唯一来源；本脚本只做 PDF 导出，不改变图像内容。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / "paper" / "figures"
STEM = "framework"
PDF_DPI = 300.0


def main() -> int:
    png = FIGDIR / f"{STEM}.png"
    if not png.exists():
        raise FileNotFoundError(f"缺少原始位图: {png}")
    image = Image.open(png).convert("RGB")
    pdf = FIGDIR / f"{STEM}.pdf"
    image.save(pdf, "PDF", resolution=PDF_DPI)
    w, h = image.size
    print(f"{pdf.relative_to(ROOT)}  {pdf.stat().st_size / 1024:.1f} KiB")
    print(f"来源位图 {w}x{h}px，按 {PDF_DPI:.0f} dpi 导出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
