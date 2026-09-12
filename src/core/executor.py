"""统一执行器与计划版本账本。

TASK_C_probe_model_corrections.md §3.3/§5：
- 统一结果记录字段：grid_contract, grid_delivered, grid_unused,
  grid_emergency, pv_available, pv_used, pv_curtail, charge, discharge,
  soc_start, soc_end。
- 计划更新必须追加新版本，不能覆盖旧版本（immutable plan records）：
  target_slot, issue_time, plan_version, previous_version, quantity,
  increase_from_previous, decrease_from_previous。

当前只实现 Q1 单版本执行（D002 P0-7 按计划执行）；Q2 的
grid_unused 与 Q3 多次结算公式待人类确认，代码里只留接口与候选注释，
不得作为已冻结事实。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from core.lp_kernel import DT, ETA_C, ETA_D, SOC_MAX, SOC_MIN


@dataclass(frozen=True)
class PlanRecord:
    """一个时段的购电计划量（单条不可变记录）。"""

    target_slot: int
    target_date: str          # ISO 日期，属于该槽位的自然日
    issue_time: datetime      # 计划制定时刻（decision_time）
    plan_version: int         # 0 = 0:00 计划；Q3: 1=6:00, 2=12:00, 3=18:00
    previous_version: int | None
    quantity: float           # 计划购电量 kWh（母线侧）
    increase_from_previous: float | None = None
    decrease_from_previous: float | None = None


@dataclass
class ExecRecord:
    """单时段执行与结算明细（Q1 语义：contract = delivered，unused = 0）。"""

    slot: int
    interval_start: datetime
    interval_end: datetime
    price: float
    load: float
    pv_available: float
    pv_used: float
    pv_curtail: float
    grid_contract: float
    grid_delivered: float
    grid_unused: float
    grid_emergency: float
    charge: float
    discharge: float
    soc_start: float
    soc_end: float
    residual: float          # 能量平衡残差（应为 ~0）
    normal_cost: float       # price * grid_delivered（Q1 = price * grid_contract）
    emergency_cost: float    # 5 倍紧急购电（Q1 恒 0）


def execute_q1(
    plan: np.ndarray,
    price: np.ndarray,
    load: np.ndarray,
    pv: np.ndarray,
    charge: np.ndarray,
    discharge: np.ndarray,
    soc0: float,
    starts: list[datetime],
    ends: list[datetime],
    plan_issue_time: datetime,
) -> list[ExecRecord]:
    """Q1 执行：按 0:00 计划执行，实际值揭示后不重调（D002 P0-7 的 Q1 版）。

    计划 = 确定性输入（附件 1 预测值），实际负荷/PV 即预测值本身；
    结果记录 contract = delivered，unused = 0，emergency = 0
    （TASK_C_probe_model_corrections.md §3.2）。
    """
    n = len(plan)
    E = soc0
    recs = []
    for t in range(n):
        E_next = E + ETA_C * charge[t] - discharge[t] / ETA_D
        residual = (
            plan[t] + pv[t] + discharge[t] - load[t] - charge[t]
        )
        recs.append(
            ExecRecord(
                slot=t,
                interval_start=starts[t],
                interval_end=ends[t],
                price=price[t],
                load=load[t],
                pv_available=pv[t],
                pv_used=pv[t],
                pv_curtail=0.0,
                grid_contract=plan[t],
                grid_delivered=plan[t],
                grid_unused=0.0,
                grid_emergency=0.0,
                charge=charge[t],
                discharge=discharge[t],
                soc_start=E,
                soc_end=E_next,
                residual=residual,
                normal_cost=price[t] * plan[t],
                emergency_cost=0.0,
            )
        )
        E = E_next
    return recs


def records_to_plan_rows(plan: np.ndarray, day: str, issue_time: datetime,
                         version: int = 0) -> list[PlanRecord]:
    """Q1 计划 → 不可变计划记录（单版本）。"""
    rows = []
    prev_q = None
    for t, q in enumerate(plan):
        rows.append(
            PlanRecord(
                target_slot=t,
                target_date=day,
                issue_time=issue_time,
                plan_version=version,
                previous_version=version - 1 if version > 0 else None,
                quantity=float(q),
                increase_from_previous=None,
                decrease_from_previous=None,
            )
        )
        prev_q = q
    return rows
