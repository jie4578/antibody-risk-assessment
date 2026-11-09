# Phase C.1 — GitHub Actions 安全 CI 审查

日期：2026-11-09。范围仅 `.github/workflows/ci.yml` 与本说明。
基准 checkpoint：`25f086122c21de2ebd334f9077aaf548d86e4d9d`（68文件，不 amend）。
`git fetch origin` 后远端 main 仍为 `846bb6c5c0f43a56c909bc02c92ae745bc7f7f95`。
开始时索引为空，两份 CLI 修改、手工表、旧 pytest 目录保持。本轮只建立独立本地提交，
不 push、不 tag、不 Release、不开始 C.2，不改测试断言/模型/科学算法。

## 1. 审查方法与发现

检查测试函数体、fixture、被调用实现和文件路径，而非按文件名判断安全。

1. 原三个默认 job 均直接 `python -m pytest -q`，因此包含 `tests/test_ml.py` 的
   `small_df -> build_dataset(n=160)` 与 `train_pipeline`；实际拟合 Logistic/Ridge/RandomForest，
   `test_save_load_bundle` 还会写入 tmp_path 的 joblib artifact。
2. `tests/test_rag.py` 不只是文本检索：`test_tfidf_embedder_roundtrip` 直接 fit；
   hybrid/end-to-end/index 测试经 `RagPipeline.index` 拟合 TfidfVectorizer。
3. **仅忽略上述两个文件不足以保证无训练**：10个 Agent/Orchestrator 用例通过
   `agent.tools.tool_rag_search -> RagPipeline(embedder='tfidf').index -> TfidfEmbedder.fit`
   间接拟合。以前872项的命令只是离线回归，不是严格无拟合的证明；本轮更正此边界。
   LangChain 的真实 tool.invoke 测试同样调用此路径，不能因当前未安装依赖而忽略。
4. 原 integrity 任务的四个文件经逐函数/fixture检查均可保留：合成规则、fake tokenizer/model、
   已发布汇总摘要只读比较，以及 tmp_path 合成 HIC workbook/statistics。它们不调用真实
   Phase8 evaluation runner、不打开 GDPa3 原件、不写冻结结果、不训练/载入真实 ESM。
5. `validation/tests/test_ml_inference_runtime.py` 的 `built_models` fixture 实际调用
   `build_deployment_models`，会读 TRAIN/VALIDATION 标签/embedding并拟合、写模型。
   名称含 frozen/manifest/runtime 也不能整文件放入默认 CI；仅三个无 fixture 的源码检查列入白名单。
6. Phase5C 的 scaler 用例确实 `pipeline.fit`，即使只用两行合成数组也属于训练 opt-in；
   Phase5D seal 用例会打开真实 sealed_test_labels；不能以“只校验 hash”为由自动执行。

没有发现本轮默认白名单会写回冻结结果。部分历史 runner 在调用时会输出分析产物，
故不能把整份 validation 目录直接交给默认 pytest。本轮没有运行这些历史数据用例。

## 2. 分类与明确执行范围

分类可以重叠；例如 deployment fixture 同时需要真实外部数据与拟合许可。
SAFE_CI 表示已审查的执行清单，不表示仓库里所有其他测试均不安全。
混合文件里的纯函数测试仍保留原样；未列入默认范围不等于断言被删掉。

### SAFE_CI

应用选择以已经验收的命令为基础，额外排除下文10个明确间接拟合 node ID：

```text
python -m pytest -o addopts='' -m 'not live' tests --ignore=tests/test_ml.py --ignore=tests/test_rag.py [每个 TRAINING_NODES 加 --deselect=<nodeid>] -q -ra
```

实际由 YAML 内的统一 Python shell runner 调用 `pytest.main`；同一 YAML anchor 用于
Linux矩阵、可选依赖和 Windows/Linux desktop job，不存在某个 job 偷用全量 pytest 的例外。
无 AI 数值生成。C.1 OLS 合成数值测试仍包含在应用范围内，不属于 ML 训练。
三个既有 job ID 与 check 显示名也保持，避免无意改变分支保护所依赖的检查名称。

