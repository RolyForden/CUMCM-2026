"""按D002与D003方案A生成并审计Q1正式结果。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import openpyxl

from core import accountant, data_io, executor, lp_kernel, template_io
from core.slot_adapter import build_day_slots


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = PROJECT_ROOT / "data/raw/official/附件5/result1.xlsm"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/q1_scheme_a"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def workbook_snapshot(path: Path) -> dict[str, Any]:
    """记录结构与非目标单元格；B2:B145是唯一允许变化的范围。"""
    wb = openpyxl.load_workbook(path, keep_vba=True, data_only=False)
    sheets = []
    non_target_cells = []
    for ws in wb.worksheets:
        sheets.append(
            {
                "title": ws.title,
                "state": ws.sheet_state,
                "max_row": ws.max_row,
                "max_column": ws.max_column,
            }
        )
        for row in ws.iter_rows():
            for cell in row:
                is_target = ws.title == "计划购电量" and cell.column == 2 and 2 <= cell.row <= 145
                if not is_target:
                    non_target_cells.append(
                        [ws.title, cell.coordinate, cell.value, cell.data_type, cell.number_format]
                    )
    # keep_vba 的 archive 包含工作簿全部 ZIP 条目；这里只比较真正与宏有关的
    # 部件。普通 sharedStrings/目录项会被 openpyxl 合法重写，不能冒充 VBA。
    archive_names = wb.vba_archive.namelist() if wb.vba_archive is not None else []
    vba_names = sorted(
        name for name in archive_names
        if "vba" in name.lower() or "macro" in name.lower()
    )
    wb.close()
    return {"sheets": sheets, "non_target_cells": non_target_cells, "vba_names": vba_names}


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()


def write_dispatch_csv(path: Path, recs: list[executor.ExecRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(recs[0]).keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in recs:
            row = asdict(record)
            row["interval_start"] = record.interval_start.isoformat()
            row["interval_end"] = record.interval_end.isoformat()
            writer.writerow(row)


def build_result(template: Path, output_dir: Path) -> dict[str, Any]:
    day = date(2025, 1, 1)
    decision_time = datetime(2025, 1, 1, 0, 0)
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = output_dir / "result1.xlsm"
    dispatch_path = output_dir / "q1_dispatch.csv"
    audit_path = output_dir / "q1_audit.json"

    source_hash_before = sha256(template)
    source_snapshot = workbook_snapshot(template)
    frame = data_io.build_q1_inputs(day, decision_time)
    inputs = lp_kernel.LpInputs(
        price=frame["price"].to_numpy(dtype=float),
        load=frame["load_forecast"].to_numpy(dtype=float) * lp_kernel.DT,
        pv_available=frame["pv_forecast"].to_numpy(dtype=float) * lp_kernel.DT,
        soc0=6000.0,
        soc_final=6000.0,
    )
    ds = lp_kernel.solve_lp(inputs, solver="highs-ds")
    ipm = lp_kernel.solve_lp(inputs, solver="highs-ipm")
    if ds.status != 0 or ipm.status != 0:
        raise RuntimeError(f"Q1求解失败：DS={ds.message}; IPM={ipm.message}")

    slots = build_day_slots(day)
    recs = executor.execute_q1(
        grid_contract=ds.grid,
        price=inputs.price,
        load=inputs.load,
        pv_available=inputs.pv_available,
        pv_used=ds.pv_used,
        pv_curtail=ds.pv_curtail,
        charge=ds.charge,
        discharge=ds.discharge,
        soc0=6000.0,
        starts=[slot.interval_start for slot in slots],
        ends=[slot.interval_end for slot in slots],
        plan_issue_time=decision_time,
    )
    audit = accountant.audit(recs)

    template_io.write_result1_plan(template, workbook_path, day, ds.grid.tolist())
    readback = np.asarray(template_io.read_result1_plan(workbook_path, day))
    output_snapshot = workbook_snapshot(workbook_path)
    source_hash_after = sha256(template)
    readback_max_abs_diff = float(np.max(np.abs(readback - ds.grid)))

    checks = {
        "dual_simplex_feasible": ds.status == 0,
        "ipm_feasible": ipm.status == 0,
        "dual_engine_cost_match": abs(ds.cost - ipm.cost) < 1e-6,
        "independent_audit_ok": audit.ok,
        "optimizer_accountant_cost_match": abs(ds.cost - audit.cost_total) < 1e-6,
        "max_energy_residual_below_1e-9": audit.max_residual < 1e-9,
        "terminal_soc_e144_is_6000": abs(recs[-1].soc_end - 6000.0) < 1e-6,
        "no_simultaneous_charge_discharge": audit.simultaneous_charge_discharge == 0,
        "template_readback_144_slots": len(readback) == 144,
        "template_readback_matches_plan": readback_max_abs_diff < 1e-9,
        "template_structure_preserved": source_snapshot["sheets"] == output_snapshot["sheets"],
        "template_non_target_cells_preserved": source_snapshot["non_target_cells"] == output_snapshot["non_target_cells"],
        "template_vba_container_preserved": source_snapshot["vba_names"] == output_snapshot["vba_names"],
        "raw_template_unchanged": source_hash_before == source_hash_after,
    }
    checks = {name: bool(passed) for name, passed in checks.items()}
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Q1正式结果验收失败：{failed}")

    write_dispatch_csv(dispatch_path, recs)
    evidence = {
        "status": "PASS",
        "scheme": "D003方案A：slot 0从00:10开始，完整执行144槽，E_144=E_0=6000 kWh",
        "model_commit": git_head(),
        "generated_at": datetime.now().astimezone().isoformat(),
        "inputs": {
            "day": day.isoformat(),
            "decision_time": decision_time.isoformat(),
            "template": str(template.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "template_sha256": source_hash_before,
        },
        "outputs": {
            "workbook": str(workbook_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "workbook_sha256": sha256(workbook_path),
            "dispatch_csv": str(dispatch_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "dispatch_csv_sha256": sha256(dispatch_path),
        },
        "solver": {
            "highs_ds_cost": ds.cost,
            "highs_ds_primary_optimum": ds.primary_optimum,
            "highs_ipm_cost": ipm.cost,
            "cost_difference": abs(ds.cost - ipm.cost),
        },
        "audit": asdict(audit) | {"ok": audit.ok},
        "summary": {
            "grid_total_kwh": float(np.sum(ds.grid)),
            "pv_used_total_kwh": float(np.sum(ds.pv_used)),
            "pv_curtail_total_kwh": float(np.sum(ds.pv_curtail)),
            "charge_total_kwh": float(np.sum(ds.charge)),
            "discharge_total_kwh": float(np.sum(ds.discharge)),
            "soc_e0_kwh": recs[0].soc_start,
            "soc_e143_kwh": recs[142].soc_end,
            "soc_e144_kwh": recs[143].soc_end,
            "readback_max_abs_diff": readback_max_abs_diff,
        },
        "template_snapshot": {
            "source_sheets": source_snapshot["sheets"],
            "output_sheets": output_snapshot["sheets"],
        },
        "checks": checks,
    }
    audit_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    evidence = build_result(args.template.resolve(), args.output_dir.resolve())
    print(json.dumps({
        "status": evidence["status"],
        "cost": evidence["audit"]["cost_total"],
        "checks_passed": sum(evidence["checks"].values()),
        "checks_total": len(evidence["checks"]),
        "workbook": evidence["outputs"]["workbook"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
