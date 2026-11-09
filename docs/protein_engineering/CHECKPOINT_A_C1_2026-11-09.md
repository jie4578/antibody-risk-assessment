# Phase A–C.1 选择性本地检查点

日期：2026-11-09。范围仅为既有 Phase A/B/B.1/C.1 成果的审查、回归与本地版本固定。
没有新功能开发，没有进入 C.2，没有训练模型、重算密封实验结果或调用真实 Provider。

## 基准与范围

已执行 `git fetch origin`；开始时 main、HEAD 与刷新后的 origin/main 均为
`846bb6c5c0f43a56c909bc02c92ae745bc7f7f95`，索引为空。
拟建本地提交消息：`feat(protein): integrate data foundation and initial-rate analysis`。
不推送、不打 tag、不发布 v4.1.0，不改历史提交或 Release。

已阅读并对照实现审查四份历史记录：

- `IMPLEMENTATION_AUDIT_2026-11-09.md`：A/B 实施时的历史快照，不代表 C.1 后的当前状态。
- `PHASE_B1_DATA_AUDIT.md`：原始层保护、单位/WT 关联、重复、导出与迁移审计。
- `PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md`：`initial-rate-1.0.0` 方法、UI 与科学限制。
- `PHASE_B1_C1_DELIVERY.md`：B.1/C.1 实施时的测试、未提交 Git 状态和本地候选记录。

确认：同一 Desktop 第七入口、九类空模板、CSV/XLSX 校验、来源原件/SHA256、
SQLite v1/v2→v3 增量迁移、原始与派生表隔离、事务回滚与原始记录不可覆盖。
Windows 管线同一 exe/安装器，不包含真实数据库、实验数据、模型、密钥或缓存。
现有 candidate-006 的130个源文件摘要与本轮审查的运行时代码一致；本轮不重建或上传它。

## 本轮唯一额外修复：来源文件换行

本机 `core.autocrlf=true`。临时索引的 Windows 检出复现：13份 Phase 0 原件和运行时
副本共26文件被转换为 CRLF，SHA256 与来源清单不符；原工作树测试无法发现这个问题。
原件内容未被修改。已按用户追加批准，仅为26个确切路径添加 `.gitattributes` 的
`text eol=lf`；不扩大到其他目录或 Excel 文件，不修改原来源摘要或模板内容。

修复后同样的 Windows 检出：**26/26 SHA256 PASS**；从检出副本实际运行
`test_phase0_resources_match_provenance_and_are_header_only`：**1 passed in 0.06s**。
真实索引在此检查期间保持为空，验证产物仅存忽略的 dist。

## 本轮实际安全回归

解释器：`dist/4.1.0rc2/venv-build/Scripts/python.exe`，Python 3.14.8 / PySide6 6.12.0。
均设置 `QT_QPA_PLATFORM=offscreen`；缓存、basetemp 与日志写入
`dist/protein-engineering/checkpoint-review/`，不纳入提交。
下列命令的 `python` 指上述解释器；附加的缓存/临时目录选项不改变测试选择。

```text
python -m pytest -o addopts='' tests/test_protein_engineering.py tests/test_protein_initial_rate.py tests/test_protein_rate_storage.py tests/test_desktop_protein_engineering.py tests/test_desktop_protein_initial_rate.py tests/test_installed_package.py tests/test_windows_delivery.py -q -ra
```

结果：**135 passed in 4.60s**。包含 C.1 数值45、SQLite18、C.1 Desktop8、既有 A/B36、
A/B Desktop6、安装 wheel1、Windows打包21；不重复累加回归数量。
v1/v2 SQL摘要不变，合成旧库升级保留数据；无真实用户数据库迁移。

```text
python -m pytest -o addopts='' -m 'not live' tests --ignore=tests/test_ml.py --ignore=tests/test_rag.py -q -ra
```

结果：**872 passed, 2 skipped, 7 deselected, 18 warnings in 10.26s**。
两项跳过为 `tests/test_agent.py:113`、`:121` 的可选 LangChain 测试（环境未安装）。
7项 live 用例未选；18项 warnings 为既有 Gradio 提示与 pandas API/dtype 警示。
整文件排除 `test_ml.py` / `test_rag.py`，避免历史训练/TF-IDF fit 路径。

另外从真实暂存树检出完整候选（不含本机未提交 .env、两份 CLI 使用 HEAD 基准版本）
再次运行同一安全应用选择。第一次因9个既有 Mock 测试的 LLM 构造器要求非空环境值，
得到 `9 failed, 863 passed, 2 skipped, 7 deselected, 18 warnings`；错误均为缺少
DEEPSEEK_API_KEY，没有 Provider 请求。这是隔离测试环境的缺失输入，不修改生产代码或测试。

随后实际使用 `python -` 测试启动器调用 `pytest.main`（相同选择参数），仅在该进程设置
`DEEPSEEK_API_KEY=OFFLINE-SYNTHETIC-NOT-A-CREDENTIAL`、`GRADIO_ANALYTICS_ENABLED=False`、
`HF_HUB_OFFLINE=1`，并拦截外部 socket/DNS、保留本机 loopback 给 Qt/Windows 事件循环。
候选重验：**872 passed, 2 skipped, 7 deselected, 18 warnings in 9.71s**。
日志为忽略的 `dist/protein-engineering/checkpoint-review/staged-application-tests-002.log`。
未复制真实凭据或私有文件，未改变基准 CLI。现有 CI 本来就为这些 Mock 测试提供非空假值。

