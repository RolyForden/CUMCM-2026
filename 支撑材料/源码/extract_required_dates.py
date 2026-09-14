"""从正式逐槽产物抽取题面指定四日的可复核摘要。

不调用优化器；四小时块和0/24时刻SOC均按真实 interval_start/end 聚合。
"""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.wallclock_output import aggregate_wallclock_days


DAYS = ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"]
OUT = ROOT / "outputs" / "paper_validation" / "required_dates_summary.csv"


def _rows(question: str) -> list[dict]:
    folder = ROOT / "outputs" / question.lower()
    dispatch = pd.read_csv(folder / f"{question.lower()}_dispatch.csv")
    daily = pd.read_csv(folder / f"{question.lower()}_daily_summary.csv").set_index("date")
    records = dispatch.to_dict("records")
    if question == "Q2":
        summaries = aggregate_wallclock_days(
            records,
            DAYS,
            charge_field="charge",
            discharge_field="discharge",
        )
    else:
        summaries = aggregate_wallclock_days(records, DAYS)

    result = []
    for summary in summaries:
        day = summary.day.isoformat()
        d = daily.loc[day]
        row = {
            "question": question,
            "date": day,
            "total_cost_yuan": float(d["cost_total"] if question == "Q2" else d["total_cost"]),
            "emergency_kwh": float(
                d["grid_emergency_kwh"] if question == "Q2" else d["emergency_kwh"]
            ),
            "soc_0000_kwh": summary.soc_0000,
            "soc_2400_kwh": summary.soc_2400,
        }
        for block in summary.blocks:
            key = block.label.replace(":00", "").replace("-", "_")
            row[f"charge_{key}_kwh"] = block.charge
            row[f"discharge_{key}_kwh"] = block.discharge
        result.append(row)
    return result


def main() -> None:
    rows = [*_rows("Q2"), *_rows("Q3")]
    frame = pd.DataFrame(rows)
    if len(frame) != 8 or frame.isna().any().any():
        raise AssertionError("指定日期摘要不完整")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT, index=False, float_format="%.6f")
    print(OUT)


if __name__ == "__main__":
    main()
