---
name: cumcm-paper-writing
description: Write, revise, or review CUMCM mathematical modeling papers, turning project evidence into compliant Chinese contest manuscripts without inventing results.
---

# CUMCM Paper Writing Skill

Use this skill when drafting, revising, or reviewing a 全国大学生数学建模竞赛 (CUMCM) paper, including converting model outputs into paper text, checking paper compliance, refining language, organizing formulas/tables/figures, or preparing AI-use and support-material statements.

## Rule Priority

Apply rules in this order:

1. 【强制】Current official CUMCM rules and AI-use rules. Read [references/official-rules.md](references/official-rules.md) before final formatting, final review, or any compliance decision.
2. 【强制】The current problem statement and explicit project decisions, such as `STATE.md`, `DECISIONS.md`, task files, and human-frozen modeling choices.
3. 【推荐】Stable patterns from high-scoring papers. Read [references/style-patterns.md](references/style-patterns.md) when designing structure, rewriting prose, choosing figures/tables, or reviewing quality.
4. 【可选】Case-specific writing habits from individual papers. Do not promote them to rules unless they are justified by the current problem.

If an excellent paper conflicts with official rules, follow the official rule. If two official-looking rules conflict and recency/authority cannot be determined, mark it as `需要人工确认` instead of guessing.

## Core Constraint

Every number, percentage, parameter, metric, ranking, figure, table, experimental conclusion, and final recommendation in the paper must be traceable to code, raw/processed data, an experiment output, a validation artifact, or an explicit derivation. If the source is missing, do not write the result as fact; write `TODO：需要实验获得` and state what must be run or checked.

Do not create sensitivity analyses, accuracy values, comparison baselines, model parameters, or "improved" conclusions for narrative completeness. A plain, verified result beats a polished unsupported claim.

## Writing Workflow

1. Confirm the problem requirements, paper format rules, AI-use requirement, and current project decisions.
2. Read the current project evidence needed for the section: problem map, method map, model code, experiment outputs, CSV/XLSX results, generated figures, validation reports, and existing LaTeX.
3. Build the section argument chain before writing: problem -> method choice -> mathematical model -> solution process -> result -> validation -> conclusion.
4. Write concise Chinese technical prose. Keep formulas, tables, and figures near the reasoning they support.
5. Check competition compliance, then mathematical consistency, then evidence traceability, then language economy.
6. Before final delivery, run the review checklist below. For LaTeX papers, compile and inspect the output if the task includes final paper editing.

## Paper Structure 【强制】

Follow the fixed page order and chapter skeleton below. Page order and page limits come from the official rules; the chapter skeleton and three-level flow are project-mandated for consistency with national-award papers. Do not add, remove, reorder chapters, or promote sub-sections to chapters.

### Page order 【强制·官方】

纸质版：第 1 页 承诺书 → 第 2 页 编号专用页 → 第 3 页 摘要专用页 → 第 4 页起 正文 → 附录（与正文装订在一起）。

电子版：第一页必须是摘要专用页；承诺书与编号专用页不得出现在电子版与支撑材料中。

### Fixed chapter skeleton 【强制】

正文（计入 30 页）按下列顺序：

| 章 | 标题 | 内容要求 |
|----|------|----------|
| 一 | 问题重述 | 背景 + 逐问复述任务、约束、所需输出；不照抄大段题面 |
| 二 | 问题分析 | 一问一节 `2.k 问题 k 的分析`：核心难点 → 与前问递进 → 拟用方法族 |
| 三 | 模型假设 | 只列影响建模/解释的假设，并说明其合理性或影响 |
| 四 | 符号说明 | 复现变量定义一次；有用的量给单位 |
| 五 | 模型建立与求解 | 全文主体，按问分节（见下三级流水） |
| 六 | 敏感性/稳健性分析 | 仅在真正运行或可解析论证时保留；参数扰动、不确定度 |
| 七 | 模型评价、改进与推广 | 优点/不足/改进与推广，须绑定证据 |
| — | AI 工具使用声明 | 置于参考文献之前（见 [references/official-rules.md](references/official-rules.md)） |
| — | 参考文献 | 正文引用处标注；末尾按科技论文规范列出 |

