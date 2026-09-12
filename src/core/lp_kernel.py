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

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

EPS = 1e-9

ETA_C = 0.9  # D002 P0-3
ETA_D = 0.9
SOC_MIN = 1200.0  # D002 数据固定口径
SOC_MAX = 10800.0
P_MAX = 5000.0  # kW
DT = 1.0 / 6.0  # h
C_MAX = P_MAX * DT  # 833.333... kWh/格


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


@dataclass
class LpSolution:
    grid: np.ndarray        # 购电（母线侧）= grid_contract = grid_delivered（Q1 语义）
    pv_used: np.ndarray
    pv_curtail: np.ndarray
    charge: np.ndarray      # c_t 母线侧充电
    discharge: np.ndarray   # d_t 母线侧放电
    soc: np.ndarray         # E_t，长度 n+1（E[0]=soc0）
    cost: float             # sum(price·grid)
    status: int
    message: str
    solver: str


def solve_lp(inp: LpInputs, solver: str = "highs-ds") -> LpSolution:
    """求解单日/窗口确定性 LP（含字典序吞吐量最小化）。

    solver: 'highs-ds'（dual simplex）| 'highs-ipm'（内点法）。
    变量布局：g[0..n), v[0..n), w[0..n), c[0..n), d[0..n)，E 由状态方程消去。
    """
    n = len(inp.price)
    assert inp.load.shape == (n,) and inp.pv_available.shape == (n,)

    # 变量：g, v, w, c, d 各 n 个
    def idx(name: str, t: int) -> int:
        return {"g": 0, "v": 1, "w": 2, "c": 3, "d": 4}[name] * n + t

    nv = 5 * n
    c_obj = np.zeros(nv)
    for t in range(n):
        c_obj[idx("g", t)] = inp.price[t]

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
        b_ub.append(C_MAX)
        row = np.zeros(nv)
        row[idx("d", t)] = 1.0
        A_ub.append(row)
        b_ub.append(C_MAX)

    # SOC 链：E_{t+1} = E_t + η_c·c_t − d_t/η_d  ∈ [SOC_MIN, SOC_MAX]
    # E_{t+1} = E_0 + Σ_{s≤t}(η_c·c_s − d_s/η_d)
    # 上界：Σ_{s≤t}(η_c·c_s − d_s/η_d) ≤ SOC_MAX − E_0
    # 下界：Σ_{s≤t}(η_c·c_s − d_s/η_d) ≥ SOC_MIN − E_0
    for t in range(n):
        row = np.zeros(nv)
        for s in range(t + 1):
            row[idx("c", s)] = ETA_C
            row[idx("d", s)] = -1.0 / ETA_D
        A_ub.append(row.copy())
        b_ub.append(SOC_MAX - inp.soc0)
        A_ub.append(-row)
        b_ub.append(-(SOC_MIN - inp.soc0))

    # 终端 SOC 约束（Q1：E_n = E_0；soc_final_slot 控制约束作用的槽位）
    if inp.soc_final is not None:
        horizon = inp.soc_final_slot if inp.soc_final_slot is not None else n - 1
        row = np.zeros(nv)
        for s in range(horizon + 1):
            row[idx("c", s)] = ETA_C
            row[idx("d", s)] = -1.0 / ETA_D
        A_eq.append(row)
        b_eq.append(inp.soc_final - inp.soc0)

    bounds = [(0, None)] * nv  # 全部非负（g≥0 禁止反送；v,w,c,d ≥ 0）

    res = linprog(
        c_obj,
        A_ub=np.array(A_ub),
        b_ub=np.array(b_ub),
        A_eq=np.array(A_eq),
        b_eq=np.array(b_eq),
        bounds=bounds,
        method=solver,
    )

    # 字典序：费用不劣于 tol 的解中最小化吞吐量 Σ(c+d)
    if res.success:
        c2 = np.zeros(nv)
        for t in range(n):
            c2[idx("c", t)] = 1.0
            c2[idx("d", t)] = 1.0
        # 主目标费用固定为第一段最优值（+1e-6 容差）
        A_eq2 = np.array(A_eq + [c_obj])
        b_eq2 = np.array(list(b_eq) + [res.fun + 1e-6])
        res2 = linprog(
            c2,
            A_ub=np.array(A_ub),
            b_ub=np.array(b_ub),
            A_eq=A_eq2,
            b_eq=b_eq2,
            bounds=bounds,
            method=solver,
        )
        if res2.success:
            res = res2
            res.fun = c_obj @ res.x  # 报告主目标费用

    if not res.success:
        return LpSolution(
            grid=np.full(n, np.nan),
            pv_used=np.full(n, np.nan),
            pv_curtail=np.full(n, np.nan),
            charge=np.full(n, np.nan),
            discharge=np.full(n, np.nan),
            soc=np.full(n + 1, np.nan),
            cost=np.nan,
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
        soc[t + 1] = soc[t] + ETA_C * charge[t] - discharge[t] / ETA_D

    return LpSolution(
        grid=grid,
        pv_used=pv_used,
        pv_curtail=pv_curtail,
        charge=charge,
        discharge=discharge,
        soc=soc,
        cost=float(res.fun),
        status=res.status,
        message=res.message,
        solver=solver,
    )


def rule_based_schedule(price: np.ndarray, load: np.ndarray, pv: np.ndarray,
                        soc0: float) -> tuple[float, np.ndarray, np.ndarray]:
    """规则法（回归测试 baseline）：净负荷优先 + 贪心充放电。

    - 光伏先供负荷，富余充电（容量允许），再弃；
    - 缺口先用电池（SOC 允许），再购电；
    - 充电只在有富余光伏时进行（避免购电充电的套利判断）。
    返回 (费用, soc 轨迹, 购电向量)。
    """
    n = len(load)
    E = soc0
    socs = [E]
    g = np.zeros(n)
    for t in range(n):
        net = load[t] - pv[t]  # 净缺口（负 = 富余）
        if net > 0:
            # 放电优先：d 满足 电池能量 d/η_d ≤ E−SOC_MIN 与 d ≤ C_MAX
            d = min(net, (E - SOC_MIN) * ETA_D, C_MAX)
            E -= d / ETA_D
            g[t] = net - d
        else:
            surplus = -net
            # 充电优先：c ≤ min(surplus, (SOC_MAX−E)/η_c, C_MAX)
            c = min(surplus, (SOC_MAX - E) / ETA_C, C_MAX)
            E += ETA_C * c
            # 剩余弃光（富余未被使用）
            g[t] = 0.0
        socs.append(E)
    return float(np.sum(price * g)), np.array(socs), g
