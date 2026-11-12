# C.2B-2A 合成联合测量传播：首版冻结设计与验收记录

算法计划版本：`synthetic-joint-mc-1.0.0`。
协议 checkpoint：`0629f9811d38087a90e9cee1cee5aeca2f7b294f`，父提交 `5b53d9d086f692954b64c8eb003a1e772fe904e6`。
本节在实现及任何模拟执行前固定；验收记录将追加于文末，不根据结果修改本节标准。

## 1. 首版范围及测量方向

所有结果均为 `SIMULATED / CONDITIONAL_MEASUREMENT_PROPAGATION`，不接收文件、数据库或外部速率。
只生成明示理论 fixture：单变体/样品/生物单位/批次，7 条独立孔位技术测量曲线，
S=[2,5,10,20,40,80,160] uM，t=[0,0.01,0.02,0.03,0.04] min，固定完整窗口。
Km=20 uM，Vmax=5 uM/min，P0=1 uM（虚构产物添加量、不影响速率的构造假设），
k0=2 RFU/uM，b0=5 RFU，blank0=2 RFU，校正信号有效域 [0,100] RFU。
固定时间戳只为确定性 replay；`initial_rate_validity=NOT_ESTABLISHED` 不变。

先按名义理论曲线生成原始信号 R=blank0+b0+k0*(P0+v*t)。
传播条件是固定这组名义读数，对读数、空白、标定和底物赋予明示的输入分布：
R*=R+仪器扰动；B*=blank0+delta_blank+delta_drift*t；
k*=k0+delta_k；b*=b0+delta_b；S*=S*(1+delta_stock)。
不随 k* 或 S* 重新生成理论信号；否则会抵消本来需要传播的标定/制备不确定性。
每个 draw 都重跑冻结 C.1 和 C.2A，固定观测成员，不使用解析参数公式代替拟合。

## 2. 显式联合误差模型与支持域

独立潜变量 U_l~Uniform[-1,1]；共享量顺序固定为
`blank_offset, blank_drift, calibration_slope, calibration_intercept, stock_delta`。
调用者必须提供线性载荷 L、其联合协方差 `L*L^T/3`、逐量支持域
`[-sum(abs(L_row)), +sum(abs(L_row))]`、单位、独立性说明和共享组到全部曲线的映射。
协方差合法 PSD 且与载荷一致才接收；秩亏可由共同潜变量合法产生，不加 jitter 或投影修复。
各潜变量独立是这个合成模型的明示构造，不是真实数据的默认假设。
仪器逐点噪声为独立 Uniform[-sqrt(3)*sigma_R,+sqrt(3)*sigma_R]，sigma_R 也必须显式提供。
零载荷/零 sigma 只代表这个虚构模型主动固定某量，不能由元数据缺失推断。

每个共享量每次只抽一次，按 blank/calibration/stock 共享组复用于全部曲线；
不同组之间的相关性由相同 U 的载荷表达，组名本身不表示独立。
共享量、独立读数扰动和同次 Km/Vmax 保留共同 draw_id。
不追加 C.1 SE、C.2B-1 区间或 MM 残差；本轮不调用剖面似然分析。

首批综合模型：sigma_R=0.001 RFU；独立 U1..U5；
blank_offset=0.01*U1；blank_drift=0.01*U2；
delta_k=0.04*U3；delta_b=0.05*(0.8*U3+0.6*U4)；delta_stock=0.02*U5。
各模型都明确列出未覆盖的自相关、完整标定标准、真实配液、生物/批次差异及模型失配。

## 3. RNG、算量及预声明精度政策

RNG：NumPy Generator(PCG64)，固定 seed=20261111。每个 draw 先抽共享潜变量，再抽全部读数潜变量；
同模型同种子 1024 是 4096 的共同前缀，不称两个独立重复实验。
首批 1024，复核 4096；可选 16384 不进入日常 CI，本轮不强制运行。
日常测试允许较少 draw 作资格/失败/解析不变量验证；低于 1024 的精度状态必须标明不足。
同环境逐位复现；跨 NumPy/SciPy/平台只承诺记录版本并按固定数值容差比较。

