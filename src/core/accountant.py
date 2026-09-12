"""独立核算器（auditor）：从计划与执行记录重推一切，不与优化器共享代码。

职责（research/C_problem_map.md 统一费用账本 + TASK §6.5）：
- 每槽能量残差（母线侧能量平衡）；
- SOC 状态转移及上下界；
- 充放电功率边界（≤ C_MAX）与非负性；
- 同时充放电次数；
- 光伏恒等式：pv_used + pv_curtail == pv_available，0 ≤ pv_used ≤ pv_available，
  且弃光只能来自光伏（pv_available = 0 时 curtail 必须为 0）；
- 费用分项（正常/紧急/上调/下调）与合计。

Q1 冻结语义（D002 + TASK §3.2）：
grid_contract = grid_delivered，grid_unused = 0，grid_emergency = 0；
总费用 = Σ price·grid_delivered。上调/下调分项记 0。
优化器目标值仅供对照，论文数字以本核算器为准。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from core.executor import ExecRecord
from core.lp_kernel import C_MAX, DT, ETA_C, ETA_D, SOC_MAX, SOC_MIN

EMERGENCY_MULT = 5.0  # Q2 5 倍（Q1 恒不触发）


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
    cost_normal: float
    cost_emergency: float
    cost_up: float
    cost_down: float
    cost_total: float
    violations: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.soc_bounds_ok
            and self.power_bounds_ok
            and self.nonneg_ok
            and self.simultaneous_charge_discharge == 0
            and self.pv_identity_ok
            and self.curtail_only_from_pv
            and self.max_residual < 1e-9
            and not self.violations
        )


def audit(recs: Iterable[ExecRecord]) -> AuditResult:
    """独立复算执行记录，返回审计结论。"""
    recs = list(recs)
    violations: list[str] = []

    max_res = 0.0
    soc_min_seen = float("inf")
    soc_max_seen = float("-inf")
    soc_ok, power_ok, nonneg_ok = True, True, True
    pv_id_ok, curtail_src_ok = True, True
    n_simul = 0

    for r in recs:
        # 能量残差（母线侧）：g + v_used + d − l − c
        res = (
            r.grid_delivered + r.pv_used + r.discharge - r.load - r.charge
        )
        max_res = max(max_res, abs(res))

        # SOC 转移：E_next = E + η_c·c − d/η_d（独立复算，不用记录里的 soc_end）
        e_next = r.soc_start + ETA_C * r.charge - r.discharge / ETA_D
        if abs(e_next - r.soc_end) > 1e-6:
            violations.append(f"slot {r.slot}: SOC 转移不符，记录 {r.soc_end:.9f} vs 复算 {e_next:.9f}")
        soc_min_seen = min(soc_min_seen, r.soc_start, r.soc_end)
        soc_max_seen = max(soc_max_seen, r.soc_start, r.soc_end)
        if r.soc_start < SOC_MIN - 1e-6 or r.soc_start > SOC_MAX + 1e-6:
            soc_ok = False
            violations.append(f"slot {r.slot}: SOC 起点越界 {r.soc_start:.6f}")
        if r.soc_end < SOC_MIN - 1e-6 or r.soc_end > SOC_MAX + 1e-6:
            soc_ok = False
            violations.append(f"slot {r.slot}: SOC 终点越界 {r.soc_end:.6f}")

        # 充放电边界与非负
        for name, v in (("charge", r.charge), ("discharge", r.discharge)):
            if v < -1e-9:
                nonneg_ok = False
                violations.append(f"slot {r.slot}: {name} 为负 {v:.9f}")
            if v > C_MAX + 1e-6:
                power_ok = False
                violations.append(f"slot {r.slot}: {name} 超功率上限 {v:.6f} > {C_MAX:.6f}")
        for name, v in (("grid", r.grid_delivered), ("pv_used", r.pv_used), ("pv_curtail", r.pv_curtail)):
            if v < -1e-9:
                nonneg_ok = False
                violations.append(f"slot {r.slot}: {name} 为负 {v:.9f}")

        # 同时充放电
        if r.charge > 1e-6 and r.discharge > 1e-6:
            n_simul += 1

        # 光伏恒等式：used + curtail = available，且 curtail 只能来自光伏
        if abs(r.pv_used + r.pv_curtail - r.pv_available) > 1e-6:
            pv_id_ok = False
            violations.append(
                f"slot {r.slot}: 光伏恒等式不成立 "
                f"{r.pv_used:.9f}+{r.pv_curtail:.9f} != {r.pv_available:.9f}"
            )
        if r.pv_used > r.pv_available + 1e-9 or r.pv_curtail > r.pv_available + 1e-9:
            curtail_src_ok = False
            violations.append(f"slot {r.slot}: 弃光/消纳超过光伏可用量")
        if r.pv_available <= 1e-9 and r.pv_curtail > 1e-9:
            curtail_src_ok = False
            violations.append(f"slot {r.slot}: 无光伏却出现弃光（弃光吞购电）")

        # 购电语义（Q1）：contract = delivered，unused = 0，emergency = 0
        if abs(r.grid_contract - r.grid_delivered) > 1e-6:
            violations.append(f"slot {r.slot}: Q1 下合同购电 ≠ 实际受电")
        if r.grid_unused > 1e-9 or r.grid_emergency > 1e-9:
            violations.append(f"slot {r.slot}: Q1 下出现未用合同电或紧急购电")

    cost_normal = float(sum(r.normal_cost for r in recs))
    cost_emergency = float(sum(r.emergency_cost for r in recs))
    # 上调/下调分项：Q1 无调整，从记录推（ExecRecord 未含则记 0）
    cost_up = float(sum(getattr(r, "up_cost", 0.0) for r in recs))
    cost_down = float(sum(getattr(r, "down_cost", 0.0) for r in recs))
    cost_total = cost_normal + cost_emergency + cost_up + cost_down

    # 分项一致性：normal_cost 应等于 price·grid_delivered
    for r in recs:
        expect = r.price * r.grid_delivered
        if abs(r.normal_cost - expect) > 1e-6:
            violations.append(f"slot {r.slot}: normal_cost 与 price·delivered 不符")

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
        cost_normal=cost_normal,
        cost_emergency=cost_emergency,
        cost_up=cost_up,
        cost_down=cost_down,
        cost_total=cost_total,
        violations=violations,
    )
