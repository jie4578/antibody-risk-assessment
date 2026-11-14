# Phase C.2A-D1 Desktop 显式拟合与本地报告交付

## 2026-11-14：独立审核 P1/P2 修复与重新验收（现行）

SCIENCE_REVIEW：**PASS_WITH_LIMITATIONS**。
CHECKPOINT_READY：**YES（本机源码范围，可进入选择性检查点审查；没有自动提交）**。
下方 2026-11-13 记录保留为历史。原 FAIL 证据位于
`dist/protein-engineering/c2a-desktop-d1-independent-20261114/`，没有修改或覆盖。
本轮新 RED/GREEN、命令、逐项结果及保护核对位于
`dist/protein-engineering/c2a-desktop-d1-fixes-20261114/`。

### P1-A：逐操作、逐会话生命周期

新增 `desktop/protein_operations.py`，只供蛋白质工程页使用；通用 `desktop/workers.py` 未改。
每个任务拥有唯一 operation_id、session_id、generation、任务类型、深复制输入快照和自己的回调。
完成信号显式 QueuedConnection 连接页面 QObject 的 @Slot；启动和接收均检查 GUI 线程。
不通过 Python 闭包直接接收跨线程完成信号，不再使用共享可变 `_on_done`。

数据库切换/接受重开会生成新会话，立即使旧审核/结果失效；只有正确类型的 ProteinStore
才能赋值给 store。旧完成仅更新其自身账本为 STALE_OPERATION，不执行新回调或解除新 busy。
新会话取消尚未启动的旧任务，阻止过期排队写入；已开始的调用不强杀，完成后仅记终态。
取消有独立通知，因 pool.clear 未运行的任务也能解除逻辑状态；运行中取消和实际停止分别记录。
正常、失败、取消、过期、回调失败和关闭均有可解释终态，回调异常不逸出 Qt。
关窗后不更新文本/控件，仅做终态和引用清理。账本为会话内数据，不是新增 SQLite 持久化。

### P1-B：原件字节获取与私有副本

先比较 OS 锁原件直连、副本、仅离线确认三种方案并通过设计门槛，再新增
`desktop/protein_snapshot.py`。现行路径不对原件建立 SQLite 连接。
原件受保护读取期间核对完整 hash、文件身份/时间、头和 sidecar；
副本关闭后复读 hash，与采集前/复制流/采集后 hash 全部一致才交给原领域适配器。
使用 Windows 读共享或 POSIX SQLite 字节锁；私有副本 0700、限定安全 Windows Python 补丁版本。
读后再次核对原件和副本，变化、WAL、日志、锁/权限或校验错误均拒绝；sidecar 元数据不可核验时也拒绝，不能当作不存在。
不自动 checkpoint、删除源边车、切换模式或用 immutable 忽略活跃 WAL。
领域适配器、C.1 记录、算法及 SQLite v3 不改；安全保证针对 Desktop 隔离入口。
详见[现行只读方案](PHASE_C2A_WAL_READ_ONLY_REVIEW.md)。

可观察来源测试记录 23 个场景、33 次 SQLite 打开；26 次只读 URI 均指向私有副本，
程序自身的原件只读 URI 次数为 0。直接源连接仅是测试显式注入的写入者。
外部写入者产生的 WAL/SHM 单独归因，原件/边车在读取前后核对完整 hash 和大小。
数据管理/C.1 在用户显式操作下原有的写入功能不被此只读来源合同替代。

### P2-C：导出失败分类

在 UI 发起导出前验证原生结果和严格 JSON；非有限/摘要损坏会撤销结果、审核及导出按钮。
原件消失或来源失效同样撤销，不伪装成单纯输出失败。
路径选择、扩展名、目标权限或已有文件问题保留有效计算结果，明确显示“报告导出未完成”，
允许重新选择目标；不把所有导出错误称为科学计算失败。
HTML 转义、原输入/结果绑定、不覆盖及原子发布保持有效；报告仍 fsync。
报告外层新增来源策略/身份，原 C.2A 科学结果和指纹不变，不添加区间或 MC。

