# Phase C.2A — Michaelis–Menten 实现与验收

日期：2026-11-10。工作基线 HEAD/origin/main 均为
`6a1d1cb230734dc1b88c160631fe7392505e33c8`，main、索引为空。
原配置的 C: 仓库路径已失效；本轮在原仓库实际位置 `D:/Desktop-Archive/antibody_risk`
完成，不复制仓库。未提交、推送、建 tag、发布安装包或变更 4.1.0rc2 状态。

## 交付与协议审查

先建立 [拟合协议](PHASE_C2A_MM_PROTOCOL.md)，再实现内核和适配。
没有修改 C.1 算法/数据库 schema，也未新增 v4 或 Desktop UI。

| 新文件 | 实际能力 |
| --- | --- |
| `protein_engineering/mm_kinetics.py` | RateRecord、FitReview、输入摘要、C.1 只读内存回放、资格检查、确定性无权重 MM 拟合、诊断与独立结果 |
| `protein_engineering/mm_rate_adapter.py` | 显式 v3 SQLite 只读选择、迁移摘要/原件 SHA256/行关联/标定/身份与条件核对 |
| `tests/test_mm_kinetics.py` | 69 个合成数值、资格、失败、重复、来源与只读集成用例 |
| `docs/protein_engineering/PHASE_C2A_MM_PROTOCOL.md` | 模型、输入资格、固定数值策略、诊断门槛和科学边界 |
| 本文 | 实际实现、命令、验收与剩余工作 |

条件限制：同一变体、样品、批次、生物重复；技术重复逐条保留、等权参与。
不自动混合生物重复、选择最佳窗口/子集、丢异常点、补值或取负速率绝对值。
批次须显式为时间序列；批次条件必需字段不能缺失；观测自带条件不能与批次冲突。
所有输入 C.1 快照、窗口/配置/标定/QC/原件来源、原始重复 ID 均进入独立结果及输入摘要。

## 接口与只读约束

```python
from protein_engineering.mm_rate_adapter import load_rate_records
from protein_engineering.mm_kinetics import FitReview, input_digest, fit_michaelis_menten

# 仅示意 API；本轮测试实际只打开 pytest 临时合成数据库。
# 必须显式选择库和全部 analysis_id，不自动发现/读取用户默认数据库。
records = load_rate_records(explicit_existing_database, selected_analysis_ids)
review = FitReview(
    reviewer=explicit_reviewer,
    reviewed_at_utc=explicit_review_utc,
    rationale=explicit_review_rationale,
    input_sha256=input_digest(records),
    direction="PRODUCT_FORMATION",
    acknowledge_not_established=True,
)
result = fit_michaelis_menten(records, review)
```

拟合不会自动读取库、文件或联网。独立快照调用者提供来源，适配器调用才核验 SQLite 中
实际来源字节；两者都对 C.1 快照作内存确定性回放，不保存/覆盖 C.1。
SHA256 和回放检查保证一致性，不证明仪器标定真实可靠或实验已具初始速率条件。

适配使用 `mode=ro`、query_only 和读事务，不实例化会迁移的 ProteinStore。
不存在的库不创建，v1/v2 拒绝并说明需通过既有 C.1 流程升级；本接口不迁移。
有 journal/WAL/SHM 边车时拒绝，要求先关闭并完成数据库 checkpoint；不做恢复或清理。
只读取所选结果及其依赖，不操作真实用户数据库，不增加持久化拟合表。
遗留 v1/v2→v3 升级仍由未改动的原 C.1 存储代码负责，专项回归验证兼容。

## 数值方法与结果含义

经典 `v=Vmax*S/(Km+S)`；SciPy least_squares 的 TRF，解析 Jacobian，linear loss，
无权重、无随机初始化。浓度中位数/最大正速率缩放；对数参数保证正值；
相对数值边界 `[1e-8,1e8]`，初值、容差和最大次数依照已写入协议固定。
记录算法版本 `mm-unweighted-1.0.0`、实际初值/边界/尺度、SciPy/NumPy 版本、
优化器状态/次数/optimality、实测/拟合值、残差、SSE、RMSE、数学上有定义的 R²。
数值边界不是生物阈值，没有调规则或模型。

状态只有 `FIT_WITH_LIMITATIONS` 或 `NOT_ESTIMABLE`；失败不输出参数。
即使有审阅，initial_rate_validity 和 experimental_validation 仍为 `NOT_ESTABLISHED`。
不存在“点击确认即实验有效”或“R² 高即参数可信”的状态。

| 合成场景 | N | Km (uM) | Vmax (uM/min) | SSE | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| 标准无噪声，S=2/5/10/20/40/80/160 | 7 | 20.000000000000004 | 5.000000000000009 | 1.06450e-28 | FIT_WITH_LIMITATIONS |
| 固定噪声 +0.01/-0.03/+0.02/-0.04/+0.06/-0.02/+0.03 | 7 | 20.282195311350875 | 5.032750639672563 | 0.007097842490158724 | FIT_WITH_LIMITATIONS |
| 仅低浓度 0.001/0.002/0.005/0.01/0.02/0.06 | 6 | 不提供 | 不提供 | 1.06682e-28 | NOT_ESTIMABLE，R²=1 仍拒绝 |
| 仅高浓度 2000/4000/8000/16000/32000/80000 | 6 | 不提供 | 不提供 | 8.92438e-27 | NOT_ESTIMABLE，R²=1 仍拒绝 |
| 窄范围 20–20.05 | 6 | 约 20 | 约 5 | 3.47099e-29 | 有限估计，保留窄范围/饱和/低浓度覆盖警告 |

