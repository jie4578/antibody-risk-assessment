# Phase B.1 / C.1 本轮交付记录

日期：2026-11-09。结论：限定范围实现与离线合成验收通过，停止于 C.1。
没有宣称实际酶实验验证通过，也没有进入 C.2。

## 1. B.1 审计结果

见 [科学数据审计](PHASE_B1_DATA_AUDIT.md)。无 P0；修复 3 类 P1：
原始记录层不可改写保护、空白/报告校正值与文本单位校验、明确 WT 角色与批次跨靶标关联。
3 类 P2 已处理：可核验导出、分析重复分组、旧版本迁移 fixture。
没有静默改变已存实验值、标签、单位或历史迁移，没有重设计整个数据库。

## 2. 数据库兼容性

schema v3 为增量迁移，新增 `initial_rate_analyses`、`initial_rate_inputs` 与不可覆盖触发器。
合成 v1 和 v2 数据库均可升级到 v3，原记录/来源 BLOB 保持、FK 检查通过；重复打开幂等。
v1 迁移 SHA256：`694be3e1ffbbdc66550047689601b9fe4b700e31213c14ef13fb9b57ba9afc4c`。
v2 迁移 SHA256：`8e875c47d5ad0630553656365df4974ececf3aa6de7a7a1e8956bc49c6439e40`。
没有打开或升级任何真实用户数据库。外部数据库、未来版本、历史摘要不符会拒绝。

## 3. C.1 实现

独立领域计算 `protein_engineering.initial_rate`，版本 `initial-rate-1.0.0`。
输入保留批次、样品、底物/单位、观测、时间/信号单位、两层重复、来源文件 ID/SHA256。
支持明确时间窗口、三种空白策略、带理由排除与显式缺失策略、OLS 斜率/截距/残差/
R²/RMSE/N/条件标准误、QC、完整输入决策和确定性指纹。
充分标定时可换算产物浓度速率，无标定仅报告信号/时间。
不足、错单位、终点、重复 ID 等返回 NOT_ESTIMABLE 及明确原因。
不自动选窗口，不因差拟合删点，不造测量值，不调用 AI/LLM。

## 4. 数值测试

仅用合成 fixture，解析预期独立核对：

| 场景 | 核验 |
|---|---|
| `y=20+2t` / `20−2t` / 常数 | 斜率 +2/−2/0，截距 20，零残差；常数 R² 缺失 |
| 不规则时间点 + 空白漂移 | 原 y=5+5t，扣除显式 3t 空白后斜率 2 |
| 匹配空白 | 精确同时间扣除，原件 ID/SHA 留存；不插值/平均 |
| `signal=2 product+5` | 原 5+2t 转换产物速率 1 uM/min |
| 显式负标定系数 | 不改信号负斜率；只按报告公式转换产物 |
| 缺失与零 | None 不补零；0 保留；默认失败或按明确策略排除 |
| 重复/点不足 | 同 ID 拒绝；不同 ID 同时间保留；少于 3 不同时间点拒绝 |
| 抛物线 `y=t²,t=0..4` | 斜率 4，残差 [2,−1,−2,−1,2]，斜率 SE=√(14/30)，曲率/低线性警示但不删点 |
| 错单位/无效标定/范围外 | 不猜单位或标定，不外推；数值型 Excel 单位被拒绝 |
| 重复身份/来源 | 分离生物/技术/孔位/底物上下文，来源字节/哈希与保存结果可核验 |

本轮新数值测试 **45 passed**，新 SQLite 集成测试 **18 passed**，新 C.1 Desktop 测试 **8 passed**。
这些测试包含在下方专项与应用回归内，不应把重复运行数量相加视为不同测试总数。

## 5. 科学限制

线性与高 R² 不证明真正初始速率、底物未消耗、信号校准有效或反应机制成立。
始终标记 `initial_rate_validity=NOT_ESTABLISHED`；必须人工/实验核实实验条件。
标准误仅为条件 OLS，不传播空白/标定误差，不建模时间相关性或重复层级。
未知单位不转换，无真实标定不计算产物速率；不输出 kcat、U/mg 或通用酶活预测。
非线性启发式只警示，没有警示也不证明有效。真实数据/协议确认尚未完成。
详见 [C.1 方法与使用说明](PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md)。

