# Windows 产品交付准备记录（2026-11-07）

**当前决定：本地候选可供审查；NOT_READY_FOR_STABLE_RELEASE。**
版本保持 **4.1.0rc2**，目标稳定版 **4.1.0**。未创建 tag、Release 或上传安装包。
本报告记录本地准备阶段；其起点 HEAD 与远程 main 核对为
`c2b6d19133cecc4ec5b239093e539f6cc1e9f8f7`。用户随后授权了选择性源码提交/推送，
具体后续 checkpoint 与 CI 以 GitHub 的精确提交为准。旧 CI 不转移为新改动的结果。
历史 v4.0.0 标签和 Release 保持原样。

## 已实现的交付能力

- PyInstaller onedir + Inno Setup 6.7.4 基础安装器，捆绑 Python/Qt、numpy/pandas、
  openpyxl、Windows keyring 和 AI SDK，不要求终端用户运行 Python 或 pip。
- 当前用户安装、开始菜单/可选桌面快捷方式、固定 AppId、卸载入口的安装定义。
  这些定义已编译，不等于安装/卸载已通过验收。
- 冻结 exe 的缓存/错误类型记录使用用户目录，不写安装目录。配置 JSON 不保存 Key。
- 设置页增加静态 ML 部署检查、模型/缓存目录选择、独立可信 manifest 摘要输入。
  缺文件、缺依赖、缺缓存和摘要不匹配分别提示；来源不可信时拒绝加载。
- 选择配置后、实际推理前重新检查文件；模型目录改变清除旧 ML 证据，缓存位置
  在 HF 模块已加载后发生变化会要求重启。冻结推理模块、权重和表示没有修改。
- 基础 exe 不含 torch/transformers、模型和 ESM2 缓存。不能通过导入模型或在安装
  目录运行 pip 变成高级版；高级 ML 仍需单独验收的源码环境和合法可信文件。
- 新 Windows 用户指南、候选门槛、版本标题、GUI 启动入口和手动候选构建 workflow。
  CLI/Gradio 源码入口保留，未因基本 exe 排除高级依赖而删除原功能。

## 实际测试和范围

| 检查 | 本次结果 | 边界 |
|---|---|---|
| 基础应用源码回归 | **738 passed, 2 skipped, 7 deselected, 18 warnings** | 官方 CPython 3.14.8 独立验收 venv；排除历史 `test_ml.py`、`test_rag.py` 研发拟合测试；7 个 live 用例不运行 |
| 新部署检查与相关回归 | **41 passed** | 合成非 pickle 文件、信任/路径/篡改/缺依赖/旧结果失效，不反序列化 |
| validation 代码回归 | **185 passed, 3 warnings** | 测试夹具回归；含既有合成估计器夹具，不重建部署模型、不运行研究分析或重算性能 |
| 独立构建 venv `pip check` | PASS | 该打包环境，不代表所有可选 extras |
| 实际冻结 exe 离线 smoke | PASS | 六页、NNST 重叠位点、重复 ID 两条记录、XLSX 导出、规则突变、无 ML 启动、WinVaultKeyring/AI SDK 可导入 |
| 外部 Python 需求 | smoke 无需 | 子进程 PATH 仅保留 Windows 系统目录；不等于未装 Python 的干净 OS |
| 本机真实安装器运行 | **FAIL / 权限受限，已回滚** | 解包后，开始菜单目录和 HKCU 卸载注册项创建返回 Error 5；Setup exit 4 |
| 快捷方式/正常卸载/跨版本升级 | **NOT_PASSED / NOT_TESTED** | 桌面快捷方式曾创建后随回滚移除；不能把回滚当正常卸载认证 |
| 原生窗口检查 | PARTIAL | exe 窗口启动；UIA 读到候选标题、六页、ML 未安装提示；截图 FrameArrived 超时、点击 geometry unavailable；Alt+F4 后进程退出 |
| 干净 Win10/Win11 图形安装 | **NOT_PERFORMED** | 没有可用且获授权的干净 VM；不能以当前开发机/离屏替代 |
| 安装器候选工作流 | **NOT_RUN** | 仅定义；不因源码 CI 运行而自动成为构建/安装认证 |

保留 pandas 弃用警告、可选 LangChain 跳过和原生 `libpng iCCP` 警告。
原生控件读取不能证明字体/裁切或鼠标点击通过。新增文档图片由真实 Qt 控件离屏
导出，空配置、不读取凭据，已目视检查；不是原生截图或干净 OS 认证。

