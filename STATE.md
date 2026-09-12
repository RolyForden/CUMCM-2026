# 当前状态

阶段：SOLVING

状态：原探针 41/41 保留为整改前基线；整改提交 `7464ccc` 的主探针 48/48、独立交叉验证 39/39 均通过。

结论：Q1 数值锚点可复现，执行—核算—官方模板链已在冻结口径 A 下重新认证；N4 未经人类复核前仍是条件性结果。

## 当前硬闸门

- 不运行 Q2–Q4 全年正式模型。
- 不修改 DECISIONS.md D002 的 N1–N4；均等待人类裁决。
- N1 阻塞 Q2 执行器；N2 阻塞 Q3 费用账本；N3 阻塞附件 3 预测适配；N4 阻塞 Q1 最终墙钟解释和论文定稿。

## 当前证据

- 整改前提交：`2250523`；历史报告：`experiments/probe_timing.md`（41/41，仅作基线）。
- 整改代码提交：`7464ccca35ad5a0eb454d0441fb6e051264e1582`。
- 整改后主探针：`src/probe_timing.py`，48/48。
- 独立交叉验证：`src/probe_cross_validation.py`，39/39；逐项输出：`experiments/probe_cross_validation_results.json`。
- 审查报告：`research/C_probe_cross_validation.md`。
- N4 人类裁决材料：`research/C_time_boundary_decision.md`。

## 下一步

1. 人类复核 N4；在此之前只可使用“冻结口径 A 下的 Q1 条件性结果”。
2. 人类依次裁决 N1–N3 后，再实现并小窗口验证 Q2/Q3；未裁决前不得全年运行。
