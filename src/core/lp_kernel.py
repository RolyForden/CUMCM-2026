"""统一 LP 内核：确定性购电 + 储能调度（四问共用）。

冻结口径（DECISIONS.md D002）：
- P0-3 η_c = η_d = 0.9，母线侧计量：
  母线侧能量平衡 g + v_used + d = l + c（v_used = 光伏消纳量）；
  电池状态 E_{t+1} = E_t + η_c·c_t − d_t/η_d。
- P0-4 允许弃光（仅限光伏）、禁止反送。
- P0-2/6 SOC ∈ [1200, 10800]，E_0 由调用方给定。
- 功率上限 5000 kW → 每格电量 ≤ 5000·Δt = 833.333... kWh。

TASK_C_probe_model_corrections.md §3：
- 弃光只能来自光伏：pv_used ≤ pv_available，pv_curtail = pv_available − pv_used；
  严禁通过增大 pv_curtail 处理多买的外网电。
- Q1 语义：grid_contract = grid_delivered，grid_unused = 0，grid_emergency = 0；
  目标只算 sum(price·grid_contract)。Q2 的紧急/未使用合同电规则不混入。

求解器是配置项：scipy HiGHS dual simplex 主引擎 + IPM 对拍。
字典序吞吐量最小化：先最小化费用，再在费用不劣于 tol 的解中最小化
sum(c+d)（不引入 ε 惩罚改变主目标）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linprog

from core.params import BatteryParams, DEFAULT_BATTERY

EPS = 1e-9

# 兼容现有调用；新代码应通过 BatteryParams 显式传参。
ETA_C = DEFAULT_BATTERY.eta_charge
ETA_D = DEFAULT_BATTERY.eta_discharge
SOC_MIN = DEFAULT_BATTERY.soc_min
SOC_MAX = DEFAULT_BATTERY.soc_max
P_MAX = DEFAULT_BATTERY.power_max
DT = DEFAULT_BATTERY.delta_t
C_MAX = DEFAULT_BATTERY.energy_limit
LEX_TOL = 1e-7


@dataclass
class LpInputs:
    """单日/窗口 LP 输入（母线侧，kWh 或 kWh/格）。"""

    price: np.ndarray       # 电价 元/kWh
    load: np.ndarray        # 负荷 每格 kWh
    pv_available: np.ndarray  # 光伏可用量 每格 kWh
    soc0: float             # 初始 SOC kWh
    soc_final: float | None = None  # 终端 SOC 约束值；None = 自由
    soc_final_slot: int | None = None  # 终端约束作用的槽位下标：
        # None → 全部 n 槽之后（E_n = soc_final，D002 P0-2 冻结口径）；
        # k → 前 k+1 槽之后（E_{k+1} = soc_final，用于敏感性对照 E_143=E_0）
    terminal_value: float = 0.0  # 终端库存价值 元/kWh（0 时为 Q1/D002 原型）
    params: BatteryParams = field(default_factory=lambda: DEFAULT_BATTERY)


@dataclass
class LpSolution:
    grid: np.ndarray        # 购电（母线侧）= grid_contract = grid_delivered（Q1 语义）
    pv_used: np.ndarray
    pv_curtail: np.ndarray
    charge: np.ndarray      # c_t 母线侧充电
    discharge: np.ndarray   # d_t 母线侧放电
    soc: np.ndarray         # E_t，长度 n+1（E[0]=soc0）
    cost: float             # sum(price·grid)，纯购电费
    primary_optimum: float  # 第一阶段真实最优目标值（含终端价值项）
    objective: float        # 最终选择的真实目标值（购电费 − 终端价值）
    status: int
    message: str
    solver: str


def solve_lp(inp: LpInputs, solver: str = "highs-ds") -> LpSolution:
    """求解单日/窗口确定性 LP（含字典序吞吐量最小化）。

    solver: 'highs-ds'（dual simplex）| 'highs-ipm'（内点法）。
    变量布局：g[0..n), v[0..n), c[0..n), d[0..n)，E 由状态方程消去。
    """
    n = len(inp.price)
    assert inp.load.shape == (n,) and inp.pv_available.shape == (n,)

    params = inp.params

    # 变量：g, v, c, d 各 n 个；弃光由 pv_available - v 推导。
    def idx(name: str, t: int) -> int:
        return {"g": 0, "v": 1, "c": 2, "d": 3}[name] * n + t

    nv = 4 * n
    c_obj = np.zeros(nv)   # 正常购电费用（用于报告，永远是最小化目标的一部分）
    for t in range(n):
        c_obj[idx("g", t)] = inp.price[t]

    # 终端库存价值：E_n = E_0 + Σ(η_c·c_s − d_s/η_d)，按 terminal_value 计价。
    # 该项只影响优化目标；报告的 cost 仍为纯购电费。terminal_value=0 时与原型完全一致。
    c_opt = c_obj.copy()
    if inp.terminal_value != 0.0:
        for t in range(n):
            c_opt[idx("c", t)] -= inp.terminal_value * params.eta_charge
            c_opt[idx("d", t)] += inp.terminal_value / params.eta_discharge

    A_ub = []
    b_ub = []
    A_eq = []
    b_eq = []

    # 母线侧能量平衡：g + v + d − l − c = 0
    for t in range(n):
        row = np.zeros(nv)
        row[idx("g", t)] = 1.0
        row[idx("v", t)] = 1.0
        row[idx("d", t)] = 1.0
        row[idx("c", t)] = -1.0
        A_eq.append(row)
        b_eq.append(inp.load[t])

    # 光伏消纳上限（弃光只能来自光伏）：v ≤ pv_available
    for t in range(n):
        row = np.zeros(nv)
        row[idx("v", t)] = 1.0
        A_ub.append(row)
        b_ub.append(inp.pv_available[t])

    # 充放电功率上限：c ≤ C_MAX, d ≤ C_MAX
    for t in range(n):
        row = np.zeros(nv)
        row[idx("c", t)] = 1.0
        A_ub.append(row)
        b_ub.append(params.energy_limit)
        row = np.zeros(nv)
        row[idx("d", t)] = 1.0
        A_ub.append(row)
        b_ub.append(params.energy_limit)

    # SOC 链：E_{t+1} = E_t + η_c·c_t − d_t/η_d  ∈ [SOC_MIN, SOC_MAX]
    # E_{t+1} = E_0 + Σ_{s≤t}(η_c·c_s − d_s/η_d)
    # 上界：Σ_{s≤t}(η_c·c_s − d_s/η_d) ≤ SOC_MAX − E_0
    # 下界：Σ_{s≤t}(η_c·c_s − d_s/η_d) ≥ SOC_MIN − E_0
    for t in range(n):
        row = np.zeros(nv)
        for s in range(t + 1):
            row[idx("c", s)] = params.eta_charge
            row[idx("d", s)] = -1.0 / params.eta_discharge
        A_ub.append(row.copy())
        b_ub.append(params.soc_max - inp.soc0)
        A_ub.append(-row)
        b_ub.append(-(params.soc_min - inp.soc0))

    # 终端 SOC 约束（Q1：E_n = E_0；soc_final_slot 控制约束作用的槽位）
    if inp.soc_final is not None:
        horizon = inp.soc_final_slot if inp.soc_final_slot is not None else n - 1
        row = np.zeros(nv)
        for s in range(horizon + 1):
            row[idx("c", s)] = params.eta_charge
            row[idx("d", s)] = -1.0 / params.eta_discharge
        A_eq.append(row)
        b_eq.append(inp.soc_final - inp.soc0)

    bounds = [(0, None)] * nv  # 全部非负（g≥0 禁止反送；v,c,d ≥ 0）

    res = linprog(
        c_obj,
        A_ub=np.array(A_ub),
        b_ub=np.array(b_ub),
        A_eq=np.array(A_eq),
        b_eq=np.array(b_eq),
        bounds=bounds,
        method=solver,
    )

    primary_optimum = float(res.fun) if res.success else np.nan

    # 字典序：真实目标（购电费 − 终端价值）不劣于 tol 的解中最小化吞吐量 Σ(c+d)。
    # 费用上界用真实目标 c_opt 表达；报告费用仍为纯购电费 c_obj·x。
    if res.success:
        c2 = np.zeros(nv)
        for t in range(n):
            c2[idx("c", t)] = 1.0
            c2[idx("d", t)] = 1.0
        A_ub2 = np.array(A_ub + [c_opt])
        b_ub2 = np.array(list(b_ub) + [primary_optimum + LEX_TOL])
        res2 = linprog(
            c2,
            A_ub=A_ub2,
            b_ub=b_ub2,
            A_eq=np.array(A_eq),
            b_eq=np.array(b_eq),
            bounds=bounds,
            method=solver,
        )
        if res2.success:
            res = res2
            res.fun = float(c_opt @ res.x)  # 报告真实目标值

    if not res.success:
        return LpSolution(
            grid=np.full(n, np.nan),
            pv_used=np.full(n, np.nan),
            pv_curtail=np.full(n, np.nan),
            charge=np.full(n, np.nan),
            discharge=np.full(n, np.nan),
            soc=np.full(n + 1, np.nan),
            cost=np.nan,
            primary_optimum=primary_optimum,
            status=res.status,
            message=res.message,
            solver=solver,
        )

    x = res.x
    grid = np.array([x[idx("g", t)] for t in range(n)])
    pv_used = np.array([x[idx("v", t)] for t in range(n)])
    pv_curtail = inp.pv_available - pv_used
    charge = np.array([x[idx("c", t)] for t in range(n)])
    discharge = np.array([x[idx("d", t)] for t in range(n)])

    soc = np.zeros(n + 1)
    soc[0] = inp.soc0
    for t in range(n):
        soc[t + 1] = (
            soc[t]
            + params.eta_charge * charge[t]
            - discharge[t] / params.eta_discharge
        )

    return LpSolution(
        grid=grid,
        pv_used=pv_used,
        pv_curtail=pv_curtail,
        charge=charge,
        discharge=discharge,
        soc=soc,
        cost=float(c_obj @ x),          # 纯购电费，与终端价值无关
        objective=float(c_opt @ x),     # 优化器真实目标（购电费 − 终端价值）
        primary_optimum=primary_optimum,
        status=res.status,
        message=res.message,
        solver=solver,
    )


def no_storage_schedule(
    price: np.ndarray,
    load: np.ndarray,
    pv_available: np.ndarray,
    soc0: float,
) -> dict[str, np.ndarray | float]:
    """同初末 SOC 的可行基线：完全不使用电池。"""
    pv_used = np.minimum(load, pv_available)
    pv_curtail = pv_available - pv_used
    grid = load - pv_used
    n = len(load)
    return {
        "cost": float(np.sum(price * grid)),
        "grid": grid,
        "pv_used": pv_used,
        "pv_curtail": pv_curtail,
        "charge": np.zeros(n),
        "discharge": np.zeros(n),
        "soc": np.full(n + 1, soc0, dtype=float),
    }