附录（不计入 30 页）：支撑材料文件列表 + 建模所用全部完整可运行源程序；无程序时注明「本论文没有用到程序」。

数据处理若为独立建模步骤，作为第五章开篇小节，不单列章。

### 三级流水（第五章每问）【强制】

每问二级标题统一为 `问题 k 模型的建立与求解`，其下三级标题固定按序（可裁剪但顺序不乱）：

1. 问题背景与目标
2. 模型建立（定义 → 机理/约束方程 → 目标函数）
3. 求解算法（原理 1–2 句 + `·` 一步一行步骤）
4. 计算结果（表/关键图紧随）
5. 结果分析（独立小节；禁止只有表图、没有分析）

### 结构忌讳

- 禁止把「逐图说明 / 可复现性 / 方法比较 / 自检清单」升为独立章节；并入第五章或第七章。
- 禁止空洞标题（相关工作、进一步讨论、补充说明）。
- 二级/三级标题依赖自动编号，标题内不要手写「5.1」「5.1.1」，避免双重编号与嵌套复杂公式。
- 章节只为「看起来完整」而存在时删除；无已验证内容时写 `TODO` 而非注水。

## 版面与页数硬约束

【强制·官方】以下条款来自 2026 修订稿，交付前逐条核对（细则见 [references/official-rules.md](references/official-rules.md)）。

### 页数与顺序
- 摘要专用页含标题+关键词，原则上 ≤1 页；电子版第 1 页必须是摘要页。
- 正文自问题重述起至参考文献止，≤30 页，不要目录；附录页数不限且不计入 30 页。
- 摘要页与附录独立于 30 页；禁用「摘要+正文合计 ≤30」旧口径。

### 版面
- 页边距上、下、左、右各 ≥2.5 cm；从左侧装订。
- 页码自摘要页起，页脚中部，阿拉伯数字从 1 连续编号。
- 字号、字体、行距、颜色官方不做统一要求；项目模板有规定则服从模板，但不得违反上述硬条款。

### 交付文件
- 论文为单一 PDF/Word（建议 PDF），≤20 MB，不压缩，含附录且与纸质版一致。
- 支撑材料压缩为一个 RAR/ZIP，≤20 MB；文件列表写入附录；无支撑材料须在附录注明「本论文没有支撑材料」。
- 全文（含附录、源码、支撑材料、AI 使用详情）不得出现队名/校名/赛区/绝对个人路径等身份信息。

【项目硬指标】以下为落实上述铁律的内部可操作阈值，非官方原文，但本项目按硬性执行：

| 项 | 硬指标 |
|----|--------|
| 摘要篇幅 | ≥800 汉字，结果导向 |
| 数据图 | ≥18 张（依工作量裁剪时须在正文说明） |
| 流程图+概念图 | 合计 ≥5；总览图须含各主单元一级子动作 |
| 简单图配额 | 折线+柱+帕累托 合计 ≤7 |
| 图宽 | 默认 0.70–0.78\textwidth；宽图 ≤0.88\textwidth |
| 连续空白 | 任一页 ≲1/4 页；禁大 `\vspace`/`\vfill`、禁整页堆图留白 |
| 图后解释 | ≥3–5 句实质分析（指向数值/比较/含义/局限） |
| 编号公式 | 建议 ≥30；低于此值须逐问排查论述是否不足，禁止装饰公式凑数 |
| 每问齐备 | 机理→推导→求解→结果→图释→边界 六段齐备 |

## Section Rules

**摘要** should be result-first. In one page, say what each problem asked, what model or method was used, the key quantitative result, and the final conclusion. Avoid long background, vague praise, detailed derivations, and method names without results.

**问题分析** should justify model choice. Do not jump from "therefore" to a named model. Connect reality to mathematics: object, decision variable, target, constraint, uncertainty, and why the chosen method handles them.

**模型假设** must be useful and testable. Avoid assumptions like "data are reliable" unless the later validation or limitation depends on it. Do not hide model weaknesses inside assumptions.

**公式** must not appear alone. Use the pattern: text motivation -> displayed formula -> symbol/units explanation -> mathematical or practical meaning. Define variables on first use and keep symbols consistent across sections.