```text
python -m pytest -o addopts='' validation/tests/test_external_preregistration.py validation/tests/test_phase5e_summary.py validation/tests/test_phase8_documentation.py validation/tests/test_ml_inference_runtime.py::test_builder_does_not_reference_or_load_sealed_test_labels validation/tests/test_ml_inference_runtime.py::test_no_external_provider_and_cpu_fallback_in_runtime_source validation/tests/test_ml_inference_runtime.py::test_core_and_scoring_are_not_modified -q -ra
```

结果：**17 passed in 1.05s**。仅核对既有协议、公开汇总、冻结摘要和源码；不运行完整历史
验证套件中的模型构建/重训/评价用例，不打开 AIntibody 密封 TEST 标签。

`git diff --check` 与临时候选 `git diff --cached --check` 均通过。
正式暂存仅使用明确文件列表，提交前再次核对清单、差异与敏感文件边界。

## 内容与科学保护

逐文件检查文本、Python AST、JSON、CSV表头及来源摘要。九模板均只有表头。
敏感模式匹配仅为 HEAD 中已存在的合成 secret-redaction 测试 fixture，没有引入真实凭据。
原四文档/九模板与用户ZIP清单一致，来源ZIP未执行任何脚本、未进入Git。

保留且不暂存：`cli.py`、`literature/cli.py`、`manual_acceptance.csv.xlsx`、
`pytest-of-Administrator/`，以及忽略的 dist、批量文件、用户数据库与模型产物。
不修改 core/scoring、冻结 ML、ESM2 revision、AIntibody/GDPa3 结果或 release tags。

当前初始速率只是显式窗口 OLS 与可选已报告标定，不宣称初始反应条件已实验验证。
线性/R²不充当有效性证明，不自动挑窗口/删点，不造缺失值。
Michaelis–Menten、WT统计比较、AI预测验证、结构映射、DBTL仍未实现。
触发器不等于文件级防篡改，条件标准误不包含完整实验不确定性。
无真实酶数据验收、干净 Win10/Win11 安装/人工验收或本检查点远程 CI 结果。
未来推送及 CI 范围须另行审核：既有默认 CI 的全量 pytest 含历史训练测试，本轮未触发。

## 拟固定的完整文件清单

以下68个明确路径属于本轮已核实范围；没有目录递归暂存或 `git add -A`。

```text
.gitattributes
.gitignore
MANIFEST.in
README.md
ROADMAP.md
desktop/installation_smoke.py
desktop/main_window.py
desktop/widgets/protein_engineering.py
desktop/widgets/protein_initial_rate.py
docs/PROTEIN_ENGINEERING_ROADMAP.md
docs/protein_engineering/ANALYSIS_REQUIREMENTS.md
docs/protein_engineering/CHECKPOINT_A_C1_2026-11-09.md
docs/protein_engineering/DATA_DICTIONARY.md
docs/protein_engineering/FOUNDATION_STATUS.md
docs/protein_engineering/IMPLEMENTATION_AUDIT_2026-11-09.md
docs/protein_engineering/PHASE0_DATA_INTAKE.md
docs/protein_engineering/PHASE0_PACKAGE_PROVENANCE.json
docs/protein_engineering/PHASE_B1_C1_DELIVERY.md
docs/protein_engineering/PHASE_B1_DATA_AUDIT.md
docs/protein_engineering/PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md
docs/protein_engineering/templates/ai_predictions_template.csv
docs/protein_engineering/templates/assay_results_template.csv
docs/protein_engineering/templates/enzyme_targets_template.csv
docs/protein_engineering/templates/experiment_batches_template.csv
docs/protein_engineering/templates/kinetic_timecourse_template.csv
docs/protein_engineering/templates/protein_variants_template.csv
docs/protein_engineering/templates/samples_template.csv
docs/protein_engineering/templates/source_manifest_template.csv
docs/protein_engineering/templates/structure_assets_template.csv
packaging/windows/workbench.spec
protein_engineering/__init__.py
protein_engineering/importer.py
protein_engineering/initial_rate.py
protein_engineering/migrations.py
protein_engineering/models.py
protein_engineering/rate_storage.py
protein_engineering/resources.py
protein_engineering/resources/phase0/ANALYSIS_REQUIREMENTS.md
protein_engineering/resources/phase0/DATA_DICTIONARY.md
protein_engineering/resources/phase0/FOUNDATION_STATUS.md
protein_engineering/resources/phase0/PHASE0_DATA_INTAKE.md
protein_engineering/resources/phase0/PHASE0_PACKAGE_PROVENANCE.json
protein_engineering/resources/phase0/PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md
protein_engineering/resources/phase0/PROTEIN_ENGINEERING_ROADMAP.md
protein_engineering/resources/phase0/templates/ai_predictions_template.csv
protein_engineering/resources/phase0/templates/assay_results_template.csv
protein_engineering/resources/phase0/templates/enzyme_targets_template.csv
protein_engineering/resources/phase0/templates/experiment_batches_template.csv
protein_engineering/resources/phase0/templates/kinetic_timecourse_template.csv
protein_engineering/resources/phase0/templates/protein_variants_template.csv
protein_engineering/resources/phase0/templates/samples_template.csv
protein_engineering/resources/phase0/templates/source_manifest_template.csv
protein_engineering/resources/phase0/templates/structure_assets_template.csv
protein_engineering/schema.py
protein_engineering/sequences.py
protein_engineering/storage.py
pyproject.toml
tests/test_desktop_chinese.py
tests/test_desktop_phase1.py
tests/test_desktop_protein_engineering.py
tests/test_desktop_protein_initial_rate.py
tests/test_installed_package.py
tests/test_protein_engineering.py
tests/test_protein_initial_rate.py
tests/test_protein_rate_storage.py
tests/test_windows_delivery.py
tools/build_windows.py
tools/make_windows_portable.py
```
