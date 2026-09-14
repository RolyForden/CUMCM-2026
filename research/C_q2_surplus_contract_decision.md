# Q2 合同余电与计划放电过剩修订说明（N1）

## 当前状态

D004 的合同余电账本保留，但它是复审前裁决稿。D007 对 N1 做了补充：N1 文档口径按本说明修订后冻结，允许做合成反例和单元测试；Q2 三天窗口还需 N1 反例通过且 Q2 光伏预测口径明确后才允许。

## 合同余电口径

每个 10 分钟槽位中，计划给出合同购电量 `grid_contract`。实际执行时，合同电按计划照常计费；未实际进入母线的部分记为：

```text
grid_unused = grid_contract - grid_delivered
```

`grid_unused` 不进入母线能量平衡，也不额外收费，因为它已经包含在 `price * grid_contract` 的正常合同费用中。

母线能量平衡使用实际进入母线的电：

```text
grid_delivered + grid_emergency + pv_used + discharge_actual
    = load_actual + charge
```

## 计划放电过剩处理

若实际负荷显著低于预测，`grid_unused` 只能处理合同电，不能吸收电池已经放出的电。因此 D007 冻结主口径为“计划优先”执行：

1. 先弃光：降低 `pv_used`，增加 `pv_curtail`。
2. 再减少合同交付：降低 `grid_delivered`，增加 `grid_unused`。
3. 若仍有过剩，则削减计划放电：`discharge_actual < discharge_planned`。
4. 削减放电后仍无法闭合，判该槽执行不可行。

该口径优先保持计划放电和合同交付，属于新增模型假设。光伏优先口径作为敏感性对照，不进入主线。

## 审计字段

执行日志至少保存：

```text
discharge_planned
discharge_actual
discharge_shortfall = discharge_planned - discharge_actual
discharge_clipped
```

其中 `discharge_clipped` 只作为事件标志，不能替代实际数量字段。

## 费用

```text
cost_normal    = price * grid_contract
cost_emergency = 5 * price * grid_emergency
cost_total     = cost_normal + cost_emergency
```

削减计划放电本身不产生电费，但会改变实际 SOC，因此下一槽和下一日必须从实际 SOC 继续。

## 必测反例

- 零负荷、无光伏、有计划放电：必须触发放电削减或不可行。
- 高光伏、低负荷、合同电过量：先弃光，再形成 `grid_unused`。
- 高计划放电、合同严重过量、SOC接近边界：检查 `discharge_actual`、`discharge_shortfall` 和 SOC 更新。
- 合同不足：形成 `grid_emergency`，按 5 倍电价计费。
