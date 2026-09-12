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

## Paper Architecture

Use the official page order from the current rules. For the paper body, prefer this structure unless the problem makes a narrower structure clearer:

- 摘要 and 关键词.
- 问题重述: restate tasks, constraints, and required outputs without copying long problem text.
- 问题分析: translate each real task into mathematical objects, variables, objectives, constraints, and method choices; show why the selected model fits.
- 模型假设: list only assumptions that affect modeling or interpretation, and state their reasonableness or impact.
- 符号说明: define recurring variables once; include units where useful.
- 数据处理: describe only cleaning, transformation, feature construction, visualization, or validation that affects modeling.
- 模型建立与求解: organize by subproblem, but preserve cross-question dependency and reuse of variables/results.
- 结果分析 and 模型检验: explain why the numbers answer the question, whether they are reasonable, and how they were checked.
- 敏感性/稳健性分析: include only when actually run or analytically justified.
- 模型评价、改进与推广: give evidence-backed strengths, limitations, applicability, and possible extensions.
- AI 工具使用声明, 参考文献, 附录, according to official placement.

Avoid adding decorative sections that do not help answer the problem. If a section has no verified content, leave a clear TODO rather than padding.

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
- Official page order, page limits, electronic/paper differences, appendix/support-material rules, AI-use statement, and anonymity are satisfied.
- No participant, school, region, local username, absolute personal path, or hidden identity clue appears in the paper, appendix, code listings, support materials, or AI-use details.
- The PDF/Word file and support archive comply with current size and content requirements.

【结构】
- Each subproblem has a complete argument chain: problem -> method -> model -> solution -> result -> validation -> conclusion.
- Cross-question dependencies are explicit; repeated setup is not duplicated.
- No section exists only to make the paper look complete.

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
