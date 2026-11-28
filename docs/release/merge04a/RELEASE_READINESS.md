# MERGE-04A 发布准备验收

日期：2026-11-27。源码基线 1aeed020546f86aee1f83942220d423175028b6e，独立分支 codex/merge-04a-release-readiness。

MERGE_04A_STATUS：PASS_WITH_LIMITATIONS。应用层补齐、兼容性优化和发布准备已实现，本轮没有正式构建或发布，尚不能将 Windows 冻结包或公开分发标为 READY。

## 基线和隔离

已独立通过 GitHub API 核对 main SHA；合并后 Run 45841750160 的六项常规作业全部 SUCCESS，Training／Live 跳过，run.head_sha 与基线一致。新 worktree 从该提交创建，没有从 MERGE-02A 的实验状态派生。

原主工作区和 MERGE-02A、02B、03A、03B、03C 及原 AB-RD-DEMO-001 受保护。实际本地证据位于 dist/integration/merge04a-20261127-001，日志、案例、截图和 wheels 都不进入源码交付清单。

## 实际实现

### DOCX 依赖与不可跳过门槛

desktop/all 声明 python-docx>=1.2.0,<2；基础依赖和 requirements.txt 不变。构建版本固定 python-docx 1.2.0、lxml 6.1.3。官方 python-docx 1.2.0 支持 Python >=3.9，使用 py3-none-any wheel，lxml 的目标 CPython 3.14 Windows x64 wheel 已按官方元数据 SHA256 核对。这不等于目标原生包已安装或冻结 ABI 已验收。

tools/check_docx_support.py 检查默认模板、中文生成/可靠解析、资源摘要、原生 libxml/libxslt 编译版本和无外部关系。现有缺少 DOCX 时明确错误且 Markdown 可用的行为与原测试不变。

Ubuntu/Windows Desktop 增加独立 SAFE_CI_SCOPE=docx 步骤，原 6 个报告测试必须被收集、执行且不能跳过。skip 或数量不足会阻断该步骤；没有删除 importorskip，没有修改原科学断言。既有 application/integrity/optional-compatibility 的目标及其科学边界保持相同，新增门槛已在本地实际执行 6 passed、0 skipped。

### 保存与文献标题

新文件仍使用硬链接原子发布，不引入不安全兼容回退。已给不支持硬链接的错误增加明确提示和错误码；权限/磁盘满保持原类别。真实 NTFS 锁定保存失败后，旧字节和未保存状态保持。FAT/exFAT/网络盘没有真实验收，见 FILESYSTEM_COMPATIBILITY.md。

完整标题通过安全转义的 Qt 悬停提示及原详情页中的完整纯文本呈现，没有新增占用阅读区高度的控件。恶意 HTML 类文本仍为字面内容。实际 1280×720、1920×1080 窗口均完成原合成批次两文献选择、完整标题/tooltip 和引文首行可见性检查。

### Actions、产品与打包准备

官方维护版本核对后，将 checkout 调整为 v7.0.1、setup-python 调整为 v7.1.0；两者声明 Node 24。基线真实 runner 为 2.338.2，满足官方相应最低 runner 条件。保留触发器、contents:read、Python/OS 矩阵与 Training/Live opt-in 条件，不新增自动上传或发布。两个 workflow 的既有 artifact 条件不变，手动流程原 upload-artifact 版本本轮未盲目调整。

这些改动尚未提交/推送，不能声称新 Actions 已通过远程 CI或 Node 警告已经在远端消失。旧实际警告日志已保存；基线警告指出 checkout@v4、setup-python@v5 仍声明 Node 20。官方参考：[checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1)、[setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0)。

产品展示使用 BioResearch Workbench／生物科研决策支持工作台，并在主窗口保留“抗体与蛋白质工程”范围以维持旧中文界面合同。版本不变，为 4.1.0rc2。仓库、Python 包、内部应用数据路径、安装器 AppId 和 EXE 基名保持；实际安装/升级仍待新包验收。

spec 按有记录的两项历史 SciPy 改动逐项迁移，新增 DOCX 模板、lxml 模块和 metadata 收集，排除不用的 isoschematron。preflight 增加严格解释器/版本/native/template/来源文件检查，支持只检查、不构建。旧 3.14.8 构建环境仍缺少新增两包，实际返回 NOT_READY；未安装依赖或改写旧 venv。详情见 PACKAGING_READINESS.md。

## 本轮实际测试

套件有覆盖重叠，不能累加。

