# High-Scoring CUMCM Paper Style Patterns

Evidence base: seven national-award paper PDFs in `D:/Data/Download/math/reference/论文规范/历年国一国二参考论文/国赛国家级奖论文/`, plus their visible appendices/support-material patterns. These patterns are recommendations, not official rules.

## Stable Structure Patterns

【推荐】Most strong papers use a compact body skeleton:

1. 摘要 and 关键词.
2. 问题重述, often splitting background and required tasks.
3. 问题分析, organized by subproblem.
4. 模型假设.
5. 符号说明.
6. 模型建立与求解, usually by subproblem.
7. 模型评价/改进/推广.
8. 参考文献.
9. 附录 with source code and support-material list.

【推荐】For multi-question problems, the strongest organization is not merely "Problem 1, Problem 2, Problem 3". It shows how earlier definitions, intermediate quantities, or validation support later questions.

【可选】Some papers place data preprocessing before assumptions/symbols when data cleaning drives the model. Use this only when data handling is a major modeling step.

## Abstract

【推荐】A strong abstract is a dense map of the solution:

- One or two sentences for the problem setting.
- One short block per subproblem: method, key model, and key numerical conclusion.
- A final sentence on validation or model value only if backed by evidence.
- Keywords are method/problem nouns, not slogans.

【禁止】Avoid abstracts that only say "建立模型并求解", spend too much space on background, list model names without results, or include derivations that belong in the body.

## Problem Analysis

【推荐】Effective problem analysis follows the chain:

real task -> mathematical object -> decision variable/unknown -> objective -> constraints -> data needed -> model choice.

Explain why the method is appropriate: geometry for spatial relationships, optimization for allocation/design under constraints, time series or regression for prediction, simulation for complex mechanisms, clustering/classification for grouping, and sensitivity analysis for uncertain parameters.

【禁止】Do not use "因此建立 XXX 模型" as the only justification.

## Data Handling

【推荐】Only include data processing that changes or validates the model:

- merging tables and key fields;
- unit conversion and time/spatial alignment;
- missing/abnormal value rules;
- feature construction tied to model equations;
- distribution, trend, or correlation checks used to select a method;
- train/test or baseline split for predictive work.

【可选】Exploratory plots can be moved to appendix when they do not affect the main conclusion.

【禁止】Do not add cleaning, standardization, or visualization just to lengthen the paper.

## Model Formulation

【推荐】Before formulas, state the modeling idea in plain mathematical language. After formulas, define variables and explain how the expression maps to the real problem.

【推荐】For optimization models, make these explicit:

- decision variables;
- objective function;
- hard constraints and soft/penalty terms;
- parameter source;
- solution algorithm and stopping/optimality evidence;
- feasibility checks.

【推荐】For prediction/fitting models, make these explicit:

- target variable and horizon;
- feature set and transformations;
- train/test or validation protocol;
- loss metric;
- baseline;
- error and uncertainty interpretation.

【推荐】For simulation models, make these explicit:

- state variables;
- random or deterministic inputs;
- sampling design and seed if relevant;
- number of trials or convergence evidence;
- output metrics.

## Results and Figures

【推荐】Tables are best for exact decisions, parameters, comparisons, and final required outputs. Figures are best for trends, distributions, spatial layouts, flow processes, and sensitivity curves.

【推荐】Each figure/table should have:

- a clear number and title;
- units and decimal precision;
- axis labels and legend for figures;
- enough explanation in surrounding text to show what conclusion it supports.

【推荐】Move huge intermediate tables, repetitive plots, and long code to appendix/support materials.

【禁止】Do not leave figures/tables unmentioned in the body. Do not write only "见图 X" without interpreting the result.

## Validation and Robustness

【推荐】Choose validation by model type:

- Optimization/accounting: independent recalculation, constraint audit, feasibility check, comparison with simple baseline, boundary cases.
- Prediction: train/test error, rolling validation, baseline comparison, residual pattern, error distribution.
- Geometry/derivation: dimensional check, special-case check, alternative derivation, numerical substitution.
- Simulation: convergence with sample size, seed sensitivity, extreme-case behavior.
- Multi-criteria decision: weight sensitivity, rank stability, dominance checks.

【推荐】Sensitivity analysis should perturb parameters that actually matter to decisions or are uncertain in the problem. Report both direction and magnitude of impact.

【禁止】Do not claim "稳健" or "精度高" without a test or calculation.

## Model Evaluation

【推荐】Good evaluation names the technical reason:

- "The explicit energy-balance constraint makes the schedule auditable by slot."
- "The method is sensitive to forecast error because purchase decisions are optimized one day ahead."
- "The geometry simplification is valid only under small-slope assumptions."

【禁止】Avoid unsupported template comments: "模型简单", "准确性高", "实用性强", "推广性好".

## Language Patterns

【推荐】Use concise technical sentences:

- "由约束 (x) 可知，变量 A 的取值上界由 B 决定。"
- "表 X 给出三种方案的费用，方案 2 比方案 1 降低 ...，主要来自 ..."
- "该异常点未删除，因为它对应题目给定的峰值负荷，属于真实边界情形。"

【推荐】Prefer quantitative verbs: increase/decrease, bind, satisfy, violate, converge, dominate, explain, approximate, constrain.

【禁止】Avoid filler and exaggerated certainty. Replace "显著提升" with the measured improvement; replace "充分证明" with the actual validation result.

## Common Low-Quality Problems

- Formula blocks without motivation or variable explanation.
- A method stack that names many algorithms but does not explain why each is needed.
- Results listed without interpreting whether they answer the required output.
- Unverified sensitivity analysis or baseline comparison.
- Long background copied from the problem statement.
- Appendices that contain code but not a usable support-material file list.
- Absolute local paths or personal information in code listings.
- Repeated "模型评价" phrases that could fit any problem.
- Figures whose axes, units, or legends are unclear.
- Official format rules copied from older templates without checking the current year.
