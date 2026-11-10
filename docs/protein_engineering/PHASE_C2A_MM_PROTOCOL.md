# Phase C.2A — Michaelis–Menten 拟合协议

协议/算法：`mm-unweighted-1.0.0`。基线 `6a1d1cb230734dc1b88c160631fe7392505e33c8`。
协议先于计算内核建立，只使用合成 fixture 验证；不是实验资格认证。

## 模型与资格

经典单底物初始速率模型：`v = Vmax × [S] / (Km + [S])`。
v 为产物浓度/时间初始速率，S 为底物浓度；Vmax 与 v 同单位，表观 Km 与 S 同单位。
不自动解释多底物、协同性、底物抑制；不计算 kcat、kcat/Km 或完整参数置信区间。

每次拟合明确选择 C.1 analysis_id，附审阅人、UTC 时间、理由、输入集合摘要、
反应方向 `PRODUCT_FORMATION`。审阅必须承认 C.1 初始速率有效性 `NOT_ESTABLISHED`，
不能借确认升级为实验已验证。成功状态只能是 `FIT_WITH_LIMITATIONS`。

C.2A 限同一 variant、sample、batch、生物学重复；技术重复逐条无权重参与，
不平均、不删异常点、不搜索子集。不同生物重复分别拟合，不将技术重复当作独立生物样本。
重复 analysis_id 或复用同一原始观测的不同窗口均拒绝。

批次条件必须明确且完全相同：protocol_id/version、温度、pH、缓冲液、底物名称/批号、
辅因子名称/浓度/单位、酶浓度/单位、反应体积/单位、读出方法。
无辅因子须显式写 `NONE`、0、`dimensionless`；缺失不是“相同”。
条件来自原批次，适配器不补值或覆盖；元数据齐全不等于实验满足模型假设。

只接收 C.1 `ESTIMATED` 且有有效 product_rate 和标定来源的记录。
信号斜率不能冒充绝对产物速率。浓度单位限 C.1 PRODUCT_UNITS，时间单位限 C.1 TIME_UNITS；
一个拟合内底物单位、速率单位必须逐字相同，不隐式换算。
保留标定公式、范围、空白模式。负斜率不取绝对值：负仪器斜率只能通过显式负标定系数
产生正产物速率；负产物速率拒绝。

至少四条速率、四种不同正底物浓度；零浓度/零速率作为真实数值保留，不能代替缺失。
负浓度、负产物速率、布尔值、缺失、非有限值拒绝整个集合，不静默跳行。
保留所有原始观测/空白、窗口决策、C.1 配置/QC/input_sha256/analysis_fingerprint
及源文件 SHA256。摘要不是实验真实性证明。

## 固定数值方法

SciPy `least_squares(method='trf', loss='linear')`，解析 Jacobian，无权重。
底物尺度取正浓度中位数，速率尺度取最大正速率。优化相对尺度参数的自然对数，
初值 Vmax=1.1×速率尺度、Km=底物尺度；无随机或多起点择优。
两个相对参数均限 `[1e-8, 1e8]`，这是数值运行边界，不是生物阈值。
`ftol=xtol=gtol=1e-12`、`max_nfev=5000`、`x_scale=1.0`。
按 analysis_id 排序计算，另保留调用输入顺序；记录依赖版本、初值、实际边界、
单位尺度、优化状态、次数与配置。这是酶学数值计算，不是 AI 模型训练。

残差=实测减拟合；SSE=残差平方和；RMSE=`sqrt(SSE/N)`；
R²=`1-SSE/SST`，只在 SST>0 时定义，可能为负。检查全部计算值有限。

## 预设诊断（不得按结果调节）

- 少于四条速率/四种正浓度：`NOT_ESTIMABLE`。
- 未收敛、非有限输出、距数值边界十倍以内：`NOT_ESTIMABLE`，不提供参数估计。
- 对数参数 Jacobian 奇异值条件数 >=1e6 或秩不足：`NOT_ESTIMABLE`；
  >=1e3 且 <1e6：有限制估计并警告。
- max(S)/Km<0.1 或 min(正 S)/Km>10：分别为仅很低/很高浓度，`NOT_ESTIMABLE`，
  即使 R² 很高。max(S)/Km<3、min(正 S)/Km>0.5 分别警告饱和/低浓度覆盖不足。
- max/min<10：范围窄；N<6：残差信息少；均警告。
- 零底物正速率、恒定速率、按浓度排序的平均速率下降、单点残差>3×RMSE
  均警告，不删点或自动替换模型。下降/残差提示不是机制诊断。

这些是保守工程诊断，不能代替实验设计、误差模型或参数区间。
高 R²、优化器 success 或良好 Jacobian 不单独证明模型/实验成立。
不传播 C.1/标定/空白/浓度误差；不输出显著性或变体优劣结论。

## 只读数据路径与范围

独立内核接收显式 C.1 快照；SQLite 适配只用 `mode=ro`、query_only 和读事务，
核对 v3 迁移摘要、来源字节 SHA256、原始行关联、标定原件和 C.1 确定性回放。
不自动打开默认用户数据库；不存在的库不创建。v1/v2 只报需先通过既有 C.1 升级，
不在此迁移。不新增 v4，不保存/覆盖拟合、原始观测或 C.1 结果。
本轮不操作真实用户数据库，不改 Desktop/安装包/冻结抗体科学/4.1.0rc2 发布状态。

## 验证与后续

仅合成：Km=20 uM、Vmax=5 uM/min，S=2/5/10/20/40/80/160，理论值由独立公式生成。
覆盖固定噪声、非等距、低/高/窄范围、重复、缺失/零、单位/条件冲突、失败与边界；
验证输入不变、摘要重复性、只读数据库和原 C.1/v1-v3 兼容。
SAFE_CI 仅无训练应用及既有只读完整性白名单，不跑历史全量 validation/训练/live。
SAFE_CI PASS 不等于历史全量训练测试均已通过。

C.2B 待独立审核：真实实验资格/化学计量、层级误差/权重/参数区间、WT/变体比较、
持久化 v4 schema/兼容性和 Desktop 集成。本轮不进入。

数值接口：[SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)。
局部线性协方差限制：[SciPy curve_fit](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)。
