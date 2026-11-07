# Windows 候选安装器验收与正式发布门槛

当前候选：4.1.0rc2；目标稳定版：4.1.0。历史 v4.0.0 标签和 Release 不改。
最新执行证据见 [2026-11-07 交付记录](RELEASE_DELIVERY_2026-11-07.md)。
许可工程核对见 [第三方审核](WINDOWS_THIRD_PARTY_AUDIT.md)。用户已授权上传 rc2
免安装预发布 ZIP；此授权不创建稳定版 v4.1.0，也不把未完成的干净系统验收视为通过。

## 必须区分的验证层次

1. 源码回归、冻结协议/规则兼容性、安装依赖一致性。
2. 实际 PyInstaller exe 的离线合成 smoke（六页、规则、批量、XLSX、突变、无 ML）。
3. 当前开发机上的安装、快捷方式、启动、同版本重装和卸载检查。
4. **干净 Windows 10 x64 / Windows 11 x64** 上无需 Python 的图形安装和人工点击。
5. 新候选提交的远程 CI：旧提交结果不能转移为当前未提交文件的通过证据。

离屏、开发机、Hosted Actions、Windows Sandbox 和完整 OS VM 的范围都要明示。
不能仅凭成功运行 exe 或源码测试勾选第 4 项。

## 正式发布审批前的清单

- [ ] 确认待发布提交和最终版本元数据、PE 版本、Setup 文件名一致。
- [ ] Windows onedir 与 Inno Setup 安装器构建成功，生成 SHA256。
- [ ] 依赖与第三方许可清单、Qt 动态链接/对应源码义务完成审阅。
- [ ] 检查签名状态和可执行文件安全扫描；候选未签名状态明确，不建议绕过系统警告。
- [ ] 干净 Win10/Win11：安装、开始菜单、可选桌面快捷方式、六页、正常退出。
- [ ] 合成序列 NNST、批量导入/导出、突变比较、摘要及过期状态实际验收。
- [ ] 无模型时基础功能可用，部署状态清楚；不训练、不制造 ML 输出。
- [ ] 高级 ML 如单独提供，具备独立来源摘要、授权、依赖/序列化/缓存/离线运行验收。
- [ ] 真实不同版本升级及卸载通过，配置/导出/外部模型保留策略准确。
- [ ] 无 Key、私密序列、原始验证数据、模型二进制和开发缓存混入安装器。
- [ ] 当前候选 CI 通过并附精确 commit SHA。
- [ ] 获得用户单独授权后才创建稳定 tag/Release、上传公开安装包。

## 维护者构建

在独立的官方标准 GIL Windows x64 CPython 3.14.8 venv 安装
`packaging/windows/requirements-build.txt`。使用经核验的官方 Inno Setup 6.7.4
编译器。Python 和 Inno 工具不安装到普通用户机器。

```powershell
python tools/build_windows.py --output dist/windows_delivery/build-001 --iscc C:\Tools\Inno\ISCC.exe
```

必须使用新的输出目录。脚本只复制明确允许的源码/资源，不递归复制仓库。
两份脏 CLI、本地数据、模型和视频不会进入快照。基础 exe 不包含 Gradio/训练模块；
源码 CLI/Gradio 功能仍保留。所有模型/缓存与构建产物保持 Git 忽略。

CI 工作流只手动构建和上传短期 Actions 候选 artifact，绝不创建 Release。
工作流还会重现官方来源声明、从 ZIP 解压启动，并执行当前用户安装、快捷方式、
同版本重装、卸载和配置保留检查。它运行在 Windows Server 2022 hosted runner，
不能替代干净 Win10/Win11 人工验收。公开 ZIP 与源码附件由维护者单独核对后上传。
手动执行前应核对候选提交和上传内容；仅有 YAML 或普通源码 CI 不能宣称安装器已通过。
