# 当前状态

阶段：SOLVING

状态：原探针 41/41 保留为整改前基线；整改提交 `7464ccc` 的主探针 48/48、独立交叉验证 39/39 均通过。N4 已由 D003 解除；N1/N2 已按 D007 完成前置合成反例，N3 已完成只读因果验证但点到10分钟展开仍未裁决，继续阻塞预测驱动滚动窗口。

结论：人类已在D003选择方案A；Q1执行—核算—官方模板链已重新认证，主口径费用为35126.948590元。**Q1正式结果已完成系统验证并写入论文 LaTeX 正文（2026-09-12）。**

## 当前硬闸门

- 不运行 Q2–Q4 全年正式模型。
- 不修改 D002 既有口径；D004-D006 保留为复审前裁决稿，冲突处由 D007 覆盖。
- N1/N2 文档口径按 D007 修订后冻结；D007 前置合成反例 17/17 已通过。
- Q2 三天窗口需 N1 接口测试通过且 Q2 光伏预测口径明确后才允许。
- Q3 纯结算账本测试已由 N2 前置反例放行，但仅限结算账本，不得接入预测驱动滚动。
- Q3 预测驱动滚动窗口需 N3 重裁后才允许。

## 当前证据

- 整改前提交：`2250523`；历史报告：`experiments/probe_timing.md`（41/41，仅作基线）。
- 整改代码提交：`7464ccca35ad5a0eb454d0441fb6e051264e1582`。
- 整改后主探针：`src/probe_timing.py`，48/48。
- 独立交叉验证：`src/probe_cross_validation.py`，39/39；逐项输出：`experiments/probe_cross_validation_results.json`。
- 审查报告：`research/C_probe_cross_validation.md`。
- N4 人类裁决记录：DECISIONS.md D003；说明材料：`research/C_time_boundary_decision.md`。
- N1-N3 复审记录：DECISIONS.md D007；审查材料：`research/C_N1_N3_decision_review.md`；修订说明：`research/C_q2_surplus_contract_decision.md`、`research/C_q3_settlement_decision.md`、`research/C_forecast_mapping_decision.md`。
- D007 前置反例与只读验证：`src/d007_prewindow_tests.py`，17/17；逐项输出：`experiments/d007_prewindow_results.json`；报告：`research/C_D007_prewindow_report.md`。
- Q1 定稿验证：`src/validate_q1.py`、`outputs/q1_validation/q1_validation_summary.json`、`research/C_q1_validation.md`；覆盖逐槽复算、导出一致性、显式互斥 MILP、参数敏感性和 60 次输入扰动。
- Q1 正式结果生成审计：`src/generate_q1_result.py`、`outputs/q1_scheme_a/q1_audit.json`；生成期 16 项检查 + 重开 8 项检查均通过。
- 论文 latex 模板已从已验证模板迁入 `paper/`（cumcmthesis.cls、字体、figures、code、ref.bib）；Q1 正文写入 `paper/数模通用模板.tex`，xelatex 编译通过（14 页无错误）。当前仓库不存在独立 `src/verify_q1_result.py` 及 `experiments/q1_cross_validation_*` 证据文件，故不再以“32/32独立交叉验证”作为当前证据。

## 下一步

1. ~~按方案A生成并回读审计Q1正式结果文件。~~ **已完成（2026-09-12）**：
   - 生成器 `src/generate_q1_result.py`：LP 双引擎求解 → 执行器 → 独立核算 → 官方模板原位填写（计划购电量 144 槽 + 按题面补齐“充放电量”表）→ 重开回读核验。
   - 产物 `outputs/q1_scheme_a/`：`result1.xlsm`、`q1_dispatch.csv`、`q1_paper_tables.json`（论文表 1/表 2）、`q1_audit.json`。
   - 验收：生成期 16 项 + 独立重开 8 项全过；主口径费用 **35126.948589390 元**；`probe_timing.py` 48/48 与 `probe_cross_validation.py` 39/39 复跑无回归。
2. ~~完成 Q1 结果验证与论文正文。~~ **已完成（2026-09-12）**：逐槽独立复算、显式互斥 MILP、参数敏感性和 60 次输入扰动均通过；正式 CSV 未修改。
3. **按 D007 进入下一步窄范围任务：**
   - N1：前置合成反例已通过；若要开 Q2 三天窗口，还需先完成执行接口单元测试并明确 Q2 光伏预测口径。
   - N2：前置账本反例已通过；下一步允许做 Q3 纯结算账本测试。
   - N3：只读验证已确认 `valid_time = issue_time + lead_hour`；下一步必须重裁点预测到10分钟展开，重裁前不得实现正式 Q3 预测适配器。
4. **禁止直接跑全年。** Q2-Q4 全年正式结果只能在上述闸门逐级通过后再启动。
