"""F0 四问统一建模框架图：把 TikZ 源渲染为交付用 framework.pdf / framework.png。

来源：paper/figures/framework_tikz.tex（与论文正文 \\input 同源）。
流程：xelatex 编译 framework_standalone.tex -> framework_standalone.pdf，
      再由 pdftocairo 转 300 dpi PNG，最后统一命名为 framework.pdf / framework.png。
输出：paper/figures/framework.pdf、paper/figures/framework.png。

该图不含数值结论，只描述四问共用的物理内核与逐级增加的信息机制，
不涉及任何正式结果，可重复运行。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / "paper" / "figures"
STANDALONE = "framework_standalone.tex"
STEM = "framework"
PNG_DPI = 300


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"未找到 {name}，请确认 TeX Live 已加入 PATH。")
    return path


def compile_pdf() -> Path:
    xelatex = _tool("xelatex")
    subprocess.run(
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", STANDALONE],
        cwd=FIGDIR,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    produced = FIGDIR / f"{STEM}_standalone.pdf"
    if not produced.exists():
        raise RuntimeError(f"编译未生成 {produced.name}")
    target = FIGDIR / f"{STEM}.pdf"
    shutil.copy2(produced, target)
    return target


def export_png(pdf: Path) -> Path:
    pdftocairo = _tool("pdftocairo")
    subprocess.run(
        [pdftocairo, "-png", "-singlefile", "-r", str(PNG_DPI), pdf.name, STEM],
        cwd=FIGDIR,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    target = FIGDIR / f"{STEM}.png"
    if not target.exists():
        raise RuntimeError(f"未生成 {target.name}")
    return target


def cleanup() -> None:
    for pattern in (
        f"{STEM}_standalone.pdf",
        f"{STEM}_standalone.aux",
        f"{STEM}_standalone.log",
        "preview_fw-*.png",
    ):
        for path in FIGDIR.glob(pattern):
            path.unlink()


def main() -> int:
    pdf = compile_pdf()
    png = export_png(pdf)
    cleanup()
    for path in (pdf, png):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.1f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