### 正式测试及独立 RED/GREEN

本轮新增正式测试 **53 项**：任务生命周期 19、来源安全 23、原 MM Desktop 文件追加 11。
原 35 项测试的完整源码前缀 hash 保持一致，不修改其断言。

| 本轮最终实跑 | 结果 |
|---|---|
| MM Desktop（含原 35） | 46 passed |
| 生命周期 / 来源副本 | 19 / 23 passed |
| C.1 数值/存储/Desktop | 45 / 18 / 8 passed，合计 71 |
| C.2A / C.2B-1 / C.2B-2A | 69 / 78 / 87 passed |
| Protein Engineering 总专项 | **435 passed**，116.44s |
| SAFE_CI 应用范围 | **1185 passed, 1 skipped, 17 deselected, 18 warnings**，121.34s |
| Frozen Integrity | **15 passed**，0.97s |
| 原已确认 P1/P2 失败节点 | **5/5 GREEN**，原最终断言不变 |

原件原生读取显式发出 Python open 审计事件，已验证禁读钩子在打开前拒绝；
全部安全 runner 的 boundary violations=0；没有训练、真实 Provider、私有实验数据或密封评价。
上述专项存在包含关系，不累加为不重复覆盖。skip 为可选 langchain 缺失；训练/Live 排除保持原范围。

原审核 old_first 的同步谓词依赖错误状态；用户明确允许仅在新重放副本改为完成 Event。
另外使用任务账本等待链式回调结束，避免线程池瞬时空闲造成误判；所有 assert 的 AST 一致。
旧脚本/日志不动。完整重放为 **33 passed, 1 failed**：唯一失败仍是已独立分类的
1e-25 绘图往返 oracle 误判，未删、未放宽、未伪装通过；80 位 Decimal 参考检查通过。
该审核脚本问题不计项目 P0/P1/P2，不以修改科学计算去满足它。

### 限制与停止点

Windows 源码条件性工作流通过；Linux/POSIX 分支尚未在本机实跑，无可用 WSL 发行版，
不能使用本次结果宣称远端 Linux CI 已通过。POSIX 协作锁/非协作写的边界如只读方案所述。
冻结 Windows 包仍排除 SciPy，依赖/许可/干净安装验收未完成，WINDOWS_FROZEN_READINESS=NOT_READY。
真实酶实验资格、NOT_ESTABLISHED、参数区间/误差传播等原限制不变。

P0_P1_P2_REMAINING：0 / 0 / 0（本轮已确认 Desktop 范围）。
本轮只提供源码验收和可审查的本地工作区；没有暂存、commit、push、tag 或发布。
HEAD 仍为 `3fe35f98dacbbae1c3799f85e04fc4b6b62f6136`。
不进入 C.2B-1 Desktop、C.2C 或 SQLite v4。

## 以下为 2026-11-13 首轮交付记录（历史，现行状态以上节为准）

日期：2026-11-13（Asia/Shanghai）。
起始基线及本地 origin/main：`8d4c6029f2c41c4a6d9218840e37d4233380ee08`。
INTEGRATION_STATUS：**PASS_WITH_LIMITATIONS（源码工作流已实现；冻结包和 WAL 支持未交付）**。

## 1. 审查、版本与范围

已逐项核对整合审查、路线图、C.1、C.2A、只读适配器、速率存储和 Windows spec。
整合计划允许有限条件的源码工作流；没有支持直接启用真实 Monte Carlo 或参数区间的依据。

经用户本轮授权，只将两份既有整合文档固定为独立本地提交：

`3fe35f98dacbbae1c3799f85e04fc4b6b62f6136`

消息：`docs(protein): record integration audit and roadmap`，父提交为起始基线。
该提交仅包含 `PHASE_C_INTEGRATION_AUDIT.md` 与 `PHASE_C_INTEGRATION_ROADMAP.md`。
本轮实现代码、测试和新报告没有暂存或提交；未推送、创建 tag、构建/发布安装包。
历史整合文档描述的是实现前状态，保留其日期性证据，本报告记录本次增量。

