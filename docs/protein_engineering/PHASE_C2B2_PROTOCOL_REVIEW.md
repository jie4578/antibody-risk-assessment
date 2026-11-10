# C.2B-2 协议审查与 SQLite v3 数据充分性报告

日期：2026-11-10；文档版本：`c2b2-protocol-review-draft-1`。
审查基线：`5b53d9d086f692954b64c8eb003a1e772fe904e6`。
本地跟踪 origin/main：`6a1d1cb230734dc1b88c160631fe7392505e33c8`。
C.2A/C.2B-1 为有意保留的本地 checkpoint，领先远端不是异常。
本次审查只读代码、迁移 SQL 文本、空白模板、合成测试与协议，不打开真实用户数据库。

## 1. 结论与结论适用范围

- **PROTOCOL_REVIEW: PASS_WITH_LIMITATIONS**
- **DATA_READINESS: PARTIAL**
- **IMPLEMENTATION_READINESS: READY_FOR_SCOPED_IMPLEMENTATION**

此结论表示测量链、缺口和后续合成实现边界已明确；可提交下一阶段的合成内核设计供人工审核。
不表示真实酶实验输入已齐备，不表示已完成任何实验误差传播计算。
当前不具备批准“真实实验不确定性已完整量化”的条件。
后续实现仍需单独授权，本轮到协议评审为止。

详细测量模型、误差预算 A-G、候选方法、状态与合成验收计划见
[实验误差预算协议](PHASE_C2B2_UNCERTAINTY_BUDGET.md)。

## 2. 实际审阅范围与冻结行为

| 文件/证据 | 实际行为和审查结论 |
|---|---|
| `protein_engineering/initial_rate.py` | `initial-rate-1.0.0`；明确时间窗口，带截距 OLS；none/per_observation/matched_time 空白模式；固定线性标定换算；没有空白/标定完整误差传播 |
| `protein_engineering/rate_storage.py` | 保存原始来源、C.1 结果/配置及输入链接；保存时验证原件并回放；不允许覆盖；标定 JSON 是明确字段的 Calibration，不是任意不确定性容器 |
| `protein_engineering/mm_kinetics.py` | `mm-unweighted-1.0.0`；正值约束、确定性初始化、无权重拟合；同一变体/样品/生物重复/批次；不自动删点或合并重复 |
| `protein_engineering/mm_rate_adapter.py` | 已有 v3 数据库的显式 ID 只读适配；校验版本、原件和输入关系；本轮不调用适配器读取用户库 |
| `protein_engineering/mm_uncertainty.py` | `mm-profile-normal-1.0.1`；给定速率下 iid 加性正态、未知方差条件区间；不包含完整测量误差模型；P1 递归有限性/单位溢出保护原样保留 |
| `protein_engineering/schema.py`、`migrations.py`、`__init__.py` | 当前 schema=3；原件/import/记录 JSON 与不可变触发器；v3 仅增加 C.1 分析和输入链接，无完整不确定性表 |
| Phase 0 CSV 模板 | 审阅 kinetic_timecourse、samples、experiment_batches、assay_results、source_manifest 的实际表头；模板具备若干身份与条件字段，但不具备受校验的误差联合模型 |
| C.1/C.2A/C.2B-1 协议、实现文档及测试 | 阅读合成数值、来源保护、重复结构、单位/失败状态及极端尺度测试的设计；本轮未执行数值测试或覆盖率模拟 |

C.2A 要求完整可比的协议、温度、pH、buffer、底物及 lot、辅因子、酶浓度、反应体积和读出条件。
技术重复逐条保留，不自动平均；原始观测重复使用被拒绝。
这些资格不能被未来抽样、用户确认或补写误差元数据绕过。
C.1 的 NOT_ESTABLISHED 不会因本审核变为通过。

## 3. SQLite v3 数据充分性矩阵

矩阵审查的是代码/字段表达能力及校验程度，**不是某个真实数据库的记录完整率**。
AVAILABLE 表示已有明确存储或输出机制，不保证实际实验已填写或科学上合格。
PARTIAL 表示只能表达部分信息或缺少结构化校验；MISSING 指缺少明确可用的结构/分析能力。
NOT_APPLICABLE 必须有目标和条件依据，不能替代“未采集”。