| 范围 | 实际结果 |
| --- | --- |
| 新增定向与案例、布局、Windows 打包回归 | 165 passed |
| 新增 MERGE-04A 正式用例 | 20 passed，包含于上行及 SAFE_CI |
| 原 6 项 DOCX 门槛 | 6 passed，0 skipped，gate 6/6 |
| 最终 SAFE_CI | 1550 passed，17 deselected，5 warnings，0 skipped |
| Frozen Integrity | 15 passed |
| 安全边界违规 | 各执行范围均为 0 |
| 真实 Windows 保存—退出—重启—恢复 | 两个独立进程完成，见下节 |
| Word 16.0 只读渲染 | 9 页，逐页核对 |
| git diff --check 及新增文件直接格式检查 | 见最终 verification.json |

最终 SAFE_CI 为 safe-ci-delivery.log/xml；它在最后的源码/测试改动后执行。此前 safe-ci.log 记录 1 failed、1545 passed、4 skipped，唯一失败是旧窗口标题合同要求“抗体”。没有修改旧断言；标题补充范围后最终通过。非提权环境的 4 个 symlink 跳过记录保留，最终具备权限的 Windows SAFE_CI 实际执行这些用例，无跳过。safe-ci-final.log 的 1550 passed 为中间通过记录；以 delivery 版本作为最后验收。

新增测试还实际验证 CI gate 对 skip 和缺失收集的拒绝，构建 preflight 的缺失依赖错误和无构建行为。模拟固定解释器/版本的成功测试明确为 mocks，不等于真实 3.14 新环境已准备完成。未运行训练、真实 Provider、历史密封评价或外部分析引擎。

## 实际桌面与报告

复用原 AB-RD-DEMO-001 合成材料，原件未更改。最终代码复演：

- PID 20908：实际序列计算、BioLab 只读导入、文献批次阅读、仅同属案例关联，保存含中文/自定义限制的案例并完全退出。
- PID 21336：独立启动恢复历史；当前来源/关联不自动恢复；显式重接三来源，匹配后人工再确认，保存并导出 Markdown/DOCX。
- PID 3176：1280×720 完整标题与首行检查，真实 Win32 独占锁导致保存失败，旧文件字节及 dirty 保留。
- PID 22240：1920×1080 完整标题与首行检查。

初次 tooltip 驱动未激活窗口，isVisible 断言失败。保留 desktop-small.log 和对应失败脚本；之后只调整本轮测试驱动的窗口激活、系统鼠标定位和悬停等待，未修改生产行为或降低断言，最终实际提示窗截图保存。

最终报告 source-mode 的序列分数 45.4、ELISA 0.1/2.1 AU 和约 10 ng/mL、9 个水平、文献 3 记录/2 引文组/0 未归组保持原事实。三材料无共同分子/样品身份。curve_validated=false 和 validated_quantification_enabled=false、原始 PDF 未独立核验、用户关联声明、强制与用户科学限制均保留。

实际 DOCX 已用 python-docx 解析，核对中文、来源摘要、人工关联和限制，未发现外部关系；再由 Microsoft Word 16.0 只读、禁宏渲染为 PDF 和 9 页 PNG，逐页检查。它是本地 Windows 实际渲染，不是远端自动化通过，也不是冻结 EXE 运行。

## 发布阻断与下一步

REMAINING_RELEASE_BLOCKERS：

1. 新改动未经过远程 Ubuntu/Windows/Python 矩阵和 Node 24 Actions 实际运行。
2. 目标新构建环境需安装固定依赖，strict preflight 通过；本轮未安装或构建。
3. 新冻结 EXE 的 SciPy least_squares/chi2/_cdflib、DOCX模板/lxml、本地案例和报告全流程未实测。
4. lxml iconv 的 LGPL 2.1 相关源码/链接/再分发义务，以及 MSVC 分发权利未解决。
5. 新包实际 DLL、第三方 notice/源码闭包、隐私排除、签名和包大小/启动性能审计未完成。
6. 干净 Windows 10/11 x64 安装、升级、重装和卸载未完成。

LICENSE_REVIEW 是发布前盘点，不是最终法律认证。文件系统支持没有扩大；MERGE-02A 自动执行继续冻结。

READY_FOR_INDEPENDENT_REVIEW：YES，待独立审查本轮源代码、测试、证据和明确的发行阻断。PUBLIC_DISTRIBUTION_ALLOWED：NO。

本轮不暂存、不提交、不推送、不构建 EXE、不创建 tag 或 Release。完成后停止。
