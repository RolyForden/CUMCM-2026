# TASK：D007 前置闸门反例与只读验证

- 状态：完成。
- 目标：按 `DECISIONS.md` D007，为 N1/N2/N3 建立进入小窗口前的证据。
- 输入：`DECISIONS.md` D007、`research/C_q2_surplus_contract_decision.md`、`research/C_q3_settlement_decision.md`、`research/C_forecast_mapping_decision.md`、附件3只读接口。
- 输出：`src/d007_prewindow_tests.py`、`experiments/d007_prewindow_results.json`、`research/C_D007_prewindow_report.md`。

## 边界

- 不运行 Q2-Q4 全年正式模型。
- 不实现正式 Q3 预测展开器。
- 不修改 `data/raw/`。
- 不改变 D002/D003；D004-D006 作为复审前裁决稿保留，当前有效口径以 D007 为准。

## 验收

- N1 合成反例覆盖零负荷、高光伏、高计划放电、合同严重过量、SOC边界与合同不足。
- N2 账本反例覆盖不调整、单次上调、单次下调、`100 -> 80 -> 100`、非法修改已执行槽、重复收费检测。
- N3 只读验证确认原始预测记录满足 `valid_time = issue_time + lead_hour`，并报告方案A末槽和发布后首小时的信息缺口。
- `python src/d007_prewindow_tests.py` 生成机器结果并全部通过。
- 原探针 `python src/probe_timing.py` 与 `python src/probe_cross_validation.py` 仍通过。

## 结果

- 执行脚本：`src/d007_prewindow_tests.py`。
- 机器输出：`experiments/d007_prewindow_results.json`。
- 人类报告：`research/C_D007_prewindow_report.md`。
- 当前结果：17/17 通过。
- 闸门结论：
  - N1 合成反例通过；Q2 三天窗口仍需补 Q2 光伏预测口径后才允许。
  - N2 账本反例通过；允许进入 Q3 纯结算账本测试。
  - N3 只读验证通过；点预测到10分钟展开仍未裁决，预测驱动 Q3 滚动窗口继续禁止。
  - Q2-Q4 全年正式运行继续禁止。
