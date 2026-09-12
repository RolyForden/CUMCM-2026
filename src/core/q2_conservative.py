"""第二问保守计划候选：点预测与经济分位调整。

方法地图 §3.3 要求把点预测与候选分位（0.7/0.8/0.9）放在同一顺序回放
上比较，不得预先指定 0.8 为最优。分位调整只用决策时刻之前已经产生的
预测残差，禁止用未来数据计算统一残差分位数。

残差定义：residual = actual − forecast。分位 q 的计划值
    plan = forecast + Quantile_q(historical residual)
对负荷，缺电代价（5 倍）高于多买代价（1 倍），因此 q 越高越保守；
对光伏，少预测会低估发电，故本模块对光伏允许同一 q（保守=调高预测）。

本模块不选择最终 q；q 由顺序选择脚本按过去数据选、未来数据评价。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from core.q2_forecast import forecast_lag_day, forecast_same_weekday

# 可选的计划口径：point 为纯点预测，其余为分位保守候选。
CONSERVATIVE_LEVELS = ("point", "0.7", "0.8", "0.9")


def _method_forecast(
    method: str,
    history: pd.DataFrame,
    target_day: date,
    decision_time: datetime,
    prior: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if method == "D-7":
        return forecast_lag_day(history, target_day, decision_time, 7)
    if method == "same-weekday-4-decay-0.8":
        return forecast_same_weekday(
            history, target_day, decision_time, weeks=4, decay=0.8, prior=prior
        )
    raise ValueError(f"未知预测方法: {method}")


def residual_pool_by_slot(
    method: str,
    history: pd.DataFrame,
    decision_time: datetime,
    lookback_days: int,
) -> dict[str, np.ndarray]:
    """按槽收集决策时刻之前已完整观测的预测残差。

    对 decision_time 之前的每一天，用同一 method 在该天的决策时刻（当天
    00:00）生成预测，与该天实际值比较；只有实际槽在 decision_time 前已经
    观测完（observed_at <= decision_time）才纳入残差。返回
    {slot: 残差数组}，其中负荷残差 = actual − forecast，光伏同理。

    这样分位只反映过去已经发生的误差，不用未来数据。
    """
    if lookback_days <= 0:
        raise ValueError("lookback_days 必须为正整数")
    loads: dict[int, list[float]] = {k: [] for k in range(144)}
    pvs: dict[int, list[float]] = {k: [] for k in range(144)}
    for offset in range(1, lookback_days + 1):
        past_day = decision_time.date() - timedelta(days=offset)
        past_decision = datetime.combine(past_day, datetime.min.time())
        if past_decision >= decision_time:
            continue
        past_history = history[history["observed_at"] <= past_decision]
        if past_history.empty:
            continue
        try:
            forecast = _method_forecast(method, past_history, past_day, past_decision)
        except ValueError:
            continue
        actual = history[
            (history["valid_time"].dt.date == past_day)
            & (history["observed_at"] <= decision_time)
        ]
        if actual.empty:
            continue
        actual_by_slot = actual.set_index("slot")
        for slot in range(144):
            if slot not in actual_by_slot.index:
                continue
            loads[slot].append(
                float(actual_by_slot.loc[slot, "load_actual"])
                - float(forecast.iloc[slot]["load_forecast"])
            )
            pvs[slot].append(
                float(actual_by_slot.loc[slot, "pv_actual"])
                - float(forecast.iloc[slot]["pv_forecast"])
            )
    return {
        "load": {k: np.asarray(v, dtype=float) for k, v in loads.items()},
        "pv": {k: np.asarray(v, dtype=float) for k, v in pvs.items()},
    }


def _quantile(values: np.ndarray, q: float) -> float:
    if values.size == 0:
        raise ValueError("没有可用残差，不能计算分位")
    if not 0.0 < q < 1.0:
        raise ValueError("分位必须在 (0,1) 内")
    return float(np.quantile(values, q))


def conservative_plan_forecast(
    method: str,
    history: pd.DataFrame,
    target_day: date,
    decision_time: datetime,
    level: str,
    lookback_days: int = 21,
    prior: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """生成点预测或分位保守的计划用负荷/光伏预测。"""
    if level not in CONSERVATIVE_LEVELS:
        raise ValueError(f"未知保守等级: {level}")
    base = _method_forecast(method, history, target_day, decision_time, prior=prior)
    if level == "point":
        out = base.copy()
        out["plan_level"] = "point"
        out["residual_slots_used"] = 0
        return out

    q = float(level)
    pool = residual_pool_by_slot(method, history, decision_time, lookback_days)
    loads = np.empty(144, dtype=float)
    pvs = np.empty(144, dtype=float)
    used_counts = []
    for slot in range(144):
        lres = pool["load"][slot]
        pres = pool["pv"][slot]
        # 残差不足时退回点预测，但记录实际使用槽数，不静默填 0。
        if lres.size == 0 or pres.size == 0:
            loads[slot] = float(base.iloc[slot]["load_forecast"])
            pvs[slot] = float(base.iloc[slot]["pv_forecast"])
            used_counts.append(0)
            continue
        loads[slot] = float(base.iloc[slot]["load_forecast"]) + _quantile(lres, q)
        pvs[slot] = float(base.iloc[slot]["pv_forecast"]) + _quantile(pres, q)
        used_counts.append(int(min(lres.size, pres.size)))

    out = base.copy()
    out["load_forecast"] = loads
    out["pv_forecast"] = pvs
    out["plan_level"] = f"quantile-{level}"
    out["residual_slots_used"] = np.mean(used_counts) if used_counts else 0
    # 保守调整后仍必须满足非负；负荷上限不额外设，光伏受物理上限约束由执行器处理。
    if (out[["load_forecast", "pv_forecast"]] < 0).any().any():
        out[["load_forecast", "pv_forecast"]] = out[["load_forecast", "pv_forecast"]].clip(lower=0.0)
    return out