均值 MCSE=`sample_SD/sqrt(M)`；协方差用无偏样本协方差，MCSE 使用中心乘积的经验标准误
（乘 M/(M-1) 与样本协方差尺度一致），是有限样本近似诊断，不宣称覆盖保证。
输出均值、协方差及其 MCSE 和单位；以归一化数据计算，再逐项检查物理单位还原。
近常量判据 SD <= 1e-8*max(abs(mean),1e-300)，标为 BELOW_NUMERICAL_RESOLUTION，
不能以浮点拟合抖动解释生物变异；样本协方差原值仍保留，不强行截零。

2.5%/97.5% 传播分位数用 NumPy linear 分位数；MC 精度带采用二项分布顺序统计量，
单个分位数名义 99% MC 带，秩为 binom.ppf(0.005,M,p) 和 binom.ppf(0.995,M,p)+1。
秩 0/M+1 时边界为 null 并标明未分辨，不能裁成最小/最大样本假装有完整精度带。
该带描述有限 MC 对目标分位数的精度，不是酶参数的频率学置信区间，也不是多个分位数联合保证。

在参数 SD 超数值分辨率时，预定目标为：均值 MCSE/SD<=0.05；
每项协方差 MCSE/(SD_i*SD_j)<=0.10；每个分位数 MC 带全宽/SD<=0.40。
涉及近常量参数的相对协方差精度不作除零评价，保留 BELOW_NUMERICAL_RESOLUTION。
M<1024 为 INSUFFICIENT_DRAWS；达到 M 门槛后全部满足才为 TARGET_MET，
否则 TARGET_NOT_MET。精度未达标不调整阈值，不强行标为充分精度；如 4096 不满足，
保留该结果等待审核是否运行预声明的 16384，不偷偷追加或换种子。

独立核对：固定窗口权重 [-20,-10,0,10,20]/min；
读数噪声速率方差=sigma_R^2*1000/k0^2；共享漂移跨速率协方差=Var(d)/k0^2。
共同 k：V*=V0*k0/k*、Km不变；共同 stock：Km*=Km0*(1+delta_stock)、Vmax不变。
解析参数不变量的容差预定相对 1e-7、绝对 1e-8（常规单位）。
独立 1D profiled least-squares 参考的参数容差相对 2e-6、绝对 1e-7。
随机均值/协方差与独立解析值之差须 <=5*经验MCSE + 1e-10（对应物理量单位）；
这只是预定的合成数值验收，不等于频率覆盖率证明。

## 4. 严格失败与来源契约

缺少显式模型：MISSING_UNCERTAINTY_INPUTS；共享/跨单位结构不支持：UNSUPPORTED_DEPENDENCE；
非法物理输入/标定资格/拟合拒绝：NOT_ESTIMABLE；计算溢出或优化数值异常：NUMERICAL_FAILURE。
输入校验阶段失败则执行 0 draw；计算阶段继续记录所有请求 draw，绝不重抽或删点。
任何失败 draw 均阻断全部正常传播摘要/区间，成功 draw 可作为审计记录但不汇总幸存区间。
汇总阶段失败单独记录 analysis_failures，不能混称失败 draw。
极端尺度 1e297 允许在拟合或单位还原/协方差阶段明确失败；不产生 inf/NaN 成功结果。

输出经递归有限性和严格 JSON 检查；不可序列化的失败输入仅保留安全身份/阶段/错误码，
不将 inf 替换为 null 后继续成功。合法未分辨 MC 精度边界的 null 必须带明确状态。
原 fixture 摘要与每个模拟 draw 摘要分开；模拟源明确标 SIMULATED，不冒用真实原件 SHA256。
不写入 C.1 保存接口、数据库、Desktop 或任何真实实验文件。

## 5. 实际实现与验收记录

实际验收日期：2026-11-11。以上冻结设计在首次模拟前的完整文件 SHA256 为
`16eb822115df793d1fc1f736b3e107d1e93cae0a55f4867bdea78c99ed51c67a`；
首次及最终验收脚本均在执行模拟前核对该摘要。本节为后加的实际交付记录，前述数值标准未修改。

### 5.1 实现及接口

- [measurement_propagation.py](../../protein_engineering/measurement_propagation.py)：
  `SyntheticExperiment`、`CurveContext`、`JointErrorModel`、`SharedGroup`、`PropagationConfig`；
  `standard_synthetic_experiment()` 和显式 `synthetic_error_model()` 构造合成定义；
  `propagate_synthetic_measurements()` 只在内存完成传播，不提供文件、数据库或真实速率导入。
