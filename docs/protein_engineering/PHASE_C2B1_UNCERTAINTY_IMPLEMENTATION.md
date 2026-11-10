# C.2B-1 参数不确定性与可辨识性实现报告

日期 2026-11-10；算法版本 `mm-profile-normal-1.0.1`（P1 数值完整性修订）。
HEAD `9b77b868b194545ec8cb299c67a9e97af5c6fe89`；本地 origin/main
`6a1d1cb230734dc1b88c160631fe7392505e33c8`。本地领先是已授权 C.2A checkpoint，非异常。
五个 C.2A 文件已在该提交中；本轮不修改它们，不提交、推送、创建 tag 或发布。

## 协议与实现范围

先建立 [统计协议](PHASE_C2B1_UNCERTAINTY_PROTOCOL.md)，明确统计对象、假设和区间准则。
实现独立 Python API，不接 Desktop、不建 SQLite v4、不持久化或改写实验/C.1/C.2A 结果。

新增四个文件：

- `protein_engineering/mm_uncertainty.py`：UncertaintyReview、analyze_mm_uncertainty；
  内部 _Profile 负责条件最小化、解析极限、扫描和端点核验。
- `tests/test_mm_uncertainty.py`：62 个合成验证用例（保留原45项，新增17项 P1 契约回归）。
- `docs/protein_engineering/PHASE_C2B1_UNCERTAINTY_PROTOCOL.md`。
- 本实现报告。

原 C.2A/C.1、schema、migrations、Desktop、抗体规则和冻结研究结果均不修改。

## 统计对象、假设和区间方法

每条 C.1 产物速率是一个条件性测量单位，时间点不是额外 N。沿用 C.2A 单一
变体/样品/批次/生物重复；生物学 N=1。技术重复不是独立生物重复。
必须额外审阅并明确接受条件性独立、同方差加性正态速率误差、固定已观察的
标定/空白/窗口/浓度，并填写独立性依据和 analysis_id→独立测量单位映射。
映射重复或缺失即拒绝；独立性是条件假设，不是点击确认后得到的实验事实。
UncertaintyReview 与完整输入摘要及 C.2A result_sha256 绑定。

v=Vmax*S/(Km+S)，Km、Vmax>0，sigma² 未知。固定目标参数，重新最小化另一参数，
得到 SSE_profile。对正态似然进一步剖面消去 sigma²：其 MLE 是 SSE/N；
LR=`N*log(SSE_profile/SSE_min)`。默认阈值为 chi²(1) 的 0.95 分位数
3.841458820694124，等价 SSE 比 exp(阈值/N)。没有使用 SSE/(N-2)、F 阈值、
已知 sigma 的 SSE 差或 Wald 区间。没有输出协方差置信区间。

Km 和 Vmax 分别计算的近似 95% 单参数剖面似然区间，并不构成 95% 同时覆盖的联合置信区域。

该阈值依据 Wilks 大样本近似；非线性、小样本和边界下不能保证 95% 频率覆盖率。
N<6 拒绝（本实现保守限制，不是通用统计定理），N<20 保留小样本警示。
归一化残差方差 <=1e-24 时拒绝，不返回零宽区间或假造噪声。
初次实现未做覆盖率模拟；随后独立审核进行了200次合成诊断，本轮 P1 修复以相同脚本和种子
重新核对，200次区间和状态与修复前逐项完全一致。种子20261110，N=7，S为标准七种浓度，
真实 Km=20 uM、Vmax=5 uM/min，独立正态速率噪声SD=0.10 uM/min。
Km 覆盖185/200=92.5%，Monte Carlo标准误1.86246个百分点；Vmax覆盖183/200=91.5%，
标准误1.97199个百分点。没有删试验、补值或据此调阈值；该单一设计和单组固定噪声
均不能证明真实数据的95%覆盖率，也不能忽视模拟误差推断普遍偏差。

## 数值和可辨识性审查

1. 在内存回放 C.2A，核对全部配置、快照、来源及结果；非 FIT_WITH_LIMITATIONS 拒绝。
   不重选原点估计或原方差基准，C.1 NOT_ESTABLISHED 不升级。
2. 固定 Km 时解析重新优化 Vmax=sum(g*y)/sum(g²)。
3. 固定 Vmax 时将 nuisance Km 正半轴变换到 t∈(0,1)，129 点确定性网格定位可见低点，
   同时细化首尾单元；分别做 bounded 最小化，并计算真实开放域极限。
   记录各局部优化状态、t/尺度、函数调用次数和失败 bracket。网格不是全局最优数学证明。
