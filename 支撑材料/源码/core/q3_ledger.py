"""Q3 多次调整的纯账本内核。

本模块只处理“某个目标槽位的计划版本如何收费”，不读取附件3，
不做预测，不做滚动优化，也不计算电池调度。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class Q3PlanVersion:
    """一个目标槽位的一版合同购电计划。"""

    target_slot: int
    issue_time: datetime
    version: int
    quantity: float


@dataclass(frozen=True)
class Q3Adjustment:
    """相邻两版计划之间产生的一笔调整现金流。"""

    from_version: int
    to_version: int
    previous_quantity: float
    new_quantity: float
    increase: float
    decrease: float
    cashflow: float


@dataclass(frozen=True)
class Q3LedgerResult:
    """单个目标槽位的版本账本结果。"""

    target_slot: int
    initial_quantity: float
    final_quantity: float
    target_price: float
    initial_contract_cost: float
    adjustment_cashflow: float
    emergency_cost: float
    total_cost: float
    adjustments: tuple[Q3Adjustment, ...]


def _sorted_versions(versions: Iterable[Q3PlanVersion]) -> list[Q3PlanVersion]:
    rows = sorted(versions, key=lambda r: (r.version, r.issue_time))
    if not rows:
        raise ValueError("Q3计划版本不能为空")

    target_slots = {r.target_slot for r in rows}
    if len(target_slots) != 1:
        raise ValueError("一次账本核算只能对应一个目标槽位")

    seen_versions: set[int] = set()
    previous_version = None
    previous_issue_time = None
    for row in rows:
        if row.version in seen_versions:
            raise ValueError(f"计划版本重复：{row.version}")
        seen_versions.add(row.version)
        if row.quantity < -1e-9:
            raise ValueError("计划购电量不得为负")
        if previous_version is not None and row.version != previous_version + 1:
            raise ValueError("计划版本必须从0开始并逐次连续")
        if previous_issue_time is not None and row.issue_time < previous_issue_time:
            raise ValueError("计划版本发布时间不能倒退")
        previous_version = row.version
        previous_issue_time = row.issue_time

    if rows[0].version != 0:
        raise ValueError("第一版计划版本必须为0")
    return rows


def settle_q3_slot(
    versions: Iterable[Q3PlanVersion],
    *,
    target_price: float,
    grid_emergency: float = 0.0,
    executed_before_version: int | None = None,
    q_final_contract_charge: float = 0.0,
) -> Q3LedgerResult:
    """按 D007 口径核算一个目标槽位的Q3合同现金流。

    规则：
    - 初始计划 q0 收 `target_price * q0`。
    - 每次相对上一版调整：上调部分按 1.5 倍目标槽价增购，
      下调部分按 0.5 倍目标槽价冲回。
    - 计划费用只能来自版本现金流；若传入 `q_final_contract_charge`
      代表试图对最终合同量再收一次普通合同费，直接拒绝。
    - `executed_before_version` 用于合成测试“不能修改已执行槽位”。
    """
    if target_price < -1e-9:
        raise ValueError("目标槽电价不得为负")
    if grid_emergency < -1e-9:
        raise ValueError("紧急购电量不得为负")
    if abs(q_final_contract_charge) > 1e-9:
        raise ValueError("不得对 q_final 再收一次普通合同费")

    rows = _sorted_versions(versions)
    if executed_before_version is not None:
        for row in rows:
            if row.version > executed_before_version:
                raise ValueError("不得修改已经执行过的槽位")

    initial_contract_cost = target_price * rows[0].quantity
    adjustments: list[Q3Adjustment] = []
    adjustment_cashflow = 0.0
    for prev, cur in zip(rows, rows[1:]):
        increase = max(cur.quantity - prev.quantity, 0.0)
        decrease = max(prev.quantity - cur.quantity, 0.0)
        cashflow = 1.5 * target_price * increase - 0.5 * target_price * decrease
        adjustment_cashflow += cashflow
        adjustments.append(
            Q3Adjustment(
                from_version=prev.version,
                to_version=cur.version,
                previous_quantity=prev.quantity,
                new_quantity=cur.quantity,
                increase=increase,
                decrease=decrease,
                cashflow=cashflow,
            )
        )

    emergency_cost = 5.0 * target_price * grid_emergency
    return Q3LedgerResult(
        target_slot=rows[0].target_slot,
        initial_quantity=rows[0].quantity,
        final_quantity=rows[-1].quantity,
        target_price=target_price,
        initial_contract_cost=initial_contract_cost,
        adjustment_cashflow=adjustment_cashflow,
        emergency_cost=emergency_cost,
        total_cost=initial_contract_cost + adjustment_cashflow + emergency_cost,
        adjustments=tuple(adjustments),
    )


def settle_q4_slot_with_price_split(
    versions: Iterable[Q3PlanVersion],
    *,
    price_forecast_for_optimizer: float,
    price_actual_for_accountant: float,
    grid_emergency: float = 0.0,
) -> tuple[Q3LedgerResult, Q3LedgerResult]:
    """Q4 价格信息集检查：优化看预测价，核算看真实价。"""
    optimizer_view = settle_q3_slot(
        versions,
        target_price=price_forecast_for_optimizer,
        grid_emergency=grid_emergency,
    )
    accountant_view = settle_q3_slot(
        versions,
        target_price=price_actual_for_accountant,
        grid_emergency=grid_emergency,
    )
    return optimizer_view, accountant_view