## 构建发现及修复

最初的许可证元数据转字符串遇到邮件头解析错误；改为保留原始 METADATA 文本。
首次冻结 exe 因 DLL 加载错误失败。构建 TOC 显示误收集宿主工具 PATH 下的旧
ucrt/API-set DLL；限制构建子进程 PATH 后重新构建，实际 exe smoke 通过。
没有修改系统 PATH、Anaconda、原 Python 安装或系统运行库。

编译器官方下载地址：
https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe
Authenticode 验证 Valid，发布者 Pyrsys B.V.。初次启动失败；给构建子进程独立
TEMP/TMP 后便携安装成功，没有注册为用户工具或改变系统 PATH。

构建目录为忽略的 `dist/windows_delivery/`；失败日志和早期候选不覆盖。
最终交付文件、字节数和 SHA256 以 **最终 build_manifest.json / SHA256SUMS.txt** 为准。
本地候选未签名，不能写成经过可信发布者签名的正式安装器。

本次最终候选为 `dist/windows_delivery/build-005/`：

- `AntibodyResearchWorkbench-4.1.0rc2-Windows-x64-Setup.exe`
- **57,633,844 bytes（54.96 MiB）**
- SHA256：`760aedfd60cc5cdd5b57a26d8558477f7f722da88bf9b7e9262913cc5c38f2a6`
- 独立目录约 181.59 MB、1,149 个文件；允许源码/资源快照 82 项与工作区逐项摘要一致。
- 最终 build-005 实际 exe smoke exit 0；build-004 的安装权限失败保留，不因新文档
  截图加入而推断安装权限问题已解决。两者基础运行代码一致。
- pyproject、窗口版本、exe ProductVersion、Setup ProductVersion 和安装文件名均为
  `4.1.0rc2`；没有把候选标为 Stable。

本地完整日志：`application-tests-final.log`、`deployment-tests-final.log`、
`validation-tests.log`、`acceptance-004/install.log`、`smoke-005/`、`visible-004/`。
路径均在忽略的 `dist/windows_delivery/` 下，对外分享前仍需审阅本机路径。

## 数据、隐私及许可核对

明确允许的源码快照不复制整个仓库，排除两份脏 CLI、私人文件、研究数据、
模型/manifest、NPZ、缓存/数据库和视频。PYZ 模块与 onedir 文件均作禁入项核对。
基础包仅带公开 `example_antibodies.csv`，不是实验验证集。
没有真实 Provider 请求、真实模型推断、模型重建、研究性能计算或新训练。

随包生成依赖版本清单、许可文件/元数据、CPython LICENSE、GNU LGPLv3/GPLv3
全文及 Qt/PyInstaller 来源链接。GPL 文本来自 Qt 官方仓库的通用 GPLv3 文本：
https://raw.githubusercontent.com/qt/qtbase/v6.10.2/LICENSES/GPL-3.0-only.txt
LGPL 全文来源：https://www.gnu.org/licenses/lgpl-3.0.txt
不使用的 Qt PDF、QML/Quick 和虚拟键盘插件不进入基础包。

**许可库存/全文收集通过，不等于公开分发的完整法律审核通过。** 发布前还需对
最终 Qt/原生第三方二进制逐项核对 attribution、归档精确对应源码和履行相应许可
义务；不能仅依赖 wheel 中一份商业许可提示或把整个安装包说成只有 MIT。
模型分发授权仍未授予；基础安装包不附任何模型。

## 对外介绍与科学保护

GitHub About 已按授权更新为 local-first PySide6 工作台；Topics 为 antibody、aidd、
developability、bioinformatics、pyside6、machine-learning、esm2、drug-discovery。
未修改仓库源代码远程 main 或公开发布安装器。

core.py、scoring.py、ml_inference 现有运行模块、agent、literature 科学/检索逻辑、
validation 协议与研究结果均未改。新部署检查位于 Desktop 层。
受保护的 cli.py、literature/cli.py、手工验收表和批量产物摘要与任务开始一致。

GDPa3 HIC 保留 rho=0.231901，95% CI [0.005418, 0.437591]，N=79；
不重算、不夸大，GDPa3 已观察，不能称 untouched test。内部 84/95 高相似性限制、
composite 的外部认证缺口和突变 ML 不等于实验效应的限制均保留。

