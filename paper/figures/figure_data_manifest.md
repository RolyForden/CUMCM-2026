# 论文图表数据来源清单

本清单记录论文中每一张图的数据来源、使用字段、聚合方式，以及与正文哪张表/哪个正式
数字交叉核验。所有绘图脚本只读取正式产物，不修改任何模型、正式结果或核算口径。

正式产物目录：`outputs/q1_scheme_a/`、`outputs/q1_validation/`、`outputs/q2/`、
`outputs/q3/`、`outputs/q4/`。

## 论文图号对照

| 论文图号 | label | 本清单编号 |
| --- | --- | --- |
| 图 1 | `fig:overall_framework` | F0 |
| 图 2 | `fig:q1_dispatch` | F1 |
| 图 3 | `fig:q2_yearly_series` | F2 |
| 图 4 | `fig:q2_monthly_cost` | F3 |
| 图 5 | `fig:q3_forecast_error` | F4 |
| 图 6 | `fig:q3_cost_waterfall` | F5 |
| 图 7 | `fig:q3_monthly_cumulative` | F6 |
| 图 8 | `fig:q3_typical_day` | F7 |
| 图 9 | `fig:q4_price_forecast` | F8 |
| 图 10 | `fig:q4_cost` | F9 |
| 图 11 | `fig:q1_sens` | F10 |
| 图 12 | `fig:q1_alt` | F10 |

---


## F0 四问统一建模框架及信息递进关系

- 文件：`paper/figures/framework.pdf` / `.png`
- 类型：框架图（TikZ 生成，无需数值数据）。上层为四问共用的物理内核、执行器与
  独立核算器，并嵌入问题一"日内调度示意解"（分时电价柱 + 储能轨迹，仅示意
  结构、不取正式数值）；下层为四问逐级增加的信息集、滚动机制与结算方式，每问
  附信息可得性条或双价格通道条。
- 源文件：`paper/figures/framework_tikz.tex`（正文第 2 章 2.1 直接 `\input`）；
  独立渲染入口 `paper/figures/framework_standalone.tex`。
- 生成脚本：`src/render_framework_figure.py`（xelatex 编译 + pdftocairo 转 300 dpi PNG）。
- 数据：无。结构来自论文第 2 章与各问建模口径。
- 交叉核验：与 2.1 总体建模思路、第 5–8 章模型设定一致；不引入任何数值结论。
  正文与支撑材料图同源，由同一份 `framework_tikz.tex` 生成。

---

## F1 问题一典型日购电—光伏—储能协同调度结果

- 文件：`paper/figures/q1_dispatch.pdf` / `.png`
- 脚本：`src/plots/plot_q1_dispatch.py`
- 数据：`outputs/q1_scheme_a/q1_dispatch.csv`
- 字段：`slot, price, load, pv_available, pv_used, grid_contract, grid_delivered,
  charge, discharge, soc_start, soc_end`
- 聚合：逐槽原始值，不做平滑。时间轴由槽位换算（槽 t 的结束时刻 = (t+1)/6 小时）。
- 参考线：`SOC_MIN=1200`、`SOC_MAX=10800`、初始/终端 `6000` kWh。
- 交叉核验：全天购电量 `59482.699` kWh、购电费 `35126.949` 元与表
  `tab:q1_grid` 及 `outputs/q1_scheme_a/q1_paper_tables.json` 一致。

---

## F2 问题二全年逐日费用与紧急购电变化

- 文件：`paper/figures/q2_yearly_series.pdf` / `.png`
- 脚本：`src/plots/plot_q2_yearly.py`
- 数据：`outputs/q2/q2_daily_summary.csv`
- 字段：`date, cost_normal, cost_emergency, cost_total, grid_emergency_kwh`
- 聚合：按自然日；`total_cost = cost_normal + cost_emergency`。原始逐日细线，
  叠加 14 日滚动均值作为趋势（明确区分为平滑线）。
- 区间：2025-02-01 至 2025-12-31，334 天。
- 标注：单日紧急购电量最高点（按正式数据取 `grid_emergency_kwh` 最大值，不硬编码）。
- 交叉核验：全年总费用 `16 886 077.67` 元、正常合同费 `12 190 821.03` 元、
  紧急购电费 `4 695 256.64` 元、紧急购电量 `1 199 863.45` kWh，与表
  `tab:q2_result` 一致。