4. 目标参数按 log 比扫描，默认每侧80步；端点为 LR 临界值的 brentq 根。
   有限根须满足 LR 容差，不用扫描端点填充区间。
5. 解析检查 Km→0、Km→∞、Vmax→0/∞ 的剖面极限；线性渐近模型支持可接受任意大
   参数时，upper=null。只达到数值预算则 BOUNDARY_LIMITED，不冒充统计不可辨识。
6. 局部 log 参数相关性和 Jacobian 条件数仅为辅助；强相关、宽区间、C.2A 覆盖警示
   或非单调剖面导致 WEAKLY_IDENTIFIABLE。多个交叉/开放 nuisance 边界限制端点显示。

状态分别保留 INTERVAL_ESTIMATED、WEAKLY_IDENTIFIABLE、BOUNDARY_LIMITED、
NOT_IDENTIFIABLE、NOT_ESTIMABLE、NUMERICAL_FAILURE。NOT_IDENTIFIABLE 仅表示
本条件似然准则不能有界约束；不声称已经区分结构性与实践性原因。
每参数输出原点估计、单位、两端点或 null、置信水平/方法/假设、状态、原因、
解析极限 LR、全部已计算 profile 点和数值诊断。结果另有版本、输入摘要和结果摘要。

## 合成结果（本轮实际计算）

| 场景 | N | 参数 | 点估计 | 近似95%条件区间 | 状态 |
| --- | ---: | --- | ---: | --- | --- |
| S=2/5/10/20/40/80/160，固定噪声 | 7 | Km (uM) | 20.2821953114 | [19.2121252683, 21.4111763123] | INTERVAL_ESTIMATED |
| 同上 | 7 | Vmax (uM/min) | 5.03275063967 | [4.94704477248, 5.12052316954] | INTERVAL_ESTIMATED |
| S=1/2/3/4/5/6/8，较小固定噪声 | 7 | Km (uM) | 20.6585896777 | [18.6892142021, 22.9923894327] | WEAKLY_IDENTIFIABLE |
| 同上 | 7 | Vmax (uM/min) | 5.13651954986 | [4.75199053746, 5.59118833606] | WEAKLY_IDENTIFIABLE |
| 独立构造正交残差，使线性渐近尾部被接受 | 7 | Km (uM) | 20.0000000070 | 下侧5.67818173028，上侧null | NOT_IDENTIFIABLE |
| 同上 | 7 | Vmax (uM/min) | 5.00000000137 | 下侧2.15188195885，上侧null | NOT_IDENTIFIABLE |
| 无噪声 Km=20、Vmax=5 | 7 | 两参数 | C.2A估计保留 | 两端均null，方差退化 | NOT_ESTIMABLE |

固定噪声为 +0.01/-0.03/+0.02/-0.04/+0.06/-0.02/+0.03。
理想噪声场景局部相关为0.8343829425；弱辨识场景相关为0.9973087969，即使 R²>0.99
仍明确报告弱辨识。无界示例通过独立过原点直线残差 SSE 核对接受的无限参数极限。
不将这些计算描述为真实实验验证或预测性能。

独立参考实现使用物理单位：固定 Km 解析求 Vmax，固定 Vmax 在 log Km 上做另一个
一维最小化，再独立求 LR 根；不调用生产 _Profile、t 变换或其 Jacobian。
上下界相对误差断言 1e-8，LR 根绝对误差 1e-6。单位从 uM 换算到 mM 的独立输入
fixture 验证 Km 点估计/区间随尺度换算，Vmax 不变；内核不自动换算单位。

## 失败案例与数值稳定性

- C.2A 低/高浓度极端覆盖、参数边界或 NOT_ESTIMABLE：拒绝进入区间阶段。
- 空来源、错单位、篡改配置/点估计/有效性、非有限观测或摘要不符：拒绝。
- 未确认独立性/正态同方差假设、重复或缺失独立单位、仅技术重复却无独立测量依据：拒绝。
- 零/近零残差：拒绝估计方差退化下的参数区间。
- 优化器未收敛、非有限目标、根求解失败：NUMERICAL_FAILURE，失败侧不返回有限区间。
- 极小置信水平导致临界值下溢、伪根或无法分辨双侧端点：NUMERICAL_FAILURE，不返回零宽区间。
- 极小搜索预算 fixture：BOUNDARY_LIMITED，上下界不以搜索端点伪造。
- 固定/极低/极高范围、相关性、未知方差和开放域极限均用合成数据覆盖。