| 计划 job / step | 环境 | 范围 |
|---|---|---|
| `test` | Ubuntu / Python 3.10、3.11、3.12，原矩阵不变 | guarded application，864个选中 node（本机收集） |
| `test-optional` application | Ubuntu / Python 3.12，CPU torch + all extras（含 LangChain） | 完全相同 application 排除边界；工具包装的纯契约测试保留 |
| `test-optional` optional-compatibility | 同上 | `tests/test_ml.py::test_transformer_build_when_torch_present`，小型随机模型构造/前向形状检查，不 fit、无 optimizer/backward、无权重下载 |
| `desktop-integrity` application | Ubuntu / Windows，Python 3.12，Qt offscreen | 同一 application；含 wheel 构建/安装外导入、资源、原六页与新增第七页 |
| `desktop-integrity` integrity | 同上，Biopython依赖与完整 Git历史保留 | 下方15项合成/只读完整性白名单 |

Protein Engineering 已由默认应用选择覆盖，不增加重复的 CI job：数据模型/来源/序列、
SQLite v1/v2→v3、原件不可覆盖、初始速率数值、异步 Desktop 与第七入口、wheel资源。
相关7文件135项专项本轮另作本地分组验收，但不重复加入默认 CI 任务。

保留原 integrity 四个整文件：

```text
validation/tests/test_audit_compatibility.py                         # 2项，合成NNST与Git源码边界
validation/tests/test_runtime_embedding_parity.py                  # 1项，FakeTorch/Tokenizer/Model
validation/tests/test_phase8_documentation.py                       # 2项，只读已发布汇总与摘要
validation/external_developability/tests/test_phase8c_hic_external_evaluation.py # 7项，合成 workbook/labels/tmp_path
```

最后一文件虽调用统计函数做合成单元验证，但不执行真实GDPa3评价、不修改seal/result。
原始实验标签/工作簿和冻结测试个体记录不参与。另添加三个无 `built_models` fixture 的检查：

```text
validation/tests/test_ml_inference_runtime.py::test_builder_does_not_reference_or_load_sealed_test_labels
validation/tests/test_ml_inference_runtime.py::test_no_external_provider_and_cpu_fallback_in_runtime_source
validation/tests/test_ml_inference_runtime.py::test_core_and_scoring_are_not_modified
```

### TRAINING_OPT_IN

仅 `workflow_dispatch` 且 `run_training_tests == true` 启动；默认false；push/PR条件均不成立。
保留历史测试，49项仅在手动训练 job 中选择：

- `tests/test_ml.py`：包含4个明确拟合用例与 tmp_path artifact；其余编码/构造/数据生成测试
  与历史文件共同保留于该手动组，并非声称每一项都训练。可选 Transformer 兼容项单独保留默认检查。
- `tests/test_rag.py`：包含4条实际 TF-IDF fitting/index 路径；其余纯检索辅助测试也随历史文件保留。
- 下方10个已核实的间接 TF-IDF node ID（原函数/断言不改）。
- `validation/tests/test_phase5c_benchmark.py::test_standard_scaler_can_only_be_fitted_on_supplied_train_rows`：
  合成两行数组拟合 StandardScaler+Ridge，不读取真实数据。

此手动 job 只选合成弱标签/内置知识库测试，不运行真实冻结 deployment rebuild。
训练产物仅原测试 tmp_path；没有 artifact上传、发布或推送步骤。

### LIVE_OPT_IN

仅 `workflow_dispatch` 且 `run_live_tests == true` 启动；默认false；push/PR不启动。
该 job 可能访问外网或消耗API额度；只有独立专用 secret `CI_LIVE_DEEPSEEK_API_KEY`
可传入此 job，不传入任何 SAFE_CI。无凭据配置持久化到Git，测试profile不保存Key。

```text
tests/test_literature/test_live.py::test_live_europepmc_search
tests/test_literature/test_live.py::test_live_pubmed_search
tests/test_literature/test_live.py::test_live_fulltext_oa
tests/test_desktop_acceptance_live.py::test_real_agent_calls_scan_and_preserves_overlapping_sequons
tests/test_desktop_acceptance_live.py::test_real_copilot_explains_only_synthetic_summary
tests/test_desktop_acceptance_live.py::test_real_copilot_preserves_metadata_types
tests/test_agent.py::test_local_ollama_completion_live
```