| 要求 | 状态 | 实际位置/能力 | 缺口与后续要求 |
|---|---|---|---|
| 原始时间序列 | AVAILABLE | kinetic_timecourse 的 observation_id、time_value/time_unit、raw_signal/signal_unit、well_id；原始 JSON/来源字节 | raw_signal 在导入层可缺失；实际数据完整性及时间校准须逐库另审 |
| 原始空白测量 | PARTIAL | blank_signal 可逐行给出；独立空白曲线可作为观测并由 C.1 matched_time 关联，initial_rate_inputs 保存 BLANK 角色 | 无专用空白重复/共享过程/相关结构；不得把每行 blank_signal 当独立测量 |
| 标定原始标准 | MISSING | source_files 可保存原始字节，但没有已实现的标准点解析/拟合/标准浓度误差模型 | 附件容量不等于可计算能力；需要标准点、单位、重复、空白及来源的结构化关联 |
| 标定点参数、公式、有效域和来源 | AVAILABLE | Calibration 的 signal_per_product、intercept、signal_unit、product_unit、valid_signal_min/max、blank_mode、calibration_id、实际文件 SHA256 | 只接收点参数，不推断其可信度；标定原始数据+参数整体能力因此为 PARTIAL |
| 标定参数协方差/联合分布 | MISSING | 无 typed covariance 字段；额外 calibration JSON 字段不会自动成为支持能力 | 需参数顺序、单位、协方差、自由度/方法、支持域、标准来源；不能独立抽 k/b |
| 名义底物浓度和单位 | AVAILABLE | kinetic_timecourse 的 substrate_concentration / substrate_concentration_unit | 不代表浓度真实无误差；单位兼容性仍须满足 C.2A |
| 配液、stock 和稀释误差 | MISSING | batch 有 substrate_lot，样品有 concentration 等，但没有配液谱系和受校验误差模型 | 需 stock、纯度、体积/质量、仪器、稀释父子关系与共享协方差；“浓度及配液记录”整体 PARTIAL |
| 技术重复身份 | PARTIAL | kinetic_timecourse/assay_results 的 technical_replicate、well_id，C.1 按上下文分组 | 可选字符串，缺少统一反应单位与共享制备层级；不证明误差独立 |
| 生物学重复身份 | PARTIAL | samples 和 timecourse 的 biological_replicate、sample_lot_id、variant_id | 无受校验的独立表达/制备单位与嵌套/交叉模型；C.2A 仅同一生物单位内拟合 |
| 批次与实验条件 | AVAILABLE | experiment_batches 的协议、时间、仪器、温度、pH、buffer、底物、辅因子、体积、readout 等；batch/sample 关联 | 字段存在不证明实际完整或跨批次可比；批次效应模型/桥接设计仍缺失 |
| 原始来源 SHA256 | AVAILABLE | source_files 原始 BLOB 的实际哈希、imports、original_json/source_row、C.1 输入链接与回放 | provider 报告的 source_file_id/SHA 不替代实际导入哈希；哈希不证明实验真实性 |
| C.1 分析版本与配置 | AVAILABLE | initial_rate_analyses.result_json、analysis_version/fingerprint，initial_rate_inputs | 已可追溯；新增传播不能覆盖旧分析 |
| C.2A 分析版本与完整输入 | PARTIAL | 内存输出及输入摘要、`mm-unweighted-1.0.0`、只读 RateRecord 适配 | SQLite 无 C.2A 派生分析表；仅代码版本不等于实际结果已持久化 |
| C.2B-1 分析版本与区间来源 | PARTIAL | 内存输出、`mm-profile-normal-1.0.1`、review/config/输入摘要、严格 JSON | SQLite 无相应分析及来源链接表；不可声称 v3 已存完整区间链 |
| 完整不确定性账本/联合协方差 | MISSING | 无受校验分布、共享组、单位顺序和依赖图 | notes/fields_json 可保留额外文本，但不是已实现的误差传播数据模型 |
| kcat 的活性酶定量传播 | NOT_APPLICABLE | 本轮目标只有 Km/Vmax；不计算 kcat | 若未来改变目标必须另审，不能扩张本结论 |

额外 JSON 字段、原件 BLOB 或 notes 可能包含人工说明；未解析、未校验的内容不能自动用于传播。
本审查没有打开真实用户 SQLite、手工工作簿、私人序列或实验资料，也没有统计实际缺失率。

## 4. 相关结构与现有推断的兼容性

已知共享空白、calibration_id、stock/lot、样品、孔位和批次之间应形成显式依赖图。
同名标签只能提供候选关联，不自动确定相关系数或独立性。
每个共享潜变量按共享层级共同抽取，保留跨曲线和 Km/Vmax 联合信息。
若只有边际标准差但依赖未知，不能用对角协方差代替；应标记 UNSUPPORTED_DEPENDENCE。