- [test_measurement_propagation.py](../../tests/test_measurement_propagation.py)：52 个合成测试。
  涵盖解析 OLS 方差、共享漂移的非对角协方差、k/b 相关、stock 不变量、合法秩亏、
  无效协方差/缺失声明拒绝、重复结构、标定域/负浓度/负速率、优化失败、1e297 和 JSON 契约。
- 正常 draw 保留共同潜变量、逐点仪器扰动、共享效应、Km/Vmax 对、7 条速率、
  C.1 输入摘要/指纹/观测成员及模拟来源 SHA256、C.2A 输入/输出摘要和 QC。
  失败 draw 保留阶段、具体原因和可重现来源。没有覆盖原始/C.1/C.2A 记录。
- 共同载荷模型支持共享组间相关；首版各共享量仅支持映射到全部曲线。
  不支持任意子组、复杂时间自相关或真实多批次联合模型，不在未支持情形下假装独立。
- C.2A 的原 QC 原文保留，标记 `INNER_DETERMINISTIC_C2A_ONLY`；其中“未传播”描述的是
  内层冻结点估计调用，不是把外层 MC 结果当成既有 C.2A 已有功能。
  “不同孔位”也不代表整条曲线间统计独立：共享空白、标定、stock 按模型共同抽样。

### 5.2 固定模型的实际 MC 精度

| 抽样数 | Km 均值 (uM) | Vmax 均值 (uM/min) | 失败 draw | 参数精度状态 |
|---|---|---|---|---|
| 1024 | 20.010274286964304 | 5.003701694939408 | 0 | TARGET_NOT_MET |
| 4096 | 20.00136447750093 | 5.0025186393950065 | 0 | TARGET_MET |

1024 次的 Km 上分位数 MC 精度带宽/SD=0.5946545，大于事前目标 0.40，故明确未达标；
未调整阈值。4096 次 Km 两端带宽/SD 分别为 0.1727346、0.2817809，
Vmax 为 0.1040191、0.1249563；最大协方差相对 MCSE=0.0205782<0.10。
均值 MCSE/SD=1/64=0.015625<0.05。
未运行可选 16384 次，也未挑选新种子。

4096 次边际传播分位区间（不是频率学置信区间，不是联合区域）：

| 参数 | 2.5% | 97.5% | 均值 MCSE | SD |
|---|---|---|---|---|
| Km (uM) | 19.37831083404535 | 20.65296530432526 | 0.005213115117319311 | 0.3336393675084359 |
| Vmax (uM/min) | 4.897110253406272 | 5.108786432763863 | 0.0009461677923988328 | 0.0605547387135253 |

同次 draw 的参数顺序为 [Km,Vmax]；协方差矩阵为
`[[0.11131522755142914,0.003721298764406077],[0.003721298764406077,0.0036668763806633198]]`，
单位按行列物理量相乘保存。
1024 个 draw 与 4096 个 draw 的前缀逐对象相同，不能相加后称为 5120 个独立实验。
小规模独立一维 profiled least-squares 参考与原内核符合预声明参数容差。
最终错误路径修复后重新运行相同两批，全部成功结果与修复前逐对象相同，未改变区间。

### 5.3 发现并修正的问题与保留证据

1. 首轮 `25 passed, 1 failed`：高读数噪声测试错误地预期失败只可能发生在标定域检查；
   原输入实际同时可产生被 C.2A 拒绝的负速率。保留同一数据、种子和全部失败 draw，
   测试分别验证 INITIAL_RATE 标定域拒绝与 MM_FITTING 负速率拒绝，未放宽数值容差。
   内核补留 C.1/C.2A 详细原因及来源，没有 abs、删点、重抽或改变拟合区间。
2. 最终审计增加了独立反例：显式字段为 null 时缺失元数据曾误报数值错误；
   最终结果被注入 NaN 时，fail-closed 分支曾丢失实际执行计数和成功 draw 的审计记录。
   初次针对测试 `7 failed, 1 passed`，修复后相同反例 `8 passed`。
   现缺失信息返回 MISSING_UNCERTAINTY_INPUTS；最终汇总失败仍保留实际请求/执行数、
   安全输入摘要和各次 draw，隔离无效汇总，返回 NUMERICAL_FAILURE，不输出正常区间。