## 2. 文件与调用关系

| 文件 | 职责 |
|---|---|
| desktop/protein_mm.py（新增） | 严格 JSON、只读来源应用边界、依赖探测、原内核调用、结果摘要核对、显示几何、离线 HTML/JSON 导出 |
| desktop/widgets/protein_mm_fit.py（新增） | 显式多选、审核、异步请求、失效控制、Qt 绘图与导出操作 |
| desktop/widgets/protein_engineering.py | 在既有第七页加入 C.2A 子标签，连接 busy/换库/保存后的失效；更新本轮能力说明 |
| desktop/widgets/protein_initial_rate.py | C.1 保存后使 C.2A 旧快照失效；更新相邻入口说明；不改计算 |
| tests/test_desktop_protein_mm.py（新增） | 35 项全合成 Desktop/报告/来源边界测试 |
| tests/test_desktop_protein_engineering.py | 保留七个顶层入口断言；将内部标签及规划页的索引断言更新为新增 C.2A 后的实际结构 |
| PHASE_C2A_WAL_READ_ONLY_REVIEW.md（新增） | 原适配器 WAL 行为复现、保守 UI 边界和待审合同方案 |

仍是一个应用、七个顶层页面；蛋白质工程内部由 7 个子标签变为 8 个。
原六个抗体页面、数据管理和 C.1 保留。

调用路径：

`已保存 C.1 目录 → 明确 analysis_id 多选 → load_rate_records 来源核验 → input_digest / FitReview → fit_michaelis_menten → 原结果核对 → 数值表 / Qt 图形 → 显式本地报告`

目录复用原 C.1 读取方法，使用新的只读连接外壳；目录信息没有科学资格。
拟合、计算后发布和导出都重新调用原领域适配器核验，不通过目录或当前 C.1 面板构造替代输入。

## 3. 输入与科研审核

- 默认不选行、不拟合；支持全部已保存记录，无数量截断、不自动去重或平均。
- 每格绑定真实 analysis_id；排序后仍按稳定 ID 选择。
- 目录显示底物、单位、产物速率、样品、批次、生物/技术重复和来源摘要；
  来源核验后显示变体与完整上下文、条件、标定、孔位、输入观察 ID、C.1 指纹及 QC。
- 用户必须填写审核人员、明确 UTC 时间和理由；可显式点击填入当前 UTC。
  产品生成方向和接受 NOT_ESTABLISHED 限制的两个确认默认不勾选。
- `FitReview.input_sha256` 绑定当前所选完整输入摘要。
  应用层同时保存核验时主数据库字节 SHA256，防止未选记录变化后沿用旧审核。
- 选择变化清空时间、理由、确认和来源快照；审核编辑清空确认与结果。
  换库、导入或保存 C.1 使整个 C.2A 选择/审核失效。
- 外部数据库变化在拟合前、计算后和导出前重新核验；不是持续文件监听。
  旧结果在动作前检查不通过后撤销，不将旧结果继续导出为当前结果。
- 核心资格仍由原 C.2A 决定；混单位、跨条件/上下文、复用原观测、
  缺标定和不可辨识数据不能通过人工确认绕过。

确认只记录研究人员接受条件性使用的限制，不证明实验初始速率成立。
C.1 `initial_rate_validity=NOT_ESTABLISHED` 未改写；审核文本不是账户认证或电子签名。

## 4. 异步、计算与显示

所有来源读取、依赖探测、拟合和导出在既有 Worker 中执行，复用页面 busy 和关闭等待机制。
没有用户动作不执行拟合；忙碌时锁定数据库、选择和审核控件；防止重复提交。
请求绑定路径与 epoch，旧请求回调不能覆盖改变后的输入。
损坏的后台返回值被捕获，撤销正常结果和导出，不让异常逸出 Qt 回调。