前三项确实调用 Europe PMC/PubMed；中三项在fixture许可下调用真实DeepSeek，载荷为
明确的合成AAANNSTTT摘要，不运行ML/真实实验；最后一项依赖本机Ollama服务。
缺少专用secret、可用OA论文或本机服务时按既有测试报告SKIPPED，不宣称真实Provider验收通过。
本轮只收集7项，未执行该job或任何live test body。

### EXTERNAL_DATA_REQUIRED / 非默认历史混合测试

下表是调用实现与fixture审查结论，不是通过名称猜测，也不是为绕过失败而删断言。
不提供“手动全量validation”按钮绕过冻结协议。依赖真实标签、原件、embedding或模型的
测试保留在源码，需受控数据环境和相应科学授权；本轮未运行或读取其数据。

| 来源 | 实际行为与处理 |
|---|---|
| `test_foundation.py` | `normalize_aintibody` 读取真实XLSX；同文件也有tmp_path/合成函数。混合文件不默认整跑 |
| `test_feature_extraction.py` | 多项 `pd.read_csv` Jain/AIntibody processed数据；合成回归函数单独存在，不整文件默认跑 |
| `test_jain_benchmark.py` | `load_jain_inputs`/source columns读真实实验表，其他函数用合成数组；默认不重算Jain关系 |
| `test_aintibody_population_audit.py` | `_run` 读processed/feature表并写tmp审计输出，非纯源码检查 |
| `test_aintibody_external_validation.py` | `load_primary_join` 后重新计算实际assay/classification结果；不默认运行 |
| `test_hic_robustness.py` | 真实PRIMARY/FEATURES关联；分类调整会拟合，兼属TRAINING_OPT_IN；不默认重跑 |
| `test_ml_similarity_split.py` | 既有population与`write_split_artifacts`读外部processed并重写tmp split/labels；有纯合成图测试混合 |
| `test_ml_benchmark_preregistration.py` | 首项读取真实primary；其他协议/源码项只读。未整体列入白名单 |
| `test_ml_benchmark_amendment.py` / `test_ml_benchmark_entity_exact.py` | 真实population路径与纯合成小图/临时seal并存；不能整文件当作纯合成 |
| `test_esm2_embeddings.py` | FakeModel合成项安全，但多项 `load_frozen_split_inputs(ROOT)` 读外部split；默认只由parity复用fake类，不调用那些fixture |
| `test_phase5c_benchmark.py` | `load_phase5c_data` 读TRAIN/VALIDATION标签/NPZ；scaler纯合成fit已单列手动；其他协议项未扩大默认 |
| `test_phase5d_evaluation.py` | `verify_test_seal` 实际打开sealed TEST labels与test_features；严禁默认执行整文件 |
| `test_phase5e_summary.py` | 首两项读忽略的final_test manifest/aggregate CSV；另有只读已发布摘要项。本轮默认不扩展此混合文件 |
| `test_ml_inference_runtime.py` | 6项依赖`built_models` fixture，另1项直接重建两次，均会使用真实embedding/标签并写模型；仅上述3个无fixture源码项默认 |
| `test_external_preregistration.py` | 协议/常量检查及目录名审计，无拟合；SAFE_CI-eligible，本轮不扩大既有默认白名单 |
| `external_developability/tests/test_gdpa3_audit.py` / `test_phase8_preregistration.py` | Workbook()/合成DataFrame/tmp_path加源码审查，无真实工作簿读取；SAFE_CI-eligible，本轮未新增默认任务 |
| `external_developability/tests/test_phase8b_blind_prediction.py` | `_write_model`为占位字节、FakePredictor与tmp_path，不载入真实模型；SAFE_CI-eligible，但不等于可执行真实blind runner |
| `external_family_validation/tests/*` | 合成schema/hash/identity/聚类/报告与FakeModel；SAFE_CI-eligible；未新增默认任务或实际SAbDab2 embedding执行 |

真实 deployment fixture 的调用链是 `built_models -> build_deployment_models -> phase5c
TRAIN/VALIDATION数据 -> scaler/estimator.fit -> joblib`；不因fixture输出位于tmp就认为安全。
ESM2 `from_pretrained`/模型缓存下载只存在实际运行器路径，默认fake parity不会走入；
SAFE_CI不下载权重、不打开模型二进制。

