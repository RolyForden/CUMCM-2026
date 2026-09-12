"""模板写入与回读：按 slot_id 对列写入，禁止字符串拼接。

D002 P0-1/P2-1：
- result1 计划购电量表：145 行（表头 + 144 区间）× 2 列，
  区间标签 0:10-0:20 … 0:00+1-0:10+1；
- 结果模板按槽位对列写入，写后回读逐槽验证位置一致
  （TASK §6.4 跨日和模板回读测试）。
"""

from __future__ import annotations

from datetime import date

import openpyxl

from core.slot_adapter import N_SLOTS, build_day_slots


def write_result1_plan(path: str, day: date, grid: list[float]) -> None:
    """写 result1 的“计划购电量”表（槽位对列，第一行表头）。"""
    slots = build_day_slots(day)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "计划购电量"
    ws.cell(row=1, column=1, value="时间段")
    ws.cell(row=1, column=2, value="购电量")
    for k, s in enumerate(slots):
        ws.cell(row=k + 2, column=1, value=s.template_interval)
        ws.cell(row=k + 2, column=2, value=float(grid[k]))
    wb.save(path)


def read_result1_plan(path: str, day: date) -> list[float]:
    """回读 result1 计划购电量表，返回 144 个槽位的购电量（按 slot 顺序）。"""
    slots = build_day_slots(day)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(min_row=1, max_row=145, values_only=True))
    wb.close()
    if len(rows) != 145:
        raise ValueError(f"result1 计划购电量表行数 = {len(rows)} ≠ 145")
    out = []
    for k, s in enumerate(slots):
        label = rows[k + 1][0]
        # 禁止模糊匹配：区间标签必须逐字符等于适配器给出的标签
        if str(label).strip() != s.template_interval:
            raise ValueError(
                f"slot {k}: 模板区间标签 {label!r} != 适配器 {s.template_interval!r}"
            )
        out.append(float(rows[k + 1][1]))
    return out
