"""生成第四问两条正式因果回放的CSV中间产物。"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.data_io import load_forecast_vintages
from core.q2_replay import prior_from_attachment1
from core.q4_energy import make_q42_energy_provider, make_q43_energy_provider
from core.q4_price import load_attachment4_prices
from core.q4_replay import replay_q42, replay_q43


START = date(2025, 1, 1)
EVAL_START = date(2025, 2, 1)
END = date(2025, 12, 31)
METHOD = "same-weekday-weighted"
ACTUAL_CACHE = ROOT / "experiments/q2_actuals_cache.csv"
DEFAULT_OUTPUT = ROOT / "outputs/q4"


def _write_frame(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"{path.name}没有记录")
    pd.DataFrame(rows).to_csv(path, index=False)


def _load_actuals() -> pd.DataFrame:
    if not ACTUAL_CACHE.exists():
        raise FileNotFoundError("缺少experiments/q2_actuals_cache.csv")
    frame = pd.read_csv(
        ACTUAL_CACHE, parse_dates=["date", "valid_time", "observed_at"]
    )
    frame["date"] = frame["date"].dt.date
    if frame.date.min() != START or frame.date.max() != END:
        raise ValueError("实际负荷和光伏缓存未完整覆盖2025年")
    return frame


def _checkpoint(path: Path, **values) -> None:
    current = {}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    current.update(values)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def _completed(output: Path, branch: str) -> bool:
    required = [
        output / f"{branch}_dispatch.csv",
        output / f"{branch}_daily_summary.csv",
        output / f"{branch}_price_sources.csv",
    ]
    if branch == "q4_3":
        required.append(output / "q4_3_versions.csv")
    return all(path.exists() and path.stat().st_size > 100 for path in required)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output / "q4_generation_checkpoint.json"
    t0 = time.time()
    actuals = _load_actuals()
    prior = prior_from_attachment1(START)
    prices = load_attachment4_prices()
    vintages = load_forecast_vintages()
    q42_energy = make_q42_energy_provider(actuals, prior)
    q43_energy = make_q43_energy_provider(actuals, prior, vintages)

    def progress(branch: str):
        def update(day: date, row: dict) -> None:
            _checkpoint(
                checkpoint, active_branch=branch, last_completed_day=day.isoformat(),
                last_day_cost=float(row.get("cost_total", row.get("total_cost_actual", 0.0))),
                updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            if day.day == 1 or day == END:
                print(f"{branch} {day} 已完成", flush=True)
        return update

    if not (args.resume and _completed(args.output, "q4_2")):
        q42 = replay_q42(
            actuals, prices, q42_energy, START, END,
            evaluation_start=EVAL_START, price_method=METHOD,
            collect_records=True, progress=progress("q4_2"),
        )
        _write_frame(args.output / "q4_2_dispatch.csv", q42.pop("records"))
        _write_frame(
            args.output / "q4_2_daily_summary.csv",
            [row for row in q42.pop("daily") if row["date"] >= EVAL_START.isoformat()],
        )
        _write_frame(args.output / "q4_2_price_sources.csv", q42.pop("price_sources"))
        (args.output / "q4_2_summary.json").write_text(
            json.dumps(q42, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _checkpoint(checkpoint, q4_2_complete=True)

    if not (args.resume and _completed(args.output, "q4_3")):
        q43 = replay_q43(
            actuals, prices, q43_energy, START, END,
            evaluation_start=EVAL_START, price_method=METHOD,
            collect_records=True, progress=progress("q4_3"),
        )
        _write_frame(args.output / "q4_3_dispatch.csv", q43.pop("records"))
        versions = q43.pop("versions")
        _write_frame(args.output / "q4_3_versions.csv", versions)
        _write_frame(
            args.output / "q4_3_daily_summary.csv",
            [row for row in q43.pop("daily") if row["date"] >= EVAL_START.isoformat()],
        )
        q43_sources = [{
            "issue_time": row["issue_time"], "target_time": row["date"] + "T00:00:00",
            "source_time": row["price_source_time"],
            "source_observed_at": row["price_source_observed_at"],
            "price_forecast": row["price_forecast"], "method": row["price_method"],
            "slot": row["slot"], "version": row["version"],
        } for row in versions]
        # target_time按槽位从正式执行记录回填，避免方案A末槽的日期歧义。
        target_lookup = {
            (row["date"], int(row["slot"])): row["interval_start"]
            for row in pd.read_csv(args.output / "q4_3_dispatch.csv").to_dict("records")
        }
        for row, version in zip(q43_sources, versions):
            row["target_time"] = target_lookup[(version["date"], int(version["slot"]))]
        _write_frame(args.output / "q4_3_price_sources.csv", q43_sources)
        (args.output / "q4_3_summary.json").write_text(
            json.dumps(q43, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _checkpoint(checkpoint, q4_3_complete=True)

    q42_sources = pd.read_csv(args.output / "q4_2_price_sources.csv").assign(branch="q4_2")
    q43_sources = pd.read_csv(args.output / "q4_3_price_sources.csv").assign(branch="q4_3")
    pd.concat([q42_sources, q43_sources], ignore_index=True).to_csv(
        args.output / "q4_price_vintages.csv", index=False
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    q42_summary = json.loads((args.output / "q4_2_summary.json").read_text(encoding="utf-8"))
    q43_summary = json.loads((args.output / "q4_3_summary.json").read_text(encoding="utf-8"))
    summary = {
        "model_commit": commit,
        "price_method": METHOD,
        "evaluation_start": EVAL_START.isoformat(),
        "evaluation_end": END.isoformat(),
        "q4_2": q42_summary,
        "q4_3": q43_summary,
        "elapsed_seconds_this_run": time.time() - t0,
    }
    (args.output / "q4_replay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _checkpoint(checkpoint, all_complete=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
