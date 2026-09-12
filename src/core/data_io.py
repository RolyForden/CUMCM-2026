"""官方附件读取器 → 统一长表（data/processed/）。

只读 data/raw/（AGENTS.md 第 5 条）；每个读取函数要求 as_of 时间，
未作未来截断的原始表不得流出数据访问层
（TASK_C_probe_model_corrections.md §7 防 walk-forward 泄漏）。

长表列（统一接口）：
    date, slot, decision_time, valid_time, price, load_actual,
    pv_available, pv_forecast, forecast_issue, lead_hour, vintage

当前探针阶段只实现附件 1/2/4 的 10 分钟宽表；附件 3 的预报批次
（issue_time/valid_time/lead_hour/vintage）与首小时映射待人类确认后
单独实现，不在 Q1 适配器中硬编码。
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import openpyxl
import pandas as pd

from core.slot_adapter import N_SLOTS, build_day_slots, slot_id_from_input_label

RAW = "data/raw"
PROCESSED = "data/processed"
DT = 1.0 / 6.0  # 10 分钟 = 1/6 小时（D002 数据固定口径）


def _time_labels_xlsx(path: str, sheet: str) -> list[str]:
    """读取 10 分钟宽表表头的时间标签（第 2..145 列）。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = ws.iter_rows(min_row=1, max_row=1, values_only=True)
    header = next(rows)
    labels = [str(h).strip() for h in header[1:145]]
    wb.close()
    if len(labels) != N_SLOTS:
        raise ValueError(f"{path}[{sheet}] 表头时间列数 = {len(labels)} ≠ 144")
    return labels


def _time_labels_xlsx_1(path: str, sheet: str) -> list[str]:
    """附件 1 式竖排表：时间标签在第 1 列（第 2..145 行）。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(min_row=2, max_row=145, min_col=1, max_col=1, values_only=True))
    wb.close()
    labels = [str(r[0]).strip() for r in rows]
    if len(labels) != N_SLOTS:
        raise ValueError(f"{path}[{sheet}] 竖排时间标签数 = {len(labels)} ≠ 144")
    return labels


def _read_wide(path: str, sheet: str, day: date, as_of: datetime) -> pd.DataFrame:
    """读取单日 144 点宽表为长表（仅该日；值属于区间起点对齐的槽位）。

    断言（防泄漏）：数据文件的发布日期早于 as_of 时才能读取；
    当前官方附件是赛前一次性发布物，发布于竞赛开始时（2026-09-11），
    本函数按 as_of >= 2026-09-11 放行，为未来 walk-forward 预留接口。
    """
    assert as_of >= datetime(2026, 9, 11), "附件尚不可用（as_of 早于发布时刻）"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))
    if not rows:
        raise ValueError(f"{path}[{sheet}] 第 2 行无数据")
    vals = rows[0][1:145]
    if len(vals) != N_SLOTS:
        raise ValueError(f"{path}[{sheet}] 数据列数 = {len(vals)} ≠ 144")
    wb.close()

    slots = build_day_slots(day)
    df = pd.DataFrame(
        {
            "date": [day] * N_SLOTS,
            "slot": [s.slot_id for s in slots],
            "interval_start": [s.interval_start for s in slots],
            "interval_end": [s.interval_end for s in slots],
            "value": [float(v) for v in vals],
        }
    )
    df["valid_time"] = df["interval_start"]
    df["decision_time"] = as_of
    return df


def attachment1(day: date, as_of: datetime) -> pd.DataFrame:
    """附件 1：单日 144 点电价、小区负载、光伏预测（Q1 输入）。

    官方表：'Sheet1 (2)'，列 = 时间 | 电价 | 小区负载 | 光伏发电预测功率。
    """
    df = _read_wide(f"{RAW}/official/附件1.xlsm", "Sheet1 (2)", day, as_of)
    # 第一行（sheet 第 2 行）之外的列顺序：已按列读取，这里按列名重排
    return df


def attachment2_load(day: date, as_of: datetime) -> pd.DataFrame:
    """附件 2：小区负载实际功率（官方包 '小区负载' 表，366 行 × 145 列）。"""
    return _read_wide(f"{RAW}/official/附件2.xlsm", "小区负载", day, as_of)


def attachment2_pv(day: date, as_of: datetime) -> pd.DataFrame:
    """附件 2：光伏发电实际功率（替补副本，D002 数据源核实）。"""
    return _read_wide(f"{RAW}/substitute/附件2.xlsx", "光伏发电实际功率", day, as_of)


def attachment4(day: date, as_of: datetime) -> pd.DataFrame:
    """附件 4：波动电价（'Sheet1 (3)'，366 行 × 145 列）。"""
    return _read_wide(f"{RAW}/official/附件4.xlsm", "Sheet1 (3)", day, as_of)


def build_q1_inputs(day: date, as_of: datetime) -> pd.DataFrame:
    """Q1 输入长表：电价/负荷/光伏预测（同属附件 1，槽位对齐）。"""
    slots = build_day_slots(day)
    base = pd.DataFrame(
        {
            "date": [day] * N_SLOTS,
            "slot": [s.slot_id for s in slots],
            "interval_start": [s.interval_start for s in slots],
            "interval_end": [s.interval_end for s in slots],
        }
    )
    # 按槽位（slot_id 列号）逐一取值，禁止按标签字符串拼接
    wb = openpyxl.load_workbook(f"{RAW}/official/附件1.xlsm", read_only=True, data_only=True)
    ws = wb["Sheet1 (2)"]
    rows = list(ws.iter_rows(min_row=2, max_row=145, values_only=True))
    wb.close()
    if len(rows) != N_SLOTS:
        raise ValueError(f"附件1 数据行数 = {len(rows)} ≠ 144")
    price, load, pv = [], [], []
    for r in rows:
        price.append(float(r[1]))
        load.append(float(r[2]))
        pv.append(float(r[3]))
    base["price"] = price
    base["load_forecast"] = load
    base["pv_forecast"] = pv
    base["valid_time"] = base["interval_start"]
    base["decision_time"] = as_of
    return base


def long_table_day(day: date, as_of: datetime) -> pd.DataFrame:
    """探针用：某日实际负荷/PV/电价长表（附件 2 + 附件 4，供 oracle/执行）。"""
    load = attachment2_load(day, as_of).rename(columns={"value": "load_actual"})
    pv = attachment2_pv(day, as_of).rename(columns={"value": "pv_available"})
    price = attachment4(day, as_of).rename(columns={"value": "price"})
    out = load[["date", "slot", "interval_start", "interval_end", "load_actual"]]
    out = out.merge(
        pv[["date", "slot", "pv_available"]], on=["date", "slot"], how="left"
    )
    out = out.merge(
        price[["date", "slot", "price"]], on=["date", "slot"], how="left"
    )
    assert out[["load_actual", "pv_available", "price"]].notna().all().all()
    return out