## 6. Desktop / 打包验收

同一 Desktop 第七入口→“酶学分析（C.1）”；原六页位置与流程保留。
可选择/检查原始时间序列、明确确认身份/区间/空白、异步计算、查看诊断、显式保存、
只读读取旧派生结果。更改输入使旧结果失效。后台运行时定时器仍响应，配置锁定。
Michaelis–Menten、AI 预测验证、结构映射、DBTL 仍标注规划中。

最终本地候选：`dist/protein-engineering/windows-candidate-006/`。
原 Windows 管线同一 exe/Setup，版本仍 4.1.0rc2；含16项文档/来源/模板资源。
安装外 wheel 导入、资源读取、拒绝私有快照/SQLite/CSV/模型入包测试通过。

- Setup：57,786,305 bytes，SHA256
  `272cb7ee4d07c04b878acb678adecad205e049c2447c12b9ff1fefbe0e5f545c`。
- Portable ZIP：81,214,515 bytes，SHA256
  `c767bef29d83b1f215b7493f49f6914e4dbb3d38b286e94696dfe24d77430cba`。
- ZIP CRC、全部原包文件 SHA256、私有文件排除通过；包1161文件/182589260 bytes。
- 最终 exe 离线 smoke：7页、9模板、C.1 合成斜率/独立保存，以及原抗体规则、批量重复 ID、
  XLSX 和突变均 PASS。`model_loaded=false`、`trained=false`、`provider_called=false`。
  PATH 仅系统 Windows 目录，未依赖外部 Python 启动。
- Qt 中文离屏布局检查通过，只在 QA 进程加载本机已有字体，不改生产字体或公开截图。

这不是干净 Win10/Win11、图形安装/卸载或人工验收。没有远程 CI、签名、发布或上传。
既有分发许可待确认状态与默认不上传二进制保护保持。
候选来自未提交工作树；build_manifest 记基准 HEAD 与实际源文件 SHA，不把旧提交 CI 当本轮验证。

## 7. 本轮文件范围

新增：

- `protein_engineering/initial_rate.py`、`protein_engineering/rate_storage.py`
- `desktop/widgets/protein_initial_rate.py`
- `tests/test_protein_initial_rate.py`、`tests/test_protein_rate_storage.py`、`tests/test_desktop_protein_initial_rate.py`
- `docs/protein_engineering/PHASE_B1_DATA_AUDIT.md`、`PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md`、本交付记录
- `protein_engineering/resources/phase0/PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md`

在既有 A/B 本地文件上继续修改：

- `protein_engineering/__init__.py`、`migrations.py`、`schema.py`、`storage.py`、`resources.py`
- `desktop/widgets/protein_engineering.py`、`desktop/installation_smoke.py`
- `tests/test_protein_engineering.py`、`test_desktop_protein_engineering.py`、`test_installed_package.py`、`test_windows_delivery.py`
- `.gitignore`、`README.md`、`ROADMAP.md`、`pyproject.toml`、`tools/build_windows.py`、`tools/make_windows_portable.py`
- `docs/protein_engineering/FOUNDATION_STATUS.md` 及相同字节的运行时副本

此前 A/B 的 `MANIFEST.in`、`desktop/main_window.py`、spec、导航测试等本地改动继续保留。
原始 Phase 0 四文档/九模板及其来源清单不改，源 ZIP 不改，不执行其中脚本。

## 8. 最终回归

环境：CPython **3.14.8**、PySide6 **6.12.0**，现有隔离环境，未安装新依赖。

| 范围 | 实际结果 |
|---|---|
| A/B + 新数值/SQLite/UI + wheel/Windows 打包专项 | **135 passed in 4.28s** |
| 安全应用回归 | **872 passed, 2 skipped, 7 deselected, 18 warnings in 10.41s** |
| 只读冻结完整性 | **17 passed in 1.07s** |
| `git diff --check` | PASS |

