# 当前状态

阶段：SOLVING

状态：第一问、第二问已完成并冻结。第三问已完成附件3因果展开、四时点滚动优化、334天正式回放、独立核算、更新时点消融和论文正文；正式总费用15805751.77元，独立验证19/19通过。

结论：Q1、Q2、Q3均已形成可复现的正式结果、独立验证与论文正文；当前只等待人类命令决定是否进入Q4。

## 当前硬闸门

- 不重新运行或修改已冻结的 Q1/Q2/Q3 正式结果；Q4 尚未进入正式实现。
- 不修改 D002 既有口径；D004-D006 保留为复审前裁决稿，冲突处由 D007 覆盖。
- N1/N2 文档口径按 D007 修订后冻结；D007 前置合成反例 17/17 已通过。
- Q2 核算硬错误已修复；人类已在D008选择库存安全削减方案A，D009选择零点桥接方案A；执行与核算接口8/8通过。
- Q2严格因果预测候选接口已完成，8/8测试通过；已证明七天前和同星期日衰减平均可生成完整144槽，昨天同刻法在方案A末槽会使用尚未观测数据，当前明确拒绝。
- 人类已在D009选择零点桥接方案A：00:00先用已知库存和旧计划动作估计00:10库存制定新计划，再执行旧计划最后一槽；实际偏差由安全削减吸收。
- 一月15日至30日预测只读比较是历史筛选证据；正式策略已由D012冻结为D-7/point/rolling-7d。
- 人类已在D010选择冷启动方案A：1月1日用附件1典型日先验并正常调度，1月2日至7日用已观测同槽历史均值、缺槽继续用附件1，1月8日起启用历史候选。
- Q2 三天连续窗口（1月预热 + 2月1日至3日）已运行：两种预测候选三天总费用分别为142390.20元和143347.46元；独立验收 `src/q2_three_day_acceptance.py` 29/29 通过；计划层暂用每日首尾库存相等，两套方案一月末库存都顶到上限，该临时口径不能升格为全年正式规则。
- Q2 终端库存对照（D011）：plan-eq 把库存钉死上限；低终端价值抽空库存；滚动7天视野费用与轨迹最好。人类已裁决全年采用 rolling-7d。
- Q2 正式预测方法与保守程度（D012）：全年334天 rolling-7d 下，D-7 点预测总费用16,884,898元，低于同星期日衰减平均的17,296,323元；分位保守（0.7/0.8/0.9）反而比点预测更贵。已冻结 D-7/point/rolling-7d 为主口径。
- Q3 的 N3 已由D013重裁并实现；跨午夜24小时预测不截断回归4/4通过，单日 smoke 7/7通过。
- Q3 正式四时点回放与 `result3.xlsm` 已完成：334天总费用15805751.77元，紧急购电量809227.14 kWh，不可行天数0；独立验证19/19通过。
- Q3 更新消融表明6:00和12:00具有明确收益，18:00边际增费2.90元、贡献可忽略；当前无需再引入更密集的发布时间。

## 当前证据

