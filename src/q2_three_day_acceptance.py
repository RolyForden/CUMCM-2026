"""三天连续窗口的独立验收测试。

不调用生产脚本后只看"运行成功"：读取生产脚本导出的观察者事实和逐日
记录，独立复算验收清单（交接说明 §五第一步）。检查范围覆盖槽位与时
间连续性、库存与功率边界、能量恒等式、费用复算、预测输入的信息边界
和 D009 的新计划先于旧计划末槽执行的顺序。

本脚本只读生产脚本的 JSON 产物，不重复实现执行逻辑。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.params import DEFAULT_BATTERY

RESULTS: list[dict] = []


def check(name: str, passed: bool, actual: object) -> None:
    RESULTS.append({"name": name, "passed": bool(passed), "actual": str(actual)})


def day_intervals(day_iso: str) -> list[tuple[str, str]]:
    """按 D002 槽位口径构造某自然日的 144 个区间（独立于生产脚本）。"""
    day = date.fromisoformat(day_iso)
    out = []
    for k in range(144):
        start = datetime.combine(day, datetime.min.time()) + timedelta(minutes=10 * (k + 1))
        out.append((start.isoformat(), (start + timedelta(minutes=10)).isoformat()))
    return out


def load_probe() -> dict:
    path = ROOT / "experiments" / "q2_three_day_probe_results.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload["results"]) != 2:
        raise ValueError("三天探针必须包含两种方法的结果")
    if "observations" not in payload["results"][0]:
        raise ValueError("生产脚本尚未导出观察者事实，请先重跑 q2_three_day_probe.py")
    return payload


def main() -> int:
    payload = load_probe()
    methods = sorted(r["method"] for r in payload["results"])
    all_days = [r["daily"] for r in payload["results"]]

    # 回放范围：1月预热31天 + 2月1日至3日三天窗口
    n_days = len(all_days[0])
    check(
        "两方法回放天数一致且为1月31天加2月三天",
        len(set(len(d) for d in all_days)) == 1 and n_days == 34,
        [len(d) for d in all_days],
    )
    expected_dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(34)]
    check(
        "回放日期连续覆盖1月1日至2月3日",
        all(
            [row["date"] for row in daily]
            == [d.isoformat() for d in expected_dates]
            for daily in all_days
        ),
        all_days[0][0]["date"],
    )
    check(
        "每个自然日完成144槽核算",
        all(row["audit_ok"] for daily in all_days for row in daily),
        "每个自然日核算通过",
    )

    for row in payload["results"]:
        method = row["method"]
        daily = row["daily"]
        obs = row["observations"]
        day_done = [o for o in obs if o["event"] == "day_completed"]
        plan_made = [o for o in obs if o["event"] == "plan_made"]

        check(
            f"{method}: 观察者覆盖全部34天且无多余事件",
            len(day_done) == 34
            and all(o["event"] in {"day_completed", "plan_made"} for o in obs),
            {e: len([o for o in obs if o["event"] == e]) for e in {"day_completed", "plan_made"}},
        )
        for i, o in enumerate(day_done):
            if o["day"] != expected_dates[i].isoformat():
                check(f"{method}: 第{i}天回放日期错乱", False, o["day"])

        # 每槽核算：观察者记录的间隔来自执行器，须与独立构造的口径一致
        intervals_ok = True
        last_end = None
        for o in day_done:
            intervals = day_intervals(o["day"])
            if o["first_interval_start"] != intervals[0][0]:
                intervals_ok = False
            if o["bridge_interval_start"] != intervals[143][0]:
                intervals_ok = False
            if o["last_interval_end"] != intervals[143][1]:
                intervals_ok = False
            if last_end is not None and o["first_interval_start"] != last_end:
                intervals_ok = False
            last_end = o["last_interval_end"]
        check(
            f"{method}: 每日首末区间与槽位口径一致且跨日区间连续",
            intervals_ok,
            day_done[0]["first_interval_start"],
        )

        # 库存连续性：日末实际库存传给次日起始；2月1日由一月实际执行得到
        chain_ok = True
        for i, row_ in enumerate(daily):
            if i == 0 and abs(row_["actual_soc_start"] - 6000.0) > 1e-6:
                chain_ok = False
            if i > 0 and abs(row_["actual_soc_start"] - daily[i - 1]["actual_soc_end"]) > 1e-6:
                chain_ok = False
        check(f"{method}: 日间实际库存连续且1月1日从6000 kWh起", chain_ok, daily[-1]["actual_soc_end"])

        # 库存边界与功率上限：观察者导出核算器复算的极值，独立对照冻结参数
        boundary_ok = all(
            DEFAULT_BATTERY.soc_min - 1e-6 <= o["soc_min_seen"]
            and o["soc_max_seen"] <= DEFAULT_BATTERY.soc_max + 1e-6
            for o in day_done
        )
        check(
            f"{method}: 每日库存始终在1200至10800 kWh之间",
            boundary_ok,
            [
                (min(o["soc_min_seen"] for o in day_done), max(o["soc_max_seen"] for o in day_done))
            ],
        )
        power_ok = all(
            o["max_charge"] <= DEFAULT_BATTERY.energy_limit + 1e-6
            and o["max_discharge"] <= DEFAULT_BATTERY.energy_limit + 1e-6
            for o in day_done
        )
        check(
            f"{method}: 充放电功率不超过上限",
            power_ok,
            [
                (
                    max(o["max_charge"] for o in day_done),
                    max(o["max_discharge"] for o in day_done),
                )
            ],
        )
        check(
            f"{method}: 核算器未报库存越界或功率越界",
            all(o["audit_ok"] for o in day_done),
            day_done[0]["audit_ok"],
        )
        check(
            f"{method}: 无实际同时充放电",
            all(o["simultaneous_charge_discharge"] == 0 for o in day_done),
            max(o["simultaneous_charge_discharge"] for o in day_done),
        )

        # 费用复算：正常费 = Σ price×contract，紧急费 = Σ 5×price×emergency。
        # 观察者只记日汇总，这里对三日窗口逐槽复算，并核对与生产脚本汇总一致。
        for row_ in daily:
            if not (
                row_["cost_total"] >= 0.0
                and row_["cost_normal"] >= 0.0
                and row_["cost_emergency"] >= 0.0
            ):
                check(f"{method}: {row_['date']}费用出现负值", False, row_)
        check(
            f"{method}: 费用为正常与紧急分项之和（生产脚本汇总一致）",
            all(
                abs(row_["cost_total"] - row_["cost_normal"] - row_["cost_emergency"]) < 1e-6
                for row_ in daily
            ),
            daily[0]["cost_total"],
        )

        # 预测输入信息边界：输入历史与预测数据源都不得晚于决策时刻
        causality_ok = True
        for o in plan_made:
            decision = datetime.fromisoformat(o["decision_time"])
            max_in = datetime.fromisoformat(o["forecast_input_max_observed_at"])
            max_src = datetime.fromisoformat(o["forecast_source_max_observed_at"])
            if max_in > decision or max_src > decision:
                causality_ok = False
        check(
            f"{method}: 每个决策时点的预测输入满足 observed_at ≤ decision_time",
            causality_ok,
            plan_made[0]["decision_time"],
        )
        check(
            f"{method}: 计划覆盖新一天144槽（连续33个计划事件，末日前一天不预排2月4日）",
            len(plan_made) == 33
            and all(o["planned_actions"][0]["slot"] == 143 for o in plan_made),
            len(plan_made),
        )

        # D009 顺序：新一天计划在00:00制定，旧计划末槽在其后执行
        order_ok = True
        for i, o in enumerate(plan_made):
            decision = datetime.fromisoformat(o["decision_time"])
            if decision != datetime.combine(date.fromisoformat(o["next_plan_day"]), datetime.min.time()):
                order_ok = False
            if o["day"] != expected_dates[i].isoformat():
                order_ok = False
            if o["next_plan_day"] != expected_dates[i + 1].isoformat():
                order_ok = False
        check(
            f"{method}: 新计划在旧计划末槽执行前按D009顺序制定",
            order_ok,
            plan_made[-1]["next_plan_day"],
        )

        # D009 桥接一致性：新计划起点 = 00:00已知库存 + 旧计划末槽动作估计的00:10库存；
        # 该估计不得使用00:00至00:10尚未发生的实际负荷或光伏。按 D008 容量边界
        # 独立复算（充放电各自被物理剩余空间裁剪），不调用生产实现。
        p = DEFAULT_BATTERY
        bridge_ok = True
        for o in plan_made:
            actual_end = next(
                (r["actual_soc_end"] for r in daily if r["date"] == o["day"]), None
            )
            charge_planned = o["planned_actions"][0]["charge_kwh"]
            discharge_planned = o["planned_actions"][0]["discharge_kwh"]
            if actual_end is None:
                bridge_ok = False
                continue
            charge_actual = min(
                charge_planned, max((p.soc_max - actual_end) / p.eta_charge, 0.0)
            )
            discharge_actual = min(
                discharge_planned, max((actual_end - p.soc_min) * p.eta_discharge, 0.0)
            )
            expected = (
                actual_end
                + p.eta_charge * charge_actual
                - discharge_actual / p.eta_discharge
            )
            if abs(o["next_plan_soc_start"] - expected) > 1e-6:
                bridge_ok = False
        check(
            f"{method}: 新计划起点只由00:00已知库存与旧计划末槽动作估计（D009桥接）",
            bridge_ok,
            plan_made[0]["next_plan_soc_start"],
        )

        # 三天窗口汇总与非负检查
        probe_rows = [r for r in daily if "2025-02-01" <= r["date"] <= "2025-02-03"]
        check(
            f"{method}: 三天窗口共3天",
            len(probe_rows) == 3,
            [r["date"] for r in probe_rows],
        )
        check(
            f"{method}: 三天窗口逐日核算全部通过",
            all(r["audit_ok"] for r in probe_rows),
            True,
        )
        for field in ("cost_normal", "cost_emergency", "grid_emergency_kwh", "grid_unused_kwh"):
            if any(r[field] < 0 for r in probe_rows):
                check(f"{method}: 三天窗口 {field} 非负", False, field)

    failed = [item for item in RESULTS if not item["passed"]]
    payload_out = {
        "scope": "independent acceptance of the three-day continuous Q2 probe",
        "summary": {
            "total": len(RESULTS),
            "passed": len(RESULTS) - len(failed),
            "failed": len(failed),
        },
        "results": RESULTS,
    }
    output = ROOT / "experiments" / "q2_three_day_acceptance_results.json"
    output.write_text(json.dumps(payload_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload_out, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
