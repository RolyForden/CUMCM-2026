"""从主仓库同步生成提交用支撑材料、SHA-256 清单与压缩包。

只同步正式产物和源码，不包含大体积逐槽中间文件。可重复运行。
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "支撑材料"

# 论文正文实际引用的六张图
FIGURES = (
    "q1_sensitivity_robustness.png",
    "q1_alternative_validation.png",
    "q3_two_stage_benefit.png",
    "q3_cost_and_updates.png",
    "q3_typical_day_dispatch_20250923.png",
    "q4_cost_comparison.png",
)

RESULTS = {
    "outputs/q1_scheme_a/result1.xlsm": "result1.xlsm",
    "outputs/q2/result2.xlsm": "result2.xlsm",
    "outputs/q3/result3.xlsm": "result3.xlsm",
    "outputs/q4/result4-2.xlsm": "result4-2.xlsm",
    "outputs/q4/result4-3.xlsm": "result4-3.xlsm",
}


def sync_sources() -> int:
    dst = PKG / "源码"
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "core").mkdir(parents=True)
    count = 0
    for path in sorted((ROOT / "src").glob("*.py")):
        shutil.copy2(path, dst / path.name)
        count += 1
    for path in sorted((ROOT / "src" / "core").glob("*.py")):
        shutil.copy2(path, dst / "core" / path.name)
        count += 1
    return count


def sync_figures() -> int:
    dst = PKG / "论文图"
    dst.mkdir(exist_ok=True)
    for name in dst.glob("*.png"):
        name.unlink()
    for name in FIGURES:
        src = ROOT / "paper" / "figures" / name
        if not src.exists():
            raise FileNotFoundError(f"论文图缺失: {src}")
        shutil.copy2(src, dst / name)
    return len(FIGURES)


def sync_results() -> int:
    dst = PKG / "正式结果"
    dst.mkdir(exist_ok=True)
    for rel, name in RESULTS.items():
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(f"正式结果缺失: {src}")
        shutil.copy2(src, dst / name)
    return len(RESULTS)


def write_sums() -> int:
    lines = []
    for path in sorted(PKG.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        rel = path.relative_to(PKG).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    (PKG / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def make_zip() -> Path:
    target = ROOT / "支撑材料.zip"
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PKG.rglob("*")):
            if path.is_file():
                zf.write(path, Path("支撑材料") / path.relative_to(PKG))
    return target


def main() -> int:
    print("sources:", sync_sources())
    print("figures:", sync_figures())
    print("results:", sync_results())
    print("sha256 entries:", write_sums())
    target = make_zip()
    print("zip:", target, round(target.stat().st_size / 1024 / 1024, 2), "MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
