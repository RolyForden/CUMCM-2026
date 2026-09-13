"""第四问双价格回放内核的纯合成 smoke；不读取官方附件，不跑全年。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q4_replay import replay_q42, run_q43_day
from core.slot_adapter import build_day_slots


START = date(2025, 2, 1)


def synthetic_actuals(days: int = 2) -> pd.DataFrame:
    rows = []
    for offset in range(days):
        day = START + timedelta(days=offset)
        for slot in build_day_slots(day):
            rows.append({
                "date": day, "slot": slot.slot_id,
                "load_actual": 60.0 + 6.0 * (slot.slot_id >= 72),
                "pv_actual": 0.0,
            })
    return pd.DataFrame(rows)


def synthetic_actual_prices(days: int = 2) -> pd.DataFrame:
    rows = []
    for offset in range(days):
        day = START + timedelta(days=offset)
        for slot in build_day_slots(day):
            # 真实价故意与优化器看到的预测价不同。
            value = 1.7 if slot.slot_id < 72 else 0.4
            rows.append({
                "target_time": slot.interval_start,
                "observed_at": slot.interval_end,
                "price_actual": value,
            })
    return pd.DataFrame(rows)


def energy_provider(decision_time: datetime, target_times: list[datetime]) -> pd.DataFrame:
    return pd.DataFrame({
        "target_time": target_times,
        "load_forecast": [60.0 + 6.0 * (t.hour >= 12) for t in target_times],
        "pv_forecast": np.zeros(len(target_times)),
        "source_max_observed_at": [decision_time - timedelta(minutes=1)] * len(target_times),
    })


def price_provider(
    actual_prices: pd.DataFrame,
    decision_time: datetime,
    target_times: list[datetime],
    method: str,
) -> pd.DataFrame:
    # 各发布时间的预测略有变化，用来触发第三问重新优化；绝不读取actual_prices。
    if decision_time.hour == 0:
        forecast = [0.25 if t.hour < 12 else 1.25 for t in target_times]
    elif decision_time.hour in (6, 18):
        forecast = [1.40 if t < decision_time + timedelta(hours=12) else 0.20
                    for t in target_times]
    else:
        forecast = [0.20 if t < decision_time + timedelta(hours=12) else 1.40
                    for t in target_times]
    source = decision_time - timedelta(days=7)
    return pd.DataFrame({
        "issue_time": [decision_time] * len(target_times),
        "target_time": target_times,
        "source_time": [source] * len(target_times),
        "source_observed_at": [decision_time - timedelta(minutes=1)] * len(target_times),
        "price_forecast": forecast,
        "method": [method] * len(target_times),
    })


def leaking_price_provider(
    actual_prices: pd.DataFrame,
    decision_time: datetime,
    target_times: list[datetime],
    method: str,
) -> pd.DataFrame:
    frame = price_provider(actual_prices, decision_time, target_times, method)
    frame["source_observed_at"] = decision_time + timedelta(minutes=1)
    return frame


def main() -> int:
    actuals = synthetic_actuals()
    prices = synthetic_actual_prices()
    q42 = replay_q42(
        actuals, prices, energy_provider, START, START + timedelta(days=1),
        price_provider=price_provider,
    )
    q43_plan, q43_records, q43 = run_q43_day(
        START, 6000.0, actuals, prices, energy_provider,
        price_provider=price_provider,
    )

    q42_manual = sum(
        row["price_actual"] * row["grid_contract"]
        + 5.0 * row["price_actual"] * row["grid_emergency"]
        for row in q42["records"]
    )
    q43_manual = sum(
        ledger.initial_contract_cost + ledger.adjustment_cashflow + ledger.emergency_cost
        for ledger in q43["ledgers"]
    )
    leak_rejected = False
    try:
        replay_q42(
            actuals.iloc[:144], prices, energy_provider, START, START,
            price_provider=leaking_price_provider,
        )
    except ValueError as exc:
        leak_rejected = "之后" in str(exc)

    r42 = q42["records"]
    checks = {
        "Q4-2双价格确实不同": any(
            abs(r["price_forecast"] - r["price_actual"]) > 1e-6 for r in r42
        ),
        "Q4-2按真实价结算": abs(q42["cost_total"] - q42_manual) < 1e-6,
        "Q4-2两天各144槽": len(r42) == 288,
        "Q4-2午夜桥接时间连续": r42[143]["interval_end"] == r42[144]["interval_start"],
        "Q4-2午夜桥接库存连续": abs(r42[143]["soc_end"] - r42[144]["soc_start"]) < 1e-6,
        "Q4-2所有价格来源因果": all(
            pd.Timestamp(r["price_source_observed_at"]) <= pd.Timestamp(r["decision_time"])
            for r in r42
        ),
        "Q4-3完整144槽": len(q43_records) == 144,
        "Q4-3按真实价版本账本结算": abs(q43["total_cost_actual"] - q43_manual) < 1e-6,
        "Q4-3合成更新产生真实调整": any(
            abs(rows[-1].quantity - rows[0].quantity) > 1e-6
            for rows in q43_plan.versions.values()
        ),
        "Q4-3已执行槽不被改写": len(q43_plan.versions[34]) == 1,
        "Q4-3六点后的首槽仅改一次": len(q43_plan.versions[35]) == 2,
        "Q4-3十二点后的首槽共三版": len(q43_plan.versions[71]) == 3,
        "Q4-3十八点后的首槽共四版": len(q43_plan.versions[107]) == 4,
        "Q4-3优化与核算价格分离": any(
            abs(r["price_forecast"] - r["price_actual"]) > 1e-6
            for r in q43["records"]
        ),
        "未来价格来源被拒绝": leak_rejected,
    }
    payload = {
        "scope": "纯合成第四问双价格回放；两天Q4-2与单日Q4-3；未读取官方附件",
        "summary": {
            "total": len(checks), "passed": sum(checks.values()),
            "failed": len(checks) - sum(checks.values()),
        },
        "checks": checks,
        "metrics": {
            "q42_cost_total_actual": q42["cost_total"],
            "q43_cost_total_actual": q43["total_cost_actual"],
            "q43_adjustment_cashflow_actual": q43["adjustment_cashflow_actual"],
        },
    }
    out = ROOT / "experiments/q4_replay_smoke_results.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