**图表** must each answer a specific question. Prefer tables for exact values and scheme comparisons; prefer figures for trends, distributions, spatial layouts, sensitivity curves, and algorithm flows. The text must interpret the important numbers, not merely say "如图所示".

**结果分析** should answer "so what". Explain trends, exceptions, feasibility, practical meaning, and differences between schemes. Mention abnormal or weak results honestly.

**验证** should match the model type: independent recalculation for optimization/accounting models, baseline comparison for predictive models, residual/error analysis for fitting, parameter perturbation for sensitive assumptions, extreme-case tests for constraints, and theoretical consistency checks for derived formulas.

**模型评价** must be technical. Tie advantages and limitations to actual evidence, assumptions, data quality, computational cost, or applicability. Avoid unsupported phrases such as "精度高、实用性强".

## Language

Write like a formal undergraduate mathematical modeling paper: objective, compact, quantitative, and causally clear. Prefer subjects such as "模型", "约束", "结果", "算法", "误差", "费用", "覆盖率" over vague subjects like "我们" when possible.

Limit empty intensifiers and AI-like filler, especially repeated "值得注意的是", "从多个维度", "综合来看", "进一步地", "不仅……而且……", "显而易见", "众所周知", "效果很好", "具有重要意义", "极大提高", "充分证明". Use them only when evidence follows.

Do not copy, paraphrase closely, or splice wording from reference papers. Their role is to reveal structure and reasoning habits, not to provide reusable prose.

## Review Checklist

【赛事规范】
- 页序正确：电子版第 1 页为摘要页；承诺书/编号页只出现在纸质版，不在电子版与支撑材料中。
- 页数：摘要专用页 ≤1 页；正文 ≤30 页且无目录；附录不计入。
- 页边距各 ≥2.5 cm；页码自摘要页起、页脚中部、阿拉伯数字从 1 连续。
- 电子版为单一 PDF/Word、≤20 MB、不压缩、与纸质版一致；支撑材料一个 RAR/ZIP ≤20 MB。
- 附录含支撑材料文件列表 + 全部可运行源程序；无程序/无支撑材料时按规范明文注明。
- AI 使用声明置于参考文献前；用了 AI 则附 `AI 工具使用详情.pdf`。
- 匿名：摘要页、正文、附录、源码 listing、支撑材料、AI 详情中无队名/校名/赛区/绝对个人路径/邮箱/电话/用户名等身份线索。

【结构】
- 章节为固定八章 + AI 声明 + 参考文献，无增删/重排；数据处理未单列为章。
- 第五章每问三级流水「背景→建立→求解→结果→结果分析」按序齐备，结果分析独立成节。
- 标题靠自动编号，无手写「5.1」、无嵌套复杂公式。
- Each subproblem has a complete argument chain: problem -> method -> model -> solution -> result -> validation -> conclusion.
- Cross-question dependencies are explicit; repeated setup is not duplicated.
- No section exists only to make the paper look complete.

【版面】
- 无单页连续空白超过约 1/4 页；无大 `\vspace`/`\vfill`、无整页堆图留白。
- 图宽在 0.70–0.88\textwidth 区间；图型与 manifest 一致。
- 图后 ≥3–5 句实质解释；无空图、无「仅见图 X」。

【数学】
- All variables are defined once, units are consistent, objectives and constraints match the problem, and formulas are referenced and explained.
- Assumptions are relevant, not excuses for unverified conclusions.

【实验与证据】
- Every number, figure, table, and conclusion has a source artifact.
- Results can be reproduced from the recorded data/code/parameters/seeds when applicable.
- No unrun baseline, sensitivity analysis, accuracy, or comparison is stated as completed.

【结果】
- The paper directly answers each required output.
- Important anomalies, infeasible cases, or weak assumptions are discussed.
- Tables and figures are necessary, labeled, and interpreted.

【语言与引用】
- Prose is concise, formal, and specific; filler and exaggerated claims are removed.
- External methods, public data, and borrowed formulas are cited at their use sites and listed in references.
- Similarity risk is low: no large copied problem text or reference-paper phrasing.
