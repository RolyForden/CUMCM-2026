# TASK：完成第三问闭环

- 状态：已完成（2026-09-12）。
- 目标：复用 Q2 的因果预测、滚动库存、执行与核算内核，接入附件3四时点光伏预测，完成 Q3 smoke、全年结果、独立验证和论文正文。
- 冻结基线：Q2 只读；Q3 调整费用按 D007 版本现金流；目标槽电价；不得重复计费。
- 当前关键路径：附件3一次加载并缓存；点预测按线性插值展开到10分钟；0/6/12/18仅更新未执行槽。
- 验收：无未来批次泄漏；已执行槽不可修改；全年334天、SOC/功率/能量/费用/跨日连续全部通过；result3回读一致；论文数字来自正式审计产物。
- 结果：四时点正式回放总费用15805751.77元，紧急购电量809227.14 kWh，不可行天数0；跨午夜预测回归4/4、正式结果独立验证19/19、更新时点消融四组均完成。
- 产物：`outputs/q3/result3.xlsm`、`outputs/q3/q3_replay_summary.json`、`outputs/q3/q3_validation.json`、`outputs/q3/q3_update_ablation.json`、`research/C_Q3_validation_report.md`、`research/C_Q3_update_ablation_report.md`、`paper/数模国赛C题.tex`。