无噪声理论率由测试独立公式生成，参数断言 Km 相对误差 1e-9、Vmax 1e-10。
噪声预期通过独立方法核对：给定 Km 时解析消去 Vmax，再用一维 bounded minimizer
求解；不复用内核预测函数或解析 Jacobian。噪声 RMSE=0.031843013340356205，
R²=0.9994942121816869。这是合成计算正确性检验，不是模型预测性能或生物学验证。

诊断包括：数量/浓度种类不足、原始观测复用、重复身份不清、不同条件/单位、
信号无产物标定、负值/缺失/非有限输入、无正速率、优化失败、边界、
Jacobian 奇异/病态、低/高/窄浓度覆盖、常量速率、非单调/零底物正速率、大残差。
每次保留所有技术重复与不良点；失败测试模拟优化器异常/未收敛/非有限输出/边界/奇异值。
低、高浓度示例均显式由 `EXTREME_COVERAGE` 拒绝，不利用 R² 放宽资格。

## 实际本地验收

环境：Windows、Python 3.14.8、NumPy 2.5.4、SciPy 1.18.1。
本轮未运行远程 CI 或其他 Python 版本；不把既有基线 CI 当作新文件的远程验收。

安全 harness：`dist/protein-engineering/c2a/run_safe.py`（忽略的本地工具）重放当前
`.github/workflows/ci.yml` 中的原始 safe_ci_runner，确认与既有本地 runner 一致。
专项只用相同 runner 的保护前缀再调用 pytest；完整 application/integrity 使用原 runner。
隔离 APPDATA/LOCALAPPDATA 与 pytest basetemp，阻止 sklearn/TF-IDF fit、外网和冻结私有数据路径。
SciPy 的本阶段酶学最小二乘是明确授权的数值计算，不是 ML 训练。

以下命令均使用 `dist/4.1.0rc2/venv-build/Scripts/python.exe`，
`PYTHONIOENCODING=utf-8`，每次不同 `C2A_RUN_ID` 指向忽略的独立临时目录。

```powershell
# C2A_RUN_ID=numeric-03；未设置 SAFE_CI_SCOPE，使用安全保护前缀。
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_mm_kinetics.py
# 69 passed in 1.35s

# C2A_RUN_ID=protein-01；同样使用保护前缀。
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py tests/test_protein_engineering.py tests/test_protein_initial_rate.py tests/test_protein_rate_storage.py tests/test_desktop_protein_engineering.py tests/test_desktop_protein_initial_rate.py tests/test_installed_package.py tests/test_windows_delivery.py
# 135 passed in 4.59s

$env:SAFE_CI_SCOPE='application'
$env:SAFE_CI_COLLECT_ONLY='0'
$env:C2A_RUN_ID='application-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py
# 932 passed, 1 skipped, 17 deselected, 18 warnings in 11.04s

$env:SAFE_CI_SCOPE='integrity'
$env:C2A_RUN_ID='integrity-01'
& dist/4.1.0rc2/venv-build/Scripts/python.exe dist/protein-engineering/c2a/run_safe.py
# 15 passed in 1.03s

git diff --check
```

全部安全边界违规计数为 0。135 项属于完整应用范围的子集，不累加宣称额外覆盖。
跳过：未安装 LangChain 的适配用例。17 个取消选择包括 live 和显式训练节点。
18 个 warnings 来自既有 Gradio 上传提示与 pandas 弃用/类型兼容提示，无失败。
完整应用自动收集新增 C.2A 文件，未改 CI 或删改历史断言。
15 项为原 workflow 的只读/合成完整性白名单，并非全量 validation 运行。
SAFE_CI PASS 不等于历史全量训练测试均已通过。

未运行：训练/部署模型构建、历史 TEST 重评估、真实 Provider、网络、私有实验数据。
只读检查及本轮 source diff 保护抗体核心、冻结 ESM/ML、AIntibody/GDPa3 与 Phase 5。

## 局限与 C.2B 前置审核

1. 目前是独立 Python API；Desktop 仍为 C.1，没有拟合界面或保存入口。
2. 没有真实实验资格认证、初始速率条件验证、底物/产物化学计量或校准真实性检验。
3. 无权重，未传播 C.1/标定/空白/底物浓度误差；没有完整参数区间或层级重复模型。
4. 浓度覆盖/Jacobian 门槛是保守工程诊断，不是完整统计可辨识性证明。
5. 无 WT/变体优劣统计、kcat、多底物/协同/抑制自动解释、AI 模型或新预测任务。
6. 若下一阶段持久化，应先另行审核 SQLite v4 schema、迁移兼容和不可覆盖策略；
   本轮只保留 v3，不设计或执行新迁移。

本轮仅新增上述五个文件；原 cli.py、literature/cli.py、manual_acceptance.csv.xlsx、
pytest-of-Administrator/ 保留。安全测试日志和合成数值摘要只在忽略的 dist 下。
停止于 C.2A 本地交付，等待后续审核。
