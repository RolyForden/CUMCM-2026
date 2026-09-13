"""第四问不可执行的完美信息费用下界，仅用于评价因果策略。"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q3_optimizer import solve_standard_sparse


OUT = ROOT / "outputs/q4"


def solve_branch(path: Path) -> dict:
    frame = pd.read_csv(path).sort_values(["date", "slot"]).reset_index(drop=True)
    soc0 = float(frame.iloc[0].soc_start)
    soc_final = float(frame.iloc[-1].soc_end)
    solution = solve_standard_sparse(
        price=frame.price_actual.to_numpy(float),
        load=frame.load_actual.to_numpy(float),
        pv_available=frame.pv_available.to_numpy(float),
        soc0=soc0,
        soc_final=soc_final,
    )
    if solution.status != 0 or not np.isfinite(solution.cost):
        raise AssertionError(f"完美信息下界求解失败：{solution.message}")
    balance = solution.grid + solution.pv_used + solution.discharge - frame.load_actual.to_numpy(float) - solution.charge
    soc_step = solution.soc[:-1] + 0.9 * solution.charge - solution.discharge / 0.9 - solution.soc[1:]
    simultaneous = int(((solution.charge > 1e-7) & (solution.discharge > 1e-7)).sum())
    return {
        "soc0": soc0, "soc_final": soc_final,
        "oracle_cost": float(solution.cost),
        "max_energy_residual": float(np.abs(balance).max()),
        "max_soc_residual": float(np.abs(soc_step).max()),
        "simultaneous_charge_discharge_slots": simultaneous,
        "solver": solution.solver,
    }


def main() -> int:
    t0 = time.time()
    formal = json.loads((OUT / "q4_replay_summary.json").read_text(encoding="utf-8"))
    q42 = solve_branch(OUT / "q4_2_dispatch.csv")
    q43 = solve_branch(OUT / "q4_3_dispatch.csv")
    q42["causal_cost"] = formal["q4_2"]["cost_total"]
    q43["causal_cost"] = formal["q4_3"]["total_cost_actual"]
    for row in (q42, q43):
        row["causal_oracle_gap"] = row["causal_cost"] - row["oracle_cost"]
        row["causal_oracle_gap_percent"] = 100 * row["causal_oracle_gap"] / row["oracle_cost"]
    payload = {
        "meaning": "使用未来真实负荷、光伏和电价的一次性全窗口LP，不可执行，只作下界",
        "fairness": "每条分支分别固定为其正式回放的期初和期末SOC",
        "q4_2": q42, "q4_3": q43,
        "elapsed_seconds": time.time() - t0,
    }
    (OUT / "q4_oracle_benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report = ROOT / "research/C_Q4_oracle_benchmark.md"
    report.write_text(
        "# 第四问完美信息下界\n\n"
        "该对照提前知道全年真实负荷、光伏和电价，因此不能作为实际策略，只用于衡量因果决策的代价。"
        "两条对照分别固定为对应正式回放的期初、期末库存，比较口径一致。\n\n"
        "| 分支 | 因果策略费用（元） | 完美信息下界（元） | 差额（元） | 相对下界 |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| 第二问式 | {q42['causal_cost']:.6f} | {q42['oracle_cost']:.6f} | {q42['causal_oracle_gap']:.6f} | {q42['causal_oracle_gap_percent']:.3f}\\% |\n"
        f"| 第三问式 | {q43['causal_cost']:.6f} | {q43['oracle_cost']:.6f} | {q43['causal_oracle_gap']:.6f} | {q43['causal_oracle_gap_percent']:.3f}\\% |\n\n"
        "下界不含预测误差导致的紧急购电或调整现金流；它回答的是未来信息最多能带来多大的费用空间。\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
