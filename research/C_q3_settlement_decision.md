# Q3 多次调整结算修订说明（N2）

## 当前状态

D005 的逐次现金流公式保留，但它是复审前裁决稿。D007 对 N2 做了补充：N2 文档口径按本说明修订后冻结，允许先做纯结算账本反例；Q3 预测驱动滚动窗口仍需 N3 重裁后才允许。

## 逐次现金流

每个槽位先在 0:00 形成初始计划 `q0`，之后 6:00、12:00、18:00 若更新该槽位计划，从上一版 `q_prev` 调整到新版 `q_new`，按差额产生现金流：

```text
increase = max(q_new - q_prev, 0)
decrease = max(q_prev - q_new, 0)

cost_plan = price[target_slot] * q0
          + sum(1.5 * price[target_slot] * increase_k)
          - sum(0.5 * price[target_slot] * decrease_k)
```

电价为 1 时，`100 -> 80 -> 100` 的计划相关费用为：

```text
100 - 0.5 * 20 + 1.5 * 20 = 120
```

## 防重复计费

Q3 计划费用唯一来源是版本现金流：

```text
price[target_slot] * q0 + adjustments
```

执行器可使用最终有效合同量 `q_final` 决定 `grid_delivered/grid_unused/grid_emergency`，但核算器不得再对 `q_final` 调用一次普通合同计费，否则会重复收费。

紧急购电另计：

```text
cost_emergency = 5 * price_actual[target_slot] * grid_emergency
```

## 价格信息集

调整现金流使用目标交付槽电价。

- 固定电价版本：目标槽电价按已知日内曲线取值。
- Q4 波动电价版本：优化器只能使用决策时可获得的 `price_forecast[target_slot]`；事后核算器使用 `price_actual[target_slot]`。不得因为采用目标槽电价而读取未来真实价格。

## 版本约束

- 计划版本不可变追加，不覆盖旧版本。
- 每次调整只能作用于尚未执行的槽位：`target_slot.start >= issue_time`。
- `计划购电量` 表写 0:00 初始计划 `q0`。
- `调整购电量` 表写该槽位最终生效计划，不写增量。
- 费用核算必须读取版本日志，不能只看最终表。

## 必测反例

- 不调整：费用为 `price*q0`。
- 只上调、只下调：分别检查 1.5 倍增购和 0.5 倍冲回。
- `100 -> 80 -> 100`：电价1时费用为120。
- 非法修改已执行槽：必须拒绝。
- 重复收费检测：若再对 `q_final` 收普通合同费，测试必须失败。

## 实施状态（2026-09-12）

纯合成账本内核已单独实现并测试：

- 代码：`src/core/q3_ledger.py`
- 测试：`src/q3_ledger_synthetic_tests.py`
- 结果：`experiments/q3_ledger_synthetic_results.json`，9/9 通过
- 报告：`research/C_Q3_pure_ledger_report.md`

该结果只证明“多次改计划怎么收费”的账本内核通过，不代表完整 Q3 完成；不得据此接入附件3预测、滚动窗口或全年运行。
