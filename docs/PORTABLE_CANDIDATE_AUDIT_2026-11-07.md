# 4.1.0rc2 免安装候选：许可与安装验收结果

## 当前决定

**保留 GitHub Draft，不公开发布。** 维护者已授权准备免安装 ZIP，但表示没有或
不确定是否具有适用的 Visual Studio / Build Tools 使用许可。Microsoft VC++
运行库的再分发授权仍须确认；来自官方 Python wheels 不等于该项已确认。
没有创建稳定版 v4.1.0 Release，也不改变历史 v4.0.0。

## 已完成

- Windows 基础候选 ZIP：81,098,639 bytes；SHA256：
  `81e990d5b0b8cea60a4f1190576919f80f41f3ffbe4eb7d94b605ddb969cd87c`。
  归档 CRC、全部 1,145 个原包文件的 SHA256 保持检查通过。
- 构建源码为 `6e252fb7b343e16f8321807350081dd55c80ef5c`，标准 GIL CPython
  3.14.8；后续验收工具提交不改变这份基础 Desktop 的源码行为。
- 最终 ZIP 实际解压并使用新建空配置离线启动通过：六页、NNST 重叠位点、重复 ID
  批量记录、XLSX 导出、规则突变、无模型启动、Windows keyring 后端、OpenAI SDK
  导入。PATH 中没有外部 Python；未加载模型或调用 Provider。
- 新增打包测试：15 passed。基础应用回归：753 passed、2 skipped、7 deselected、
  18 warnings。历史 ML/RAG 拟合模块不属于该基础应用回归范围。
- 离线 validation：185 passed、3 warnings。没有运行新的实验预测或科学分析，
  没有重训或更改发布模型。
- 原有两份 CLI 修改、手工验收表和批量生成文件未修改或提交；构建快照显式排除
  `literature/cli.py`，不将保留的本地修改嵌入 Desktop。
- `git diff --check` 通过。原样保留的上游 notice 文本使用限定到该文件的空白属性，
  不修改第三方许可证正文来迎合代码空白检查。

## 远程安装验收

[Windows 工作流 42369126887](https://github.com/jie4578/antibody-risk-assessment/actions/runs/42369126887)
在源码 `4d3eb180767edb7ffef87387d6dc5e55f771b95c` 上成功：

| 项目 | 结果 |
|---|---|
| 官方编译器签名、冻结候选构建 | PASS |
| 官方来源 notice 的 SHA256 重现 | PASS |
| ZIP 解压和实际 exe 离线 smoke | PASS |
| 当前用户安装 | PASS |
| 开始菜单和可选桌面快捷方式 | PASS |
| 已安装 exe 离线 smoke | PASS |
| 同版本重装 | PASS |
| 正常卸载、快捷方式和卸载注册项清除 | PASS |
| 用户数据 sentinel 保留 | PASS |

执行环境为 GitHub Hosted **Windows Server 2022**，不是干净 Win10/Win11。
该提交的[六项源码 CI](https://github.com/jie4578/antibody-risk-assessment/actions/runs/42369125725)
也全部通过。

之前三个安装工作流失败，原始结果保留。诊断显示 WScript 的 TargetPath 返回空；
验收脚本补充使用 Microsoft 的 ShellLinkObject.Path 读取，仍要求目标等于已安装
exe，没有用“链接存在”代替目标正确性检查。没有更改生产科学代码。

## 许可资料

修复了 LICENCE 拼写导致的 openpyxl/et_xmlfile 许可遗漏，并排除误收集的 .py/.pyc。
补充官方精确版本的 Qt/PySide 原生声明和 GPL/LGPL 文本，保留 Python wheel 许可，
核对 Mesa/LLVM 和 OpenSSL 材料。匹配 Qt/PySide/Mesa 源码原包已作为草稿附件上传。
内容及取得来源的 SHA256 见
[manifest](../packaging/windows/licenses/native/source_manifest.json)；
详细范围见[第三方工程审核](WINDOWS_THIRD_PARTY_AUDIT.md)。

所有草稿附件的 GitHub 服务端 SHA256 与本地对应文件一致。
这些资料与源码附件已准备，不表示待确认的 MSVC 分发权利已通过。
安装 CI 的含二进制 artifact 在下载留存验收证据后撤回；后续工作流默认只上传报告，
含二进制上传需显式确认分发权利。GitHub Draft 保持未公开。
取得或确认适用授权后，还需复核候选包和发布状态，再公开，不直接把草稿当成正式版。

## 未完成的资格验收

- 干净 Windows 10 x64 与 Windows 11 x64 的完整人工安装/六页点击/退出。
- 真实不同版本升级；同版本重装不能替代跨版本升级。
- 主程序和安装器的正式代码签名。
- 可选高级 ML 的独立部署验收；基础 ZIP 不携带模型或 ESM 权重。

发现的现有 Win10 Enterprise 17763 虚拟机有使用记录，不能直接视为干净系统。
本机 VMware 启动时报告无有效许可证，系统没有成功启动；未修改安全策略或绕过
许可。虚拟化环境合法恢复后可用于补充兼容性测试，仍须记录实际环境和限制。