使用浓度/速率缩放、解析条件解和 nuisance 自适应尺度避免大参数尾部的数值消去。
SSE 比基准低超过协议数值容差时失败；微小舍入负 LR 仅归零，绝不重设 C.2A 基准。
短预算测试首轮发现原来的一步扫描已能找到根，修正为显式注入极小扫描步长以测试
预算不足路径；没有放宽区间精度断言、统计阈值或删除失败数据。

## 初次实现阶段验收记录（历史，不代替本轮 P1 验收）

环境 Windows、Python 3.14.8、NumPy 2.5.4、SciPy 1.18.1。未运行远程 CI，
不使用旧成绩冒充本轮验收。使用原 `.github/workflows/ci.yml` 的 SAFE_CI runner；
本地 harness `dist/protein-engineering/c2a/run_safe.py`，输出是忽略的本地日志。
所有命令的 Python 均为 `dist/4.1.0rc2/venv-build/Scripts/python.exe`。
QT offscreen、隔离 profile/basetemp、阻止 sklearn/TF-IDF fit、外网和真实数据路径。

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:SAFE_CI_SCOPE='targeted'
$env:C2A_RUN_ID='c2b1-numerical-04'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_mm_uncertainty.py tests/test_mm_kinetics.py
# 114 passed in 4.13s（新增45 + 原C.2A 69）

$env:C2A_RUN_ID='c2b1-c1-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_protein_initial_rate.py
# 45 passed in 0.16s

$env:C2A_RUN_ID='c2b1-protein-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_protein_engineering.py tests/test_protein_initial_rate.py tests/test_protein_rate_storage.py tests/test_desktop_protein_engineering.py tests/test_desktop_protein_initial_rate.py tests/test_installed_package.py tests/test_windows_delivery.py
# 135 passed in 3.84s

$env:SAFE_CI_SCOPE='application'
$env:SAFE_CI_COLLECT_ONLY='0'
$env:C2A_RUN_ID='c2b1-application-02'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py
# 977 passed, 1 skipped, 17 deselected, 18 warnings in 13.05s

$env:SAFE_CI_SCOPE='integrity'
$env:C2A_RUN_ID='c2b1-integrity-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py
# 15 passed in 0.94s