3. 1e297 反例中单次 C.2A 参数仍有限，联合参数协方差物理还原溢出被明确拒绝：
   `NUMERICAL_FAILURE / PHYSICAL_UNIT_RESTORATION_OVERFLOW`。不混称统计无有限上界。
4. 成功及失败结果经递归有限性和 `allow_nan=False` 检查；最终输出非有限数值计数为 0。

首次失败、RED/GREEN、最终测试日志和 JUnit 结果均保留在 Git 忽略的
`dist/protein-engineering/c2b2a/`，正式测试不导入该目录中的脚本或计算证据。
没有为得到绿色结果降低断言精度、删除失败 draw 或更换科学模型。

### 5.4 实际验收命令与结果

本地运行器 `dist/protein-engineering/c2b2a/run_safe.py` 从受跟踪的 `.github/workflows/ci.yml`
读取原 SAFE_CI runner。focused 范围执行同一训练/外网/数据根隔离前缀并增加原用户文件、
SQLite 临时目录保护；application/integrity 原样执行对应 runner。所有范围边界违规数为 0。
测试缓存、用户配置、SQLite fixtures 及日志只进入隔离 dist 子目录。

| 范围/实际目标 | 最终结果 |
|---|---|
| `run_safe.py tests/test_measurement_propagation.py`，scope=focused | **52 passed** |
| `run_safe.py tests/test_protein_initial_rate.py tests/test_protein_rate_storage.py tests/test_desktop_protein_initial_rate.py tests/test_mm_kinetics.py tests/test_mm_uncertainty.py` | **202 passed** |
| 上述 C.1 细分 | initial_rate 45、rate_storage 18、Desktop initial_rate 8，共 **71 passed** |
| 上述 C.2A / C.2B-1 细分 | **69 passed / 62 passed** |
| `run_safe.py tests/test_protein_engineering.py tests/test_desktop_protein_engineering.py` | **42 passed**；完整 SAFE_CI 中再次通过同样 42 项 |
| `run_safe.py`，scope=application | **1046 passed, 1 skipped, 17 deselected, 18 warnings** |
| `run_safe.py`，scope=integrity，原 CI 冻结完整性 allowlist | **15 passed** |
| `accept_mc.py`，原 seed/model，1024 后 4096；最终再核对 | 均 0 失败；4096 TARGET_MET；共同前缀和严格 JSON 通过 |

实际 Python 及 NumPy/SciPy 版本随输出 metadata 保存，未以历史 CI 成绩代替本轮验收。
SAFE_CI 保留 `tests/test_ml.py` / `tests/test_rag.py` 排除、10 个已审训练节点排除及 `-m 'not live'`。
本机缺少 langchain，1 项可选适配测试如实 skipped；18 条警告来自原 Gradio/Pandas 测试。
**SAFE_CI PASS 不等于历史全量训练测试均已通过。**
本轮无 ML 训练、Provider/外网调用、真实实验/私有数据库读取、密封历史实验重评估。
这里的 SciPy 调用只用于获授权的冻结酶动力学点估计及独立合成数值核验。

### 5.5 保护、限制和停止点

原 `core.py`、`scoring.py`、CLI、工作簿/批量产物及 C.2A/C.2B-1 checkpoint 文件摘要一致；
原临时目录 565 个文件路径/大小/修改时间一致。既有受跟踪工作树修改仍只有两个 CLI。
SQLite schema 仍为 v3，无迁移；C.1/C.2A/C.2B-1 代码、冻结模型、验证结果和 CI 工作流未修改。
最终 Git 空白检查及索引检查另于交付核对，不执行实现代码提交。

SCIENTIFIC_REVIEW：**PASS_WITH_LIMITATIONS（实现内核对，仍等待独立科学审核）**。
JOINT_DEPENDENCE_VALIDATION：PASS；NO_DOUBLE_COUNTING：PASS；
DATA_READINESS：真实实验仍为 PARTIAL，仅启用明示的合成模型。
传播区间不是置信区间、不是生物变异，也不完成真实实验误差预算。
首版没有校准原始标准重拟合、任意误差分布、时间/空白随机过程、
多生物/跨批次层级统计、参数外部验证或完整实验误差传播。
仅两份已审核协议建立本地 commit；这三个新增实现/测试/报告文件保持未提交。
不推送、不发布、不进入下一阶段，等待独立科学与工程审核。

