"""第二问保守计划候选的因果性与单调性测试。

只测试已冻结的因果边界和分位定义，不选择最终保守等级，也不运行整年。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.q2_conservative import (
    CONSERVATIVE_LEVELS,
    conservative_plan_forecast,
    residual_pool_by_slot,
)


RESULTS: list[dict] = []


def check(name: str, passed: bool, actual: object) -> None:
    RESULTS.append({"name": name, "passed": bool(passed), "actual": str(actual)})


def synthetic_history(decision: datetime, days: int = 120) -> pd.DataFrame:
    """构造决策时刻之前若干天的实际值：负荷带随机但有偏误差，光伏白天非零。"""
    rng = np.random.default_rng(20250912)
    rows = []
    start = decision.date() - timedelta(days=days)
    for offset in range(days):
        day = start + timedelta(days=offset)
        for slot in range(144):
            interval_start = datetime.combine(day, datetime.min.time()) + timedelta(
                minutes=10 * (slot + 1)
            )
            observed_at = interval_start + timedelta(minutes=10)
            # 负荷：基础 1000，叠加与槽位相关的确定性偏差，制造非零残差分位
            load = 1000.0 + 3.0 * slot + 40.0 * (slot % 7) + rng.normal(0, 20)
            pv = max(0.0, 400.0 * np.sin(np.pi * (slot - 30) / 84) + rng.normal(0, 15))
            rows.append(
                {
                    "date": day,
                    "slot": slot,
                    "valid_time": interval_start,
                    "observed_at": observed_at,
                    "load_actual": float(max(0.0, load)),
                    "pv_actual": float(pv),
                }
            )
    return pd.DataFrame(rows)


def main() -> int:
    decision = datetime(2025, 2, 1)
    history = synthetic_history(decision)
    history = history[history["observed_at"] <= decision].copy()
    target = date(2025, 2, 1)

    point = conservative_plan_forecast(
        "D-7", history, target, decision, "point"
    )
    check(
        "point 等级等于七天前点预测本身",
        len(point) == 144 and (point.plan_level == "point").all(),
        point.plan_level.iloc[0],
    )
    check("point 不读取未来", point.source_max_observed_at.max() <= decision, point.source_max_observed_at.max())

    pool = residual_pool_by_slot("D-7", history, decision, lookback_days=21)
    total = sum(pool["load"][k].size for k in range(144))
    check("残差池按槽收集且只含已观测日", total > 0, total)

    # 因果：把决策时刻之后的实际值追加进来，残差池不应变化
    future_rows = []
    for offset in (1, 2):
        day = target + timedelta(days=offset)
        for slot in range(144):
            interval_start = datetime.combine(day, datetime.min.time()) + timedelta(
                minutes=10 * (slot + 1)
            )
            future_rows.append(
                {
                    "date": day,
                    "slot": slot,
                    "valid_time": interval_start,
                    "observed_at": interval_start + timedelta(minutes=10),
                    "load_actual": 9999.0,
                    "pv_actual": 9999.0,
                }
            )
    tampered = pd.concat([history, pd.DataFrame(future_rows)], ignore_index=True)
    pool_tampered = residual_pool_by_slot("D-7", tampered, decision, lookback_days=21)
    same = all(
        np.allclose(pool["load"][k], pool_tampered["load"][k]) for k in range(144)
    )
    check("追加决策时刻之后的实际值不改变残差池（无未来泄漏）", same, same)

    # 分位单调性：0.7 <= 0.8 <= 0.9 的负荷计划值逐槽单调不减
    plans = {
        level: conservative_plan_forecast("D-7", history, target, decision, level)
        for level in ("0.7", "0.8", "0.9")
    }
    mono07_08 = (plans["0.8"].load_forecast >= plans["0.7"].load_forecast - 1e-9).all()
    mono08_09 = (plans["0.9"].load_forecast >= plans["0.8"].load_forecast - 1e-9).all()
    check("分位越高负荷计划越高（0.7≤0.8≤0.9）", mono07_08 and mono08_09, (mono07_08, mono08_09))

    # 分位方案相对点预测上调负荷均值（保守）
    diff = (
        plans["0.8"].load_forecast - point.load_forecast
    ).mean()
    check("0.8 分位相对点预测抬高负荷计划", diff > 0, diff)

    # 非负：分位调整后不产生负负荷/负光伏
    for level, frame in plans.items():
        if (frame[["load_forecast", "pv_forecast"]] < 0).any().any():
            check(f"{level} 分位调整后非负", False, level)
    check("所有分位调整后负荷与光伏非负", True, CONSERVATIVE_LEVELS)

    # 残差不足时退回点预测：从回看窗口内删除槽100（保留 D-7 基础值），
    # 该槽残差池为空，应退回点预测而非静默填零。
    gap = history[
        ~(
            (history["valid_time"].dt.date >= decision.date() - timedelta(days=5))
            & (history["slot"] == 100)
        )
    ].copy()
    fallback = conservative_plan_forecast(
        "D-7", gap, target, decision, "0.9", lookback_days=5
    )
    point_gap = conservative_plan_forecast(
        "D-7", gap, target, decision, "point"
    )
    check(
        "残差不足的槽退回点预测而非静默填零",
        len(fallback) == 144
        and abs(
            float(fallback.iloc[100]["load_forecast"])
            - float(point_gap.iloc[100]["load_forecast"])
        )
        < 1e-9
        and (fallback[["load_forecast", "pv_forecast"]] >= 0).all().all(),
        float(fallback.residual_slots_used.iloc[0]),
    )

    failed = [item for item in RESULTS if not item["passed"]]
    payload = {
        "scope": "Q2 conservative plan candidates: causality and monotonicity only",
        "summary": {"total": len(RESULTS), "passed": len(RESULTS) - len(failed), "failed": len(failed)},
        "results": RESULTS,
    }
    output = ROOT / "experiments" / "q2_conservative_candidate_results.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