计算只调用原 `fit_michaelis_menten()`；版本仍为 `mm-unweighted-1.0.0`。
没有重写 least_squares、初始化、阈值、权重、残差、R² 或可辨识性规则。

显示原 Km/Vmax、单位、N、状态、观察/拟合速率、残差、SSE/RMSE/R²、
原优化器和可辨识性诊断、原因/QC、审核及输入/结果摘要。
`FIT_WITH_LIMITATIONS` 保留；`NOT_ESTIMABLE` 不展示可用参数和正常模型线。
R² 等未定义字段保留原空值，不补零。

使用 Qt QPainter，不新增 QtSvg、matplotlib 或大型绘图库。
模型线仅由原 Km/Vmax 生成，在观察浓度范围内取 121 个显示位置；不是新观测、重新拟合或外推。
每条重复逐点展示，残差使用原生 observed−fitted；不自动删点或选择最佳子集。
参数区间始终明确“未计算”，不展示误差带，不调用 C.2B-1 或合成 MC。

无噪声合成 N=7 场景恢复 Km=20 uM、Vmax=5 uM/min；保留浮点残差而不人工归零。
该结果仅证明软件数值与整合路径，不是酶机制或真实实验验证。

## 5. 只读来源、WAL 与数据库保护

DATABASE_READ_ONLY：PASS，限定当前支持的普通本地、无并发写入、无边车 v3 来源。
原 `load_rate_records()`、C.1 存储、SQLite schema/migrations 均未修改。
不调用迁移构造器作拟合来源检查，不保存任何 C.2 结果到数据库。

新增只读应用连接在 SQLite 打开前拒绝现存 sidecar 及 WAL/未知头格式，
使用 mode=ro、query_only、读事务和 application_id/v3 检查。
主库摘要在读事务下取得，与所选输入摘要一起绑定请求。
领域适配器原有源字节 SHA256、身份/观察链接、迁移史、C.1 回放、标定来源检查完整保留。

发现原适配器对“关闭且无边车的 WAL 库”仍会创建共享内存/日志文件。
原失败证据保留，见[独立 WAL 设计审查](PHASE_C2A_WAL_READ_ONLY_REVIEW.md)。
本轮只收紧应用入口，不修改领域适配器合同，不自动删除日志、checkpoint、恢复或更改模式。
WAL 支持停止于设计审查，不能宣称已支持所有 SQLite 只读场景。
默认 DELETE 模式的同一 Desktop 导入→C.1→保存→C.2A 已通过测试，没有新增边车或源字节变化。

SHA256 是内容一致性记录，不证明源数据真实性；读事务也不是恶意文件替换防护。
并发数据库管理、WAL 共享快照和 SQLite v4 持久化均未交付。

## 6. 报告与隐私

REPORT_EXPORT：PASS（源码、合成本地目标目录）。

- 用户明确选择新的 HTML 或 JSON 文件；取消不写入、不撤销当前有效结果。
- 导出前再次核验来源及审核摘要，检查原生完整结果的 `result_sha256`、
  `input_sha256`、版本和审核绑定；严格 JSON 拒绝 NaN/Infinity。
- JSON 外层 `protein-c2a-report-1` 含参数、逐点数据、诊断/优化器/QC、审核、
  版本/配置/依赖、来源摘要、数据库 SHA256 和科学限制。
  默认不复制完整序列、原件 BLOB、原始来源文件字节。
- 原生结果摘要仍指向完整内存结果，报告明确它不是缩减报告本身的 hash；
  另计算 report_sha256 绑定报告 payload，不修改原生科学结果。
- HTML 含可离线读取的表格、内联 SVG 图、来源/审核和限制。
  所有用户/来源文本 HTML 转义，CSP 禁止网络与脚本，不使用远程资源。
- 同目录临时文件完整写入并 fsync 后以不覆盖硬链接发布。
  已有目标保持原样；不支持硬链接/权限不足时明确失败，清理本次临时文件，不采用覆盖回退。