## 下一道发布门槛

1. 在不受本会话文件/注册表权限限制的干净 Win10/Win11 x64 环境实际安装、
   原生点击六页和合成流程、验证快捷方式/正常卸载；未来真实版本升级单独验收。
2. 完成第三方原生组件 attribution/精确对应源码审核，决定签名与候选分发渠道。
3. 选择性审查本地代码/测试/文档，再经授权提交并运行精确提交对应的 CI。
4. 以上门槛和用户单独批准均满足后，才能升级正式版本、创建 tag/Release 和上传。

当前交付是**安装器与产品化源码准备**，不是“普通用户安装与正式发布全部验收通过”。

## 本轮文件范围（32 项；不包括保留的原有改动）

| 类别 | 新增或修改 |
|---|---|
| 构建/CI | `.github/workflows/windows-installer.yml`、`tools/build_windows.py`、`tools/test_windows_installer.ps1` |
| 安装定义 | `packaging/windows/launcher.py`、`workbench.spec`、`installer.iss`、`requirements-build.txt`、`licenses/GPL-3.0.txt`、`licenses/LGPL-3.0.txt`（后五项同属 packaging/windows） |
| Desktop 部署 | `desktop/ml_deployment.py`、`desktop/widgets/ml_deployment.py`、`desktop/ml_adapter.py`、`desktop/installation_smoke.py`、`desktop/version.py` |
| Desktop 接入 | `desktop/main_window.py`、`desktop/widgets/settings_page.py`、`desktop/widgets/single_analysis.py`、`desktop/widgets/mutation.py` |
| 回归 | `tests/test_desktop_ml_deployment.py` |
| 版本与收录 | `.gitignore`、`MANIFEST.in`、`pyproject.toml` |
| 用户与维护文档 | `README.md`、`ROADMAP.md`、`docs/INSTALL_WINDOWS.md`、`docs/WINDOWS_DELIVERY_ACCEPTANCE.md`、本报告、`docs/ML_DEPLOYMENT_CHECKLIST.md`、`docs/ML_MODEL_CARD.md`、`docs/RELEASE_NOTES_V4_1.md`、`docs/RELEASE_READINESS_2026-11-05.md` |
| 真实 Qt 导出图片 | `docs/images/windows/ml-deployment.png` |

31 份文本逐项扫描未发现实际 API Key、私钥头或硬编码用户主目录；图片另作目视
检查。安装包未签名和公开分发许可审核待完成的限制不因扫描通过而解除。
两份原有 CLI 修改与 `manual_acceptance.csv.xlsx` 未触碰，不属于后续选择性提交范围。

## 安装启动恢复补记（2026-11-07）

用户反馈双击 Setup 后出现商店窗口。重新核对最终 Setup SHA256 一致，`.exe`
关联为 exefile，打开命令为标准 `"%1" %*`，未修改关联或安全设置。商店弹窗本身
的原因仍未确认，不能仅凭截图归因为系统安装策略。

独立 TEMP 下的交互启动产生了新日志：创建默认目录
`%LOCALAPPDATA%\Programs\AntibodyResearchWorkbench` 被 Error 5 拒绝，安装失败并
回滚。这是本次重试中确认的阻塞，不是成功安装。日志位于忽略的
`dist/windows_delivery/open-recovery-20261107/`。

为使基础功能可用，将已经通过 smoke 的 build-005 onedir **原样**打包为
`dist/windows_delivery/AntibodyResearchWorkbench-4.1.0rc2-Windows-x64-Portable.zip`：
80,899,869 bytes，SHA256
`bfa030c7f35f88de9bc44abbb043384b17d3fb1db41d3f43178a5acfe0ed5e9e`。
ZIP CRC 检查通过，1149 个原文件与主 exe 保持不变，另附中文使用说明。
这是免安装备选，不创建快捷方式或卸载注册项，不代表安装门槛已解除。

完整解压后打开 `AntibodyResearchWorkbench/AntibodyResearchWorkbench.exe`，必须
保留 `_internal`；不能在 ZIP 内直接运行或只复制 exe。本次已直接启动该主程序，
通过原生 UIA 确认候选标题、六页和无 ML 提示，窗口留给用户使用。使用独立空配置，
没有读取现有 Key 或调用服务。干净 OS、签名、许可证和 CI 的待验收结论保持不变。
