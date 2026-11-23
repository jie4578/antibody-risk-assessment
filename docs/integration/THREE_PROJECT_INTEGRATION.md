# MERGE-01 — BioResearch Workbench 只读结果接入

实施日期：2026-11-23。主项目仍为 `jie4578/antibody-risk-assessment`，没有创建第二个应用或仓库。

## 三个项目与边界

| 项目 | 本轮代码依据 | 版本/合同 | 当前角色 |
|---|---|---|---|
| antibody-risk-assessment | `0a15ef0a639164822a40939c5a42270558b26a23` | `4.1.0rc2`；SQLite v3 | 现有 PySide6 主程序，增加第八页 |
| BioLab-Copilot | `dcc7ac4a9accae4a03ad7857950169e0f2ed640c` | 包版本 `0.1.0`；合同 `1.0` | 独立实验分析引擎，只读接收已有结果 |
| local-literature-evidence-assistant | `99ac4a54de687239b68b57ace19b24ecb32c6269` | `0.3.0-bilingual-corpus-preview`；Local Offline 批次 schema **整数 2** | 独立论文/证据引擎，只读接收已有批次 |

BioLab 本机工作树另有未提交修改，因此按上述 **Git commit 内容**审阅 contracts、reporting、CLI 和依赖，不将其本地新文件混作参考基线。文献代码通过 GitHub connector 按完整 SHA 读取。只保存必要源码证据到本轮隔离审计目录，没有执行外部项目。

`contract_revision` 是本适配器审阅的合同代码版本，不是已认证的运行来源提交。BioLab manifest 中 `software_versions` 作为上游声明显示；文献 v2 manifest 未记录引擎软件版本时，不凭空补造运行版本。

BioLab 的 `Python >=3.11,<3.14`、`NumPy >=2.0,<2.5` 与主项目 Windows 构建 `CPython 3.14.8 / NumPy 2.5.4` 保持分离。本轮新增适配器只依赖 Python 标准库，页面复用 PySide6；没有导入 BioLab 的统计模块、PDF 提取器、LLM 模块或它们的依赖。

## 实际连接的数据合同

### BioLab 运行及报告包

依据：`src/biolab_copilot/contracts/models.py` 中 `RunManifest`、`ReportManifest`、`ArtifactFile`、`InputFile`，`contracts/enums.py`，`cli.py::_output_file` 和 `reporting/renderer.py::_write_manifest`。

* `run_manifest.json`：`schema_version="1.0"`、`run_id`、`experiment_id`、`status`、`created_at`、`input_files`、`configuration`、`software_versions`、`warnings`、`output_files`；显示 assay/method、来源哈希和未验证标记。接受已审阅 RunStatus，失败/进行中不会显示为完成。
* `report_manifest.json`：额外核对 `report_id`、`report_version="1.0"`、`report_type`、`source_manifests`、`source_artifacts`。报告类型限 `generic_grouped / welch_two_group / elisa_4pl`。
* 输出产物使用 `path / sha256 / size_bytes / artifact_type`。SHA256 是整个实际文件字节的 SHA256，不是 JSON 重新序列化摘要。存在、大小、声明与实际哈希分别检查。
* 上游 CLI 记录 **绝对输出路径**，报告 renderer 记录 **包内相对路径**。相对路径限定于所选 manifest 父目录；绝对路径也必须原样落在该目录中。迁移后的旧绝对路径不猜测 basename、不扫描原目录、不自动重映射，明确拒绝。可以选择上游独立生成的相对路径报告包。
* `analysis_issues / validation_issues` 读取已列出且哈希匹配的 JSON issue 列表。`report_data` 读取已列出且哈希匹配的报告 JSON，核对 report id/type/version，展示其 QC、methods 中未验证标志及原有限制；不将报告中原始观测表导入摘要，不重算统计。
* QC severity 严格使用上游 `info / warning / error / blocking` 枚举；未知值拒绝，不能静默作为正常状态。合法 `error / blocking` 使完成结果标为 `NEEDS_REVIEW`。
* `input_files` 的原始路径只是惰性元数据，不 resolve、不打开。`imported_data / input_artifact / sample_artifact / source_file` 仅作元数据清单，不读取内容或声称哈希已复核。**PDF 即便位于授权目录内，也在打开、哈希或解析前拒绝**；其他产物须先满足已审核角色/格式匹配，不能借 issues/report 角色读取原始文件。CSV 不作为结构化结果读取。
* `curve_validated=false`、`quantification_enabled=false`、`validated_quantification_enabled=false` 和科研用途限制保留；违反该合同的 true/clinical 声明拒绝。流程完成不证明实验或模型有效。

