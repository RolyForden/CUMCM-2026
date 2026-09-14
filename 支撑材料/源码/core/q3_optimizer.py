"""Q3 剩余时域调整优化：当前日按增减量结算，未来日按普通购电计价。"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix, vstack

from core.lp_kernel import LEX_TOL, LpSolution
from core.params import BatteryParams, DEFAULT_BATTERY


def solve_standard_sparse(
    *,
    price: np.ndarray,
    load: np.ndarray,
    pv_available: np.ndarray,
    soc0: float,
    soc_final: float,
    params: BatteryParams = DEFAULT_BATTERY,
) -> LpSolution:
    """与统一LP同口径的稀疏状态显式实现，供Q3反复滚动求解。"""
    price = np.asarray(price, dtype=float)
    load = np.asarray(load, dtype=float)
    pv_available = np.asarray(pv_available, dtype=float)
    n = len(price)
    if load.shape != (n,) or pv_available.shape != (n,):
        raise ValueError("Q3初始优化输入长度不一致")
    g0, v0, c0, d0, e0 = 0, n, 2*n, 3*n, 4*n
    nv = 5*n+1
    obj = np.zeros(nv)
    obj[g0:g0+n] = price
    Aeq = lil_matrix((2*n+2, nv), dtype=float)
    beq = np.zeros(2*n+2)
    row = 0
    for t in range(n):
        Aeq[row, g0+t] = 1; Aeq[row, v0+t] = 1
        Aeq[row, c0+t] = -1; Aeq[row, d0+t] = 1
        beq[row] = load[t]; row += 1
    for t in range(n):
        Aeq[row, e0+t] = -1; Aeq[row, e0+t+1] = 1
        Aeq[row, c0+t] = -params.eta_charge
        Aeq[row, d0+t] = 1/params.eta_discharge; row += 1
    Aeq[row, e0] = 1; beq[row] = soc0; row += 1
    Aeq[row, e0+n] = 1; beq[row] = soc_final
    bounds = (
        [(0, None)]*n
        + [(0, float(max(x, 0.0))) for x in pv_available]
        + [(0, params.energy_limit)]*(2*n)
        + [(params.soc_min, params.soc_max)]*(n+1)
    )
    matrix = Aeq.tocsr()
    res = linprog(obj, A_eq=matrix, b_eq=beq, bounds=bounds, method="highs-ds")
    primary = float(res.fun) if res.success else np.nan
    if res.success:
        throughput = np.zeros(nv); throughput[c0:c0+n] = 1; throughput[d0:d0+n] = 1
        Aub = lil_matrix((1, nv), dtype=float); Aub[0, :] = obj
        res2 = linprog(throughput, A_ub=Aub.tocsr(), b_ub=[primary+LEX_TOL],
                       A_eq=matrix, b_eq=beq, bounds=bounds, method="highs-ds")
        if res2.success: res = res2
    if not res.success:
        nan = np.full(n, np.nan)
        return LpSolution(nan, nan.copy(), nan.copy(), nan.copy(), nan.copy(),
                          np.full(n+1, np.nan), np.nan, primary, np.nan,
                          res.status, res.message, "highs-ds-sparse")
    x = res.x
    grid=x[g0:g0+n]; pv=x[v0:v0+n]; charge=x[c0:c0+n]; discharge=x[d0:d0+n]
    return LpSolution(grid, pv, pv_available-pv, charge, discharge, x[e0:e0+n+1],
                      float(price@grid), primary, float(obj@x), 0, "optimal", "highs-ds-sparse")


def solve_adjustment_lp(
    *,
    price: np.ndarray,
    load: np.ndarray,
    pv_available: np.ndarray,
    soc0: float,
    previous_contract: np.ndarray,
    adjusted_slots: int,
    soc_final: float,
    params: BatteryParams = DEFAULT_BATTERY,
) -> LpSolution:
    """最小化本次调整现金流与后续未签约时段普通购电费。"""
    price = np.asarray(price, dtype=float)
    load = np.asarray(load, dtype=float)
    pv_available = np.asarray(pv_available, dtype=float)
    previous_contract = np.asarray(previous_contract, dtype=float)
    n = len(price)
    m = int(adjusted_slots)
    if load.shape != (n,) or pv_available.shape != (n,):
        raise ValueError("Q3优化输入长度不一致")
    if m < 1 or m > n or previous_contract.shape != (m,):
        raise ValueError("调整槽数或上一版合同量长度错误")

    # g,v,c,d 各n；E共n+1；up/down各m。
    g0, v0, c0, d0, e0, up0, down0 = 0, n, 2*n, 3*n, 4*n, 5*n+1, 5*n+1+m
    nv = 5*n + 1 + 2*m
    obj = np.zeros(nv)
    obj[g0+m:g0+n] = price[m:]
    obj[up0:up0+m] = 1.5 * price[:m]
    obj[down0:down0+m] = -0.5 * price[:m]

    neq = 2*n + m + 2
    Aeq = lil_matrix((neq, nv), dtype=float)
    beq = np.zeros(neq)
    row = 0
    for t in range(n):
        Aeq[row, g0+t] = 1
        Aeq[row, v0+t] = 1
        Aeq[row, c0+t] = -1
        Aeq[row, d0+t] = 1
        beq[row] = load[t]
        row += 1
    for t in range(n):
        Aeq[row, e0+t] = -1
        Aeq[row, e0+t+1] = 1
        Aeq[row, c0+t] = -params.eta_charge
        Aeq[row, d0+t] = 1 / params.eta_discharge
        row += 1
    for t in range(m):
        Aeq[row, g0+t] = 1
        Aeq[row, up0+t] = -1
        Aeq[row, down0+t] = 1
        beq[row] = previous_contract[t]
        row += 1
    Aeq[row, e0] = 1
    beq[row] = soc0
    row += 1
    Aeq[row, e0+n] = 1
    beq[row] = soc_final

    bounds = []
    bounds.extend([(0, None)] * n)
    bounds.extend([(0, float(max(x, 0.0))) for x in pv_available])
    bounds.extend([(0, params.energy_limit)] * n)
    bounds.extend([(0, params.energy_limit)] * n)
    bounds.extend([(params.soc_min, params.soc_max)] * (n+1))
    bounds.extend([(0, None)] * (2*m))

    res = linprog(obj, A_eq=Aeq.tocsr(), b_eq=beq, bounds=bounds, method="highs-ds")
    primary = float(res.fun) if res.success else np.nan
    if res.success:
        throughput = np.zeros(nv)
        throughput[c0:c0+n] = 1
        throughput[d0:d0+n] = 1
        throughput[up0:up0+m] = 1
        throughput[down0:down0+m] = 1
        Aub = lil_matrix((1, nv), dtype=float)
        Aub[0, :] = obj
        res2 = linprog(
            throughput,
            A_ub=Aub.tocsr(),
            b_ub=np.array([primary + LEX_TOL]),
            A_eq=Aeq.tocsr(),
            b_eq=beq,
            bounds=bounds,
            method="highs-ds",
        )
        if res2.success:
            res = res2

    if not res.success:
        nan = np.full(n, np.nan)
        return LpSolution(nan, nan.copy(), nan.copy(), nan.copy(), nan.copy(),
                          np.full(n+1, np.nan), np.nan, primary, np.nan,
                          res.status, res.message, "highs-ds-adjustment")
    x = res.x
    grid = x[g0:g0+n]
    pv_used = x[v0:v0+n]
    charge = x[c0:c0+n]
    discharge = x[d0:d0+n]
    soc = x[e0:e0+n+1]
    return LpSolution(
        grid=grid,
        pv_used=pv_used,
        pv_curtail=pv_available-pv_used,
        charge=charge,
        discharge=discharge,
        soc=soc,
        cost=float(price @ grid),
        primary_optimum=primary,
        objective=float(obj @ x),
        status=0,
        message="optimal",
        solver="highs-ds-adjustment",
    )
