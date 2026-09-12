# 第二问执行与核算接口阶段报告

## 范围

本轮只落实已经冻结的第二问规则：正常电费按计划购电量计算，未使用合同电不进入母线，供电缺口用五倍价格紧急购电，计划放电过剩按 D007 记录削减量。未选择预测方法、终端库存方案或时间方案A的零点衔接办法。

## 修复内容

- 核算器的母线平衡加入紧急购电。
- 正常电费统一按 `price * grid_contract` 独立复算。
- 紧急费用按 `5 * price * grid_emergency` 独立复算。
- 非第一问执行检查 `grid_contract = grid_delivered + grid_unused`。
- 新增第二问顺序执行接口，记录计划放电、实际放电、放电缺额和削减标志。
- 实际库存越界时明确失败，不静默修改计划。

## 结果

- `python src/q2_accounting_tests.py`：7/7 通过。
- `python src/probe_timing.py`：48/48 通过。
- `python src/probe_cross_validation.py`：39/39 通过。
- 机器结果：`experiments/q2_accounting_results.json`。

## 人类裁决后的补充

人类已选择方案A（DECISIONS.md D008）：满电附近若实际负荷偏低，计划放电被削减并使后续计划充电越上限，执行器临时削减必要的充电量。执行记录保存计划充电、实际充电、少充量和事件标志，核算器独立复查；少充后不需要的合同电按未使用合同电处理。
