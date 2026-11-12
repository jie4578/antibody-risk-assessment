# C.2B-1 极小似然比临界值：数值分辨率修复

日期：2026-11-12。修复基线：`9921d80872574d0fa699917dff40ed8b83edb169`。
仅处理数值资格与失败响应；统计模型、置信集合、原有容差和点估计规则不变。

## 1. 原始远端失败与 Windows 偶然通过

[原 CI run 43220253890](https://github.com/jie4578/antibody-risk-assessment/actions/runs/43220253890)
在五个 Linux jobs 中同样失败：
`test_unresolvable_confidence_cutoff_never_produces_zero_width_interval[1e-20]`
预期 NUMERICAL_FAILURE，实际 BOUNDARY_LIMITED。
Windows job 通过；这不证明该平台已有统一的数值资格保护。

修复前本机复现显示：Km 最终因 LR 根残差不合格而 NUMERICAL_FAILURE，
Vmax 仍为 BOUNDARY_LIMITED，总状态只因优先级取前者而通过旧测试。
Linux 的后续数值路径没有触发相同根错误，因此总状态不同。
本修复让不合格 cutoff 在任何参数 Profile 构造前统一拒绝，不依赖后续偶然失败。
旧测试及其断言完全保留。

## 2. 数学准则与浮点缺口

未知方差条件性 iid 正态模型仍使用 `D=N*log(SSE_profile/SSE_min)`，
方差 MLE 仍为 SSE/N；单参数临界值仍为 `c=chi2.ppf(confidence_level,1)`。
等价 SSE 比值为 `r=exp(c/N)`，不改为 F 阈值、已知方差准则或其他定义。

当 N=7、confidence_level=1e-20，c 约为 1.5707963267948978e-40，
`c/N` 约为 2.2439947525641397e-41，`expm1(c/N)` 仍为正，
但 float64 的 `exp(c/N)` 等于 1.0；1.0 的 ULP 约为 2.220446049250313e-16。
保留一个正的相对增量，不代表它能与已记录 SSE 相加后分辨，也不代表能验证一个 LR 根。

原 Profile 的 LR 计算仍为 `N*log1p(max(0,SSE_profile-SSE_min)/SSE_min)`。
log1p 保护了日志计算，却不能恢复在 SSE 减法前已丢失的信息。
域极限比较仍使用绝对 `limit_lr_tolerance=1e-8`；
根验收仍使用 `min(root_lr_tolerance,c*1e-6)`，其中绝对上限为 1e-6。
因此不能仅检查 c>0，亦不能误把根的绝对上限当成唯一有效容差。

## 3. 搜索前的必要数值资格

[mm_uncertainty.py](../../protein_engineering/mm_uncertainty.py) 新增私有函数
`_confidence_cutoff_resolution(c,N,B)`，B 是既有归一化 SSE_min。
它只评估可分辨性，不替换或抬高 B、c、N 或任何容差。

必须同时满足：

1. c 有限且为正；全部资格计算有限。
2. float64 中 `exp(c/N)>1` 且 `B*exp(c/N)>B`。
3. `c>limit_lr_tolerance`，使原域极限容差不把零 LR 与请求 cutoff 混为一谈。
4. 有效根容差 `t=min(root_lr_tolerance,c*1e-6)` 为正且小于 c。
5. t 不小于 SSE 在 B 及 B*exp(c/N) 两处各一 ULP 对应的 LR 步长最大值：
   `max(N*log1p(ulp(s)/s))`。

这些均为现有算法下的必要工程资格，不是新的统计显著性阈值，
也不是所有置信水平共享的一个固定下限。
通过资格不保证后续优化/求根成功；原根残差、搜索、开放域及可辨识性检查继续执行。
例如本机 confidence=1e-4 可通过此资格，却仍因实际根残差不合格安全失败。
不通过资格时，不启动任一参数 Profile：

- 总状态和 Km/Vmax 状态均为 NUMERICAL_FAILURE。
- 原因 `CONFIDENCE_CUTOFF_UNRESOLVABLE`；阶段 `CONFIDENCE_CUTOFF_QUALIFICATION`。
- 两个参数 lower/upper 均为 null，剖面为空，保留原点估计、单位、输入摘要、review 和配置。
- metadata 保存资格诊断；非有限诊断仅在明确失败的资格记录中隔离并注明检查失败。
- 完整响应仍经既有递归有限性、严格 JSON 和结果摘要生成。

零/近零残差的 VARIANCE_DEGENERATE 判定保持原行为，不人为加入噪声。
`_Profile.lr/at/side`、数值搜索与容差、ANALYSIS_VERSION、METHOD、ERROR_MODEL、
POLICY、C.1/C.2A/C.2B-2A、SQLite v3、抗体核心及冻结结果均不修改。
实现版本仍为 mm-profile-normal-1.0.1，本次源码差异由独立 Git 修复 checkpoint 标识。

## 4. 独立不回归与反例

原精确失败节点修复前在 Windows 为 1 passed；不把它伪称为本机 RED。
追加的预搜索拒绝/可分辨性反例修复前实际为 9 failed，证据保留。
新增正式反例覆盖 1e-300、1e-20、1e-10、1e-5、可表示却低于域极限容差的 cutoff、
有效根容差与 SSE ULP、0/NaN/Infinity 的 χ² 返回值、可分辨的小置信水平、
正常 95%、真正的开放参数域和弱可辨识、输入不变及严格 JSON。

独立比较修复前保存的 N=7 固定噪声默认 95% 完整结果对象，逐字段精确不变，
包括 result_sha256。保留的数值为：

| 参数 | 点估计 | 下界 | 上界 | 单位 |
|---|---|---|---|---|
| Km | 20.282195311350875 | 19.212125268315038 | 21.411176312254113 | uM |
| Vmax | 5.032750639672563 | 4.947044772475335 | 5.120523169542443 | uM/min |

该固定示例不是频率覆盖率证明，也不改变 N=7 的 Wilks 渐近近似局限。
原有全部测试的 AST 未改变；原 `_Profile`、严格 JSON/helpers 及 POLICY 的 AST 未改变。
最终测试记录在第 6 节补充。

## 5. 科学复核范围与环境限制

预搜索拒绝来自明确的表示与现有容差条件，不依赖 OS、BLAS 或优化器的后续偶然路径。
这解决原缺口，但不能代替新提交上的真实 Linux CI 验收。
本机 WSL 列表为空，未发现 Docker；未安装新 Linux 环境，未宣称 Linux 回归已通过。
后续必须另行授权推送，由 GitHub Actions 验证 Python 3.10/3.11/3.12 及 Linux/Windows。

仍只支持已明示的条件误差假设；不是完整实验误差传播，不改参数区间数学定义，
不训练 AI、不访问私人实验/历史密封数据、不调用真实 Provider、不迁移数据库。
实际命令、XML、修复前后诊断及工作树摘要保留于忽略的
`dist/protein-engineering/c2b1-cutoff-fix-20261112/`；正式测试不依赖这些证据文件。

## 6. 最终本地验收与审查结论

运行 Python 3.14.8、NumPy 2.5.4、SciPy 1.18.1，Windows 本地合成测试。
隔离 runner 原样读取受跟踪的 `.github/workflows/ci.yml` 安全护栏，
禁止 ML/TF-IDF 训练、外网 Provider 和真实数据/模型根读取。
focused 范围另保护手工工作簿和原临时目录；所有缓存/合成 SQLite 只写隔离 dist。

| 本轮真实验收范围 | 结果 |
|---|---|
| 原失败精确节点，修复后首先执行 | 1 passed |
| C.2B-1 全部测试 | 78 passed（原 62 项 + 新 16 项，原断言不变） |
| C.2A 回归 | 69 passed |
| C.1 数值/存储/Desktop | 71 passed |
| C.2B-2A 合成传播 | 87 passed |
| Protein Engineering 基础专项 | 42 passed |
| 上述合并专项 | 347 passed |
| SAFE_CI 应用范围 | 1097 passed, 1 skipped, 17 deselected, 18 warnings |
| Frozen Integrity | 15 passed |
| 默认 95% 完整结果与修复前逐字段比较 | 精确一致，含结果 SHA256 |
| 严格 JSON、非有限/极端尺度及全部输出有限性反例 | PASS |

所有范围的 SAFE_CI boundary violations 均为 0。
1 skipped 来自既有可选 langchain 缺失；18 warnings 为原 Gradio/Pandas 警告。
SAFE_CI PASS 不等于历史全量训练测试均已通过。
本轮没有重算密封研究评价，也没有重训模型或重新抽取 1024/4096 次 MC 验收结果。
合成传播正式 87 项已重新执行，既有传播内核字节和抽样规则未变。

SCIENCE_REVIEW: PASS_WITH_LIMITATIONS。
未知方差似然、单参数区间定义、原阈值/方差估计/搜索规则均未改变；
资格检查是确定性的必要数值门槛，不把未分辨性表述为统计不可辨识。
真实开放参数域、弱可辨识及原零残差拒绝继续通过原回归。
没有声称 Linux 回归通过、精确有限样本覆盖率或完整实验误差传播。

提交范围仅为 C.2B-1 内核、其正式测试和本数值说明。
CLI、工作簿、原临时目录、C.1/C.2A/C.2B-2A、SQLite schema 和冻结研究文件应继续通过摘要保护核查。
本轮只授权独立本地修复提交；不推送、不创建 tag/Release，不进入后续阶段。
