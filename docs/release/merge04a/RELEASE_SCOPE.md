# BioResearch Workbench 预计发行范围

产品展示名：BioResearch Workbench。中文：生物科研决策支持工作台。当前窗口补充“抗体与蛋白质工程”范围，以保留既有中文界面合同。版本为 4.1.0rc2，仍是候选版。

GitHub 仓库 jie4578/antibody-risk-assessment、Python distribution antibody-risk 和既有 CLI/GUI 命令不改名。安装器 AppId、安装目录、EXE 基名 AntibodyResearchWorkbench 继续保留，以避免本轮引入身份/升级路径变化；安装器展示名和将来生成的 PE ProductName 使用新展示名。

## 预计产品边界

- 目标：Windows x64 桌面工作台。具体 Windows 版本支持以最终干净系统实测为准。
- 原六个抗体页面、蛋白质工程和科研工作流共八页保留。
- 复用原有科研计算；本轮不改变规则评分、C.1/C.2A/C.2B、冻结模型或 SQLite v3。
- 案例本地 JSON 可编辑，恢复先显示历史；当前来源必须显式接入、历史关联必须人工确认。
- 报告支持 Markdown；Desktop 安装增加 DOCX 依赖，缺少它时仍明确拒绝 DOCX 并保持 Markdown 可用。
- BioLab 和文献助手继续使用独立执行环境。主程序只读接入已有结果，不自动执行两者。
- MERGE-02A 自动 ELISA 执行保持冻结。不得把合成 MC 当成真实实验不确定性。
- 不内置模型权重、私人数据库、私人 PDF、公司序列、Provider 密钥或开发缓存。原仓库已有公开示例需在最终清单中单独审查，不宣称包内完全没有生物序列。
- 工具仅作科研决策支持，不宣传为临床诊断、临床定量或自动科学事实判定系统。

## 版本与验证

源码优先读取 pyproject.toml 的 4.1.0rc2；安装包模式使用实际 distribution metadata 回退；冻结模式读取捆绑 VERSION.txt。构建工具从源码版本生成 VERSION.txt、PE 版本和 Inno AppVersion，没有在本轮提升版本或创建 tag。

本地真实 Windows Qt 复演和 Word 渲染只证明源码环境。当前新增 DOCX CI 门槛、Actions 版本升级以及 Windows 新打包配置尚未在远端执行；本轮没有提交或推送。旧 main CI 的成功仅证明基线，不能转移为这些未提交文件的远端通过结论。

MERGE-04B 应完成新依赖环境、onedir/安装器、冻结科学与案例工作流、许可闭包、干净系统与签名/升级策略审查。公开发布须另行授权。
