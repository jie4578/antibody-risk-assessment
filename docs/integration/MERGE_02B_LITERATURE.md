# MERGE-02B：已有文献证据只读阅读

日期：2026-11-25。实施基线：`a9ec5724a5e0ef78080c32cf2b683a416902acd3`。
独立分支：`codex/merge-02b-literature-20261125`。没有使用 MERGE-02A 实验工作区的实现。

## 已实现的操作

在原第八页「科研工作流」中打开「C. 论文与科研证据｜只读结果」，点击「导入文献批次与已有证据」，
明确选择本地 `batch_manifest.json`。授权范围是该文件所在的结果目录。

读取通过后，可以选择文献表的任意列，查看标题候选、来源标签、处理状态、已有证据数、声明的 DOI、
document_id 和来源 PDF SHA256；选择证据后，阅读既有原文、物理页码范围、质量标记和来源关联。
标题候选缺失时只显示文件名及缺失提示，不推断论文标题；证据缺失时不补写证据。
报告位置和结构化读取摘要位于「来源、报告位置与安全摘要」标签中，路径不自动打开。

新批次的读取、校验和文本序列化全部完成后才替换当前快照。失败、取消文件选择、后台异常均保留此前
已成功接入的文献、证据、来源摘要和当前路径。正在读取的目标与已接受路径分别保存。
只有明确清除或关闭页面会清空当前接入。请求 ID 与 QObject queued slot 隔离旧 Worker 的迟到回调；
取消只停止接受旧任务结果，不声称已经中断底层读取。

原八页导航顺序、原 BioLab 只读导入和蛋白质工程功能保留；没有启用 ELISA 或文献引擎自动执行。

## 已核对的真实上游合同

