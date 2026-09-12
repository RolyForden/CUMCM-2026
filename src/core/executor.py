"""统一执行器与计划版本账本。

TASK_C_probe_model_corrections.md §3.3/§5：
- 统一结果记录字段：grid_contract, grid_delivered, grid_unused,
  grid_emergency, pv_available, pv_used, pv_curtail, charge, discharge,
  soc_start, soc_end。
- 计划更新必须追加新版本，不能覆盖旧版本（immutable plan records）：
  target_slot, issue_time, plan_version, previous_version, quantity,
  increase_from_previous, decrease_from_previous。

Q1 单版本执行保持原语义。Q2 按 D007 落实合同余电、紧急购电与计划
放电削减；Q3 多次结算由独立版本账本处理。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from core.params import BatteryParams, DEFAULT_BATTERY


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
    normal_cost: float       # Q1/Q2: price * grid_contract
    emergency_cost: float    # 5 倍紧急购电（Q1 恒 0）
    discharge_planned: float | None = None
    discharge_shortfall: float = 0.0
    discharge_clipped: bool = False
    charge_planned: float | None = None
    charge_shortfall: float = 0.0
    charge_clipped: bool = False


def execute_q1(
    grid_contract: np.ndarray,
    price: np.ndarray,
    load: np.ndarray,
    pv_available: np.ndarray,
    pv_used: np.ndarray,
    pv_curtail: np.ndarray,
    charge: np.ndarray,
    discharge: np.ndarray,
    soc0: float,
    starts: list[datetime],
    ends: list[datetime],
    plan_issue_time: datetime,
    params: BatteryParams = DEFAULT_BATTERY,
) -> list[ExecRecord]:
    """Q1 执行：按 0:00 计划执行，实际值揭示后不重调（D002 P0-7 的 Q1 版）。

    计划 = 确定性输入（附件 1 预测值），实际负荷/PV 即预测值本身；
    结果记录 contract = delivered，unused = 0，emergency = 0
    （TASK_C_probe_model_corrections.md §3.2）。
    """
    n = len(grid_contract)
    arrays = {
        "price": price,
        "load": load,
        "pv_available": pv_available,
        "pv_used": pv_used,
        "pv_curtail": pv_curtail,
        "charge": charge,
        "discharge": discharge,
    }
    for name, values in arrays.items():
        if len(values) != n:
            raise ValueError(f"{name} 长度 {len(values)} != 计划长度 {n}")
    if len(starts) != n or len(ends) != n:
        raise ValueError("槽位起止时间长度与计划不一致")

    E = soc0
    recs = []
    for t in range(n):
        if pv_used[t] < -1e-9 or pv_curtail[t] < -1e-9:
            raise ValueError(f"slot {t}: 光伏消纳/弃光不得为负")
        if pv_used[t] > pv_available[t] + 1e-9:
            raise ValueError(f"slot {t}: 光伏消纳超过可用量")
        if abs(pv_used[t] + pv_curtail[t] - pv_available[t]) > 1e-8:
            raise ValueError(f"slot {t}: 光伏消纳与弃光不守恒")

        E_next = (
            E
            + params.eta_charge * charge[t]
            - discharge[t] / params.eta_discharge
        )
        residual = (
            grid_contract[t] + pv_used[t] + discharge[t] - load[t] - charge[t]
        )
        recs.append(
            ExecRecord(
                slot=t,
                interval_start=starts[t],
                interval_end=ends[t],
                price=price[t],
                load=load[t],
                pv_available=pv_available[t],
                pv_used=pv_used[t],
                pv_curtail=pv_curtail[t],
                grid_contract=grid_contract[t],
                grid_delivered=grid_contract[t],
                grid_unused=0.0,
                grid_emergency=0.0,
                charge=charge[t],
                discharge=discharge[t],
                soc_start=E,
                soc_end=E_next,
                residual=residual,
                normal_cost=price[t] * grid_contract[t],
                emergency_cost=0.0,
            )
        )
        E = E_next
    return recs


def execute_q2(
    grid_contract: np.ndarray,
    price: np.ndarray,
    load_actual: np.ndarray,
    pv_available: np.ndarray,
    charge_planned: np.ndarray,
    discharge_planned: np.ndarray,
    soc0: float,
    starts: list[datetime],
    ends: list[datetime],
    plan_issue_time: datetime,
    params: BatteryParams = DEFAULT_BATTERY,
) -> list[ExecRecord]:
    """按 D002/D007 顺序回放第二问的实际运行。

    电池动作尽量按计划执行；为保证库存物理边界，必要时只削减所需的
    充电或放电量。需求分配顺序为计划放电、合同电、实际光伏，
    仍不足时紧急购电；这等价于过剩时先弃光、再形成未用合同电、最后
    削减计划放电。所有安全削减均显式记入执行记录。
    """
    n = len(grid_contract)
    arrays = {
        "price": price,
        "load_actual": load_actual,
        "pv_available": pv_available,
        "charge_planned": charge_planned,
        "discharge_planned": discharge_planned,
    }
    for name, values in arrays.items():
        if len(values) != n:
            raise ValueError(f"{name} 长度 {len(values)} != 计划长度 {n}")
        if np.any(np.asarray(values, dtype=float) < -1e-9):
            raise ValueError(f"{name} 不得为负")
    if len(starts) != n or len(ends) != n:
        raise ValueError("槽位起止时间长度与计划不一致")

    E = float(soc0)
    recs: list[ExecRecord] = []
    for t in range(n):
        if charge_planned[t] > 1e-9 and discharge_planned[t] > 1e-9:
            raise ValueError(f"slot {t}: 计划不得同时充放电")

        charge_room = max((params.soc_max - E) / params.eta_charge, 0.0)
        charge_actual = min(float(charge_planned[t]), charge_room)
        charge_shortfall = float(charge_planned[t]) - charge_actual

        demand = float(load_actual[t] + charge_actual)
        discharge_room = max((E - params.soc_min) * params.eta_discharge, 0.0)
        discharge_actual = min(float(discharge_planned[t]), demand, discharge_room)
        remaining = demand - discharge_actual

        grid_delivered = min(float(grid_contract[t]), remaining)
        grid_unused = float(grid_contract[t]) - grid_delivered
        remaining -= grid_delivered

        pv_used = min(float(pv_available[t]), remaining)
        pv_curtail = float(pv_available[t]) - pv_used
        remaining -= pv_used
        grid_emergency = max(remaining, 0.0)

        discharge_shortfall = float(discharge_planned[t]) - discharge_actual
        E_next = (
            E
            + params.eta_charge * charge_actual
            - discharge_actual / params.eta_discharge
        )
        if E_next < params.soc_min - 1e-6 or E_next > params.soc_max + 1e-6:
            raise AssertionError(f"slot {t}: 安全削减后SOC仍越界 {E_next:.6f}")
        residual = (
            grid_delivered + grid_emergency + pv_used + discharge_actual
            - float(load_actual[t]) - charge_actual
        )
        recs.append(
            ExecRecord(
                slot=t,
                interval_start=starts[t],
                interval_end=ends[t],
                price=float(price[t]),
                load=float(load_actual[t]),
                pv_available=float(pv_available[t]),
                pv_used=pv_used,
                pv_curtail=pv_curtail,
                grid_contract=float(grid_contract[t]),
                grid_delivered=grid_delivered,
                grid_unused=grid_unused,
                grid_emergency=grid_emergency,
                charge=charge_actual,
                discharge=discharge_actual,
                soc_start=E,
                soc_end=E_next,
                residual=residual,
                normal_cost=float(price[t] * grid_contract[t]),
                emergency_cost=float(5.0 * price[t] * grid_emergency),
                discharge_planned=float(discharge_planned[t]),
                discharge_shortfall=discharge_shortfall,
                discharge_clipped=discharge_shortfall > 1e-9,
                charge_planned=float(charge_planned[t]),
                charge_shortfall=charge_shortfall,
                charge_clipped=charge_shortfall > 1e-9,
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
