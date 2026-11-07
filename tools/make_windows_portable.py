"""Create a reproducible portable ZIP from an audited Windows onedir build."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from tools.build_windows import audit_bundle, digest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = """抗体科研工作台 4.1.0rc2（预发布候选版）免安装包

1. 下载 Portable.zip 并对照同一 Release 的 SHA256SUMS.txt 核验。
2. 右键 ZIP，选择“全部解压”，解压到有写权限的普通文件夹。
3. 打开 AntibodyResearchWorkbench 文件夹，双击 AntibodyResearchWorkbench.exe。

无需安装 Python。不要在压缩包内启动；不要只复制 exe；必须保留 _internal。
不创建开始菜单/桌面快捷方式，不注册卸载项。删除解压目录即可移除程序。
用户配置、凭据库中主动保存的 Key、缓存和自行导出文件另外保留。

这是基础 Desktop：包含规则分析、批量分析、规则突变比较和确定性摘要。
不包含 ESM2/PyTorch、冻结模型、实验数据或预先配置的 Provider/Key。
文献需要网络；在线 AI 需要主动配置并调用；模型不会自动下载或训练。
规则分数不是实验可开发性概率；ML 差值不是经过验证的实验突变效果。
科研支持用途，仍需人工审查与实验验证。

本候选未签名。不要关闭安全软件或绕过组织安全策略。
当前验收范围和未完成项以 Release 说明为准，不能视为所有 Win10/Win11 已认证。
使用说明：_internal/docs/INSTALL_WINDOWS.md。
许可审核：_internal/docs/WINDOWS_THIRD_PARTY_AUDIT.md。
项目 MIT 许可：_internal/LICENSE；第三方保留各自许可：_internal/THIRD_PARTY_NOTICES。
Qt/PySide 动态库可替换为接口兼容的修改版，允许为调试这些修改而逆向工程。
同一 Release 提供匹配版本的 Qt/PySide 源码附件；无需为获取源码支付费用。
"""


def package(bundle, output):
    bundle, output = Path(bundle), Path(output)
    if output.exists():
        raise ValueError("Use a new ZIP path; do not overwrite a candidate")
    if not (bundle / "AntibodyResearchWorkbench.exe").is_file():
        raise ValueError("Windows onedir executable missing")
    for required in ("_internal/THIRD_PARTY_NOTICES/native/NOTICES.txt",
                     "_internal/THIRD_PARTY_NOTICES/native/source_manifest.json",
                     "_internal/THIRD_PARTY_NOTICES/LGPL-3.0.txt"):
        if not (bundle / required).is_file():
            raise ValueError("Required distribution notice missing: " + required)
    audit = audit_bundle(bundle)
    entries = {}
    for file in sorted(bundle.rglob("*")):
        if file.is_symlink():
            raise ValueError("Symlinks are not permitted in portable builds")
        if file.is_file():
            relative = file.relative_to(bundle).as_posix()
            entries["AntibodyResearchWorkbench/" + relative] = file
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, file in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with file.open("rb") as src, archive.open(info, "w") as dst:
                import shutil
                shutil.copyfileobj(src, dst)
        info = zipfile.ZipInfo("先读我.txt", date_time=(2026, 11, 7, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, GUIDE.encode("utf-8-sig"))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive CRC failed")
        for name, file in entries.items():
            h = hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest() != digest(file):
                raise ValueError("Portable content changed: " + name)
    return {"file": output.name, "bytes": output.stat().st_size, "sha256": digest(output),
            "archive_crc": "PASS", "all_bundle_file_hashes_preserved": True,
            "bundle_audit": audit, "clean_windows_qualification": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "dist"):
        parser.error("Output must stay under repository dist/")
    report = package(args.bundle, args.output)
    args.output.with_suffix(".manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.output.with_suffix(".sha256").write_text(report["sha256"] + "  " + args.output.name + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
