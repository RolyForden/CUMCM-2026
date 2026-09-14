"""Q3 日内预测更新频率消融；逐配置保存，避免长任务结果丢失。"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.q2_replay import daily_price, prior_from_attachment1
from core.q3_replay import replay
from generate_q3_result import load_actuals

START = date(2025, 1, 1)
EVAL_START = date(2025, 2, 1)
END = date(2025, 12, 31)
OUT = ROOT / "outputs" / "q3" / "q3_update_ablation.json"
FORMAL = ROOT / "outputs" / "q3" / "q3_replay_summary.json"
CONFIGS = ((), (6,), (6, 12))


def key(hours: tuple[int, ...]) -> str:
    return "+".join(["00", *(f"{hour:02d}" for hour in hours)])


def compact(result: dict, elapsed: float, source: str) -> dict:
    fields = (
        "update_hours",
        "evaluation_days",
        "initial_contract_cost",
        "up_cost",
        "down_credit",
        "adjustment_cashflow",
        "emergency_cost",
        "total_cost",
        "increase_kwh",
        "decrease_kwh",
        "emergency_kwh",
        "unused_kwh",
        "infeasible_days",
        "soc_min",
        "soc_max",
        "soc_end_final",
    )
    row = {field: result[field] for field in fields}
    row["elapsed_seconds"] = float(elapsed)
    row["source"] = source
    return row


def save(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    if not FORMAL.exists():
        raise FileNotFoundError("缺少正式Q3汇总，不得用消融脚本替代正式回放")
    payload = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {
        "evaluation_start": EVAL_START.isoformat(),
        "evaluation_end": END.isoformat(),
        "configurations": {},
    }
    formal = json.loads(FORMAL.read_text(encoding="utf-8"))
    payload["configurations"]["00+06+12+18"] = compact(
        formal, formal["elapsed_seconds"], "q3_replay_summary.json"
    )
    save(payload)

    actuals = load_actuals()
    prior = prior_from_attachment1(START)
    vintages = data_io.load_forecast_vintages()
    price = daily_price()
    for hours in CONFIGS:
        name = key(hours)
        if name in payload["configurations"]:
            print(f"skip {name}: checkpoint exists", flush=True)
            continue
        t0 = time.time()

        def progress(day: date, row: dict) -> None:
            if day.day == 1 or day == END:
                print(
                    f"{name} {day} total={row['total_cost']:.2f} "
                    f"emergency={row['emergency_kwh']:.2f} elapsed={time.time()-t0:.0f}s",
                    flush=True,
                )

        result = replay(
            actuals,
            prior,
            vintages,
            price,
            START,
            EVAL_START,
            END,
            update_hours=hours,
            collect_records=False,
            progress=progress,
        )
        if result["evaluation_days"] != 334 or result["infeasible_days"] != 0:
            raise AssertionError(f"{name} 消融回放天数或可行性失败")
        payload["configurations"][name] = compact(result, time.time() - t0, "ablation_replay")
        save(payload)
        print(json.dumps(payload["configurations"][name], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