专项文件为上列新测试及 `tests/test_protein_engineering.py`、`test_desktop_protein_engineering.py`、
`test_installed_package.py`、`test_windows_delivery.py`。

安全应用命令：

```text
python -m pytest -o addopts='' -m 'not live' tests --ignore=tests/test_ml.py --ignore=tests/test_rag.py -q
```

两项跳过为 `test_agent.py` 的可选 LangChain adapter 用例；本环境未安装 LangChain。
7项 live 用例未选；18 warnings 是原 Gradio 用户提示与 pandas API/dtype 警示，未调整既有代码。
`test_ml.py` 和 `test_rag.py` 整体排除，避免训练/TF-IDF fit 路径。

本轮**没有运行完整历史验证套件**，因为其中 runtime/build/model-selection 用例会训练模型。
只运行下面的无重训检查：

```text
validation/tests/test_external_preregistration.py
validation/tests/test_phase5e_summary.py
validation/tests/test_phase8_documentation.py
validation/tests/test_ml_inference_runtime.py::test_builder_does_not_reference_or_load_sealed_test_labels
validation/tests/test_ml_inference_runtime.py::test_no_external_provider_and_cpu_fallback_in_runtime_source
validation/tests/test_ml_inference_runtime.py::test_core_and_scoring_are_not_modified
```

这些只读既有协议/汇总/摘要与源码，不打开 AIntibody 密封 TEST 标签、不重算性能。
没有加载/拟合 AI 模型，也没有重跑 GDPa3/AIntibody 实验评价。

## 9. Git / 科学边界

工作树位于 `D:/Desktop-Archive/antibody_risk`，仍是原仓库。
分支 main，HEAD 与**本地跟踪引用** origin/main 均保持
`846bb6c5c0f43a56c909bc02c92ae745bc7f7f95`；本轮没有刷新远程状态或执行 Git 写操作。
index 空，没有暂存、commit、amend、reset、clean、stash、rebase、tag、push、Release。

`core.py` SHA256：`3be81969450ad7766519396373f56cfeac69c8590d06c1e33a6ebabbe6623e74`。
`scoring.py` SHA256：`7139918dfe4f45afbc3149a598ec9c80255547d0fa6f0662a71b917ba86a3af0`。
两份 CLI 本地改动和原批量文件的字节摘要保持，ml_inference/ml/validation 没有改动。

交付末尾的短状态如下（目录按 Git 默认聚合，包含之前的未提交改动）：

```text
 M .gitignore
 M MANIFEST.in
 M README.md
 M ROADMAP.md
 M cli.py
 M desktop/installation_smoke.py
 M desktop/main_window.py
 M literature/cli.py
 M packaging/windows/workbench.spec
 M pyproject.toml
 M tests/test_desktop_chinese.py
 M tests/test_desktop_phase1.py
 M tests/test_installed_package.py
 M tests/test_windows_delivery.py
 M tools/build_windows.py
 M tools/make_windows_portable.py
?? desktop/widgets/protein_engineering.py
?? desktop/widgets/protein_initial_rate.py
?? docs/PROTEIN_ENGINEERING_ROADMAP.md
?? docs/protein_engineering/
?? manual_acceptance.csv.xlsx
?? protein_engineering/
?? pytest-of-Administrator/
?? tests/test_desktop_protein_engineering.py
?? tests/test_desktop_protein_initial_rate.py
?? tests/test_protein_engineering.py
?? tests/test_protein_initial_rate.py
?? tests/test_protein_rate_storage.py
```

## 10. C.2 尚需事项

先由科学人员审查真实数据、标定来源、重复设计、初始条件与单位，再另行确定
Michaelis–Menten 非线性拟合协议、可识别性/边界、完整不确定性、WT/变体统计比较，
以及需要可靠活性酶浓度的 kcat。仪器原生格式、完整编辑/修订策略也尚未实现。
本轮到此停止，不进行 C.2、AI 预测验证、结构映射、DBTL 或模型训练。
