"""探针测试与运行脚本（单文件，无 pytest 依赖，退出码 0 = 全绿）。

按 tasks/TASK_C_probe_timing.md + TASK_C_probe_model_corrections.md §6 实现：
T1 槽位适配器基础（标签解析、slot_id 主键）
T2 单槽位脉冲测试（首/中/尾三槽，识别整体平移）
T3 弃光来源测试（富余弃光合法）
T4 禁止弃光吞购电（光伏为 0 时强塞余电应不可行）
T5 跨日边界 + 模板回读（23:50/0:00+1 槽位）
T6 小窗口 LP vs 独立核算器对拍 + 规则法下界
T7 Q1 全日回归锚点（双引擎对拍 35126.948589）

报告写 experiments/probe_timing.md；任何一项失败 → 退出码 1。
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import accountant as acct
from core import data_io, executor, template_io
from core import lp_kernel as lp
from core.slot_adapter import (
    N_SLOTS,
    build_day_slots,
    slot_id_from_input_label,
    template_column_label,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    if not cond:
        print(f"  [FAIL] {name}: {detail}")


# ---------------------------------------------------------------- T1 适配器
def t1_adapter() -> None:
    day = date(2025, 1, 1)
    slots = build_day_slots(day)
    check("T1 每天恰 144 槽", len(slots) == 144, f"got {len(slots)}")
    check(
        "T1 slot_id 连续且主键唯一",
        [s.slot_id for s in slots] == list(range(144)),
    )
    check(
        "T1 槽位区间首尾（冻结映射 A）",
        slots[0].interval_start.strftime("%H:%M") == "00:10"
        and slots[0].template_interval == "0:10-0:20"
        and slots[142].template_interval == "23:50-0:00+1"
        and slots[143].template_interval == "0:00+1-0:10+1",
        f"{slots[0].template_interval} / {slots[143].template_interval}",
    )
    check("T1 跨日槽只有 23:50-0:00+1 一格", sum(s.is_cross_day for s in slots) == 1)
    check("T1 次日槽只有 0:00+1-0:10+1 一格", sum(s.is_next_day_slot for s in slots) == 1)
    # 标签解析：官方输入标签 → slot_id（起点对齐，无平移）
    check("T1 00:10 → slot 0", slot_id_from_input_label("00:10", day) == 0)
    check("T1 23:50 → slot 142", slot_id_from_input_label("23:50", day) == 142)
    check("T1 0:00+1 → slot 143", slot_id_from_input_label("0:00+1", day) == 143)
    check(
        "T1 0:00+1 解析为次日 0:00",
        slots[143].interval_start.date() == date(2025, 1, 2),
        f"{slots[143].interval_start}",
    )
    check(
        "T1 模板标签首尾",
        slots[0].template_interval == "0:10-0:20"
        and slots[143].template_interval == "0:00+1-0:10+1",
        f"{slots[0].template_interval} / {slots[143].template_interval}",
    )
    # 官方输入表没有 00:00 列：遇之必须报错而不是平移
    raised = False
    try:
        slot_id_from_input_label("00:00", day)
    except ValueError:
        raised = True
    check("T1 非官方标签 00:00 被拒绝", raised)
    # 与官方输入表标签逐列比对（按解析后的时间值比较，官方表 '00:10:00'
    # 带秒、末行 '0:00+1' 不带秒，字符串格式本身不一致）
    labels = data_io._time_labels_xlsx_1(
        "data/raw/official/附件1.xlsm", "Sheet1 (2)"
    )
    from core.slot_adapter import parse_input_time_label
    ok = True
    for k in range(144):
        try:
            t = parse_input_time_label(labels[k], day)
        except ValueError:
            ok = False
            check("T1 官方输入表头对齐", False, f"col {k}: 无法解析 {labels[k]!r}")
            break
        if t != slots[k].interval_start:
            ok = False
            check("T1 官方输入表头对齐", False, f"col {k}: {labels[k]!r} → {t} vs {slots[k].interval_start}")
            break
    if ok:
        check("T1 官方输入表头对齐", True)
    # 官方 result1 模板区间逐列比对（首列区间标签必须一致）
    import openpyxl
    wb = openpyxl.load_workbook(
        "data/raw/official/附件5/result1.xlsm", read_only=True, data_only=True
    )
    ws = wb[wb.sheetnames[-1]]
    rows = list(ws.iter_rows(min_row=1, max_row=145, values_only=True))
    wb.close()
    tmpl_ok = True
    for k in range(144):
        if str(rows[k + 1][0]).strip() != slots[k].template_interval:
            tmpl_ok = False
            check(
                "T1 官方 result1 区间标签对齐",
                False,
                f"row {k}: {rows[k+1][0]!r} vs {slots[k].template_interval!r}",
            )
            break
    if tmpl_ok:
        check("T1 官方 result1 区间标签对齐", True)


# ---------------------------------------------------------------- T2 脉冲测试
def t2_pulse() -> None:
    """单槽位脉冲：只有被测槽有负荷，验证负荷/价格/模板列落在同一 slot_id。

    手工可算：单槽负荷 100 kWh、价格 p、无光伏、E0=6000 充足 →
    该槽购电 100，费用 100p。若整体平移一格，则费用落在相邻槽。
    """
    day = date(2025, 1, 1)
    slots = build_day_slots(day)
    n = N_SLOTS
    for k in (0, 71, 143):  # 首、中、尾（含跨日槽 143）
        price = np.full(n, 1.0)
        price[k] = 0.5  # 不同槽不同电价
        load = np.zeros(n)
        load[k] = 100.0
        pv = np.zeros(n)
        sol = lp.solve_lp(lp.LpInputs(price=price, load=load, pv_available=pv,
                                      soc0=6000.0, soc_final=6000.0))
        ok_cost = abs(sol.grid[k] - 100.0) < 1e-4 and abs(sol.cost - 50.0) < 1e-4
        ok_else = np.sum(sol.grid) - sol.grid[k] < 1e-4
        check(
            f"T2 单槽脉冲 slot {k}（购电落在被测槽且费用=50）",
            ok_cost and ok_else,
            f"grid[{k}]={sol.grid[k]:.6f} cost={sol.cost:.9f}",
        )


# ---------------------------------------------------------------- T3 弃光来源
def t3_curtail_source() -> None:
    """光伏富余、电池已满、负荷很低：允许 pv_curtail>0；购电必须为 0；
    pv_curtail ≤ pv_available。"""
    n = 4
    price = np.full(n, 1.0)
    load = np.full(n, 50.0)
    pv = np.full(n, 300.0)
    soc0 = 10800.0  # 电池已满
    sol = lp.solve_lp(lp.LpInputs(price=price, load=load, pv_available=pv,
                                  soc0=soc0, soc_final=10800.0))
    check("T3 富余弃光可行", sol.status == 0, sol.message)
    check(
        "T3 弃光>0 且 购电=0",
        np.all(sol.pv_curtail > 0.5) and np.all(sol.grid < 1e-3),
        f"curtail={sol.pv_curtail} grid={sol.grid}",
    )
    check(
        "T3 curtail ≤ available",
        np.all(sol.pv_curtail <= pv + 1e-9),
    )
    check(
        "T3 弃光恒等式",
        np.allclose(sol.pv_used + sol.pv_curtail, pv, atol=1e-9),
    )


# ---------------------------------------------------------------- T4 禁吞购电
def t4_no_swallow() -> None:
    """光伏为 0、负荷 50、强制外网受电 100、电池已满：
    弃光路径（v ≤ pv_available = 0）结构上不可能吞掉多余购电——
    v 必须为 0。松弛 LP 若仍可行，只能靠"同时充放电"制造假出口
    （电池循环损耗），该解必须被独立审计器拒绝
    （simultaneous_charge_discharge > 0）。"""
    from scipy.optimize import linprog

    nv = 5  # g, v, w(弃光=可用-使用，隐含), c, d —— 与内核一致：v ≤ pv 即弃光受限
    c_obj = np.array([1.0, 0, 0, 0, 0])
    # 平衡式与内核一致：g + v + d − c = l → [1, 1, 0, -1, 1]
    A_eq = np.array([[1.0, 1.0, 0, -1.0, 1.0]])
    b_eq = np.array([50.0])
    A_ub = []
    b_ub = []
    A_ub.append([0, 1.0, 0, 0, 0]); b_ub.append(0.0)   # v ≤ pv = 0 ← 弃光只能来自光伏
    A_ub.append([0, 0, 0, 1.0, 0]); b_ub.append(lp.C_MAX)  # c ≤ C_MAX
    A_ub.append([0, 0, 0, 0, 1.0]); b_ub.append(lp.C_MAX)  # d ≤ C_MAX
    A_ub.append([0, 0, 0, lp.ETA_C, -1.0 / lp.ETA_D]); b_ub.append(0.0)  # SOC 上界（E 已满）
    bounds = [(100.0, 100.0), (0, None), (0, None), (0, None), (0, None)]  # g 固定 100
    res = linprog(c_obj, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs-ds")
    if res.success:
        g, v, w, c, d = res.x
        check(
            "T4 弃光路径不吞购电（光伏为 0 时 v=0）",
            v < 1e-9,
            f"v={v:.9f}",
        )
        # 松弛 LP 可行 ⟺ 同时充放电（假出口）。审计器必须拒绝。
        is_cycling = c > 1e-6 and d > 1e-6
        check(
            "T4 松弛解只能靠同时充放电可行 → 审计拒绝",
            is_cycling,
            f"c={c:.6f} d={d:.6f}（若 c、d 不同时>0，说明存在其他未建模出口，需排查）",
        )
        if is_cycling:
            # 用该解构造执行记录，独立审计器必须报同时充放电
            from datetime import datetime
            day = date(2025, 1, 1)
            slots = build_day_slots(day)
            recs = executor.execute_q1(
                plan=np.array([g]),
                price=np.array([1.0]),
                load=np.array([50.0]),
                pv=np.array([0.0]),
                charge=np.array([c]),
                discharge=np.array([d]),
                soc0=10800.0,
                starts=[slots[0].interval_start],
                ends=[slots[0].interval_end],
                plan_issue_time=datetime(2025, 1, 1, 0, 0),
            )
            audit = acct.audit(recs)
            check(
                "T4 审计器标记同时充放电",
                audit.simultaneous_charge_discharge == 1,
                f"n_simul={audit.simultaneous_charge_discharge}",
            )
    else:
        # 若不可行，也接受：说明约束直接拒绝，更严格
        check("T4 弃光路径不吞购电（光伏为 0 时 v=0）", True, "模型直接不可行")
        check("T4 松弛解只能靠同时充放电可行 → 审计拒绝", True, "模型直接不可行，无需审计")


# ---------------------------------------------------------------- T5 跨日 + 回读
def t5_cross_day_roundtrip() -> None:
    """跨日边界窗口 23:30–0:10+1（槽 k=141,142,143）+ 模板写读一致。"""
    day = date(2025, 1, 1)
    slots = build_day_slots(day)
    # 日期推进：槽 142 区间 23:50→次日 0:00；槽 143 完全落在次日
    check(
        "T5 跨日槽日期推进",
        slots[141].interval_end.date() == date(2025, 1, 1)
        and slots[142].interval_end.date() == date(2025, 1, 2)
        and slots[143].interval_start.date() == date(2025, 1, 2),
    )
    check(
        "T5 0:00+1 不重复不遗漏",
        [s.source_label for s in slots].count("0:00+1") == 1
        and [s.template_interval for s in slots].count("23:50-0:00+1") == 1
        and [s.template_interval for s in slots].count("0:00+1-0:10+1") == 1,
    )
    # 模板写读
    grid = [float(k) for k in range(144)]  # 可辨识的槽位值
    path = "data/processed/_probe_result1_roundtrip.xlsx"
    template_io.write_result1_plan(path, day, grid)
    back = template_io.read_result1_plan(path, day)
    check(
        "T5 模板回读 144 槽逐列一致",
        len(back) == 144 and all(abs(a - b) < 1e-9 for a, b in zip(back, grid)),
    )
    # 故意错位应被拒绝：读入一个平移一格的标签必须报错
    import openpyxl
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    ws.cell(row=2, column=1, value="0:20-0:30")  # 把 slot0 的标签改成平移一格
    wb.save("data/processed/_probe_result1_corrupt.xlsx")
    rejected = False
    try:
        template_io.read_result1_plan("data/processed/_probe_result1_corrupt.xlsx", day)
    except ValueError:
        rejected = True
    check("T5 错位标签被拒绝", rejected)


# ---------------------------------------------------------------- T6 小窗口对拍
def t6_small_window() -> None:
    """3 时段小窗口（含跨日槽 142 与次日槽 143）：LP 目标值 == 核算器复算值；
    规则法 ≥ LP。"""
    price = np.array([0.5, 1.0, 1.5])
    load = np.array([400.0, 500.0, 300.0])
    pv = np.array([0.0, 200.0, 0.0])
    soc0 = 6000.0
    sol = lp.solve_lp(lp.LpInputs(price=price, load=load, pv_available=pv,
                                  soc0=soc0, soc_final=6000.0))
    check("T6 小窗口 LP 可行", sol.status == 0, sol.message)
    day = date(2025, 1, 1)
    slots = build_day_slots(day)
    # 跨日窗口：k=141 [23:30,23:40), k=142 [23:50,0:00+1), k=143 [0:00+1,0:10+1)
    starts = [slots[k].interval_start for k in (141, 142, 143)]
    ends = [slots[k].interval_end for k in (141, 142, 143)]
    recs = executor.execute_q1(
        plan=sol.grid,
        price=price,
        load=load,
        pv=pv,
        charge=sol.charge,
        discharge=sol.discharge,
        soc0=soc0,
        starts=starts,
        ends=ends,
        plan_issue_time=datetime(2025, 1, 1, 0, 0),
    )
    audit = acct.audit(recs)
    check("T6 核算器全绿", audit.ok, str(audit.violations[:5]))
    check(
        "T6 优化器目标 == 核算器复算",
        abs(sol.cost - audit.cost_total) < 1e-6,
        f"{sol.cost:.9f} vs {audit.cost_total:.9f}",
    )
    # 规则法 baseline 要满足同一终端约束（E_n = E_0）：先按规则跑，
    # 末段缺口用购电补齐、富余用弃光吸收，保证可比。
    r_cost, r_socs, r_grid = lp.rule_based_schedule(price, load, pv, soc0)
    final_e = r_socs[-1]
    if final_e < soc0:
        # 规则法末段购电补齐到 soc0（单价 = 该段电价）
        r_cost += price[-1] * (soc0 - final_e)
    check(
        "T6 规则法 ≥ LP",
        r_cost + 1e-9 >= sol.cost,
        f"rule={r_cost:.6f} lp={sol.cost:.6f}",
    )
    check(
        "T6 无同时充放电",
        audit.simultaneous_charge_discharge == 0,
    )
    check("T6 能量残差 < 1e-9", audit.max_residual < 1e-9, f"{audit.max_residual:.3e}")


# ---------------------------------------------------------------- T7 Q1 全日回归
def t7_q1_full_day() -> None:
    """冻结口径 Q1 全日 144 时段，双引擎对拍锚点 35126.948589。"""
    day = date(2025, 1, 1)
    as_of = datetime(2026, 9, 11, 12, 0)
    df = data_io.build_q1_inputs(day, as_of)
    inp = lp.LpInputs(
        price=df["price"].to_numpy(),
        load=df["load_forecast"].to_numpy() * lp.DT,
        pv_available=df["pv_forecast"].to_numpy() * lp.DT,
        soc0=6000.0,
        soc_final=6000.0,
    )
    sols = {}
    for engine in ("highs-ds", "highs-ipm"):
        sols[engine] = lp.solve_lp(inp, solver=engine)
        check(f"T7 Q1 {engine} 可行", sols[engine].status == 0, sols[engine].message)
    check(
        "T7 Q1 双引擎费用一致",
        abs(sols["highs-ds"].cost - sols["highs-ipm"].cost) < 1e-6,
        f"{sols['highs-ds'].cost:.9f} vs {sols['highs-ipm'].cost:.9f}",
    )
    check(
        "T7 Q1 锚点 35126.948589",
        abs(sols["highs-ds"].cost - 35126.948589) < 1e-4,
        f"{sols['highs-ds'].cost:.9f}",
    )
    # 独立核算器对拍
    slots = build_day_slots(day)
    recs = executor.execute_q1(
        plan=sols["highs-ds"].grid,
        price=inp.price,
        load=inp.load,
        pv=inp.pv_available,
        charge=sols["highs-ds"].charge,
        discharge=sols["highs-ds"].discharge,
        soc0=6000.0,
        starts=[s.interval_start for s in slots],
        ends=[s.interval_end for s in slots],
        plan_issue_time=as_of,
    )
    audit = acct.audit(recs)
    check("T7 Q1 核算器全绿", audit.ok, str(audit.violations[:5]))
    check(
        "T7 Q1 目标==核算",
        abs(sols["highs-ds"].cost - audit.cost_total) < 1e-6,
        f"{sols['highs-ds'].cost:.9f} vs {audit.cost_total:.9f}",
    )
    check("T7 Q1 最大残差 ~1e-13", audit.max_residual < 1e-9, f"{audit.max_residual:.3e}")
    check(
        "T7 Q1 首尾 SOC 相等（E_144 = E_0）",
        abs(recs[0].soc_start - recs[-1].soc_end) < 1e-6,
        f"{recs[0].soc_start} vs {recs[-1].soc_end}",
    )
    # 敏感性对照：终端约束作用于 E_143（槽 142 后，即 24:00 时刻）
    # 目的：量化"144 槽周期首尾相等"与"0:00/24:00 相等"两种读法的差异，
    # 确认冻结口径（D002 P0-2）的数值后果，供人类复核。
    alt = lp.solve_lp(
        lp.LpInputs(price=inp.price, load=inp.load, pv_available=inp.pv_available,
                    soc0=6000.0, soc_final=6000.0, soc_final_slot=142),
        solver="highs-ds",
    )
    if alt.status == 0:
        print(f"  [INFO] E_143=E_0 对照费用 = {alt.cost:.9f} 元"
              f"（主口径 E_144=E_0 = {sols['highs-ds'].cost:.9f} 元，"
              f"差 {alt.cost - sols['highs-ds'].cost:+.6f} 元）")


def main() -> int:
    print("== C 题探针：槽位适配器 + 最小 LP + 独立核算 ==")
    t1_adapter()
    t2_pulse()
    t3_curtail_source()
    t4_no_swallow()
    t5_cross_day_roundtrip()
    t6_small_window()
    t7_q1_full_day()
    n_fail = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"\n共 {len(RESULTS)} 项检查，失败 {n_fail}")
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAIL {name}: {detail}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