上游：[local-literature-evidence-assistant v0.4 发布标签](https://github.com/jie4578/local-literature-evidence-assistant/releases/tag/v0.4.0-evidence-retrieval-preview)，
标签解析到提交 `99ac4a54de687239b68b57ace19b24ecb32c6269`。

直接核对以下该提交的源文件，并在隔离验收目录保留只读合同副本：

| 源文件 | Git blob SHA | 使用的实际定义 |
| --- | --- | --- |
| `batch_manager.py` | `c04f7ea86526735825fffa2e13bc4bc1d23417a3` | `MANIFEST_SCHEMA_VERSION = 2`；inputs/documents 双层身份、逐篇 result_file、批次计数、status.json |
| `local_extractor.py` | `dd2e5dc041635b8629c1fd8100d9704b4f80051c` | 结果顶层 title_candidate/title_source/doi；pages 中 raw_text/text 和物理 page_number |
| `scientific_facts.py` | `8807e0cf070350ffb6f78f48b08fae57a85d9aa1` | facts 的 evidence_quote_raw、source_file、pdf_page_start/end、verified、quality_flags |
| `version.py` | `46c7fd68c4282ec272ac341e6b23d786a5abca73` | 仍声明 `0.3.0-bilingual-corpus-preview`，与 v0.4 标签不一致 |

此版本字符串差异如实保留：适配器依据已审阅提交及整数 schema v2 校验，不用旧 version.py 字符串
证明输入由 v0.4 运行产生。`contract_revision` 是合同参考版本，不是上传结果的可信生产者身份认证。

支持具有此批次合同的既有 Local Offline 结果；不支持脱离批次来源链的独立 JSON、EvidencePack/QA
导出、独立 Provider pipeline status.json，也不运行检索、PDF 解析、OCR、翻译、Embedding 或问答。

## 来源与定位的含义

复用 MERGE-01 的输入/document_id/PDF 声明哈希关联、引文 source_file 关联、可选 task_id/source_alias
身份一致性检查、状态计数核对、受限文件读取、严格 JSON、文件身份和读取末尾重哈希。
同名不同哈希的歧义文档不能仅凭文件名绑定引文。来源缺失或跨文献引用直接拒绝整批接入。

增强阅读入口检查已有 pages 的正整数物理页码、重复页码、可选页面来源文件名，以及引文页码范围。
页码超出已有非空页清单或范围不完整时拒绝。缺少页文本的记录只显示定位信息不足；不凭人工点击升级。
原 `inspect_literature()` 兼容入口保留；阅读入口为 `inspect_literature_evidence()`。

| location_status | 展示与限制 |
| --- | --- |
| RESULT_TEXT_MATCH | 上游声明 verified=true，且已有结果对应页的原始文本含完整引文；只匹配结果 JSON，不核对 PDF |
| LOCATION_NOT_REPRODUCED | 保留上游定位声明，但已有页文本未匹配；不能展示为已核验 |
| INSUFFICIENT_LOCATION | 缺少完整定位资料；未核验 |
| UPSTREAM_UNVERIFIED | 上游未验证，不能因本程序发现文字相同而升级 |
| UPSTREAM_CLAIM_ONLY | 兼容入口只保留上游声明 |

上游 verified 字段原样保存在 upstream_verified 中，并明确标为「上游声明」。全部状态都不代表
科学事实真实、语义蕴含、方法学验证或临床结论有效。质量标记与引文一并显示。物理页码不是印刷页码。

v2 manifest 的 content_sha256 是原始 PDF 的声明摘要，本程序不打开 PDF，故不独立核验它。
逐篇结果 JSON 没有上游提供的独立预期哈希；读取时保存的 observed_sha256 只标为 OBSERVED_HASH_ONLY。
它与 manifest 的声明身份核对、同次读取前后摘要核对是不同层次的检查，不得混称外部认证。
没有外部可信锚点时，不能用一致的哈希证明未被整体替换的来源真实性。

## 只读与安全边界

只按用户选定的批次目录读取允许的结构化结果和既有报告清单；PDF 角色在任何内容打开或哈希前拒绝。
不自动访问 source_alias 指向的原件，不解释文本中的指令，不执行路径/URL/命令，所有用户文本使用
QTableWidgetItem、QPlainTextEdit 或 PlainText QLabel 展示。导入不创建或写入 SQLite、原件或报告。

复用既有本地路径限制，拒绝越界、UNC、ADS、设备路径、已发现的 symlink/junction/reparse point。
现有 JSON/累计读取/条目/层级限制继续有效；新增阅读不解除这些限制。
本轮不把这些检查描述为操作系统沙箱，也未扩展为对具备同用户权限的任意恶意并发修改者的完整隔离。
不重新处理 PDF，不执行外部 Python，不安装依赖，不调用 Provider，不引入外部文献项目的运行时依赖。

已接受内容是内存中的只读快照，不自动监视之后的磁盘变更；需要用户重新导入以读取后续结果。
同一次读取中的文件替换或内容变化由既有身份和重哈希检查拒绝。

## 本次交付范围

- 修改 `desktop/integrations/common.py`：不可变文献元数据与定位状态字段。
- 修改 `desktop/integrations/adapters.py`：复用批次校验的新阅读入口、物理页码与已有页文本检查。
- 修改 `desktop/widgets/research_workflow.py`：原第八页的文献标签接入阅读面板。
- 新增 `desktop/widgets/literature_evidence.py`：文献/证据表、纯文本原文、原子导入和异步状态隔离。
- 新增 `tests/test_literature_evidence_reader.py`：纯合成合同、来源、页码、文件与路径反例。
- 新增 `tests/test_desktop_literature_evidence.py`：实际 Qt 页面、失败保留旧数据、选择与 Worker 生命周期。
- 新增本文档。

没有改动科学算法、SQLite v3、CI 策略、打包配置或 MERGE-02A。没有自动暂存、提交、推送或发布。

## 原实施验收记录（修复前历史记录）

验收环境：现有 Windows Python 3.13.9 / PySide6，Qt offscreen。全部输入为合成数据。
隔离证据目录：主工作区 `dist/integration/merge02b-20261125-001/`，不作为运行时依赖。

使用现有 `.github/workflows/ci.yml` 的 SAFE_CI runner 原文，阻断训练/TF-IDF 拟合、外网、真实数据
和模型目录访问。定向执行先于应用全量回归；没有采用旧 CI 成绩替代本轮结果。

首次定向测试 71 passed、1 skipped，另有超大测试参数自动生成的 pytest ID 超过 Windows 环境变量
32767 字符限制，产生 setup/teardown 两个错误。只增加短测试 ID 后，原断言不变，72 passed、1 skipped。
随后新增真实 Windows junction 回归。原日志保留，不隐藏此测试基础设施问题。

最终结果（不同范围存在包含关系，不相加）：

| 范围 | 本轮实际结果 |
| --- | --- |
| 新增两份测试文件 | 74 项：73 passed、1 skipped |
| 新增测试 + MERGE-01 合同/P1/P2 + 既有科研工作流页面 | 217 passed、4 skipped |
| SAFE_CI 应用全量 | 1403 passed、4 skipped、17 deselected、5 warnings；边界违规 0 |
| Frozen Integrity 只读白名单 | 15 passed；边界违规 0 |
| UTF-8、AST 语法、逐文件空白/结尾与 git diff --check | PASS |
| 原工作区及 MERGE-02A/历史审核证据保护摘要 | 23,932 个受保护文件，变化/缺失 0 |

应用回归命令由现有工作流执行：`python -m pytest -o addopts='' -m 'not live' tests
--ignore=tests/test_ml.py --ignore=tests/test_rag.py`，并沿用工作流 TRAINING_NODES 的 10 个逐节点 deselect；
其余 deselected 包含 live 标记。完整参数、日志与 XML 保存在隔离证据目录。
Frozen Integrity 逐项执行现有 SAFE_CI_SCOPE=integrity 白名单，没有运行历史标签评价。
已安装 wheel 测试沿用本地 `pip wheel --no-deps --no-build-isolation --no-index`，不安装或下载依赖。
原八页 Qt 回归在该应用范围内通过；C.1/C.2A/C.2B 数值内核没有修改。
5 个 warning 来自既有 Gradio 弃用/提示路径；没有为获得通过修改原测试断言。

上述通过不代表历史训练测试、真实 Provider、真实论文语料或跨平台验收通过。

Windows 无 symlink 创建权限的用例保留 SKIPPED；junction 实测不能替代 symlink，仍需 Linux 或
具备权限的受控 Windows 环境实际执行这些节点。本轮没有远端 CI、冻结 EXE 或安装包验收。
停止于代码与本地回归交付，等待独立审核。


## MERGE-02B-FIX：独立审核两项 P2 定向修复

日期：2026-11-25（Asia/Shanghai）。基线和分支保持不变。本节记录修复，前节为保留的原实施历史。
持久化证据目录：`dist/integration/merge02b-fix-20261125-001/`，不作为运行时依赖。

原独立审核的源码、日志、XML 和运行器共 18 份文件原样复制到 `original-review/`；
逐文件字节数及 SHA256 记录在 `original-evidence-sha256.json`。原临时审核目录没有修改。
修改生产代码前，原四个失败节点重新执行为 4 failed（`red-four.log/xml`）；
修改后，完全相同的测试源码和断言转为 4 passed（`green-four.log/xml`）。

### P2-01：严格阅读入口完整性

`inspect_literature_evidence()` 的 `for_reader` 策略在返回摘要之前拒绝：

- 缺少 `status.json`：`MISSING_STATUS`，错误消息列出文件名。
- 已声明的 `individual_report` 文件缺失：`MISSING_REPORT`，错误消息列出声明路径。
- 已完成文献的结构化结果缺失：继续使用 `MISSING_RESULT`，增加相关结果路径。

上游 schema v2 的 `_write_state()` 写出批次状态文件；`update_batch_manifest(report_paths=...)`
只在报告实际声明时增加 `individual_report`。因此不要求未声明或为 null 的可选报告，
不额外要求 XLSX、总报告、PDF 原件、独立 Provider 或 EvidencePack 文件。
未完成或失败文献继续不把结果当作可用证据，本修复没有强迫其必须拥有已完成结果文件。

不对所有 `INCOMPLETE_ARTIFACTS` 状态做全局拦截。MERGE-01 的 `inspect_literature()`
在缺少状态或报告时仍按既有合同降级返回，并保留原警示与状态。正式测试覆盖此兼容性。

现有 `LiteratureEvidencePanel._received()` 在 loader 报错时保留已接受快照，故本轮不改界面生产代码。
新增 Qt 测试验证列表、当前选中文献与证据单元格、来源摘要、原文和已接受路径全部保留；
首次不完整导入保持未导入状态。Worker 取消、请求 ID、迟到回调及连续导入逻辑没有修改。
报告仅沿用既有受限文件读取与摘要检查，不执行其内容，也不读取原始 PDF。

### P2-02：结果身份与证据数量解耦

`_literature_identity()` 复用已有身份一致性规则。`_literature()` 读取已完成结果后，
在构建文献元数据和遍历 facts/evidence 之前独立检查结果身份；`_citation_source()`
继续检查每条引文的来源及可选身份。必需的 document_id/content_sha256 核对保持，
已声明的 task_id/source_alias 必须一致，原来允许缺省的字段仍允许缺省。

正式测试覆盖空 facts、空 facts/evidence、两字段缺失时的矛盾身份拒绝，以及合法零证据文献和
可选 task_id/source_alias 单独或同时缺省时正常接入。非空引文、跨文献来源和物理页码检查保留。
身份自洽只表示本次结构化数据的内部一致性，不代表来源生产者认证或科学事实真实。

### 修复范围与验证

本轮相对独立审核时仅修改 `desktop/integrations/adapters.py`、两份已有文献测试及本文档。
两份测试仅追加 24 个参数化场景，原文件字节前缀及断言完整保留；文件句柄机制没有重构。
完整结果、复现命令、保护摘要与最终状态见独立验收目录 `ACCEPTANCE.md`。

### 本轮最终回归结果

| 范围 | 实际结果 |
| --- | --- |
| red-four | 0 passed、4 failed、0 skipped |
| green-four | 4 passed、0 failed、0 skipped |
| independent-full | 47 passed、0 failed、0 skipped |
| integration | 245 passed、0 failed、0 skipped |
| symlink | 4 passed、0 failed、0 skipped |
| safe-ci | 1431 passed、0 failed、0 skipped |
| frozen-integrity | 15 passed、0 failed、0 skipped |

上述范围有包含关系，不相加。SAFE_CI 沿用现有工作流 runner 和选择边界，未运行训练或 live 节点；
独立测试与 CI 边界违规为 0。Windows 四项 symlink 本轮实际执行通过，未修改系统权限。
未执行 Linux、真实论文 PDF 原文件核验、科学事实真实性验证、远端 CI 或冻结 EXE 验收。
未提交、推送、发布或创建 Checkpoint；停止等待最终复核。
