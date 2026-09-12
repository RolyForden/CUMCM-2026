"""独立执行审计器。

核算器只共享题意参数，不调用 LP 的状态更新或目标函数实现。它从执行
记录重新计算能量、SOC、费用和跨槽连续性。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from core.executor import ExecRecord
from core.params import BatteryParams, DEFAULT_BATTERY


@dataclass
class AuditResult:
    max_residual: float
    soc_min: float
    soc_max: float
    soc_bounds_ok: bool
    power_bounds_ok: bool
    nonneg_ok: bool
    simultaneous_charge_discharge: int
    pv_identity_ok: bool
    curtail_only_from_pv: bool
    slots_unique: bool
    slots_contiguous: bool
    intervals_contiguous: bool
    soc_chain_ok: bool
    q1_semantics_ok: bool
    cost_normal: float
    cost_emergency: float
    cost_up: float
    cost_down: float
    cost_total: float
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.soc_bounds_ok
            and self.power_bounds_ok
            and self.nonneg_ok
            and self.simultaneous_charge_discharge == 0
            and self.pv_identity_ok
            and self.curtail_only_from_pv
            and self.slots_unique
            and self.slots_contiguous
            and self.intervals_contiguous
            and self.soc_chain_ok
            and self.q1_semantics_ok
            and self.max_residual < 1e-9
            and not self.violations
        )


def audit(
    recs: Iterable[ExecRecord],
    params: BatteryParams = DEFAULT_BATTERY,
    require_q1_semantics: bool = True,
) -> AuditResult:
    """独立复算执行记录；空集、乱序、断槽和 SOC 断链均为硬错误。"""
    recs = list(recs)
    if not recs:
        raise ValueError("审计记录不能为空")

    violations: list[str] = []
    slots = [r.slot for r in recs]
    slots_unique = len(set(slots)) == len(slots)
    slots_contiguous = slots == list(range(slots[0], slots[0] + len(slots)))
    intervals_contiguous = True
    soc_chain_ok = True

    if not slots_unique:
        violations.append("槽位编号重复")
    if not slots_contiguous:
        violations.append("槽位必须按升序连续排列")
    for prev, cur in zip(recs, recs[1:]):
        if prev.interval_end != cur.interval_start:
            intervals_contiguous = False
            violations.append(f"slot {prev.slot}->{cur.slot}: 时间区间不连续")
        if abs(prev.soc_end - cur.soc_start) > 1e-6:
            soc_chain_ok = False
            violations.append(f"slot {prev.slot}->{cur.slot}: SOC 链断裂")

    max_res = 0.0
    soc_min_seen = float("inf")
    soc_max_seen = float("-inf")
    soc_ok = True
    power_ok = True
    nonneg_ok = True
    pv_id_ok = True
    curtail_src_ok = True
    q1_semantics_ok = True
    n_simul = 0

    for r in recs:
        residual = r.grid_delivered + r.pv_used + r.discharge - r.load - r.charge
        max_res = max(max_res, abs(residual))

        expected_soc_end = (
            r.soc_start
            + params.eta_charge * r.charge
            - r.discharge / params.eta_discharge
        )
        if abs(expected_soc_end - r.soc_end) > 1e-6:
            violations.append(
                f"slot {r.slot}: SOC 转移不符，记录 {r.soc_end:.9f} "
                f"vs 复算 {expected_soc_end:.9f}"
            )

        soc_min_seen = min(soc_min_seen, r.soc_start, r.soc_end)
        soc_max_seen = max(soc_max_seen, r.soc_start, r.soc_end)
        for label, value in (("SOC 起点", r.soc_start), ("SOC 终点", r.soc_end)):
            if value < params.soc_min - 1e-6 or value > params.soc_max + 1e-6:
                soc_ok = False
                violations.append(f"slot {r.slot}: {label}越界 {value:.6f}")

        for name, value in (("charge", r.charge), ("discharge", r.discharge)):
            if value < -1e-9:
                nonneg_ok = False
                violations.append(f"slot {r.slot}: {name} 为负 {value:.9f}")
            if value > params.energy_limit + 1e-6:
                power_ok = False
                violations.append(
                    f"slot {r.slot}: {name} 超功率上限 "
                    f"{value:.6f} > {params.energy_limit:.6f}"
                )

        for name, value in (
            ("grid_contract", r.grid_contract),
            ("grid_delivered", r.grid_delivered),
            ("grid_unused", r.grid_unused),
            ("grid_emergency", r.grid_emergency),
            ("pv_available", r.pv_available),
            ("pv_used", r.pv_used),
            ("pv_curtail", r.pv_curtail),
        ):
            if value < -1e-9:
                nonneg_ok = False
                violations.append(f"slot {r.slot}: {name} 为负 {value:.9f}")

        if r.charge > 1e-6 and r.discharge > 1e-6:
            n_simul += 1

        if abs(r.pv_used + r.pv_curtail - r.pv_available) > 1e-6:
            pv_id_ok = False
            violations.append(f"slot {r.slot}: 光伏消纳与弃光不守恒")
        if r.pv_used > r.pv_available + 1e-9 or r.pv_curtail > r.pv_available + 1e-9:
            curtail_src_ok = False
            violations.append(f"slot {r.slot}: 弃光/消纳超过光伏可用量")
        if r.pv_available <= 1e-9 and r.pv_curtail > 1e-9:
            curtail_src_ok = False
            violations.append(f"slot {r.slot}: 无光伏却出现弃光")

        if require_q1_semantics:
            if abs(r.grid_contract - r.grid_delivered) > 1e-6:
                q1_semantics_ok = False
                violations.append(f"slot {r.slot}: Q1 合同购电不等于实际受电")
            if abs(r.grid_unused) > 1e-9 or abs(r.grid_emergency) > 1e-9:
                q1_semantics_ok = False
                violations.append(f"slot {r.slot}: Q1 出现未用合同电或紧急购电")

        expected_normal = r.price * (
            r.grid_contract if require_q1_semantics else r.grid_delivered
        )
        if abs(r.normal_cost - expected_normal) > 1e-6:
            violations.append(f"slot {r.slot}: 正常购电费用复算不符")

    cost_normal = float(sum(r.normal_cost for r in recs))
    cost_emergency = float(sum(r.emergency_cost for r in recs))
    cost_up = float(sum(getattr(r, "up_cost", 0.0) for r in recs))
    cost_down = float(sum(getattr(r, "down_cost", 0.0) for r in recs))

    return AuditResult(
        max_residual=max_res,
        soc_min=float(soc_min_seen),
        soc_max=float(soc_max_seen),
        soc_bounds_ok=soc_ok,
        power_bounds_ok=power_ok,
        nonneg_ok=nonneg_ok,
        simultaneous_charge_discharge=n_simul,
        pv_identity_ok=pv_id_ok,
        curtail_only_from_pv=curtail_src_ok,
        slots_unique=slots_unique,
        slots_contiguous=slots_contiguous,
        intervals_contiguous=intervals_contiguous,
        soc_chain_ok=soc_chain_ok,
        q1_semantics_ok=q1_semantics_ok,
        cost_normal=cost_normal,
        cost_emergency=cost_emergency,
        cost_up=cost_up,
        cost_down=cost_down,
        cost_total=cost_normal + cost_emergency + cost_up + cost_down,
        violations=violations,
    )
