"""第二问的严格因果历史基线预测。

这里只提供可比较的候选，不替项目选择最终主方法。输入必须来自
history_actuals_as_of(decision_time)，每条历史记录都应带 observed_at。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from core.slot_adapter import build_day_slots


FORECAST_COLUMNS = ["load_forecast", "pv_forecast"]
ACTUAL_COLUMNS = {"load_forecast": "load_actual", "pv_forecast": "pv_actual"}


def _validate_history(history: pd.DataFrame, decision_time: datetime) -> None:
    required = {"valid_time", "observed_at", "load_actual", "pv_actual"}
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"历史数据缺少字段: {sorted(missing)}")
    if history.empty:
        raise ValueError("决策时刻没有可用历史数据")
    if history["valid_time"].duplicated().any():
        raise ValueError("历史数据 valid_time 必须唯一")
    if (history["observed_at"] > decision_time).any():
        raise ValueError("历史数据包含决策时刻之后才观测到的值")


def _target_frame(target_day: date, decision_time: datetime) -> pd.DataFrame:
    slots = build_day_slots(target_day)
    return pd.DataFrame(
        {
            "date": [target_day] * len(slots),
            "slot": [s.slot_id for s in slots],
            "valid_time": [s.interval_start for s in slots],
            "issue_time": [decision_time] * len(slots),
        }
    )


def forecast_lag_day(
    history: pd.DataFrame,
    target_day: date,
    decision_time: datetime,
    lag_days: int,
) -> pd.DataFrame:
    """用若干天前同一墙钟时刻的实际值预测；缺一槽即明确失败。"""
    if lag_days <= 0:
        raise ValueError("lag_days 必须为正整数")
    _validate_history(history, decision_time)
    targets = _target_frame(target_day, decision_time)
    lookup = history.set_index("valid_time")
    rows: list[dict] = []
    for row in targets.itertuples(index=False):
        source_time = row.valid_time - timedelta(days=lag_days)
        if source_time not in lookup.index:
            raise ValueError(
                f"{row.valid_time.isoformat()} 缺少 D-{lag_days} 已观测值"
            )
        source = lookup.loc[source_time]
        if source.observed_at > decision_time:
            raise ValueError(
                f"{row.valid_time.isoformat()} 的 D-{lag_days} 来源尚未观测"
            )
        rows.append(
            {
                **row._asdict(),
                "load_forecast": float(source.load_actual),
                "pv_forecast": float(source.pv_actual),
                "source_max_observed_at": source.observed_at,
                "method": f"D-{lag_days}",
            }
        )
    return pd.DataFrame(rows)


def forecast_same_weekday(
    history: pd.DataFrame,
    target_day: date,
    decision_time: datetime,
    weeks: int = 4,
    decay: float = 0.8,
) -> pd.DataFrame:
    """按最近若干个同星期日的同一时刻作衰减加权平均。"""
    if weeks <= 0 or not 0 < decay <= 1:
        raise ValueError("weeks 必须为正，decay 必须在 (0,1] 内")
    _validate_history(history, decision_time)
    targets = _target_frame(target_day, decision_time)
    lookup = history.set_index("valid_time")
    rows: list[dict] = []
    for row in targets.itertuples(index=False):
        sources = []
        for k in range(1, weeks + 1):
            source_time = row.valid_time - timedelta(days=7 * k)
            if source_time in lookup.index:
                source = lookup.loc[source_time]
                if source.observed_at <= decision_time:
                    sources.append((k, source))
        if not sources:
            raise ValueError(f"{row.valid_time.isoformat()} 没有已观测的同星期历史")
        weights = np.array([decay ** (k - 1) for k, _ in sources], dtype=float)
        weights /= weights.sum()
        rows.append(
            {
                **row._asdict(),
                "load_forecast": float(
                    sum(w * source.load_actual for w, (_, source) in zip(weights, sources))
                ),
                "pv_forecast": float(
                    sum(w * source.pv_actual for w, (_, source) in zip(weights, sources))
                ),
                "source_max_observed_at": max(source.observed_at for _, source in sources),
                "method": f"same-weekday-{weeks}-decay-{decay:g}",
            }
        )
    return pd.DataFrame(rows)


def validate_forecast_causality(frame: pd.DataFrame) -> None:
    if len(frame) != 144 or frame["slot"].tolist() != list(range(144)):
        raise ValueError("预测必须按槽位0至143恰好给出144项")
    if (frame["source_max_observed_at"] > frame["issue_time"]).any():
        raise ValueError("预测使用了发布时刻之后才观测到的数据")
    if frame[FORECAST_COLUMNS].isna().any().any():
        raise ValueError("预测含空值")
    if (frame[FORECAST_COLUMNS] < 0).any().any():
        raise ValueError("负荷或光伏预测不得为负")