- 报告含样品/批次/来源文件名及审核信息，仍可能敏感，须由用户自行保管。
  没有上传、Provider、文献、Copilot 或其他自动发送路径。

报告格式不是原数据库或完整原始实验包的替代品；保留原件及来源库仍是重现前提。

## 7. 依赖与 Windows 打包结论

| 环境 | 本轮结论 |
|---|---|
| 本机源码 Desktop | PASS：Python 3.14.8、NumPy 2.5.4、SciPy 1.18.1、PySide6 6.12；明确依赖存在时完成拟合/报告 |
| 缺少/无法加载 SciPy | PASS：显式来源核验时提示不可用并禁用拟合；不在页面导入时强制加载 SciPy，数据管理/C.1 不因此崩溃 |
| 当前冻结 Windows spec | NOT_READY：仍显式排除 SciPy；不因源码测试通过宣称 exe 含完整数值依赖 |
| 本轮新 Windows 包/干净机器/远端 CI | 未构建、未发布、未触发；不能使用旧基线 CI 成绩代替新实现验收 |

`packaging/windows/workbench.spec`、依赖及许可证允许列表均未改动。
扩展 SciPy/native libraries、第三方许可/SBOM、包体和实际 exe 验收需独立授权与评审。
没有为了通过测试删除排除项或上传二进制。

## 8. 实际安全验收

证据根：`dist/protein-engineering/c2a-desktop-d1-20261113/`（忽略目录，不纳入源码提交）。
测试复用当前 `.github/workflows/ci.yml` 的 SAFE_CI guard，并隔离 APPDATA、缓存、basetemp 和 junit。
focused 额外禁止读取保留的手工工作簿和旧 pytest 临时目录。

### 命令与结果

以下命令均使用本机 `dist/4.1.0rc2/venv-build/Scripts/python.exe`，不是旧测试成绩。

```powershell
# 每项通过 REVIEW_RUN_ID 指定独立日志；runner 从现有 workflow 取得原安全 guard。
$env:SAFE_CI_SCOPE='focused'
$env:REVIEW_RUN_ID='desktop-final'
python dist/protein-engineering/c2a-desktop-d1-20261113/focused/run_review.py tests/test_desktop_protein_mm.py tests/test_desktop_protein_engineering.py tests/test_desktop_protein_initial_rate.py

$env:REVIEW_RUN_ID='protein-final'
python dist/protein-engineering/c2a-desktop-d1-20261113/focused/run_review.py tests/test_protein_engineering.py tests/test_protein_initial_rate.py tests/test_protein_rate_storage.py tests/test_desktop_protein_engineering.py tests/test_desktop_protein_initial_rate.py tests/test_desktop_protein_mm.py tests/test_mm_kinetics.py tests/test_mm_uncertainty.py tests/test_measurement_propagation.py

$env:SAFE_CI_SCOPE='application'
$env:REVIEW_RUN_ID='application-final'
python dist/protein-engineering/c2a-desktop-d1-20261113/application/run_review.py

$env:SAFE_CI_SCOPE='integrity'
$env:REVIEW_RUN_ID='integrity-final'
python dist/protein-engineering/c2a-desktop-d1-20261113/integrity/run_review.py
git diff --check
```

| 本次测试 | 真实结果 |
|---|---|
| 新 C.2A Desktop | **35 passed**；与原 C.1/page Desktop 合计 **49 passed**，5.52s |
| 蛋白质工程全专项 | **382 passed**，119.44s |
| 其中 C.1 数值/存储/Desktop | 45 / 18 / 8 passed（合计 71） |
| C.2A 原数值/适配回归 | **69 passed** |
| C.2B-1 原区间回归 | **78 passed** |
| C.2B-2A 原合成传播回归 | **87 passed**；含原 1e297、缺失指纹、摘要篡改及负方差/JSON 反例 |
| SAFE_CI 应用范围 | **1132 passed, 1 skipped, 17 deselected, 18 warnings**，126.70s |
| Frozen Integrity 白名单 | **15 passed**，1.08s |
| Qt offscreen 合成画面/报告检查 | **1 passed**；检查中文面板、两幅曲线、观察表和可导出状态 |

