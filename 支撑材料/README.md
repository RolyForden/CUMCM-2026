# C题支撑材料说明

本目录是提交用精简支撑材料，不包含体积较大的逐槽审计中间文件。正式结果均可由这里的源程序和官方附件重新生成。

## 目录

- `源码/`：项目 `src/` 中全部53个 Python 源文件，保留 `core/` 子目录结构。
- `正式结果/`：五份已经填写并核验的正式结果工作簿。
- `官方附件/`：附件1至附件5原始输入和官方空模板，保持原文件不变。
- `论文图/`：论文使用的四张 PNG 结果图。
- `AI 工具使用详情.pdf`：AI辅助范围、提问方式、采纳原则和人工核验说明。
- `requirements.txt`：主要 Python 运行依赖。
- `SHA256SUMS.txt`：包内文件完整性校验值。

## 运行环境

- Python 3.13.9
- Windows 11 / PowerShell
- 依赖版本见 `requirements.txt`

建议在虚拟环境中安装依赖：

```text
python -m pip install -r requirements.txt
```

程序默认按原仓库结构读取 `data/raw/official/` 并写入 `outputs/`。如需完整复现，请将：

- `官方附件/` 复制为 `data/raw/official/`；
- `源码/` 复制为 `src/`；
- 在项目根目录运行相应生成与验证脚本。

主要入口：

```text
python src/generate_q1_result.py
python src/generate_q2_result.py
python src/generate_q3_result.py
python src/generate_q4_results.py
python src/finalize_q4_results.py
```

主要验证入口：

```text
python src/validate_q1.py
python src/q2_three_day_acceptance.py
python src/validate_q3_result.py
python src/validate_q4_results.py
```

说明：全年滚动计算耗时较长；第四问程序支持按日落盘和恢复。原始附件只读，不应在复现过程中覆盖。

