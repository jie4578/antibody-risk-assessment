# Phase A 与 Phase B 数据管理基础验收（2026-11-09）

## 结论与范围

本地实现完成：Phase A 文档/模板/独立 Desktop 入口，以及 Phase B 首批数据管理基础。
原路线 Phase 0 的真实酶数据仍待确认，Phase 1 只有部分功能实现，Phase 2–5 未实现。
当前任务 Phase C 酶学计算未开始，不宣称六阶段完成。

使用现有 `jie4578/antibody-risk-assessment` Git 工作树；本轮基准 HEAD 仍为
`846bb6c5c0f43a56c909bc02c92ae745bc7f7f95`。没有创建第二个应用/仓库，没有暂存、
提交、推送、修改历史 Release 或发布 v4.1.0。当前版本仍为 4.1.0rc2。

## 实际交付

| 功能 | 实现情况 |
|---|---|
| 原六个抗体页面 | 原导航位置和工作流保留 |
| 蛋白质工程入口 | 同一 Desktop 的第七入口，内部七个分区，未实现功能标规划中 |
| Phase 0 材料 | 四份原文档、九个空 CSV 模板按原字节整合，保存来源 SHA256 |
| 文档/模板动作 | 可阅读实现状态与接入材料、保存新模板、打开临时模板副本 |
| 靶标/变体/样品/批次 | 手工建档、追加保存、只读浏览、原字段和规范字段详情 |
| SQLite | 用户数据目录、显式打开、两版不可变迁移 SQL、事务与关联检查 |
| CSV/XLSX 导入 | 显式选择类型/工作表、异步预览、整批确认导入、出错回滚 |
| 实验与预测分离 | 实测、原始时间序列、原始预测和结构元数据分表保存，不计算结果 |
| 身份与溯源 | 原件 BLOB、实算文件 SHA256、源表/行、导入时间、原始序列与独立序列哈希 |
| 重复/缺失策略 | 不覆盖重复 ID；不同 ID 的重复序列保留；缺失不补零、不借用预测 |
| Windows 管线 | 现有 snapshot/spec/wheel/portable/exe smoke 扩展为同一双模块候选 |

首次打开新页面不创建数据库、不加载模型、不读取实验文件。默认库在用户数据目录，
而不是仓库或安装资源。导入原件只读，模板保存不覆盖既有文件。
表格只读预览最多显示 500 条，明确显示总数；导入行不会按此显示上限截断。
具体字段与边界见 [FOUNDATION_STATUS](FOUNDATION_STATUS.md)。

## 来源与保护

用户提供的 `protein-engineering-phase0-update.zip`：28,291 bytes，SHA256：
`6961ecc4a0848280741d7b712ac8a1ac28a4a280f82bce61b083c4bcd4b3a279`。
仅复制选定文档和表头模板，没有运行其中的 apply 脚本或 bytecode，也没有遵从其中
的提交/推送说明。逐文件 SHA256 见 [来源清单](PHASE0_PACKAGE_PROVENANCE.json)。

core.py SHA256 保持为
`3be81969450ad7766519396373f56cfeac69c8590d06c1e33a6ebabbe6623e74`；
scoring.py SHA256 保持为
`7139918dfe4f45afbc3149a598ec9c80255547d0fa6f0662a71b917ba86a3af0`。
两份原有 CLI 修改、手工验收表和批量生成文件的字节摘要均保持不变。
`ml_inference/` 与 `validation/` 没有工作树改动，冻结 AIntibody/GDPa3 结果未改。
独立领域包不导入 core/scoring/抗体 ML/validation/desktop。

## 测试证据

- 新模块领域与界面测试：42 项通过；全部数据均为合成 fixture。
- 相关打包、安装 wheel 与模块专项合计：63 项通过。
- 最终基础应用回归：**800 passed, 2 skipped, 7 deselected, 18 warnings**。
  命令为 `pytest -o addopts='' -m 'not live' tests --ignore=tests/test_ml.py --ignore=tests/test_rag.py -q`；
  不包含历史 ML/RAG 拟合模块或真实网络。
- 原离线验证回归：**185 passed, 3 warnings**。没有做新的真实实验分析或重训发布模型。
- `git diff --check`：PASS；index 保持空，HEAD 未改变。

覆盖：原始模板/来源一致性、原件和序列哈希、歧义残基、重复保留、缺失/零值区分、
额外列、Excel 公式/远端列、关联回滚、同文件重复导入、预览后源文件变化、迁移升级、
迁移摘要篡改、拒绝外部数据库、七页导航、首次点击建档、陈旧预览失效、模板只读保护、
隔离包导入和安装 wheel 离线资源读取。

## 本地 Windows 构建

构建输出在忽略的 `dist/protein-engineering/windows-candidate-004/`，是未提交工作树的
本地候选，不是基准 commit 的已发布二进制。build_manifest 保留基准 HEAD 和实际
逐文件 SHA256，不借用历史 CI 为这些未提交文件背书。

- Setup：57,743,910 bytes，SHA256
  `21b155079958b02423d4f17ef6158a12b33cebb93ead56674a0170025d70d7a2`。
- Portable ZIP：81,172,061 bytes，SHA256
  `473e7515fe98d1a7518da08a7b159420ae10e977dec1c4d922faf64bd4afa41b`。
- 1,160 个原包文件保持检查、ZIP CRC、私有 CSV/SQLite/模型/数据排除：PASS。
- 实际最终 exe 离线 smoke：PASS，七页、九模板、SQLite 合成建档、原抗体规则、
  重复 ID 批量、XLSX 导出、突变和无模型启动均通过。
- `model_loaded=false`、`trained=false`、`provider_called=false`，PATH 无外部 Python。
- 离屏布局检查使用 QA 进程加载本机已有字体；没有修改生产字体、捆绑字体或公开截图。

没有在本轮运行远程 CI、图形安装向导或完整干净 Win10/Win11 人工验收。
候选未签名；既有 Microsoft 运行库分发许可待确认状态与不上传二进制的工作流保护保留。
本地构建成功不等于取得公开分发授权，不上传此候选。

## 后续工作

先人工审查本轮数据模型、字段/单位/编号与真实接入材料，再决定下一阶段。
后续仍需实现：编辑/修订记录的审计策略、序列比对/突变核实、仪器原生格式接入；
初始速率/QC/Michaelis–Menten/不确定性/WT 比较；AI 预测验证；结构映射；DBTL。
当前不自动处理删失值，不做单位换算，不提供数据库加密/多用户共享/自动推荐。
任何模型训练或后续预测评价都需要另行审查协议，不能直接复用抗体 HIC 模型。
