# TASK：Q3 纯合成结算账本测试

- 状态：完成。
- 目标：只验证 Q3 多次修改计划时如何收费，不做完整 Q3。
- 输入：`DECISIONS.md` D007、`research/C_q3_settlement_decision.md`。
- 输出：`src/core/q3_ledger.py`、`src/q3_ledger_synthetic_tests.py`、`experiments/q3_ledger_synthetic_results.json`、`research/C_Q3_pure_ledger_report.md`。

## 边界

- 不接入附件3预测。
- 不调用预测适配器。
- 不做滚动窗口。
- 不运行 Q2-Q4 全年正式模型。
- 不修改 `data/raw/`。

## 必测反例

- 不调整：`100`。
- 单次上调：`100 -> 120`。
- 单次下调：`100 -> 80`。
- 来回调整：`100 -> 80 -> 100`，费用应为 `120`。
- 禁止对 `q_final` 再收一次普通合同费。
- 禁止修改已经执行过的槽位。
- Q4 价格逻辑分开：优化器用预测价，核算器用真实价。

## 结果

- 测试脚本：`src/q3_ledger_synthetic_tests.py`。
- 机器输出：`experiments/q3_ledger_synthetic_results.json`。
- 人类报告：`research/C_Q3_pure_ledger_report.md`。
- 当前结果：9/9 通过。
- 结论：Q3 纯结算账本内核通过；这不代表完整 Q3 完成，不放行附件3预测适配器、滚动窗口或全年运行。
