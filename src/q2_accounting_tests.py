"""第二问执行账本的独立合成测试。

只测试已冻结的题意：合同计划量计费、未使用合同量不入母线、缺口以
五倍价格紧急购电。这里不选择预测方法、终端库存或零点衔接方案。
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.accountant import audit
from core.executor import ExecRecord, execute_q2
from core.slot_adapter import build_day_slots


RESULTS: list[dict] = []


def check(name: str, passed: bool, actual: object) -> None:
    RESULTS.append({"name": name, "passed": bool(passed), "actual": str(actual)})


def rec(**changes: float) -> ExecRecord:
    slot = build_day_slots(date(2025, 2, 1))[0]
    values = dict(
        slot=0,
        interval_start=slot.interval_start,
        interval_end=slot.interval_end,
        price=1.0,
        load=50.0,
        pv_available=0.0,
        pv_used=0.0,
        pv_curtail=0.0,
        grid_contract=100.0,
        grid_delivered=50.0,
        grid_unused=50.0,
        grid_emergency=0.0,
        charge=0.0,
        discharge=0.0,
        soc_start=6000.0,
        soc_end=6000.0,
        residual=0.0,
        normal_cost=100.0,
        emergency_cost=0.0,
    )
    values.update(changes)
    return ExecRecord(**values)


def main() -> int:
    paid_unused = audit([rec()], require_q1_semantics=False)
    check(
        "合同100实供50仍按100收费",
        paid_unused.ok and abs(paid_unused.cost_normal - 100.0) < 1e-9,
        paid_unused.violations,
    )

    emergency = audit(
        [rec(grid_contract=0.0, grid_delivered=0.0, grid_unused=0.0,
             grid_emergency=50.0, normal_cost=0.0, emergency_cost=250.0)],
        require_q1_semantics=False,
    )
    check(
        "紧急购电进入能量平衡且按五倍收费",
        emergency.ok and emergency.max_residual < 1e-9
        and abs(emergency.cost_emergency - 250.0) < 1e-9,
        emergency.violations,
    )

    wrong_contract = audit(
        [rec(grid_unused=40.0)], require_q1_semantics=False
    )
    check("合同量恒等式错误被拒绝", not wrong_contract.ok, wrong_contract.violations)

    wrong_normal = audit(
        [rec(normal_cost=50.0)], require_q1_semantics=False
    )
    check("按实供量少算正常费用被拒绝", not wrong_normal.ok, wrong_normal.violations)

    wrong_emergency = audit(
        [rec(grid_contract=0.0, grid_delivered=0.0, grid_unused=0.0,
             grid_emergency=50.0, normal_cost=0.0, emergency_cost=50.0)],
        require_q1_semantics=False,
    )
    check("紧急费用不是五倍时被拒绝", not wrong_emergency.ok, wrong_emergency.violations)

    slots = build_day_slots(date(2025, 2, 1))[:2]
    replay = execute_q2(
        grid_contract=np.array([50.0, 20.0]),
        price=np.array([1.0, 2.0]),
        load_actual=np.array([10.0, 100.0]),
        pv_available=np.array([100.0, 0.0]),
        charge_planned=np.array([0.0, 0.0]),
        discharge_planned=np.array([20.0, 30.0]),
        soc0=6000.0,
        starts=[s.interval_start for s in slots],
        ends=[s.interval_end for s in slots],
        plan_issue_time=datetime(2025, 2, 1),
    )
    replay_audit = audit(replay, require_q1_semantics=False)
    check(
        "两槽连续执行通过独立核算",
        replay_audit.ok and replay[0].discharge_clipped
        and abs(replay[1].grid_emergency - 50.0) < 1e-9,
        replay_audit.violations,
    )

    clipped = execute_q2(
            grid_contract=np.array([0.0, 100.0]),
            price=np.array([1.0, 1.0]),
            load_actual=np.array([0.0, 100.0]),
            pv_available=np.array([0.0, 0.0]),
            charge_planned=np.array([0.0, 100.0]),
            discharge_planned=np.array([81.0, 0.0]),
            soc0=10800.0,
            starts=[s.interval_start for s in slots],
            ends=[s.interval_end for s in slots],
            plan_issue_time=datetime(2025, 2, 1),
        )
    clipped_audit = audit(clipped, require_q1_semantics=False)
    check(
        "削减放电导致后续库存偏高时安全少充电",
        clipped_audit.ok
        and clipped[1].charge_clipped
        and abs(clipped[1].charge_planned - 100.0) < 1e-9
        and abs(clipped[1].charge - 0.0) < 1e-9
        and abs(clipped[1].charge_shortfall - 100.0) < 1e-9
        and abs(clipped[1].soc_end - 10800.0) < 1e-9,
        clipped_audit.violations,
    )

    failed = [item for item in RESULTS if not item["passed"]]
    payload = {
        "scope": "Q2 frozen accounting semantics only",
        "summary": {"total": len(RESULTS), "passed": len(RESULTS) - len(failed), "failed": len(failed)},
        "results": RESULTS,
    }
    output = ROOT / "experiments" / "q2_accounting_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