- 整改前提交：`2250523`；历史报告：`experiments/probe_timing.md`（41/41，仅作基线）。
- 整改代码提交：`7464ccca35ad5a0eb454d0441fb6e051264e1582`。
- 整改后主探针：`src/probe_timing.py`，48/48。
- 独立交叉验证：`src/probe_cross_validation.py`，39/39；逐项输出：`experiments/probe_cross_validation_results.json`。
- 审查报告：`research/C_probe_cross_validation.md`。
- N4 人类裁决记录：DECISIONS.md D003；说明材料：`research/C_time_boundary_decision.md`。
- N1-N3 复审记录：DECISIONS.md D007；审查材料：`research/C_N1_N3_decision_review.md`；修订说明：`research/C_q2_surplus_contract_decision.md`、`research/C_q3_settlement_decision.md`、`research/C_forecast_mapping_decision.md`。
- D007 前置反例与只读验证：`src/d007_prewindow_tests.py`，17/17；逐项输出：`experiments/d007_prewindow_results.json`；报告：`research/C_D007_prewindow_report.md`。
- Q3 纯合成账本验证：`src/core/q3_ledger.py`、`src/q3_ledger_synthetic_tests.py`，9/9；逐项输出：`experiments/q3_ledger_synthetic_results.json`；报告：`research/C_Q3_pure_ledger_report.md`。
- Q3 正式结果：`outputs/q3/result3.xlsm`、`q3_dispatch.csv`、`q3_versions.csv`、`q3_daily_summary.csv`、`q3_replay_summary.json`；独立验证 `src/validate_q3_result.py` 19/19，报告 `research/C_Q3_validation_report.md`。
- Q3 更新时点消融：`src/q3_update_ablation.py`、`outputs/q3/q3_update_ablation.json`、`research/C_Q3_update_ablation_report.md`。
- Q2执行与核算接口：`src/core/executor.py`、`src/core/accountant.py`、`src/q2_accounting_tests.py`，8/8；输出 `experiments/q2_accounting_results.json`；报告 `research/C_Q2_accounting_interface_report.md`。
- Q2历史预测候选：`src/core/q2_forecast.py`、`src/q2_forecast_tests.py`，8/8；输出 `experiments/q2_forecast_candidate_results.json`；报告 `research/C_Q2_forecast_candidates_report.md`。
- Q2三天连续窗口：`src/q2_three_day_probe.py`（生产脚本）、`src/q2_three_day_acceptance.py`（独立验收29/29）；输出 `experiments/q2_three_day_probe_results.json`、`experiments/q2_three_day_acceptance_results.json`；报告 `research/C_Q2_three_day_probe_report.md`。
- Q1 定稿验证：`src/validate_q1.py`、`outputs/q1_validation/q1_validation_summary.json`、`research/C_q1_validation.md`；覆盖逐槽复算、导出一致性、显式互斥 MILP、参数敏感性和 60 次输入扰动。
- Q1 正式结果生成审计：`src/generate_q1_result.py`、`outputs/q1_scheme_a/q1_audit.json`；生成期 16 项检查 + 重开 8 项检查均通过。
- 论文 latex 模板已从已验证模板迁入 `paper/`（cumcmthesis.cls、字体、figures、code、ref.bib）；Q1 正文写入 `paper/数模通用模板.tex`，xelatex 编译通过（14 页无错误）。当前仓库不存在独立 `src/verify_q1_result.py` 及 `experiments/q1_cross_validation_*` 证据文件，故不再以“32/32独立交叉验证”作为当前证据。

## 下一步

1. ~~按方案A生成并回读审计Q1正式结果文件。~~ **已完成（2026-09-12）**：
   - 生成器 `src/generate_q1_result.py`：LP 双引擎求解 → 执行器 → 独立核算 → 官方模板原位填写（计划购电量 144 槽 + 按题面补齐“充放电量”表）→ 重开回读核验。
   - 产物 `outputs/q1_scheme_a/`：`result1.xlsm`、`q1_dispatch.csv`、`q1_paper_tables.json`（论文表 1/表 2）、`q1_audit.json`。
   - 验收：生成期 16 项 + 独立重开 8 项全过；主口径费用 **35126.948589390 元**；`probe_timing.py` 48/48 与 `probe_cross_validation.py` 39/39 复跑无回归。
2. ~~完成 Q1 结果验证与论文正文。~~ **已完成（2026-09-12）**：逐槽独立复算、显式互斥 MILP、参数敏感性和 60 次输入扰动均通过；正式 CSV 未修改。
3. **Q3 已闭环。** 后续只允许修复明确错误或进行提交前格式检查，不再扩展Q3模型和实验。
4. 下一建模任务为Q4；开始前须先复核电价信息集与结果模板，不得把未来真实电价泄漏给优化器。