按固定窗口 OLS 推导，共享常量空白偏移抵消，共享空白漂移不抵消。
标定 b 对固定窗口速率的直接导数为零，但影响转换浓度和资格检查；
因此不能删除 b，也不能声称 k/b 协方差必然直接增加速率不确定性。
共同正标定倍率主要缩放 Vmax，共同底物倍率主要缩放 Km；适用条件见预算协议。

C.2B-1 的条件 iid 正态模型不是共享测量误差模型。
不得将共同误差传播后的相关速率再次假装独立来获得“完整 CI”。
剖面区间保留为条件性结果，与测量传播分布并列说明适用条件，不数学相加。

## 5. 不重复计入不确定性的审核规则

未来每次分析必须给出逐来源账本及一张“已进入哪层”的映射：
原始信号噪声若已联合抽取，则不再抽 C.1 slope SE；
标定原始标准重抽与参数协方差抽样择一；
输入测量噪声已传播时不追加相同来源的 MM 残差或 C.2B-1 区间。
无法区分残差来源就承认未完成分解，不使用减方差、截零或平方和开方制造完整预算。

Monte Carlo 输出的 2.5%/97.5% 分位区间应称为“所声明输入分布下的传播区间”，
不是自动具有频率学 95% 覆盖率的参数置信区间。
多输出的边际区间也不是 95% 联合区域；保留联合样本和协方差。
参考 [JCGM 101:2008](https://www.bipm.org/en/doi/10.59161/jcgm101-2008)
的分布传播框架及 [JCGM 102:2011](https://www.bipm.org/documents/20126/2071204/JCGM_102_2011_E.pdf)
的多输出处理；参数推断与覆盖率需另行定义。

## 6. 候选路线评审与可批准范围

一阶解析法适合局部灵敏度和共享误差核对；强非线性、边界与资格分支需另检。
MC 能保持共同来源和非线性，但前提是联合输入模型有证据且输出数值稳定。
Parametric Bootstrap 需要重复实验生成模型及明确区间构造；
分层 Bootstrap 需要足够独立层级单位，不能用单一生物重复制造总体变异；
分层模型还需可辨识的实验设计，不能由现有表头直接推断。
完整方法对比、输入/成本/追溯要求见预算协议第 5 节。

**下一阶段可供批准的最小范围**：纯内存、完全明示的合成联合测量模型，
单变体/样品/生物单位/批次，固定时间窗口和成员；复用冻结 C.1/C.2A 确定性计算。
MC 为这一合成范围的候选首条路线，不是已选定的真实数据默认方案。
提供合法的读数、共享空白/标定和底物制备分布时可验证解析不变量与联合协方差。
多生物/跨批次案例先测试明确拒绝或逐单位结果，不越权实现总体推断。
未通过数据/依赖/数值门槛时使用预算协议规定的六种状态，不填零、不删坏抽样。

本范围不包含：真实用户数据启用、完整误差模型、持久化/迁移、Desktop、
WT 比较、kcat、模型训练或任何冻结抗体研究结果重算。

## 7. 未来数据模型扩展提案（不实施）

建议先以独立、版本化 JSON sidecar 表达合成模型；不能向现有严格 Calibration JSON
硬塞未知字段，也不能把采样值冒充原始标定资料。
若未来需要持久化，再单独审核下列概念实体和 SQLite v4 迁移：

| 概念实体 | 拟保存的信息 |
|---|---|
| uncertainty_sources | 量/单位、分布及参数/支持域、Type A/B 依据、自由度（如适用）、来源、校正/不确定性区别、共享组 |
| covariance_blocks | 有序量 ID 和单位、矩阵、估计方法/来源、秩与 PSD 审核、适用条件 |
| calibration_standards | 原始标准浓度及误差、信号/空白/重复、公式与拟合方法、参数协方差、原件哈希 |
| substrate_preparations | stock/lot/纯度、质量/体积、串行稀释谱系、校准资料、共享误差映射 |
| replicate_relationships | 反应曲线、tech/bio、样品制备及批次的嵌套/交叉关系与独立性依据 |
| uncertainty_analyses/source_links | 原 C.1/C.2A/C.2B-1 ID/摘要、误差账本、版本/配置/审阅、共同 draw_id、联合输出/失败日志 |

未来迁移须验证 v1/v2/v3 升级、历史校验和/触发器、只读兼容及 append-only 来源保护。
旧数据缺失元信息保留缺失，不自动补造不确定度或共享关系。
C.1 保存接口会校验原标定字节和回放一致性；模拟场景必须另存，不能规避此保护。
本轮没有新 SQL、schema 变更或真实数据库操作。

## 8. 合成验收计划与失败标准

预算协议第 7 节列出逐项虚构输入、解析预期和失败条件，覆盖读数噪声、常量空白、
空白漂移、共享 k、k/b 相关、stock 浓度、技术重复、生物重复、批次、
元数据缺失、强相关、资格分支、极端尺度及联合输出重复性。
核对采用独立解析梯度、共享倍率不变量或独立一维积分，不能只用待测试函数自证。

未来必须先确定随机种子/抽样数、MCSE/分位数精度、数值容差及失败政策；
不能结果不理想再删点、挑种子或放宽容差。
严格 JSON/递归有限性和 1e297 极端尺度保护必须继承。
任何不合格抽样/拟合失败保留日志，不能只报告幸存样本的无条件区间。

C.2B-1 原协议记载的 200 次 N=7 模拟只是历史诊断，不是本轮新测试，
也不能证明真实酶实验区间覆盖率；本轮未重做或调整其阈值。
合成测量传播的数值精度与频率覆盖率验证是两个不同任务。

## 9. 风险分级及未解决问题

| 级别 | 问题 | 判定与下一步 |
|---|---|---|
| P0 科学使用阻断 | 真实误差输入/依赖证据不足却称完整实验不确定性 | 禁止此结论；逐来源补证据并另审真实数据 |
| P1 | 标定标准/参数协方差、stock 制备、空白共享模型不足 | 阻断相应真实传播模型；不阻断完全明示的合成方法开发 |
| P1 | 技术/生物/批次关系未充分结构化，可能相关或混杂 | 提供实验设计和独立单位证据；不默认合并或独立 |
| P1 | 重复计入读数/残差/标定误差 | 上线前必须通过来源账本与解析反例测试 |
| P1 | 弱可辨识、资格失败、单位还原溢出 | 保留既有失败状态及严格有限性；不通过删抽样掩盖 |
| P2 | C.2A/C.2B-1 无 SQLite 派生持久化链 | 暂限内存及来源明确的导出设计；以后单独审迁移 |
| P2 | MC 精度、联合区间与实际覆盖率容易混称 | 命名及单位/共同 draw_id 必须明确；覆盖率另设协议 |

风险是对未来真实使用的门槛，不表示本轮已发现并修复新计算缺陷。
初始速率有效性、复杂动力学、外部参数验证、模型失配及生物差异仍未解决。

## 10. 本轮工程核对与停止点

本次仅新增预算协议和本报告；以静态检查确认必需章节、状态、链接和来源字段，
并核对已有受跟踪文件的字节摘要及 Git 边界。

| 本轮实际检查 | 结果 |
|---|---|
| `git rev-parse HEAD` | `5b53d9d086f692954b64c8eb003a1e772fe904e6`，与预期一致 |
| `git rev-parse origin/main` | `6a1d1cb230734dc1b88c160631fe7392505e33c8`，仅读取本地跟踪引用 |
| `git diff --cached --name-only` | 空；无暂存 |
| 全部 402 个已有受跟踪文件前后 SHA256 比较 | 0 个变化，包含 CLI、计算内核、迁移及冻结代码 |
| 协议必需状态/章节、UTF-8、行尾空白、文档相互链接 | PASS；两个新文件均检查 |
| Python AST 读取已有 dataclass 字段 | PASS；未导入执行计算模块或创建数据库 |
| `git diff --check` | PASS，exit 0；已有 CLI 的 autocrlf 提示不属于空白错误 |
| 受保护临时目录元数据清单 | 565 个文件，路径/大小/修改时间与既有保护清单一致 |
| 手工工作簿保护 | 仅比较 SHA256，仍为 `c9661d18710733361ee15d804b79cea407e40a4308cc13caa9bde297cb6fb5a2`；未解析实验内容 |

未运行数值回归、MC、历史评价或真实网络 Provider；不以历史测试数量冒充本次执行。
外部资料仅查阅公开计量指导，没有发送序列或实验数据。
本轮未暂存、未提交、未推送，也未创建 tag/Release。

审核结论带有数据限制：结构基础 PARTIAL，完整真实实验量化尚不具备条件；
仅可在人工审核和另行授权后，进入上述合成范围的 C.2B-2 计算实现。
