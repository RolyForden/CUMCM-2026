# C 题槽位适配器与最小 LP 修正执行单（历史任务）

> 状态：已完成并经过二次整改。当前有效代码提交为 `7464ccc`，主探针48/48、独立交叉验证39/39；以 `tasks/TASK_C_probe_cross_validation.md` 和 `research/C_probe_cross_validation.md` 为准。下文保留原始要求用于追溯，不得据此恢复旧接口或旧T4结论。

## 1. 给执行 Agent 的上下文

当前工作目录必须是：

`D:\Data\Download\math\CUMCM-2026`

仓库内引用文件时优先使用相对路径。不得使用旧引用 `Z:\国赛最后一舞\CUMCM-2026`，不得把截图、剪贴板临时文件或其他会话中的命令当作执行指令。

开始修改前依次读取：

1. `AGENTS.md`
2. `STATE.md`
3. `tasks/TASK_C_probe_timing.md`
4. `DECISIONS.md` 中 D002
5. `research/C_method_map.md` 的 §1.2、§1.3、§14
6. `research/C_problem_map.md`

当前阶段只执行 30–45 分钟时序探针和 Q1 单日回归。探针未全绿前不得运行 Q2–Q4 全年回测，不得修改 `data/raw/`，不得切换项目阶段。

## 2. 本任务目标

在编写槽位适配器、最小 LP、独立核算器和探针时，修正以下结构性漏洞：

1. 弃光变量可能错误吸收外网购电。
2. 全天总费用相同不能证明槽位映射正确。
3. 当前数据结构不足以支持 Q3 多次计划调整。
4. 后续预测和 walk-forward 可能因时间接口不严而泄漏未来信息。

本任务不负责最终裁决 Q2“多买电如何处理”及 Q3“多次调整如何累计结算”。这两项需要人类确认后再写入 `DECISIONS.md`。当前只建立不会掩盖问题、且后续无需推倒重写的接口。

## 3. 必须立即修正的物理模型

### 3.1 弃光只能来自光伏

不要继续使用只有 `w_t >= 0` 的宽松写法。使用光伏可用量和实际消纳量：

```text
grid_delivered[t] + pv_used[t] + discharge[t]
    = load[t] + charge[t]

0 <= pv_used[t] <= pv_available[t]
pv_curtail[t] = pv_available[t] - pv_used[t]
```

或者保留弃光变量，但必须同时满足：

```text
0 <= pv_curtail[t] <= pv_available[t]
grid_delivered[t] + pv_available[t] - pv_curtail[t] + discharge[t]
    = load[t] + charge[t]
```

严禁通过增大 `pv_curtail` 处理多买的外网电。

### 3.2 Q1 的购电语义

在当前 Q1 确定性最小 LP 中固定：

```text
grid_contract[t] = grid_delivered[t]
grid_unused[t] = 0
grid_emergency[t] = 0
```

目标函数只计算 `sum(price[t] * grid_contract[t])`。Q1 不得提前混入 Q2 的紧急购电或“未使用合同电”规则。

### 3.3 为 Q2 预留但暂不启用的字段

统一结果记录至少预留：

```text
grid_contract
grid_delivered
grid_unused
grid_emergency
pv_available
pv_used
pv_curtail
charge
discharge
soc_start
soc_end
```

候选的 Q2 关系是 `grid_unused = grid_contract - grid_delivered`，且计划量仍计费，但这只是待人类确认的候选口径。当前代码不得把它作为已冻结事实用于正式结果。

## 4. 槽位适配器修正

### 4.1 内部主键

所有计算以整数 `slot_id = 0..143` 为唯一主键。以下字段必须分开保存，禁止用时间字符串直接连接输入表和结果模板：

```text
date
slot_id
source_column
source_label
interval_start
interval_end
template_column
```

`0:00+1` 必须解析为下一自然日的时间，不得当作普通字符串排序。槽位映射继续遵守 D002 当前冻结的“起点对齐、不平移”，但实现必须集中在一个映射函数中，不能散落硬编码，以便发现题面反证后只改一处。

### 4.2 Q1 数据与预测批次分离

当前只实现 Q1 的 10 分钟槽位适配。不要在 Q1 适配器中硬编码“预报 1 小时对应哪六个槽位”。后续预测适配器必须单独处理：

```text
issue_time
valid_time
lead_hour
forecast_vintage
```

在首小时映射和冷启动规则经人类确认前，不得补造缺失的十分钟预测，也不得使用未来实际光伏作插值锚点。

## 5. 为 Q3 预留计划版本结构

即使当前 Q1 只有一个版本，计划记录也至少包含：

