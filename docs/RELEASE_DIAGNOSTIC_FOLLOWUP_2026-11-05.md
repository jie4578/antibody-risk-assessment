# rc2 发布前诊断追查（2026-11-05）

范围：合成输入、隔离 Mock 配置、现有 Python/Qt，不改生产科学逻辑、
Provider 行为、系统代理、COM 模式、Windows 权限或 faulthandler。
本报告区分已定位的新对照事件与缺少原始细节的历史事件。

## UIA / COM：本次有原生证据，不是猜错误码

测试专用 `tests/qt_startup_diagnostic.py` 新增 `installed` 模式及可选网络审计，
产品启动不导入它；原来的严格分类规则没有放宽，继续传递 Windows 异常搜索。

| 对照 | 实际结果 |
| --- | --- |
| rc2 安装版，3.14.8 / Qt 6.12.0，30 秒 | exit 0；2975 心跳；原生观察器健康；1 个 COM 事件，之后继续响应 |
| 空白 QWidget，不导入任何 desktop 模块，2 秒 | exit 0；199 心跳；观察器健康；同一 COM 路径 |

两者均核对到有序栈 `RPCRT4 → combase → UIAutomationCore → qwindows → USER32`，
以及 `UiaReturnRawElementProvider` 的同一 x64 unwind 函数记录，不仅是地址相近。
严格分类为 `REVIEWED_UIA_COM_DIAGNOSTIC`、`clean=false`。
无产品 QWidget 对照也出现该事件，因此没有证据要求修改规则/ML或吞掉异常。
未确认具体的发起可访问性客户端，也不把所有同码事件一概豁免。
窗口读取工具本次还返回过 `foreground window did not report a process id`；
探针随后按预设时限退出，不将该读取失败算作完整原生点击验收。

原始 stdout 还含 `can't open file for write !`，两个对照都保留了它。
该附带消息的写入目标/发出组件未确定，不能宣称所有诊断均已消除。
本轮还生成了根目录 `debug.log`，其中明确记录 Sogou 输入法组件的初始化消息；
这定位了该日志文件的组件归属，但不足以证明同一组件发出了上述 stdout 消息或
发起了 COM 调用。新增精确的 `/debug.log` 忽略规则，保留本地日志但防止误提交。
没有新增生产异常过滤器、禁用可访问性、关掉故障处理器或系统级绕过。

## 连接：修复的是审计分类，不是关闭产品网络功能

旧验收记录只有 `network_attempts=4`，没有目标或栈，不能恢复四次各自的来源。
它既不证明四次都是 Provider 外网请求，也不证明四次都是无害内部调用。
保留旧记录，不事后改成 0，不以新对照覆盖旧事实。

新增测试专用 `NetworkAudit`：默认全部阻断；可选仅放行**真实标准库文件**中的
asyncio Proactor `_make_self_pipe` 调用 Windows socketpair，且目标必须是回环地址。
支持 `asyncio/windows_utils.py:socketpair` 及 stdlib `socket.py` 的相应实现。
任意本地 Provider/代理、远程连接或未知 DNS 查询仍阻断；不是 localhost 通配白名单。
只记录 API、阶段、地址类别和文件名/函数/行号，不记录主机、IP、端口、请求内容、
序列、密钥、源码文本或个人绝对路径。计数单位是 API 事件，不伪称唯一连接数。

实际离线对照：

- 安装版启动/空闲/关闭：0 个 Python socket API 事件。
- 规则分析、摘要、六页导航、Mock 连接测试、Mock Copilot、无工具 hello Agent：0 个事件。
- 显式创建 Windows asyncio event loop：严格全阻断会拦截 1 次回环 self-pipe，
  使构造失败并产生析构诊断；按核对过的 stdlib 路径放行后正常创建/关闭，
  1 次内部事件、0 次阻断，没有外网请求。
- 显式合成文献请求：在当前网络环境走本地代理，目标虽为回环地址，仍因调用栈
  来自 `literature.search → urllib → http.client` 被阻断。证明不能把所有回环都放行。

这些结果修正了“所有 socket 调用等于外网请求”的验收方法；不反推历史 4 次的具体来源。
后续原生验收须使用有类别/栈的探针，单凭总数不能再作泄露或零联网结论。

## 测试、源码与发布边界

针对性诊断/分类测试：66 passed；其中新增网络审计测试 14 项。
覆盖外部/DNS/任意本地连接阻断、路径/调用者核对、无敏感日志、上下文还原及
真实 Windows Proactor self-pipe；仅该 Windows 集成用例在非 Windows 上明确跳过。
新辅助文件通过 MANIFEST 进入 sdist，避免安装来源缺少测试 helper。
不修改原有 52 项 fail-closed 原生分类测试，不把未知 stderr、异常退出或无健康证据降级。

原始日志、分类 JSON、受控场景 JSON 和环境信息留在忽略的本地 dist 目录。
本报告是公开的脱敏结论，不上传原始机器日志。
完整非训练回归、包校验、选择性提交与对应提交的远程 CI 结果见最终 checkpoint；
本报告写入时不预先宣布未来 CI 成功。无 tag/Release 授权。

提交前最终干净源码非训练回归：Python 3.14.8 为 722 passed、2 skipped、
7 deselected、18 warnings；现有开发环境为 724 passed、7 deselected、5 warnings；
离线兼容子集 12 passed。两项 skip 为未安装的可选 LangChain。
先前一次沙箱内针对性运行在 Qt DLL 装载的 fixture setup 阶段报错；
同一解释器在真实 Windows 访问上下文复验通过，没有放宽断言或排除失败用例。

决定：**诊断有边界地定位，审计方法已修正，历史细节缺口明确保留；不需要无证据的生产补丁。**