---

## F3 问题二各月正常合同费用与紧急购电费用构成

- 文件：`paper/figures/q2_monthly_cost.pdf` / `.png`
- 脚本：`src/plots/plot_q2_monthly.py`
- 数据：`outputs/q2/q2_daily_summary.csv`
- 字段：`date, cost_normal, cost_emergency`
- 聚合：按自然月求和，单位万元。柱顶小字号标注紧急购电费占月总费用百分比。
- 交叉核验：11 个月加总 = `16 886 077.67` 元；紧急购电费加总 = `4 695 256.64` 元。

---

## F4 问题三不同日内发布时点下光伏预报绝对误差分布

- 文件：`paper/figures/q3_forecast_error.pdf` / `.png`
- 脚本：`src/plots/plot_q3_forecast_error.py`
- 数据来源：
  - 预报：`data/raw/official/附件3.xlsm`（经 `core.q3_forecast.expand_issue_forecast`
    按正式口径线性展开，与回放器使用完全相同的接口）
  - 真值：`outputs/q3/q3_dispatch.csv` 字段 `pv_available`（kWh/10min，×6 换算为 kW）
- 样本定义（可复现、公平口径）：对每个正式评价日与发布时点
  r ∈ {0:00,6:00,12:00,18:00}，起始槽位 s_r ∈ {0,35,71,107}，取该时点之后当天
  尚未执行的全部有效时段（槽 s_r … 143），用该时点可获得的附件3预报版本展开后
  与实际光伏比较：
  `absolute_error = |forecast_pv - actual_pv|`（单位 kW）。
  样本量：0:00 为 144 槽/日、6:00 为 109 槽/日、12:00 为 73 槽/日、18:00 为 37 槽/日。
- 辅助统计：MAE、median AE、IQR 在脚本中同时计算并打印（见运行日志）。
- 说明：不同发布时点的剩余窗口长度不同，本图反映的是各发布时点在实际滚动决策中
  可获得预报的误差分布，不等价于同一 lead time 预测器优劣比较。离群点不删除，
  按标准箱线图规则（1.5×IQR）绘制，α 调低。
- 交叉核验：不直接对应费用数字；与经济价值判断的衔接见第 7 章与表 `tab:q3_ablation`。

---

## F5 问题三相对问题二的费用改善来源分解（瀑布图）

- 文件：`paper/figures/q3_cost_waterfall.pdf` / `.png`
- 脚本：`src/plots/plot_q3_cost_waterfall.py`
- 数据：`outputs/q3/q3_update_ablation.json`（`configurations` 各档 `total_cost`）
- 阶梯：Q2 基准 → 仅 0:00（附件3预报+初始计划）→ +6:00 → +12:00 → +18:00 → Q3 最终
- 聚合：直接取各档 `total_cost`（元），显示单位万元。
- 交叉核验：基准 `16 886 077.67`；00 档 `16 350 694.80`；00+06 `16 008 998.90`；
  00+06+12 `15 805 748.88`；最终 `15 805 751.77`。与表 `tab:q3_ablation` 一致。
- 注：0:00 阶段同时包含预报来源与初始计划变化，图中单列，不与日内追加更新合并。

---

## F6 问题二与问题三的月度费用及累计经济收益

- 文件：`paper/figures/q3_monthly_cumulative.pdf` / `.png`
- 脚本：`src/plots/plot_q3_monthly_cumulative.py`
- 数据：`outputs/q2/q2_daily_summary.csv`（`cost_total`）、
  `outputs/q3/q3_daily_summary.csv`（`total_cost`）
- 聚合：
  - (a) 按自然月求和（万元），Q2 与最终 Q3 并列比较；
  - (b) 逐日 `saving_d = cost_Q2_d - cost_Q3_d`，累计
    `cumulative_saving_D = Σ_{d≤D} saving_d`（万元）。
- 交叉核验：累计曲线末点 = `16 886 077.67 − 15 805 751.77 = 1 080 325.90` 元
  （正式精确值 `1 080 325.89` 元）。局部下降不予隐藏。

---

## F7 2025 年 9 月 23 日问题三滚动调度机制