这是 **接入所需字段与版本的验证子集**，不是在主环境重新执行上游完整 Pydantic 科学验证。已知字段严格校验；额外字段不被自动展示或执行。

### 文献 Local Offline 批次 v2

依据：`batch_manager.py` 的 `_write_state / _refresh_counts / _attach_identity / update_batch_manifest`，`local_extractor.py`、`scientific_facts.py`、`paper_pipeline.py::verify_evidence/locate_evidence` 和 `exporters.py::export_individual_reports`。

* `batch_manifest.json`：整数 `schema_version=2`，`task_id / status / report_mode / created_at / updated_at / inputs / documents` 及六个 count 字段。不能把字符串 `"2"` 或布尔值当作版本 2。
* `inputs` 保留上传输入、别名、重复关系；`documents` 按完整 PDF 内容 SHA256 去重。核对双方 ID、content SHA256、input_ids、重复关系及逐条状态。按唯一文档统计完成/失败，不能将上传次数当成论文数。
* `status.json` 只从同一授权目录读取，核对版本、task id、状态、模式、updated_at 和全部计数。缺失时降级为不完整；矛盾时拒绝。独立 Provider pipeline 的无版本 `status.json` 不是此合同，不能导入。
* `documents[].result_file` 是已保存的论文结果 JSON；`individual_report` 是可选相对报告路径。只从授权目录读取有限结果；展示 `facts/evidence` 的引文、文档 ID、声明 PDF 哈希、物理页码、quality_flags、上游 verified。失败或未完成文档不产生可用证据。
* 逐引文必须保留 `source_file`，并与结果文件名、文档身份和关联输入的 `source_alias` 一致；显式提供的文档 ID、内容摘要及批次身份不得矛盾。缺失、跨文档或不一致时拒绝，不默认补成父文档。上游事实仅含文件名，无法区分批次内同名异身份文档时保守拒绝。摘要保留 `source_file / source_alias / batch_id`，这些声明链一致性不构成外部真实性认证。
* `content_sha256` 指向 **PDF 原始字节**，不是 result JSON 哈希。本轮不读取 PDF，因此标为 `PDF_DECLARED_NOT_VERIFIED`。result JSON/Word 没有上游字节摘要时仅记录 `OBSERVED_HASH_ONLY`；不能称作独立验证通过。
* `verified=true` 仅表示上游原文匹配/定位声明；本轮没有重新定位 PDF，既不验证全文真实性，也不证明科学结论。LLM 内容仍是上游研究材料。

## 已实现的可操作入口

原六个抗体页及第七个蛋白质工程页的顺序不变；追加 **科研工作流**。

1. A 区可回到现有单条、批量、突变、文献及蛋白质工程页面。
2. B 区选择 BioLab manifest，后台只读核验，显示原状态、接入状态、实验类型、QC、产物清单、来源摘要、软件声明及限制。
3. C 区选择文献 batch manifest，显示输入/唯一文档/完成/失败/重复计数、来源、证据及报告位置。
4. 导入异常清空旧结果；取消文件对话框保留当前快照；显式清除使旧任务失效。每次请求使用唯一 token，QObject bound slot 在 GUI 线程接收，旧任务不得覆盖新选择；关闭后不消费迟到结果。

结果使用只读 `QPlainTextEdit` 展示，引用中的 HTML/脚本只作为文本。报告位置不自动打开；本轮不自动调用系统程序、复制 PDF 或原始数据、写数据库、上传或调用 Provider。

## 安全和资源范围

* 授权范围为用户所选 manifest 的父目录；不启动目录扫描。manifest、本次需要的状态和结果只在显式选择后读取。
* 仅普通本地文件；拒绝 UNC、路径跳转、设备名、ADS、符号链接、junction/reparse point。Windows 锁住各父目录防替换，叶文件禁止 write/delete sharing；POSIX 用 dirfd + O_NOFOLLOW 逐级打开。不会自动清理或改写源目录。
* 单个 JSON ≤4 MiB，单个核验产物 ≤32 MiB；累计读取（包含最终重读）≤128 MiB；列表 ≤500 项、JSON 深度 ≤40、节点 ≤100000、展示证据 ≤2000。超过限制明确拒绝，不静默删点、截断来源或成功结论。
* 严格 UTF-8 JSON，拒绝损坏 JSON、重复 key、NaN、Infinity、1e999。受控返回 `IntegrationError`，UI 显示安全错误码。
* 每个已读取文件记录身份及 SHA256，完成前重新读取并比对；发现变化 fail closed。文件存在与哈希仍是一次快照，不代表此后永不变化，更不构成外部认证。
* Windows/Python 3.13 路径 stat 与句柄 fstat 的 ctime 可能语义不同。使用一致的 birthtime、dev/inode/size/mtime、共享锁及完整哈希比对，避免误拒绝。未削弱内容不一致检查。