上述是包含关系，不累加为互不重叠的测试总数。
所有 runner 均报告 **SAFE_CI boundary violations: 0**。
应用范围 skip 为可选 langchain 缺失；排除 `test_ml.py`/`test_rag.py`，
并沿用 workflow 精确训练节点 deselect 和 `-m not live`。
完整性只运行白名单的合成/源码检查，不执行历史全量 validation 或密封评价。
SAFE_CI PASS 不等于历史全量训练测试均已通过。

首次专项 34 passed / 2 failed 的记录在 `focused/desktop-01.log` 保留：
一项是报告审核字段人读转义展示缺口，已补充转义表；另一项是新增标签后旧规划页索引，
现按实际 C.2A/规划标签分别断言。没有放宽科学数值断言。
后续 38、43、49 项专项逐步通过；WAL 原复现另行保留，不抹去失败证据。

新增 35 项覆盖：稳定多选 ID、审核/选择/换库失效、混单位/跨条件/重复原始观察/
不可辨识/缺标定拒绝、C.1 警示、缺 SciPy 降级、损坏来源/后台结果、三类边车/
活动与关闭 WAL、异步重复提交与心跳、旧回调丢弃、HTML 转义、严格 JSON/三种非有限值、
取消/已有文件/文件系统失败、导出重核、未选记录变化的三个阶段拒绝、
同会话导入→C.1 保存→8 条速率拟合。

Qt offscreen 默认没有系统字体，首次截图出现方框；视觉证据脚本显式加载本机中文字体后重新检查。
这只是测试夹具设置，没有修改产品字体逻辑；离屏画面不代替真实窗口人工交互和干净安装验收。

## 9. 科学与工程保护

SCIENTIFIC_REVIEW：PASS_WITH_LIMITATIONS。
当前审核批准条件性单上下文源码工作流，不批准机制成立、真实初始速率有效或完整实验误差量化。
拟合成功不是实验资格的替代，技术重复不升级为生物学独立样本。

本轮前后字节核对：已有跟踪文件仅三份预期 UI/导航测试文件变化。
`protein_engineering/` 原有科学/存储/迁移代码、core.py、scoring.py、ml_inference/、
冻结 ESM2 与 AIntibody/GDPa3 结果、workbench.spec、SAFE_CI 工作流、版本元数据保持原样。
SQLite 仍为 **v3**；没有打开真实用户数据库、训练模型、调用真实 Provider 或重算密封实验结果。
CLI 修改及手工工作簿保留；旧 pytest 目录只核对既有文件清单/大小/mtime，不读取其实验内容。
新文件另作 UTF-8、语法、空白/结尾检查，不能仅凭 git diff --check 代表未跟踪文件已审查。

当前 HEAD 为文档 checkpoint，origin/main 仍为起始基线；索引为空。
未提交项为本轮 6 份实现/测试、2 份新增报告，以及原 CLI/工作簿/临时目录。
无实现提交、push、Release 或 tag。

## 10. 阻断项与停止点

BLOCKERS：

1. 冻结 Windows 包的 SciPy/native dependencies 与许可/实际 exe 验收未获本轮变更授权，不能发布 C.2A 包。
2. WAL 领域适配器只读合同需独立审查；本轮 UI 保守拒绝，未交付 WAL 支持。
3. 真实酶数据资格、生物学独立性和测量充分性仍需研究人员审阅；合成通过不替代真实实验。

NEXT_RECOMMENDATION：独立审查当前源码增量及只读边界，随后单独授权冻结包依赖/许可证方案和真实窗口验收。
本轮在此停止，不进入 C.2B-1 Desktop、真实 MC、C.2B-2B、C.2C 或 SQLite v4。
