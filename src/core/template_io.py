"""官方 result1 模板的原位填写与回读。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl

from core.slot_adapter import N_SLOTS, build_day_slots

# 题面表 2 的 6 个 4 小时块标签（每块 24 槽；方案 A 下块按 interval_start
# 小时分组：块 0 = 槽 0-23（00:10-03:50），…，块 5 = 槽 120-143
# （20:10-次日00:10，含跨日槽 0:00+1-0:10+1））
CD_BLOCK_LABELS = (
    "0:00-4:00",
    "4:00-8:00",
    "8:00-12:00",
    "12:00-16:00",
    "16:00-20:00",
    "20:00-24:00",
)
CD_BLOCK_SLOTS = 24


def write_result1_plan(
    template_path: str | Path,
    output_path: str | Path,
    day: date,
    grid: list[float],
) -> None:
    """复制官方模板语义，仅填写“计划购电量”表的144个数值。"""
    if len(grid) != N_SLOTS:
        raise ValueError(f"购电计划长度 {len(grid)} != 144")
    keep_vba = str(template_path).lower().endswith(".xlsm")
    wb = openpyxl.load_workbook(template_path, keep_vba=keep_vba)
    if "计划购电量" not in wb.sheetnames:
        wb.close()
        raise ValueError("官方模板缺少计划购电量工作表")
    ws = wb["计划购电量"]
    slots = build_day_slots(day)
    for k, slot in enumerate(slots):
        label = ws.cell(row=k + 2, column=1).value
        if str(label).strip() != slot.template_interval:
            wb.close()
            raise ValueError(
                f"slot {k}: 官方模板标签 {label!r} != {slot.template_interval!r}"
            )
        ws.cell(row=k + 2, column=2, value=float(grid[k]))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    wb.close()


def read_result1_plan(path: str | Path, day: date) -> list[float]:
    """从官方结构的“计划购电量”表回读144槽。"""
    keep_vba = str(path).lower().endswith(".xlsm")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_vba=keep_vba)
    if "计划购电量" not in wb.sheetnames:
        wb.close()
        raise ValueError("结果文件缺少计划购电量工作表")
    ws = wb["计划购电量"]
    slots = build_day_slots(day)
    values = []
    for k, slot in enumerate(slots):
        label = ws.cell(row=k + 2, column=1).value
        value = ws.cell(row=k + 2, column=2).value
        if str(label).strip() != slot.template_interval:
            wb.close()
            raise ValueError(f"slot {k}: 结果标签错位")
        if value is None:
            wb.close()
            raise ValueError(f"slot {k}: 购电量为空")
        values.append(float(value))
    wb.close()
    return values


def add_result1_cd_sheet(
    output_path: str | Path,
    block_charge: list[float],
    block_discharge: list[float],
    soc_0000: float,
    soc_2400: float,
) -> None:
    """在结果工作簿中按题面表 2 布局补“充放电量”工作表（D002 P2-1 补齐缺表）。

    布局（单日）：
      时间段  充电量  放电量 | 时间段  充电量  放电量
      0:00-4:00  …  …      | 4:00-8:00 … …
      …
      0:00 储电量  E0 | 24:00 储电量  E24
    官方模板只含“计划购电量”表，本表按题面补齐，官方原有工作表保持原样。
    """
    if len(block_charge) != 6 or len(block_discharge) != 6:
        raise ValueError("充放电汇总必须恰好 6 个 4 小时块")
    keep_vba = str(output_path).lower().endswith(".xlsm")
    wb = openpyxl.load_workbook(output_path, keep_vba=keep_vba)
    if "充放电量" in wb.sheetnames:
        wb.close()
        raise ValueError("输出工作簿已存在充放电量工作表")
    ws = wb.create_sheet("充放电量")
    for col, text in enumerate(
        ["时间段", "充电量", "放电量", "时间段", "充电量", "放电量"], start=1
    ):
        ws.cell(row=1, column=col, value=text)
    for i in range(6):
        row = 2 + i // 2
        col = 1 if i % 2 == 0 else 4
        ws.cell(row=row, column=col, value=CD_BLOCK_LABELS[i])
        ws.cell(row=row, column=col + 1, value=float(block_charge[i]))
        ws.cell(row=row, column=col + 2, value=float(block_discharge[i]))
    ws.cell(row=5, column=1, value="0:00 储电量")
    ws.cell(row=5, column=2, value=float(soc_0000))
    ws.cell(row=5, column=4, value="24:00 储电量")
    ws.cell(row=5, column=5, value=float(soc_2400))
    wb.save(output_path)
    wb.close()


def read_result1_cd_sheet(path: str | Path) -> dict:
    """回读“充放电量”表：6 块充放电量 + 0:00/24:00 储电量。"""
    keep_vba = str(path).lower().endswith(".xlsm")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_vba=keep_vba)
    if "充放电量" not in wb.sheetnames:
        wb.close()
        raise ValueError("结果文件缺少充放电量工作表")
    ws = wb["充放电量"]
    blocks = []
    for i in range(6):
        row = 2 + i // 2
        col = 1 if i % 2 == 0 else 4
        label = ws.cell(row=row, column=col).value
        if str(label).strip() != CD_BLOCK_LABELS[i]:
            wb.close()
            raise ValueError(f"充放电量块 {i} 标签错位: {label!r}")
        charge = ws.cell(row=row, column=col + 1).value
        discharge = ws.cell(row=row, column=col + 2).value
        if charge is None or discharge is None:
            wb.close()
            raise ValueError(f"充放电量块 {i} 数值为空")
        blocks.append((float(charge), float(discharge)))
    e0 = ws.cell(row=5, column=2).value
    e24 = ws.cell(row=5, column=5).value
    if e0 is None or e24 is None:
        wb.close()
        raise ValueError("0:00/24:00 储电量为空")
    wb.close()
    return {
        "blocks": blocks,
        "soc_0000": float(e0),
        "soc_2400": float(e24),
    }
