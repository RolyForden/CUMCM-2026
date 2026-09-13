"""用纯合成零流量CSV验证第四问官方模板写入与独立回读。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pandas as pd
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q4_price import load_attachment4_prices
from core.slot_adapter import build_day_slots


def main() -> int:
    prices = load_attachment4_prices().set_index("target_time")["price_actual"]
    dispatch42, dispatch43, versions, daily42, daily43, sources = [], [], [], [], [], []
    start, end = date(2025, 2, 1), date(2025, 12, 31)
    day = start
    while day <= end:
        decision = datetime.combine(day, datetime.min.time())
        for slot in build_day_slots(day):
            actual_price = float(prices.loc[pd.Timestamp(slot.interval_start)])
            base = {
                "date": day.isoformat(), "slot": slot.slot_id,
                "interval_start": slot.interval_start.isoformat(),
                "interval_end": slot.interval_end.isoformat(),
                "decision_time": decision.isoformat(), "price_forecast": actual_price,
                "price_actual": actual_price,
                "price_source_observed_at": decision.isoformat(),
                "grid_contract": 0.0, "grid_delivered": 0.0, "grid_unused": 0.0,
                "grid_emergency": 0.0, "load_actual": 0.0, "pv_available": 0.0,
                "pv_used": 0.0, "pv_curtail": 0.0, "charge_planned": 0.0,
                "charge_actual": 0.0, "discharge_planned": 0.0,
                "discharge_actual": 0.0, "soc_start": 6000.0, "soc_end": 6000.0,
                "normal_cost_actual": 0.0, "emergency_cost_actual": 0.0,
            }
            dispatch42.append(base.copy())
            q43 = {**base, "initial_contract": 0.0, "final_contract": 0.0}
            dispatch43.append(q43)
            versions.append({
                "date": day.isoformat(), "slot": slot.slot_id, "version": 0,
                "issue_time": decision.isoformat(), "quantity": 0.0,
                "price_forecast": actual_price,
                "price_source_observed_at": decision.isoformat(),
            })
            sources.append({
                "issue_time": decision.isoformat(), "target_time": slot.interval_start.isoformat(),
                "source_time": (decision - timedelta(days=7)).isoformat(),
                "source_observed_at": decision.isoformat(),
                "price_forecast": actual_price, "method": "synthetic",
            })
        daily42.append({"date": day.isoformat(), "cost_normal": 0.0,
                        "cost_emergency": 0.0, "cost_total": 0.0})
        daily43.append({"date": day.isoformat(), "initial_contract_cost_actual": 0.0,
                        "adjustment_cashflow_actual": 0.0, "emergency_cost_actual": 0.0,
                        "total_cost_actual": 0.0})
        day += timedelta(days=1)

    # 评价期首日00:00--00:10属于前一计划日槽143，必须显式提供。
    boundary42 = [{
        **dispatch42[0], "date": "2025-01-31", "slot": 143,
        "interval_start": "2025-02-01T00:00:00",
        "interval_end": "2025-02-01T00:10:00",
    }]
    boundary43 = [{
        **dispatch43[0], "date": "2025-01-31", "slot": 143,
        "interval_start": "2025-02-01T00:00:00",
        "interval_end": "2025-02-01T00:10:00",
    }]

    with tempfile.TemporaryDirectory(prefix="cumcm_q4_template_") as raw:
        out = Path(raw)
        pd.DataFrame(dispatch42).to_csv(out / "q4_2_dispatch.csv", index=False)
        pd.DataFrame(boundary42).to_csv(out / "q4_2_wallclock_boundary.csv", index=False)
        pd.DataFrame(daily42).to_csv(out / "q4_2_daily_summary.csv", index=False)
        pd.DataFrame(dispatch43).to_csv(out / "q4_3_dispatch.csv", index=False)
        pd.DataFrame(boundary43).to_csv(out / "q4_3_wallclock_boundary.csv", index=False)
        pd.DataFrame(daily43).to_csv(out / "q4_3_daily_summary.csv", index=False)
        pd.DataFrame(versions).to_csv(out / "q4_3_versions.csv", index=False)
        pd.DataFrame(sources).to_csv(out / "q4_price_vintages.csv", index=False)
        make = subprocess.run(
            [sys.executable, str(ROOT / "src/finalize_q4_results.py"), "--output-dir", str(out)],
            cwd=ROOT, capture_output=True, text=True,
        )
        check = subprocess.run(
            [sys.executable, str(ROOT / "src/validate_q4_results.py"), "--output-dir", str(out)],
            cwd=ROOT, capture_output=True, text=True,
        ) if make.returncode == 0 else None
        validation = {}
        if (out / "q4_validation.json").exists():
            validation = json.loads((out / "q4_validation.json").read_text(encoding="utf-8"))
        checks = {
            "官方模板副本生成成功": make.returncode == 0,
            "独立核验器全部通过": check is not None and check.returncode == 0,
            "两份VBA保持": json.loads((out / "q4_workbook_audit.json").read_text(encoding="utf-8"))["all_vba_preserved"] if make.returncode == 0 else False,
            "缺一槽会拒绝": False,
            "错误表头会拒绝": False,
        }
        book = out / "result4-2.xlsm"
        wb = openpyxl.load_workbook(book, keep_vba=True)
        wb["计划购电量 (2)"].cell(1, 2, "错误标签")
        wb.save(book)
        wb.close()
        bad_header = subprocess.run(
            [sys.executable, str(ROOT / "src/validate_q4_results.py"), "--output-dir", str(out)],
            cwd=ROOT, capture_output=True, text=True,
        )
        checks["错误表头会拒绝"] = bad_header.returncode != 0
        broken = pd.DataFrame(dispatch42[:-1])
        broken.to_csv(out / "q4_2_dispatch.csv", index=False)
        reject = subprocess.run(
            [sys.executable, str(ROOT / "src/finalize_q4_results.py"), "--output-dir", str(out)],
            cwd=ROOT, capture_output=True, text=True,
        )
        checks["缺一槽会拒绝"] = reject.returncode != 0
        payload = {
            "scope": "纯合成零流量数据；官方模板临时副本；不修改data/raw和正式outputs",
            "summary": {"total": len(checks), "passed": sum(checks.values()),
                        "failed": len(checks) - sum(checks.values())},
            "checks": checks,
            "validator_summary": validation.get("summary", {}),
            "validator_failed_checks": validation.get("failed_checks", []),
            "generator_stderr": make.stderr[-1000:],
            "validator_stderr": "" if check is None else check.stderr[-1000:],
        }
    path = ROOT / "experiments/q4_template_smoke_results.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