主要接入状态：`COMPLETED_SOURCE_REPORTED`、`FAILED`、`PARTIAL`、`INCOMPLETE`、`INCOMPLETE_ARTIFACTS`、`NEEDS_REVIEW`。前者也只表上游流程状态，没有任何“科学验证通过”状态。

## 文件范围与科学保护

新增：`desktop/integrations/{__init__,common,adapters}.py`、`desktop/widgets/research_workflow.py`、纯合成 fixtures 和两套正式测试。

P1/P2 定向修复另新增 `tests/test_integration_merge01_fixes.py`，共 75 项正式反例及合法输入正例；正式测试不依赖 dist 中的临时审核脚本。

修改：`desktop/main_window.py` 追加入口；三个既有导航测试将总数由 7 更新为 8 并保留原页面断言；installed-wheel 测试增加新包路径与不导入外部引擎断言。

未修改：C.1/C.2A/C.2B 内核、`core.py/scoring.py`、冻结模型/研究结果、SQLite v3、CI 训练隔离、依赖、打包配置或发布状态。本轮开始前的 SciPy 打包、CLI、手工工作簿及原审核文档通过独立保护快照保持原样；新增实施内容不提交、不推送。

## 验收记录

本轮独立证据目录：`dist/integration/merge01-20261123-001/`。`contracts/` 仅为固定提交的源码证据，不是运行依赖。

正式命令均在本地使用现有 `E:/ANACONDA/python.exe` **只运行测试，不安装或升级包**，`PYTHONDONTWRITEBYTECODE=1`；SAFE_CI 使用当前 `.github/workflows/ci.yml` 原 runner/guard，不运行历史训练、live Provider 或私有实验数据测试。

* 新合同/页面测试、相关 Desktop 回归、SAFE_CI 应用与 Frozen Integrity 的最终实际数量见同目录 `ACCEPTANCE.md / acceptance.json / *.xml`，按最后一次完整运行记载，专项与完整应用有重叠，不累加为独立测试总数。
* Windows junction 越界反例实际执行。三个 symlink 创建测试因本机权限跳过；Linux O_NOFOLLOW 路径需后续远端 Linux CI 实际运行，本轮未推送，不能声称已经通过。
* 本轮为源码 Desktop/offscreen 自动化验收，不是新冻结 EXE 或干净 Windows 安装验收；未重建安装器。
* SAFE_CI PASS 不等于历史全量训练测试均已通过。

### 独立审核与定向修复后的 Checkpoint 依据

原独立审核 `dist/integration/merge01-independent-20261123-001/` 保留 **52 passed、8 failed、3 skipped** 的 RED 证据及原断言。修复后以原脚本重放为 **60 passed、3 skipped**，原 8 个失败断言全部转绿。对应根因为 PDF 读取前资格缺失、逐引文来源误绑定、QC severity 枚举未校验。

修复验收 `dist/integration/merge01-fix-20261123-001/` 记录：集成合同与新增测试 **135 passed、3 skipped**（含新增 75 项）；Desktop **299 passed**；SAFE_CI **1330 passed、3 skipped、17 deselected**；Frozen Integrity **15 passed**。各范围边界违规均为 0，范围存在重叠，不累加为独立总数。这些是已归档的实际本地执行结果，不是远端 CI 或冻结 EXE 成绩。

Windows 三项 symlink 因 WinError 1314 仍为 **SKIPPED**；junction 的 GREEN 不等于完整 symlink 验收。**下一阶段必须在 Linux 或具备创建权限的受控 Windows 环境补充实际验证**，并保留原断言。本地 Checkpoint 不解除这一限制，也不代表安装包可发布。

## MERGE-02 后续接口设计（尚未实施）

先独立审核每个引擎的解释器及受限执行器，不把三套 Python 依赖装入主环境。建议以版本化 JobRequest/JobResult 连接：engine_id、批准的解释器/入口、唯一 job_id、显式输入授权、私有输出根目录、引擎/合同版本、超时/取消策略、状态和结果 manifest 哈希。以上是**拟议接口**，不是当前已有 JSON 合同。

需先解决：解释器存在性与版本检测、参数白名单（不使用 shell 字符串）、stdout/stderr 脱敏、唯一输出目录、取消与真实终态、源目录和结果目录权限、引擎版本锁定、研究数据 consent、Provider 调用独立授权、跨进程故障/断电恢复及可审计调用链。

首个 MERGE-02 范围建议限纯合成、离线、独立子进程的受控调用验收。真实数据接入、结果回写、科学结果合并、LLM 联动及依赖合包仍需另行审核。当前只读接入不提供这些授权或科学有效性证明。
