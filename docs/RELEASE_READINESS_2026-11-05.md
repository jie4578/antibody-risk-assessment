# 中文候选版发布门槛（2026-11-05）

目标：`4.1.0rc2`，未发布；上一中文源码提交为
`dd7231b88650400b847104c1b2bdc74b2a2f46d0`。
该提交的 [六项 CI](https://github.com/jie4578/antibody-risk-assessment/actions/runs/39799307895)
均为 success。此结果不转移为当前未提交 rc2 的远程 CI。
旧 `4.1.0rc1` 本地包与 v4.0.0 正式标签保留，不覆盖。

## 五项工作及验收边界

1. 中文交付：只从已提交源码加明确的发布维护覆盖清单构建新 wheel/sdist，
   排除两份脏 CLI、私有文件、数据和模型；检查版本、许可证、中文模块和摘要。
2. Windows：在真实窗口检查六页中文与滚动、合成序列和过期状态；明确区分
   原生输入、Qt 集成测试、离屏测试、Mock 与真实外部服务。诊断不隐藏。
3. ML：只验收已有可信文件、冻结 revision 及合成输入，不重建/拟合模型。
   缓存、依赖或版本不足就记为未完成，不以基础安装结果替代。
4. 科学局限：冻结证据不改，不重新读取标签或评估。泛化问题只能由未来另行
   预注册的新独立数据验证，本轮不能宣布已解决。
5. 发布维护：SPDX MIT 和显式 LICENSE 文件、匹配的构建后端最低版本、
   当前状态入口和部署指引。发布快照记录可复现环境，不虚构跨环境锁定。

## 科学证据核对

- 内部 AIntibody TEST：HIC rho=0.834662，R²=0.625834，N=72；
  composite ROC-AUC=0.691468、PR-AUC=0.611665、prevalence=0.336842，N=95。
- 84/95 TEST 与 TRAIN paired-min identity >=0.90，不是 family-independent 验证。
- GDPa3 HIC：rho=0.231901，95% CI [0.005418, 0.437591]，N=79。
  跨源/跨协议、区间宽；不是绝对校准、等价实验复现或广泛可开发性验证。
- GDPa3 已在 Phase 8C 观察，不能再次标为未触碰 holdout。
- composite 未获得相应 GDPa3 外部认证；突变 ML delta 只是估计值算术差。
- 不发布临床、因果、最佳抗体、湿实验替代或全局可开发性预测结论。

本轮不修改 core/scoring、规则版本、阈值、冻结 ML、Provider 行为或历史结果。
新外部研究、模型训练、正式 tag/Release、公开上传产物均不在本地准备授权内。

## 实际结果

### 1. 中文交付：本地候选构建 / 安装通过，未发布

源码来自 `git archive dd7231b` 加明确覆盖清单：`pyproject.toml`、README、
MANIFEST、本轮发布/汉化/部署文档、两份已观察环境约束、
`tools/check_ml_deployment.py`、`tests/test_release_readiness.py` 和
`tests/test_installed_package.py`。两份保留的 CLI 未从脏工作树复制。
Git archive 在 Windows 应用换行转换；同时核对归档字节及标准化 Git 原文，
不把不同的换行误判为 CLI 代码变更，也不把脏 CLI 偷换成候选输入。

产物为 `antibody_risk-4.1.0rc2-py3-none-any.whl` 和
`antibody_risk-4.1.0rc2.tar.gz`。本地 `source_manifest.json`、
`artifact_manifest.json`、`SHA256SUMS.txt` 保存精确源码和产物摘要。
报告自身随 sdist 打包，因此不在报告内嵌入自己的产物摘要，避免循环引用。
检查中文模块、配置、许可证、源文件一致性、路径安全及数据/模型排除。
最终 sdist round-trip wheel 的一致性以单独构建校验结果为准。

### 2. Windows：有用户辅助的原生功能通过，不是 CLEAN

实际安装的 rc2 wheel 在现有独立 standard-GIL CPython 3.14.8 新 venv
中启动真实 Windows 窗口，凭据读取隔离为 Mock，Python socket 连接被拦截。
自动化成功读取六页中文导航和控件，但截图返回 `FrameArrived timed out` /
`window capture timed out`，点击返回 `coordinate input geometry is unavailable`。
按技能恢复规则停止自动输入，没有将可访问性文字当作字体/布局的视觉证明。

用户随后实际点击分析和生成摘要。可访问性读回：NNST 长度 4、分数 73.00、
4 个位点（包含 NNS@1–3 和 NST@2–4）；中文摘要包含 `overlap_v2`、相同数值
及科学局限。用户确认“六页正常”，并确认“已关闭”。原进程已退出：
exit=0、8602 个心跳、closed=true、faulthandler=true。

原始 stderr 保留了 `can't open file for write !` 及 `0x8001010d` 诊断，
本次没有可用于分类的原生 C 栈。不能仅凭相同错误码将本次标为已审阅的 UIA 路径，
也不能宣布诊断消失。网络拦截器记录 4 次尝试，触发来源未被当前计数日志记录；
它拦截连接而非证明没有尝试，不声称本次零网络尝试或新的真实 Provider 验收。
本次是用户辅助的原生功能/视觉验收，不是完全自动原生点击验收；
运行中任务关闭仍由已有 Qt 集成测试覆盖，未伪称本轮用户在后台搜索时关闭。

### 3. ML：隔离 CPU 部署链路通过，范围有限

新的 CPU venv 不共享 Anaconda site-packages；Python 3.13.9 来自现有
Anaconda 解释器，原环境没有被安装或升级。实际 wheel 安装及 `pip check` 通过。
可信现有模型的摘要和冻结定义匹配；离线 ESM 合成输入重复一致、1280 维结构、
概率契约通过，模块来源为已安装 wheel。把原模型副本放入该隔离安装的默认目录后，
DesktopMLService READY、合成预测及缓存重复通过，socket 网络尝试 0。
未训练、未读取 TEST 标签、未计算模型性能；不是 CUDA、所有 Python 补丁或
普通用户自动获得可信模型文件的认证。参见[部署指引](ML_DEPLOYMENT_CHECKLIST.md)。

### 4. 科学局限：核对完成，泛化不足未被消除

上述冻结证据和模型卡一致。没有新外部验证、重训、调参、阈值优化或重新计算
封存分析。仍不能宣传 family-independent、广泛可开发性或突变效应预测。
未来研究必须另行人工审查/预注册；本轮不开始该研究。

### 5. 发布维护：本地完成，当前候选远程门槛仍待处理

MIT 文本不变，采用 SPDX `license="MIT"`、显式 `license-files=["LICENSE"]`，
构建与 dev 使用 setuptools >=77.0.3。该最低版本按
[setuptools 官方说明](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
及实际 wheel License-Expression/许可证文件检查核对。旧许可证表弃用提示不再出现。
新增只读部署检查的 13 项测试及 wheel 许可证/中文模块断言，不修改生产科学代码。

最终非训练回归来自干净源码副本（预先排除会拟合的 `test_ml.py`、`test_rag.py`）：

| 检查 | 实际结果 |
| --- | --- |
| Python 3.14.8 / Qt 6.12.0 源码回归 | 708 passed, 2 skipped, 7 deselected, 18 warnings |
| 现有开发环境 Python 3.13.9 源码回归 | 710 passed, 7 deselected, 5 warnings |
| 离线冻结兼容性子集 | 12 passed |
| 最小 3.14.8 wheel 安装 | pip check / site-packages 导入 / 中文摘要 / 缺模型提示 / Qt 退出通过 |
| CPU ML 隔离安装 | pip check / 离线 ESM / Desktop ML service 合成调用通过 |

3.14.8 最小安装没有 pytest、build、matplotlib、Bio、torch 或 transformers，
从记录版本的 wheelhouse 离线安装，31 个事件循环心跳、零网络尝试、无模型推理。
这是离屏 Qt 集成检查，不冒充另一次原生点击。两项 skip 为缺少可选 LangChain；
7 项 live 均未运行。没有运行会重训的完整历史 validation/runtime-builder 套件。
3.14.8 的 18 项 warnings 中包括 pandas 未来行为弃用和既有输入提示；
开发环境保留旧 Gradio 弃用与输入提示，均未隐藏或放宽断言。

本地测试 XML、依赖快照/约束、构建及诊断日志在忽略的 `dist/4.1.0rc2/`。
公开约束是已观察版本，不是跨平台/安全更新锁；安全更新后需重新验收。
沙箱曾阻止 Git DLL 启动及读取真实构建产物，随后在同一真实 Windows 上下文复核；
先前有一轮归档换行断言失败，保留记录后修正字节/换行核对方式。
隔离 ML 安装两次无输出等待被取消；后续无缓存/非交互分组安装成功，
未将等待归因为已确认的单一原因，未修改系统凭据或代理设置。

**原本地准备决定：READY_FOR_SELECTIVE_REVIEW / NOT_PUBLISHED。**
以上记录对应当时未暂存、提交、推送的本地准备阶段。用户随后授权了追查、选择性
提交/推送及 CI；新结果见[诊断追查](RELEASE_DIAGNOSTIC_FOLLOWUP_2026-11-05.md)。
当前候选的对应提交/CI 结果以最终 checkpoint 和 GitHub 为准，不能用旧 CI 代替。
正式 tag/Release 仍需单独授权。历史 4 次连接总数的细节不能追溯恢复，已知限制不删除；
不对外声称“全无诊断/全环境认证”。两份 CLI、本地手工表、批处理文件、旧 rc1、
原模型及冻结结果保持原样。