## 3. CI 内的安全漂移检查

同一个受审查的内嵌Python runner（YAML anchor）供所有默认job使用：

- 在测试进程内拦截 `TfidfEmbedder.fit` 和 sklearn estimator 的 fit/fit_transform/partial_fit；
  不伪造成功结果，尝试拟合会令SAFE_CI失败，不降低原断言。
- 拦截外部socket/DNS；仅保留loopback供Qt/Windows事件循环，源码审查确认默认选择不调用
  localhost真实Provider。HF离线、Gradio遥测关闭。依赖安装仍需网络，与Provider测试分开。
- 拦截仓库的 `validation/data`、外部raw、`artifacts/ml_models`、`ml/artifacts` 打开；
  tmp_path合成数据允许。来源工件与公开冻结汇总/源码检查分开。
- 隔离Desktop profile，禁用仓库 `.env` 读取，使用明确的合成非凭据初始化值。
- collection hook 在 marker/deselect 后检查：不得混入live或10个训练node，且Protein Engineering/
  wheel关键模块必须存在。

这些是对已审查调用路径的测试防护，不是操作系统安全沙箱。测试子进程不继承Python
monkeypatch/audit hook；已审查子进程只做离线wheel、包导入、Qt诊断，不执行训练/Provider。
可选Transformer只有前向形状契约；本机无torch，未实测该依赖环境，未把它标作已通过。
未来新增训练框架、子进程或数据路径仍须重新审查，不能只凭guard名称宣称安全。

## 4. 本地验证与未执行项

环境：现有隔离Python 3.14.8 / PySide6 6.12.0；未安装新依赖，未修改Anaconda。
从最终YAML解析出的同一runner回放，不运行训练/live job。

| 检查 | 本轮实际结果 |
|---|---|
| YAML解析、重复键、内嵌Python AST/3.10语法、矩阵/手动门控结构 | PASS（本地检查，非远端GitHub执行） |
| application收集 | 864/881选中，17 deselected：7 live + 10间接fit |
| integrity收集 | 15项；无真实数据fixture |
| optional兼容收集 | 1项；本机执行时因无torch跳过 |
| guarded安全应用 | **863 passed, 1 skipped, 17 deselected, 18 warnings in 9.19s** |
| Protein Engineering/SQLite/UI/wheel/打包专项 | **135 passed in 3.83s**（已包含于应用范围，不应相加） |
| guarded只读/合成完整性 | **15 passed in 0.99s** |
| optional兼容实际执行 | **1 skipped in 0.27s**，无torch，不宣称兼容通过 |
| TRAINING_OPT_IN | 仅收集 **49项**，未执行fixture/test body |
| LIVE_OPT_IN | 仅收集 **7项**，未执行fixture/test body |
| guard正向哨兵 | **4 PASS**：合成estimator函数体、TF-IDF拟合、外部DNS、数据打开均在操作前拦截；无真实拟合/网络/数据读取 |
| 实际SAFE_CI回放guard违规数 | **0** |
| `git diff --check` | PASS |

应用唯一skip为未安装LangChain的纯wrap_tools契约。另一条LangChain tool.invoke不是“忽略skip”，
已按其TF-IDF调用链列入训练手动范围。warnings为原Gradio用户提示和pandas API/dtype提示。

本轮只执行收集/安全任务；没有远端CI、Ubuntu、Python3.10/3.11/3.12或完整可选依赖环境
的运行结果。矩阵保持并不代表本机替代这些环境验收。未执行49训练/7live或真实外部数据测试。
**SAFE_CI PASS 不等于历史全量训练测试均已通过。**

实际本地入口：先从 `.github/workflows/ci.yml`（YAML BaseLoader，避免on被当布尔）提取
`jobs.test.steps` 的 `safe_ci_runner`，保存为忽略的 `dist/ci-safe-audit/safe_ci_runner.py`。
加载同文件env，分别设置 `SAFE_CI_SCOPE=application/integrity/optional-compatibility`，
用现有解释器执行该脚本；`SAFE_CI_COLLECT_ONLY=1` 仅收集，0执行安全范围。
缓存/basetemp/profile/logs均指向忽略的dist目录。日志名：
`collection-app-001.log`、`collection-integrity-001.log`、`collection-optional-001.log`、
`safe-application-001.log`、`safe-integrity-001.log`、`safe-optional-001.log`、
`protein-special-001.log`、`guard-positive-controls.log`、`training-collection-final.log`、`live-collection.log`。
Protein专项使用同一runner防护前缀调用pytest，完整性命令由上方15项白名单确定；
默认应用的完整参数（含10个deselect）记录在 `safe-application-001.log` 第一行。