- 文件：`paper/figures/q3_typical_day_dispatch_20250923.pdf` / `.png`
- 脚本：`src/plots/plot_q3_typical_day.py`
- 数据：`outputs/q3/q3_dispatch.csv`，日期 `2025-09-23`
- 字段：`slot, load_actual, pv_available, initial_contract, final_contract,
  grid_emergency, charge_actual, discharge_actual, soc_start, soc_end`
- 聚合：逐槽原始值；发布时点 0:00/6:00/12:00/18:00 以细竖虚线标出。
- 交叉核验：该日费用 `49 871.39` 元、紧急购电 `1 778.48` kWh 与表
  `tab:required_dates_summary` 第三问 9 月 23 日行一致。

---

## F8 波动电价下典型日预测价格与真实结算价格对比

- 文件：`paper/figures/q4_price_forecast.pdf` / `.png`
- 脚本：`src/plots/plot_q4_price.py`
- 数据：`outputs/q4/q4_2_dispatch.csv`
- 字段：`date, slot, price_actual, price_forecast`
- 典型日选择规则（客观、可复现，不主观挑图）：对正式评价期每个自然日计算当日
  `price_actual` 的标准差，按该标准差排序，取最接近全年中位数的一天。
  结果：`2025-02-25`（当日标准差 `0.31687` 元/kWh，接近中位数 `0.31692`）。
- 聚合：逐槽原始值。纵轴元/kWh。
  (a) 真实价实线 vs 0:00 因果预测价虚线；(b) 误差 `error = price_forecast − price_actual`，
  零线上下区分正负。
- 说明：仅用于事后展示预测误差；正式计划优化只读取决策时点可获得的历史价格。

---

## F9 波动电价下两条策略的逐月实际结算费用

- 文件：`paper/figures/q4_cost_comparison.pdf` / `.png`
- 脚本：`src/plots/plot_q4_monthly.py`
- 数据：`outputs/q4/q4_monthly_costs.csv`（由 `q4_2_daily_summary.csv`、
  `q4_3_daily_summary.csv` 按月聚合而来）
- 字段：`month, q4_2_cost, q4_3_cost`
- 聚合：按自然月求和，单位万元。全部费用均使用真实波动价格结算。
- 交叉核验：第二问式 11 个月加总 `17 743 324.88` 元；第三问式加总
  `16 606 095.44` 元，与表 `tab:q4_result` 一致。

---

## F10 参数敏感性与输入稳健性 / 主模型与替代模型验证

- 文件：`paper/figures/q1_sensitivity_robustness.pdf` / `.png`、
  `paper/figures/q1_alternative_validation.pdf` / `.png`
- 脚本：`src/plots/plot_q1_validation.py`
- 数据：
  - `outputs/q1_validation/q1_sensitivity.csv`（字段 `scenario, cost_change_vs_base_pct`）
  - `outputs/q1_validation/q1_robustness.csv`（字段 `noise_level_pct, cost_yuan`）
  - `outputs/q1_validation/q1_alternative_comparison.csv`
    （字段 `main_grid_kwh, alternative_grid_kwh, main_soc_end_kwh, alternative_soc_end_kwh`）
- 聚合：直接读取，不做二次加工。散点图加 y=x 参考线；SOC 轨迹主模型实线、替代模型虚线。
- 交叉核验：替代模型费用 `35126.948589` 元与主模型差处于浮点量级，与
  `outputs/q1_validation/q1_validation_summary.json` 一致。

---

## 闭合校验汇总（脚本运行时自动断言）

| 项目 | 正式值 | 校验位置 |
| --- | --- | --- |
| Q1 全天购电量 / 购电费 | 59482.699 kWh / 35126.949 元 | F1 脚本 |
| Q2 全年总费用 | 16 886 077.67 元 | F2、F3、F6 脚本 |
| Q2 正常合同费 / 紧急购电费 | 12 190 821.03 / 4 695 256.64 元 | F2、F3 脚本 |
| Q2 紧急购电量 | 1 199 863.45 kWh | F2 脚本 |
| Q3 消融四档 | 16350694.80 / 16008998.90 / 15805748.88 / 15805751.77 元 | F5 脚本 |
| Q3 最终总费用 / 紧急购电量 | 15 805 751.77 元 / 809 227.14 kWh | F5、F6 脚本 |
| Q3 相对 Q2 节省 | 1 080 325.89 元 | F6 脚本 |
| Q4 第二问式 / 第三问式 | 17 743 324.88 / 16 606 095.44 元 | F9 脚本 |
