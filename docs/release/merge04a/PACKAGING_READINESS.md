# Windows 打包准备与验证边界

日期：2026-11-27。基线 1aeed020546f86aee1f83942220d423175028b6e，源码版本 4.1.0rc2。本轮不构建 EXE、Setup 或公开二进制。

## 当前实现

requirements-build 固定保留原版本，增加 scipy==1.18.1、python-docx==1.2.0、lxml==6.1.3。普通 CLI/Web 基础依赖不增加 python-docx；desktop/all 增加 python-docx>=1.2.0,<2。

spec 移除 SciPy 排除项，仍排除 torch、transformers、sklearn、gradio、ml、validation 等。SciPy 原生扩展先依赖现有官方 hook，不预先进行大范围 DLL 复制。DOCX 的 templates/*、docx 模块和 python-docx/lxml metadata 显式收集；lxml.etree 和 lxml._elementpath 为显式 hidden imports。docx 默认模板已在源码环境实际读取、生成中文文档并可靠解析。

现有 lxml hook 会收集所有子模块，因此显式排除本产品不用的 lxml.isoschematron，避免无用 XSL/RelaxNG 资源和额外许可范围。该排除在本轮只经过静态测试，实际 PYZ/资源排除结果仍由 MERGE-04B 构建核对。

build_windows 增加 --preflight-only：检查标准 GIL CPython 3.14.8 Windows x64、固定依赖版本、NumPy/SciPy/Qt/SQLite/lxml 导入、DOCX 模板与中文往返，以及案例、报告和蛋白质工程资源存在性及摘要。它不安装依赖、不调用 PyInstaller/Inno。正常构建也先通过该门槛。

## 原工作区差异迁移

只读比较了原工作区的两项未提交 SciPy 改动：

| 原差异 | 迁移理由 | 旧证据与限制 |
| --- | --- | --- |
| requirements-build 增加 scipy==1.18.1 | 冻结 C.2A 使用现有数值引擎所必需 | Step 02 官方 wheels、源码导入和 onedir 构建成功；不是本次新包通过 |
| spec 从 excludes 删除 scipy | 否则已安装 SciPy 仍被排除 | 原 onedir 约 243.52 MiB、1253 文件；冻结 C.2A 实际运行仍未由该构建报告证明 |

没有复制原工作区 CLI、工作簿、其他脏文件或旧构建产物。新增 DOCX/lxml 规则和 preflight 是本轮独立实施。历史原件与其虚拟环境均未修改，没有把旧报告改成新代码的通过证据。

## 检查矩阵

| 项目 | 本轮结果 | 仍需 MERGE-04B |
| --- | --- | --- |
| PySide6 Widgets、NumPy/SciPy、SQLite 源码导入 | 当前开发环境通过 | 精确构建版本与 DLL 实际加载 |
| SciPy 1.18.1 旧构建环境导入 | 原 CPython 3.14.8 环境 preflight 导入通过 | 新冻结 exe 内 least_squares、chi2、_cdflib 等 |
| python-docx 1.2.0 | pure Python wheel；Requires-Python >=3.9；本地版本通过 | 精确新构建环境安装及冻结模板可用 |
| lxml 6.1.3 | 官方 cp314-cp314-win_amd64 wheel SHA256 已核对，仅作 ZIP 读取 | 安装、原生 DLL 与关联库版本/许可 |
| 蛋白质工程资源、案例/报告源码 | preflight 路径检查及现有打包回归 | 最终 bundle 文件清单与实际资源读取 |
| VERSION.txt、PE/Setup 版本 | 保留 4.1.0rc2 读取和生成规则 | 冻结实际文件/窗口/报告一致 |
| 基础 CLI/Gradio 科研算法 | 未改动；训练与 Provider 隔离保留 | 不随桌面包引入未使用大型依赖 |
| Inno Setup 安装 | 本轮未调用 | 干净系统安装、重装、卸载 |

实际开发环境为 CPython 3.13.9，不能冒充指定构建解释器。其 strict preflight 返回 NOT_READY（版本不同/PyInstaller 未安装）。只读检查旧 CPython 3.14.8 构建 venv 时，发现 python-docx/lxml 尚未安装，返回 NOT_READY；未自动安装或污染旧环境。

官方 PyPI 元数据和 wheel 标签表明存在目标候选 wheel，不等于 ABI/冻结运行已通过。lxml 编译库、两套 OpenBLAS、GCC/Fortran/MSVC 运行库闭包、包大小与启动性能必须以新构建实测为准。

## 下一阶段门槛

1. 新建独立构建环境，安装固定官方二进制依赖并保存下载来源、SHA256、解析结果；不要复用修改旧证据环境。
2. strict preflight PASS 后才允许受控构建新 onedir。
3. 审计最终 DLL、资源、许可证与源码对应关系；解决 MSVC 和 lxml iconv 权利/义务待办。
4. 真正运行冻结 exe 的八页、C.1、C.2A、案例重启、MD/DOCX 流程；不以源码 smoke 替代。
5. 再进行 Inno 和干净 Windows 10/11 x64 人工验收；Hosted Server 结果不等同干净客户端系统。

WINDOWS_FROZEN_READINESS：NOT_READY。PUBLIC_DISTRIBUTION_ALLOWED：NO。配置已准备，可进入独立审查；这不是发行许可或已完成新包构建的结论。