## 5. 科学与Git边界

不修改 core.py、scoring.py、ml_inference、ESM2 revision、AIntibody/GDPa3冻结结果、
protein_engineering初始速率算法、25f0861提交或历史tag；不训练模型、不读真实实验记录。
无关CLI、手工xlsx、旧pytest目录、所有dist/数据库/模型仍不暂存。
本地提交仅 `.github/workflows/ci.yml` 与本说明；消息 `ci: isolate safe non-training validation`。
没有推送、远端workflow dispatch、创建tag或发布Release。

官方语义参考：GitHub [workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)
与 [YAML anchors / aliases](https://docs.github.com/en/actions/concepts/workflows-and-actions/reusing-workflow-configurations)。

## 附录：精确间接训练node清单

```text
tests/test_agent.py::test_tool_rag_search_returns_context
tests/test_agent.py::test_agent_knowledge_question
tests/test_agent.py::test_agent_scan_question
tests/test_agent.py::test_agent_shares_memory
tests/test_agent.py::test_langchain_adapter_tool_invoke_when_present
tests/test_agent.py::test_orchestrator_run_aggregates
tests/test_agent.py::test_react_multistep_executes_tools_in_order
tests/test_agent_facts.py::test_run_collect_no_report
tests/test_agent_facts.py::test_orchestrator_facts_only_and_no_template
tests/test_agent_prompt.py::test_agent_with_mock_still_runs
```

## 附录：默认应用选择的实际模块

除上文整文件ignore、精确node排除与live marker外，下列60个模块的既有断言保留。

```text
tests/test_agent.py
tests/test_agent_answer_format.py
tests/test_agent_facts.py
tests/test_agent_grounding.py
tests/test_agent_prompt.py
tests/test_agent_tools.py
tests/test_app_agent.py
tests/test_app_smoke.py
tests/test_batch_analysis.py
tests/test_chain_inference.py
tests/test_config.py
tests/test_copilot_grounding.py
tests/test_copilot_metadata.py
tests/test_copilot_privacy.py
tests/test_desktop_acceptance.py
tests/test_desktop_batch.py
tests/test_desktop_chinese.py
tests/test_desktop_literature.py
tests/test_desktop_ml.py
tests/test_desktop_ml_deployment.py
tests/test_desktop_mutation.py
tests/test_desktop_mutation_ml.py
tests/test_desktop_network_audit.py
tests/test_desktop_phase1.py
tests/test_desktop_protein_engineering.py
tests/test_desktop_protein_initial_rate.py
tests/test_desktop_providers.py
tests/test_desktop_research_copilot.py
tests/test_desktop_research_summary.py
tests/test_desktop_startup.py
tests/test_download_csv.py
tests/test_glycosylation.py
tests/test_input_parser.py
tests/test_installed_package.py
tests/test_integration.py
tests/test_literature/test_cache.py
tests/test_literature/test_eval_benchmark.py
tests/test_literature/test_evidence.py
tests/test_literature/test_pipeline.py
tests/test_literature/test_query_generator.py
tests/test_literature/test_reranker.py
tests/test_literature/test_search.py
tests/test_literature/test_validator.py
tests/test_literature_relevance.py
tests/test_models.py
tests/test_mutation.py
tests/test_protein_engineering.py
tests/test_protein_initial_rate.py
tests/test_protein_rate_storage.py
tests/test_qt_lifecycle.py
tests/test_qt_startup_diagnostic.py
tests/test_release_readiness.py
tests/test_review_p1.py
tests/test_review_p2.py
tests/test_scoring.py
tests/test_v8_fixes.py
tests/test_v9_3_input_boundary.py
tests/test_v9_posthoc.py
tests/test_validation.py
tests/test_windows_delivery.py
```
