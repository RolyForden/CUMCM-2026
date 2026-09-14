"""第四问复用第二、三问能量预测口径的因果适配器。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Sequence

import pandas as pd

from core.q2_replay import Strategy, build_forecast
from core.q3_forecast import expand_issue_forecast


EnergyProvider = Callable[[datetime, Sequence[datetime]], pd.DataFrame]
Q2_STRATEGY = Strategy("D-7", "point")


def _forecast_horizon_days(
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    decision_time: datetime,
    target_times: Sequence[datetime],
) -> pd.DataFrame:
    """一次决策所需的所有目标日都使用同一个真实信息截止时刻。"""
    targets = [pd.Timestamp(value).to_pydatetime() for value in target_times]
    if not targets or targets != sorted(targets) or len(set(targets)) != len(targets):
        raise ValueError("target_times必须非空、严格递增且唯一")
    first_day = decision_time.date()
    # 方案A的午夜目标属于前一计划日；回放请求始终从decision_time所属日开始。
    last_day = max(value.date() for value in targets)
    if targets[-1].hour == 0 and targets[-1].minute == 0:
        last_day -= timedelta(days=1)
    frames = []
    day = first_day
    while day <= last_day:
        frame = build_forecast(
            Q2_STRATEGY, actuals, prior, day, decision_time=decision_time
        ).rename(columns={"valid_time": "target_time"})
        frames.append(frame[[
            "target_time", "load_forecast", "pv_forecast",
            "source_max_observed_at", "method",
        ]])
        day += timedelta(days=1)
    combined = pd.concat(frames, ignore_index=True).set_index("target_time")
    try:
        selected = combined.loc[pd.to_datetime(targets)].reset_index()
    except KeyError as exc:
        raise ValueError(f"能量预测缺少目标槽：{exc}") from exc
    selected = selected.rename(columns={"index": "target_time"})
    selected["target_time"] = pd.to_datetime(selected["target_time"])
    # 旧冷启动接口用 datetime.min 表示“附件1先验，无运行期观测来源”。
    # pandas 纳秒时间无法表示公元1年；对外统一记为当前决策时刻，既保守又可序列化。
    selected["source_max_observed_at"] = selected["source_max_observed_at"].map(
        lambda value: decision_time
        if getattr(value, "year", 9999) < 1900 else value
    )
    return selected


def make_q42_energy_provider(
    actuals: pd.DataFrame, prior: pd.DataFrame
) -> EnergyProvider:
    """第二问对应分支：负荷和光伏都沿用严格因果D-7点预测。"""

    def provider(decision_time: datetime, target_times: Sequence[datetime]) -> pd.DataFrame:
        return _forecast_horizon_days(actuals, prior, decision_time, target_times)[[
            "target_time", "load_forecast", "pv_forecast", "source_max_observed_at"
        ]]

    return provider


def make_q43_energy_provider(
    actuals: pd.DataFrame,
    prior: pd.DataFrame,
    vintages: pd.DataFrame,
) -> EnergyProvider:
    """第三问对应分支：D-7负荷 + 当时已发布的附件3光伏点预测线性展开。"""

    def provider(decision_time: datetime, target_times: Sequence[datetime]) -> pd.DataFrame:
        fallback = _forecast_horizon_days(actuals, prior, decision_time, target_times)
        fallback_map = dict(zip(
            pd.to_datetime(fallback["target_time"]),
            fallback["pv_forecast"].astype(float),
        ))
        expanded = expand_issue_forecast(
            vintages,
            decision_time,
            [pd.Timestamp(value).to_pydatetime() for value in target_times],
            method="linear",
            fallback=fallback_map,
        )
        source_issue = pd.to_datetime(expanded["source_issue_max"])
        fallback_observed = pd.to_datetime(fallback["source_max_observed_at"])
        source_max = []
        for observed, issued in zip(fallback_observed, source_issue):
            candidates = [observed]
            if not pd.isna(issued):
                candidates.append(issued)
            source_max.append(max(candidates))
        return pd.DataFrame({
            "target_time": pd.to_datetime(target_times),
            "load_forecast": fallback["load_forecast"].to_numpy(float),
            "pv_forecast": expanded["pv_forecast"].to_numpy(float),
            "source_max_observed_at": source_max,
        })

    return provider