git diff --check
```

全部安全边界违规0；专项是完整应用的子集，不将通过数相加冒充独立覆盖。
跳过1项因未安装 LangChain；17项取消选择包含 live 和已审查的训练节点，
test_ml.py/test_rag.py 不进入默认安全范围。18 warnings 来自既有 Gradio 提示与 pandas 弃用。
完整性仅原15项白名单，不运行全量 validation 及部署模型重建。
SAFE_CI PASS 不等于历史全量训练测试均已通过。

## P1 修复、严格输出契约与本轮实际复测

独立科学复核曾发现：标准固定噪声输入仅把所有底物浓度放大1e297，
输入/C.2A点估计仍有限，C.2B-1却成功返回34个inf剖面值。原失败报告、
scale-diagnostic.json、finiteness-reproducer.log和原独立测试均原样保留在
忽略的 `dist/protein-engineering/c2b1/science-review/`。
本轮先确认 RED，再修改；原独立测试断言未改，得到 GREEN。

只修改这四个 C.2B-1 文件。修复函数：`_restore_physical`、`validate_finite_json`、
`_finalize_result`，错误类型 `ResultIntegrityError`。算法版本 .0→.1 仅标识输出完整性修订；
未变动任何 likelihood、N、sigma²估计、χ²阈值、搜索步长/次数、点估计或原数值断言。

- 显式校验 Python float 乘积和 NumPy标量转为原生实数后的有限性。
  检查 target/nuisance、区间界限、所有数值诊断和最终完整结果。
- 物理还原采用原归一化剖面与尺度；原子构建物理列，失败时不返回部分溢出列。
  极端例返回 NUMERICAL_FAILURE / PHYSICAL_UNIT_RESTORATION_OVERFLOW，
  阶段 PHYSICAL_UNIT_RESTORATION，参数区间不展示；保留完整 SCALED_ONLY 剖面：
  Km 173点、Vmax 175点，未减少80步搜索或截断数值。
- 对嵌套字典、列表/元组、dataclass区间对象、Python/NumPy实数递归校验并规范为原生JSON。
  正值参数还原下溢为0也拒绝。正常有限区间必须严格位于点估计两侧。
- 最终完整对象与结果摘要通过 `json.dumps(...,allow_nan=False)`。
  意外非有限诊断导致计算结果变为 NUMERICAL_FAILURE；只有失败快照可把不可编码叶子
  替换为null，明确记录路径/错误码及标记。原始调用者/C.1/C.2A对象不修改。
  已因无效输入被拒绝的 NOT_ESTIMABLE 保持拒绝状态并记录安全快照，不插补实验值。
- 真实统计无有限上界仍使用 OPEN_DOMAIN_LIMIT/null；普通无界fixture仍为
  NOT_IDENTIFIABLE，不能与浮点溢出混淆。

独立完整结果扫描：NONFINITE_OUTPUT_COUNT=0；STRICT_JSON_SERIALIZATION=PASS。
普通固定噪声示例的Km/Vmax点估计、区间与前表逐位一致；独立物理单位根检查继续通过。
200次原诊断的 coverage-trials.json、coverage-summary.json 与新目录复测结果完全相等。

本轮仍用同一 SAFE_CI harness/开发解释器，各次独立 C2A_RUN_ID，日志实际路径如下。
下列命令均以 `dist/4.1.0rc2/venv-build/Scripts/python.exe` 运行：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:SAFE_CI_SCOPE='targeted'
$env:C2A_RUN_ID='c2b1-p1-independent-green-02'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py dist/protein-engineering/c2b1/science-review/test_review_output_finiteness.py
# 1 passed in 0.25s；修改前同一原测试1 failed in 0.37s

$env:C2A_RUN_ID='c2b1-p1-numerical-03'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_mm_uncertainty.py
# 62 passed in 4.33s

$env:C2A_RUN_ID='c2b1-p1-c2a-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_mm_kinetics.py
# 69 passed in 1.46s

$env:C2A_RUN_ID='c2b1-p1-c1-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_protein_initial_rate.py
# 45 passed in 0.16s

$env:C2A_RUN_ID='c2b1-p1-protein-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_protein_engineering.py tests/test_protein_initial_rate.py tests/test_protein_rate_storage.py tests/test_desktop_protein_engineering.py tests/test_desktop_protein_initial_rate.py tests/test_installed_package.py tests/test_windows_delivery.py
# 135 passed in 4.08s

$env:SAFE_CI_SCOPE='application'
$env:SAFE_CI_COLLECT_ONLY='0'
$env:C2A_RUN_ID='c2b1-p1-application-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py
# 994 passed, 1 skipped, 17 deselected, 18 warnings in 14.55s

$env:SAFE_CI_SCOPE='integrity'
$env:C2A_RUN_ID='c2b1-p1-integrity-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py
# 15 passed in 0.94s

git diff --check
```

安全边界违规均0；排除和skip原因沿用既有安全范围，无训练、真实Provider/网络、
真实数据库/私有数据或历史密封重评估。本地日志/新诊断在忽略的
`dist/protein-engineering/c2b1/p1-review/`，原失败证据不覆盖。
本轮科学结论：PASS_WITH_LIMITATIONS；P1已解除、P2已澄清。
只具备进入选择性Checkpoint审查的条件，本轮未暂存、提交或推送。

## 科学限制与 C.2B-2 前置条件

本阶段只输出明确假设下的条件性近似参数区间，未验证实验初始速率资格。
未传播空白/标定系数/底物浓度/C.1估计误差；未建模异方差、技术相关或批次生物差异。
没有完整实验误差模型、外部酶动力学验证、kcat/kcat/Km、WT比较、AI训练或结构分析。
需要先人工科学审核独立性和误差假设、边界/小样本适用性和数值全局性限制。
C.2B-2 须另定层级误差/相关设计、标定空白重复数据与不确定性来源、实验资格及验证方案；
若持久化则先审核迁移/兼容性；本轮不设计或执行新迁移，不读真实用户数据库。

索引保持为空；原 cli.py、literature/cli.py、manual_acceptance.csv.xlsx、
pytest-of-Administrator/ 保留。只有上述四个新增文件待审，原版本元数据及 Release 状态不变。
停止于 C.2B-1，等待科学与工程审核。