## 6. 独立审核 P1 修复与重新验收（2026-11-12）

第 5 节保留初版的本地验收记录。随后独立审核发现 3 项 P1、4 个失败用例，
原 FAIL 报告及所有证据仍保存在 `dist/protein-engineering/c2b2a/independent-review-20261111/`，
没有修改、删除或用新的 PASS 覆盖。最新修复结论以本节及新的 P1 修复审核报告为准。
本轮 HEAD 仍为 `0629f9811d38087a90e9cee1cee5aeca2f7b294f`，未提交实现。

### 6.1 完整性边界与失败响应

科学算法版本继续为 `synthetic-joint-mc-1.0.0`；新增独立的完整性契约版本
`synthetic-joint-integrity-1.0.0`，不更改 C.1/C.2A/C.2B-1 或 MC 统计配置。

- 入口明确区分缺失声明、字段类型错误、非法物理输入及数值范围问题。
  内部返回值先严格 JSON 化并脱离调用者别名，再检查必需字段、类型、版本、单位与来源。
- C.1 调用前固定当前原始观测、窗口、标定的可信快照；对返回输入摘要、实际输入对象和结果指纹逐项验证。
  指纹计算仍遵循原 C.1 规则：结果指纹排除计算时间及指纹字段本身。
- C.2A 调用前从当前 records 及 review 自行重算输入摘要，保存不可变快照；
  校验返回 input_records、review、配置、算法版本、输入/结果摘要及单位。
  观测 ID 必须完整且唯一，实测速率/底物浓度和样本数须对应当前 C.1 输入。
  自行篡改后重新生成一个自洽摘要，不能替换这些当前可信输入。
- 校验后使用独立快照；每个 draw 返回前留有私有封存记录，汇总前后及最终响应前再次核对。
  只允许将不一致记录降级为失败，不能把被篡改的成功值重新确立为基线。
  汇总本身也绑定当前输入、顺序、单位、精度配置及结果指纹。
- 缺字段为 REQUIRED_FIELD_MISSING，错误类型为 INTERNAL_RESULT_FIELD_TYPE，
  来源/摘要/单位/观测关联错误使用 INTEGRITY_MISMATCH_*，另保留具体数值错误和阶段。
  NUMERICAL_FAILURE 是现有协议的失败总状态之一，并不表示这些原因全是浮点溢出。

新增 `successful_draws`、`unexecuted_draws`；保留 requested/executed/failed 及全部 draw_id。
executed 计已开始执行的分析槽位，包括中途失败的槽位；successful 计完成且通过完整性校验的槽位。
有合法请求数时，`requested=executed+unexecuted`、`executed=successful+failed`。
入口资格失败为 0 执行并保留请求预算；汇总失败不把已成功的 draw 改成零执行或失败 draw。
任一失败 draw 均阻断正常传播区间，保留部分成功和全部失败记录，不重抽、不删点。
最终响应自身失败时，也从独立执行台账保留真实计数、已完成记录和安全来源摘要。

SHA256 只核对内容一致性及其与当前输入的绑定，不提供外部来源认证；
没有外部可信锚点时，不能证明整个来源或执行进程没有被恶意整体替换。

### 6.2 协方差资格修复

在任何容差或尺度判断之前，严格拒绝全部负对角方差，包括 -1e-320 和
最小可表示负非零 float64（-5e-324）。不裁零、不加 jitter、不投影矩阵。
零载荷对应的声明协方差行列必须确实为零。

按各量载荷尺度进行归一化验证；使用 frexp/ldexp，避免先乘两个物理尺度造成溢出/下溢。
在无量纲表示中校验对称性、PSD 和 L L^T/3 一致性，保留原 1e-12 数值一致性级别；
不再用物理量的绝对尺度地板掩盖负方差。此为资格校验修复，不调整 MC 精度标准。
合法负非对角协方差、合法秩亏、零矩阵和多数量级 PSD 模型均有正式回归覆盖。

### 6.3 RED/GREEN 与正式反例

| 证据阶段 | 实际结果 |
|---|---|
| 修复前原独立测试，字节相同副本 | 40 passed、4 failed，复现缺 C.1 指纹、缺 C.2A 指纹、摘要篡改、负方差 |
| 首次修复复测 | 43 passed、1 failed；剩余为快照字典次序重排，已修复且未修改原测试 |
| 最终原独立测试 | **44 passed**，原四个失败全部转绿 |
| P1-B 补充身份/观测/样本数反例 | 先 3 failed；补齐绑定后转绿，未改 fixture/种子/容差 |
| 正式测试 | 原 52 项保留，新增 35 项 P1 回归，共 **87 passed** |

