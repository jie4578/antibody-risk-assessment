# 发布前第三方许可盘点

日期：2026-11-27。该盘点用于工程准备，不是最终法律合规认证或公开分发授权。项目自身 LICENSE 为 MIT，不改变任何依赖的许可证。

DEPENDENCY_INVENTORY.json 区分预期固定版本、当前开发环境、旧构建环境及最终 bundle 待确认状态。构建 notices() 会收集分发元数据和原始许可，并复制 packaging/windows/licenses；是否完整必须以 MERGE-04B 新包逐项确认，不能仅以工具输出的“许可字段”代替审查。

## 主要组件

| 软件 | 预期版本/范围 | 许可与要求 | 状态 |
| --- | --- | --- | --- |
| CPython | 3.14.8 标准 GIL x64 | PSF 条款及嵌入组件许可；保留精确 LICENSE.txt | 新 bundle 待核对 |
| Qt/PySide6/shiboken6 | 6.12.0 | 当前拟采用 LGPLv3 开源选项；保留适用许可/声明、对应源码义务、动态库替换与调试权利 | 旧源码清单保留，最终模块与来源仍需审查 |
| NumPy | 2.5.4 | BSD 及精确 wheel 中附带的其他条款 | 新 DLL/原生 notice 待核对 |
| SciPy | 1.18.1 | BSD 及 BLAS/LAPACK/OpenBLAS、编译运行库等组件条款 | 未验证新冻结运行/许可闭包 |
| python-docx | 1.2.0 | MIT；保留版权及许可文本 | 官方 wheel SHA256 与 LICENSE 已核对并加入源码许可目录 |
| lxml | 6.1.3 | BSD 3-Clause，另含 PSF/ElementTree 代码及原生库条款 | 官方 cp314 Windows wheel 的 LICENSE.txt 和 LICENSES.txt 已保留 |
| lxml 的 iconv | 具体原生版本待核 | 目标 wheel 明确列为 LGPL 2.1；须核对链接方式、匹配源码及相关再分发/修改/重链接要求 | 发布阻断，尚未完成 |
| lxml 的 zlib/libxml2/libxslt/libexslt | 以最终 wheel/PE 为准 | zlib/MIT 等；不能只标一个 lxml BSD 就忽略原生库 | 新 bundle 版本与 notice 闭包待确认 |
| OpenBLAS/LAPACK/GCC/Fortran runtimes | 从精确 NumPy/SciPy wheels 确认 | 按实际组件保留各自条款及适用例外 | 最终闭包待确认 |
| SQLite | 随 CPython，schema v3 不变 | 公共领域声明与具体分发材料 | 最终 DLL 摘要待记录 |
| pandas/openpyxl/keyring/Pillow/OpenAI SDK 等 | requirements-build 固定版本及实际传递依赖 | 按各自 metadata/原始许可，不按本项目 MIT 推定 | 见 inventory；OpenAI SDK 历史版本元数据为 Apache-2.0 |
| PyInstaller | 6.22.3 | 其 bootloader 例外仅作用于适用范围，不豁免其他库许可 | 构建工具与最终文件均需区分 |
| Inno Setup | 6.7.4 | 保留二进制版权和网站信息，不误表原始作者；修改版须标明 | 既有原许可已读，本轮无安装器 |
| MSVC runtime | 最终 DLL 待确定 | 按 Microsoft 使用许可与可分发清单确认维护者资格及文件范围 | 再分发权利仍未确认，发布阻断 |

本轮只读下载 python-docx/lxml 官方 wheels，按 PyPI 声明的 SHA256 及大小核对，再用 ZIP 读取 notice；没有安装或执行下载包。原始 wheel/notice 留在隔离验收目录，仓库内三份新增许可文本仅统一换行及删除末尾多余空行。reporting-source-manifest.json 记录上游 wheel 和 notice 摘要，以及仓库文本 LF 摘要；它们是内容一致性记录，不是生产者认证。

lxml LICENSES 同时提及部分测试和 isoschematron 资源的独立条款。spec 明确排除不用的 lxml.isoschematron，避免默认 hook 将无用 XSL 资源带入；不能仅凭源码排除声明就证明最终归档不存在这些文件，仍需 MERGE-04B 核对。Qt native/NOTICES.txt 还包括某些未使用上游组件，不据此宣称这些组件全部已分发。

另已补入 GNU 官方 LGPL 2.1 完整文本，并在 reporting-source-manifest.json 记录上游和仓库文本摘要。补齐许可文本不等于 iconv 的对应源码、链接方式及其他义务已经解决。

## 仍然阻断公开发行的事项

1. MSVC 维护者再分发权利与具体 redistributable 文件范围。
2. lxml iconv 的准确版本、链接方式、对应源码及适用 LGPL 2.1 义务。
3. 新冻结包实际 Qt、NumPy/SciPy、OpenBLAS、Fortran/GCC、lxml 原生组件及其完整 notice/对应源码闭包。
4. 新候选构建、实际运行、干净客户端系统和签名/安装策略验收。

用户勾选 distribution_rights_confirmed 只记录维护者声明，不产生许可证授权。本轮没有勾选、启动或修改该上传门槛，未创建 Release。

## 官方来源

- [python-docx 1.2.0 许可](https://github.com/python-openxml/python-docx/blob/v1.2.0/LICENSE)
- [python-docx PyPI 元数据](https://pypi.org/project/python-docx/1.2.0/)
- [lxml 6.1.3 分发](https://pypi.org/project/lxml/6.1.3/)，精确 wheel 内 LICENSE.txt/ LICENSES.txt 为本轮主要依据
- [Qt for Python 许可资料](https://doc.qt.io/qtforpython-6/licenses.html)
- [NumPy 许可](https://numpy.org/doc/stable/license.html)
- [SciPy 项目许可说明](https://scipy.org/about/)
- [CPython 3.14 许可](https://docs.python.org/3.14/license.html)
- [Microsoft 运行库再分发说明](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files)
- [Inno Setup 原始许可](https://jrsoftware.org/files/is/license.txt)
- [PyInstaller 分发例外](https://pyinstaller.org/en/stable/license.html)

本轮不替代维护者与适当专业人员对实际发行包和适用许可的最终核查。
