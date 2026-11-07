# Windows 4.1.0rc2 分发许可工程审核

范围：基础 Desktop 的免安装 ZIP 和同一 onedir 生成的候选 Setup；不含 ML 权重、
训练数据、验证数据或模型缓存。此文记录许可证、来源与分发措施，不是法律意见。
项目自身为 MIT；不能把 MIT 解释成覆盖所有捆绑第三方库。

## 已实施的分发措施

- `THIRD_PARTY_NOTICES/inventory.json` 记录构建环境包版本和原始许可文件；
  同时收集 LICENSE / LICENCE / COPYING / NOTICE，排除 Python 缓存和代码文件。
  清单保守包含部分构建工具，不表示每个包都进入可执行文件。
- CPython 3.14.8 原始 LICENSE 保留，含标准库和 libffi 等第三方条款。
- NumPy、pandas、Pillow 的 wheel 原始许可保留，包括其附带的原生库声明。
  Pillow 的 FreeType 声明：本软件包含使用 FreeType 字体引擎的第三方组件。
- OpenSSL 3.5.9 的原始许可补充到 native/NOTICES.txt。
- PyInstaller 使用其 bootloader 分发例外；构建工具许可不覆盖其他依赖。
- Inno Setup 编译器不进入免安装 ZIP。安装器保留原有版权信息；其原始许可允许
  商用及二进制再分发，须保留版权与来源。上游另请求商业用户购买许可。

## Qt / PySide / shiboken

使用未修改的官方 PySide6 6.12.0 wheels。实际基础包的 Qt DLL 模块是 Core、Gui、
Network、OpenGL、Svg、Widgets，以及平台/图像/样式/TLS 插件。
未分发 WebEngine、PDF、QML、Quick、VirtualKeyboard 或 Multimedia。

采用 LGPLv3 开源选项，随包包含 LGPLv3 和 GPLv3 全文。PySide wheels 中出现的
Commercial License 文件属于上游的备选许可材料，不表示此项目取得了商业许可。
Qt/PySide/shiboken 动态库位于 `_internal/PySide6` 和 `_internal/shiboken6`，
用户可替换为接口兼容的修改版，允许为调试这些修改而逆向工程。
不使用阻止替换这些库的完整性校验、签名锁或额外禁止条款。

同一候选 Release 需提供精确 6.12.0 的 qtbase、qtsvg、qtimageformats、
pyside-setup 源码附件及 SHA256；pyside-setup 包含 shiboken 源码。
应用源码、构建脚本和依赖版本可从该 Release 对应 Git 提交取得。
源码附件是上游官方原包，未宣称能逐字节复现上游 wheel 的构建。

`native/source_manifest.json` 固定官方 URL、实际取得文件的 SHA256 与取得日期；
哈希是本地计算的内容标识，不冒充上游数字签名。
`native/NOTICES.txt` 从这些源码归档提取原始许可证、版权和 Qt attribution，
包含部分未使用平台/示例/工具的声明以避免漏项，不能据此认定全部组件均被分发。
Qt 带注释的 attribution JSON 原样保留，不因严格 JSON 解析失败而丢弃。

## 软件 OpenGL 与 Windows 原生运行库

PySide wheel 的 opengl32sw.dll 内含 Mesa 11.2.2 / LLVM 3.6.2 字符串。
与 Qt 官方 mesa_11_2_2-signed_sha256 参考包比较，全部八个 PE 节的 SHA256 相同；
整体文件 SHA256 不同，不能宣称二者整文件相同。保留 Mesa 原始许可、LLVM
University of Illinois/NCSA 声明及其第三方声明；原始 Mesa 源码提供为附件。

MSVC 运行库来自官方 CPython / PySide / NumPy wheels，保留原 DLL，不单独作为
通用运行库售卖。其分发仍受 Microsoft 的运行库条款约束，不属于项目 MIT 授权。
**当前分发权利待确认**：维护者表示没有或不确定是否具有适用的 Visual Studio /
Build Tools 使用许可。仅确认 DLL 来自官方 wheels 不足以确认该维护者的再分发
授权；当前候选只上传 GitHub 草稿，不能将本工程资料核对标记为全部许可通过。
SQLite 按原公共领域声明保留。此工程审核不是完整漏洞扫描或供应链认证。

## 重现与验收边界

```powershell
python -m tools.collect_native_notices --cache dist/license-sources --output dist/native-notices --download
```

将重现结果与 `packaging/windows/licenses/native/NOTICES.txt` 比较；下载与本地
解析可分离，测试不依赖网络。许可修复不会改变规则、模型或实验结果。

公开分发前须核对最终 ZIP 的 notices、原生 DLL 和源码附件，核验哈希、解压运行、
私密数据排除与候选标识。Windows Server CI、开发机和真实干净 Win10/Win11 的
验收分别记录；许可材料完整不等于安装或全部系统兼容性通过。

参考：[Qt 许可](https://doc.qt.io/qt-6/licensing.html)、
[Qt 第三方声明](https://doc.qt.io/qt-6/licenses-used-in-qt.html)、
[LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html)、
[PyInstaller 例外](https://pyinstaller.org/en/stable/license.html)、
[Inno Setup](https://jrsoftware.org/isinfo.php)、
[Microsoft 运行库部署](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files)。
