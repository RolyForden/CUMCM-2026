"""Q3 附件3点预测到10分钟槽位的因果展开。"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


METHODS = ("linear", "previous")


def expand_issue_forecast(
    vintages: pd.DataFrame,
    issue_time: datetime,
    target_times: Sequence[datetime],
    *,
    method: str = "linear",
    fallback: Mapping[datetime, float] | None = None,
) -> pd.DataFrame:
    """展开一个已发布批次；只使用当前批次及此前批次提供的当前时刻锚点。

    附件3的第 h 列是 `issue_time+h` 的点预测。线性主口径在相邻整点间
    插值；发布时刻的左端锚点取此前已发布批次对该时刻的预测。仅在首日
    0:00没有历史锚点时，才对缺口目标使用显式传入的因果先验 fallback。
    """
    if method not in METHODS:
        raise ValueError(f"未知展开方法: {method}")
    targets = list(target_times)
    if targets != sorted(targets) or len(set(targets)) != len(targets):
        raise ValueError("target_times 必须严格递增且不得重复")
    if any(t < issue_time for t in targets):
        raise ValueError("不得用新批次修改发布时刻之前的槽位")

    available = vintages[vintages["issue_time"] <= issue_time].copy()
    current = available[available["issue_time"] == issue_time].sort_values("lead_hour")
    if len(current) != 24 or current["lead_hour"].tolist() != list(range(1, 25)):
        raise ValueError(f"{issue_time} 预报批次不是完整24小时")

    points: dict[datetime, tuple[float, datetime]] = {
        row.valid_time: (float(row.pv_forecast), row.issue_time)
        for row in current.itertuples()
    }
    anchors = available[available["valid_time"] == issue_time].sort_values("issue_time")
    if not anchors.empty:
        anchor = anchors.iloc[-1]
        points[issue_time] = (float(anchor.pv_forecast), anchor.issue_time)

    point_times = sorted(points)
    # 不用 datetime.timestamp()：Windows 本地时区下，Python datetime 与
    # pandas Timestamp 对朴素时间的解释可能相差8小时。统一做相对时间差。
    origin = pd.Timestamp(issue_time)
    xs = np.array([(pd.Timestamp(t) - origin).total_seconds() for t in point_times], dtype=float)
    ys = np.array([points[t][0] for t in point_times], dtype=float)
    rows = []
    for target in targets:
        x = (pd.Timestamp(target) - origin).total_seconds()
        source_issues: list[datetime] = []
        if x < xs[0] or x > xs[-1]:
            if fallback is None or target not in fallback:
                raise ValueError(f"{issue_time} 对目标 {target} 没有因果预测覆盖")
            value = float(fallback[target])
            source = "fallback"
        elif method == "previous":
            idx = int(np.searchsorted(xs, x, side="right") - 1)
            value = float(ys[idx])
            source_issues = [points[point_times[idx]][1]]
            source = "previous"
        else:
            right = int(np.searchsorted(xs, x, side="left"))
            if right < len(xs) and xs[right] == x:
                value = float(ys[right])
                source_issues = [points[point_times[right]][1]]
            else:
                left = right - 1
                weight = (x - xs[left]) / (xs[right] - xs[left])
                value = float(ys[left] + weight * (ys[right] - ys[left]))
                source_issues = [points[point_times[left]][1], points[point_times[right]][1]]
            source = "linear"
        if source_issues and max(source_issues) > issue_time:
            raise AssertionError("预测展开使用了尚未发布的批次")
        rows.append(
            {
                "issue_time": issue_time,
                "target_time": target,
                "pv_forecast": max(value, 0.0),
                "method": method,
                "source": source,
                "source_issue_max": max(source_issues) if source_issues else None,
            }
        )
    return pd.DataFrame(rows)
