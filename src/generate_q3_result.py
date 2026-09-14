"""生成Q3全年正式回放中间产物；模板写入在回放成功后完成。"""

from __future__ import annotations

import argparse
import csv
from datetime import date
import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.q2_replay import daily_price, load_window_actuals, prior_from_attachment1
from core.q3_replay import replay

START = date(2025, 1, 1)
EVAL_START = date(2025, 2, 1)
END = date(2025, 12, 31)
OUT = ROOT / "outputs/q3"
CACHE = ROOT / "experiments/q3_actuals_cache.csv"


def load_actuals() -> pd.DataFrame:
    if CACHE.exists():
        frame = pd.read_csv(CACHE, parse_dates=["valid_time", "observed_at", "date"])
        frame["date"] = frame.date.dt.date
        if frame.date.min() == START and frame.date.max() == END:
            return frame
    frame = load_window_actuals(START, END)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CACHE, index=False)
    return frame


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"{path.name}没有记录")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    vintages = data_io.load_forecast_vintages()
    price = daily_price()

    def progress(day: date, row: dict) -> None:
        if day.day == 1 or day == END:
            print(f"{day} total={row['total_cost']:.2f} emergency={row['emergency_kwh']:.2f} elapsed={time.time()-t0:.0f}s", flush=True)

    result = replay(
        actuals, prior, vintages, price, START, EVAL_START, END,
        update_hours=(6, 12, 18), collect_records=True, progress=progress,
    )
    if result["evaluation_days"] != 334 or result["infeasible_days"] != 0:
        raise AssertionError("Q3全年回放天数或可行性失败")
    records = result.pop("records")
    versions = result.pop("versions")
    boundary_records = result.pop("wallclock_boundary_records")
    daily = result.pop("daily")
    write_csv(output / "q3_dispatch.csv", records)
    write_csv(output / "q3_versions.csv", versions)
    write_csv(output / "q3_wallclock_boundary.csv", boundary_records)
    write_csv(output / "q3_daily_summary.csv", [r for r in daily if r["date"] >= EVAL_START.isoformat()])
    summary = {**result, "elapsed_seconds": time.time()-t0, "record_count": len(records), "version_count": len(versions)}
    (output / "q3_replay_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
