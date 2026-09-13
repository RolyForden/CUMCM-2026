# 国赛论文写作与绘图 Skills 候选清单

> 检索时间：2026-09-13。来源：GitHub API 搜索（cumcm / 数学建模 / academic paper / scientific figure）+ 本地 pipeline 路由表已知名称。star 数为检索时点值。本清单只做候选，不替代逐个试用。

## A. 数模全流程 Skill（内嵌论文写作模块）

| Skill / 仓库 | ⭐ | 写作相关亮点 | 备注 |
|---|---|---|---|
| jihe520/MathModelAgent | 5135 | 自动完成建模并生成可直接提交论文 | 全自动黑盒感强，适合参考写作流程 |
| XiaoMaColtAI/math-modeling-skill | 1520 | 三阶段工作流，DOCX 论文生成，算法资源库 | CUMCM/MCM 专用，中文文档 |
| zhnnky329/MathModeling-skills | 888 | 分阶段建模 + 论文写作，Python/MATLAB 双分支 | Claude Code/Codex 通用 |
| yushui2022/MathModel-Skill | 429 | 题解→建模→写作→Word 交付 | 强调 evidence checks |
| Lupynow/math-modeling-skills | 381 | 一条龙，覆盖 CUMCM A/B/C + MCM A-F | 含论文模板 |
| BZDmathclub/bzd-math-modeling-skills | 331 | **国赛论文智能评审**（近五年评阅细则蒸馏） | 非写作，但定稿前自查价值高 |
| handsomeZR-netizen/mathmodel-skill | 280 | 10 阶段 + 4 反馈层 + LaTeX | harness-agnostic |
| RealSeaberry/AutoMCM-Pro | 245 | GitOps 流水线 + 代码自证 | 支持 opencode |
| sweetcornna/mathodology | 228 | 获奖级建模工作流（MCM/ICM/CUMCM） | |
| xuec699-sudo/math-modeling-skills | — | 5 人评审团、模型依赖 DAG、一站式论文 | 工业级 |
| Yoki-cmd/math-modeling-single | 16 | LaTeX-only，自带国赛标准模板，xelatex 编译 | 轻量，与本地 pipeline 同栈 |
| Y-love-han/math-modeling-skill | 14 | 12 阶段状态机、哈希链账本、56 模板 | 证据优先，偏重型 |

## B. 学术论文写作 / 润色 / 评审 Skill

| Skill / 仓库 | ⭐ | 亮点 | 对国赛的价值 |
|---|---|---|---|
| lishix520/academic-paper-skills | 1284 | strategist（规划）+ composer（写作）+ 质量检查点 | 结构规划 |
| bahayonghang/academic-writing-skills | 458 | 格式校验、语法润色、去 AI 味、审稿人视角审计，LaTeX/Typst/PDF | **去 AI 味 + 评审自查，最贴国赛定稿** |
| chtc66/academic-skills | 348 | 读论文/综述/实验总结/rebuttal | 备选 |
| LMDHQ-0420/ResearchPilot-Skills | 284 | 文献到写作全流程 | 备选 |
| yunshenwuchuxun/latex-paper-skills | 259 | 模块化 LaTeX 写作/修订/管理 | 与本地 main.tex 流程兼容 |
| cLin-c/paper-skill | 102 | SCI/IEEE 期刊 prompt 库（写作/润色/审稿/翻译） | 英文强，国赛可借润色 |
| Imbad0202/academic-research-skills | — | research→write→review→revise→finalize | 闭环流程 |

## C. 科学绘图 Skill

| Skill / 仓库 | ⭐ | 亮点 | 对国赛的价值 |
|---|---|---|---|
| Haojae/scipilot-figure-skill | 2317 | 出版级科研图 copilot | **数据图主力候选** |
| Dsadd4/AgentFigureGallery | 153 | 参考图库驱动（matplotlib/ggplot2/Nature 风） | 风格对齐优秀论文 |
| BAIKEMARK/happy-figure-skill | 145 | 从研究内容生成结构化图 prompt | 配合 InfMind 出概念图 |
| myzhao0114-del/scientific-figure-skill | 57 | 规范科研绘图流程、减少 AI 幻觉 | 轻量 |
| ywq177995212697-droid/visio-scientific-figures | 53 | 可编辑 Visio 图 + 质量检查 | 需要 Visio 环境 |
| TAO-QKV/Icarus-Figures | 40 | matplotlib & TikZ 出版级、质量门槛 | 与 LaTeX 论文同栈 |
| lwq-star/ultraplot-figures | 31 | UltraPlot 可复现静态图 | 备选 |

## D. 索引 / 市场（后续自行补搜用）

- ComposioHQ/awesome-claude-skills（74.9k⭐）与 hesreallyhim/awesome-claude-code（53.9k⭐）：技能总索引，按 writing/figure 分类找
- skihub.ai：Claude skills 市场，可搜 modex-mcm-writing、Humanizer-zh、academic-figures-drawer、scientific-visualization、nature-skills、figures4papers（本地 pipeline 路由表提到但未在 GitHub 搜到，应在市场侧查）
- 本地已有 `cumcm-master-pipeline` 为编排主干，上面技能按路由表只承担单一环节

## 初步筛选建议（按三环节各配 1-2 个）

1. **写作**：bahayonghang/academic-writing-skills（去 AI 味 + 评审）＋ XiaoMaColtAI 或 Yoki-cmd 的国赛模板
2. **绘图**：scipilot-figure-skill（数据图）＋ happy-figure-skill / AgentFigureGallery（概念图 prompt 与风格）
3. **自查**：bzd-math-modeling-skills（国赛评阅细则评审）