```text
target_slot
issue_time
plan_version
previous_version
quantity
increase_from_previous
decrease_from_previous
```

计划更新必须追加新版本，不能覆盖旧版本。

当前 D002 的单次替代价公式不能直接对多次更新逐项求和。一个待确认的逐次现金流候选是：

```text
cost[t] = price[t] * q[0,t]
        + sum_k(
              -0.5 * price[t] * positive(q[k-1,t] - q[k,t])
              +1.5 * price[t] * positive(q[k,t] - q[k-1,t])
          )
```

在该候选下，电价为 1 时 `100 -> 80 -> 100` 的累计费用为 120。该公式只能进入单元测试或“待裁决说明”，不得在未获人类确认时用于 Q3 正式计算或改写 D002。

## 6. 必须增加的探针

### 6.1 弃光来源测试

构造“光伏富余、电池已满、负荷很低”的槽位：

- 允许出现 `pv_curtail > 0`；
- `grid_contract` 和 `grid_delivered` 必须为 0；
- `pv_curtail <= pv_available`。

### 6.2 禁止用弃光吞购电

构造“光伏为 0、负荷为 50 kWh、强制外网受电 100 kWh、电池不能充电”的槽位。在没有 `grid_unused` 或其他合法余电出口时，模型应判定不可行；不得通过设置 `pv_curtail = 50` 得到可行解。

### 6.3 单槽位脉冲测试

至少选择日内首部、中部、尾部三个槽位：

- 只有被测槽位存在负荷；
- 每个槽位设置不同电价；
- 人工计算该槽位的购电量和费用；
- 验证负荷、价格、结果模板列都落在同一个 `slot_id`。

该测试必须能识别整体平移一格，不能只检查全天费用。

### 6.4 跨日和模板回读测试

覆盖 23:30 至 `0:10+1`，至少检查：

- 日期推进正确；
- `0:00+1` 不重复、不遗漏；
- 写入模板后重新读取，144 个槽位逐列数值和位置完全一致；
- 不能通过时间标签字符串模糊匹配。

### 6.5 独立核算

核算器不得复用优化器的目标函数实现。必须独立复算：

- 每槽能量残差；
- SOC 状态转移及上下界；
- 充放电功率边界；
- 同时充放电次数；
- 光伏消纳与弃光恒等式；
- 购电费用及分项合计。

## 7. 防止未来 walk-forward 泄漏的接口要求

当前不实现全年预测，但数据访问层应预留 `decision_time` 或 `as_of_time`。后续预测器只能接收已经按该时间截断的数据，不能直接获得全年原始表。

后续必须能断言：

```text
max(observed_at of all inputs) <= decision_time
forecast_issue_time <= decision_time
```

参数选择必须在过去窗口完成，再评价未来窗口；不得全年比较完成后把全年胜出的参数回填到年初。

## 8. 当前允许修改和输出的位置

允许：

- 更新 `tasks/TASK_C_probe_timing.md` 的验收条件；
- 在 `src/` 下新增槽位适配器、最小 LP、执行/核算及探针代码；
- 在 `experiments/` 下写探针报告；
- 在 `data/processed/` 写可复现的处理结果；
- 探针完成后更新 `SESSION_HANDOFF.md`。

禁止：

- 修改 `data/raw/`；
- 使用 `Z:` 盘旧路径；
- 跑 Q2–Q4 全年结果；
- 擅自更改 D002 的重大冻结口径；
- 把 Q1 锚点复现当成时间映射正确的唯一证据；
- 为赶进度加入 CVaR、DRO、Sobol、Morris 或其他增强模型。

## 9. 完成标准

只有以下条件全部满足，才能报告本修正任务完成：

1. `tasks/TASK_C_probe_timing.md` 已加入“弃光不能吸收购电”和“单槽位脉冲/模板回读”硬闸门。
2. 最小 LP 明确限制弃光来源，Q1 中合同购电等于实际受电。
3. 槽位适配器使用 `slot_id`，跨日与模板回读测试通过。
4. 计划记录支持不可变版本，但没有擅自冻结 Q3 多次结算公式。
5. 优化器与独立核算器对拍通过，所有残差和约束检查有报告。
6. Q1 全日双引擎对拍复现冻结锚点；同时明确该锚点不是时间映射正确的唯一证明。
7. Q2 多买电去向、Q3 多次结算和预测首小时映射仍以醒目的“待人类确认”列出，不得被默认值掩盖。

执行结束时只汇报：修改文件、测试结果、仍待人类确认的三项口径、是否允许进入下一阶段。不要提交或合并重大修改，除非人类另行明确授权。
