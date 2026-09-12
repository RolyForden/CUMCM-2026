"""用一月顺序回放比较第二问历史预测候选，不运行调度模型。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import data_io
from core.q2_forecast import forecast_lag_day, forecast_same_weekday, validate_forecast_causality


def load_january() -> pd.DataFrame:
    frames = []
    day = date(2025, 1, 1)
    while day <= date(2025, 1, 31):
        load = data_io.attachment2_load(day).rename(columns={"value": "load_actual"})
        pv = data_io.attachment2_pv(day).rename(columns={"value": "pv_actual"})
        frame = load[["date", "slot", "valid_time", "observed_at", "load_actual"]]
        frame = frame.merge(
            pv[["date", "slot", "pv_actual"]], on=["date", "slot"], validate="one_to_one"
        )
        frames.append(frame)
        day += timedelta(days=1)
    out = pd.concat(frames, ignore_index=True)
    if out["valid_time"].duplicated().any():
        raise ValueError("一月实际数据 valid_time 重复")
    return out


def metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    return {
        "mae_kw": float(np.mean(np.abs(error))),
        "rmse_kw": float(np.sqrt(np.mean(error ** 2))),
        "bias_kw": float(np.mean(error)),
    }


def main() -> int:
    actuals = load_january()
    methods = {
        "D-7": lambda history, day, decision: forecast_lag_day(history, day, decision, 7),
        "same-weekday-4-decay-0.8": lambda history, day, decision: forecast_same_weekday(
            history, day, decision, weeks=4, decay=0.8
        ),
    }
    buckets = {
        method: {"load_pred": [], "load_actual": [], "pv_pred": [], "pv_actual": []}
        for method in methods
    }
    evaluated_days = []
    day = date(2025, 1, 15)
    while day <= date(2025, 1, 30):
        decision = datetime.combine(day, datetime.min.time())
        history = actuals[actuals["observed_at"] <= decision].copy()
        truth = actuals[actuals["date"] == day].sort_values("slot")
        if len(truth) != 144:
            raise ValueError(f"{day} 真值不是144槽")
        for method, build in methods.items():
            forecast = build(history, day, decision)
            validate_forecast_causality(forecast)
            buckets[method]["load_pred"].extend(forecast.load_forecast.tolist())
            buckets[method]["load_actual"].extend(truth.load_actual.tolist())
            buckets[method]["pv_pred"].extend(forecast.pv_forecast.tolist())
            buckets[method]["pv_actual"].extend(truth.pv_actual.tolist())
        evaluated_days.append(day.isoformat())
        day += timedelta(days=1)

    results = {}
    for method, values in buckets.items():
        results[method] = {
            "load": metrics(np.array(values["load_pred"]), np.array(values["load_actual"])),
            "pv": metrics(np.array(values["pv_pred"]), np.array(values["pv_actual"])),
        }
    payload = {
        "scope": "causal forecast-only evaluation; no dispatch and no annual run",
        "evaluated_days": evaluated_days,
        "observations_per_method": len(evaluated_days) * 144,
        "results": results,
    }
    output = ROOT / "experiments" / "q2_forecast_candidate_evaluation.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