原独立审核测试和运行器按字节复制到新目录执行，原文件及原 718 份审核证据摘要不变。
本轮新的 RED/GREEN、XML、完整合成结果位于 `dist/protein-engineering/c2b2a/p1-fix-20261111/`；
最终验收单独位于其中的 `final-acceptance-20261112/`，不覆盖旧证据。

正式回归包括：首个/单个 draw 缺指纹或类型错误、运行前来源不足、校验后对象别名修改、
抽样完成后指纹篡改、返回摘要不一致、全部输入自洽替换、错误版本/单位/配置、
观测重复/实测速率/样本数不一致、部分成功、汇总及最终响应故障、严格 JSON、
负次正规方差、合法负协方差/秩亏、多数量级、非有限矩阵及极端数值范围。
入口不接收既有分析结果；缺既有指纹在内部分析返回值消费之前拒绝，
不把已实际执行的 draw 伪称为尚未执行。

### 6.4 原科学结果精确不变

使用原 seed=20261111、PCG64、载荷、独立读数噪声及 1024/4096 安排。
直接复用原独立统计参考函数，重新计算均值、SD、协方差/相关、MCSE 和二项分位数精度带。
当前实际结果与修复前归档比较时，仅排除明确新增的 7 个契约字段：
两个根计数字段、metadata.integrity_version，以及两个汇总各自的 input_sha256/analysis_fingerprint。
**其余全部旧字段（包括每个 draw、来源摘要及所有科学数值）逐对象精确一致。**

| 抽样数 | 原字段精确一致 | 失败 draw | MC 精度 |
|---|---|---|---|
| 1024 | YES | 0 | TARGET_NOT_MET |
| 4096 | YES | 0 | TARGET_MET |

4096 的生产均值仍为 Km=20.00136447750093 uM、Vmax=5.0025186393950065 uM/min；
第 5.2 节记录的协方差和边际传播区间未变化。共同前缀仍相同，不把两批相加作为独立实验。
未运行可选的 16384 次，未改变精度阈值或任何科学模型。
传播分位区间仍不是频率学置信区间或联合 95% 区域。

### 6.5 最终回归、保护及结论

| 范围 | 本轮最终实际结果 |
|---|---|
| 原独立审查 | **44 passed** |
| 正式 C.2B-2A（严格 JSON/极端尺度/P1 反例均包含） | **87 passed** |
| C.1 | **71 passed**（45 数值 + 18 存储 + 8 Desktop） |
| C.2A | **69 passed** |
| C.2B-1 | **62 passed** |
| Protein Engineering 基础专项 | **42 passed** |
| SAFE_CI 应用范围 | **1081 passed, 1 skipped, 17 deselected, 18 warnings** |
| Frozen Integrity | **15 passed** |
| 最终原模型 1024/4096 独立复算 | PASS；所有旧字段精确不变；边界违规 0 |

SAFE_CI 继续隔离 ML/TF-IDF 训练、live Provider、真实实验及密封历史评价；本轮未执行这些操作。
SAFE_CI PASS 不等于历史全量训练测试均已通过。1 skipped 为缺少 langchain 的既有可选适配项；
18 条警告来自原 Gradio/Pandas 测试。SQLite 仍为 v3，C.1/C.2A/C.2B-1、抗体核心及冻结模型未改变。
三个交付文件仍未跟踪，除 git diff --check 外另直接执行了 AST、UTF-8、内容和空白格式检查。

P2 数值分辨率限制保留：BELOW_NUMERICAL_RESOLUTION 或零样本协方差不证明物理误差为零；
不截断、不隐藏实际数值、不改变原统计含义。本轮不宣称完成真实实验误差传播，真实 DATA_READINESS 仍为 PARTIAL。

重新审核结论：**SCIENCE_REVIEW: PASS_WITH_LIMITATIONS**；三个 P1 已消除，
具备进入选择性 Checkpoint 审查的条件。原始 FAIL 报告保留为历史证据。
本轮不暂存、不提交、不推送、不发布，不进入 C.2B-2B、C.2C 或真实数据集成。
