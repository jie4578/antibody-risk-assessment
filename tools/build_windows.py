"""Maintainer-only allowlisted Windows onedir/installer build. Never publish.

Run in a dedicated Windows x64 CPython venv with requirements-build.txt.
Outputs stay beneath dist; the working tree and index are read only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("desktop", "ml_inference", "agent", "literature", "rag", "protein_engineering")
TOP_LEVEL = ("core.py", "scoring.py", "models.py", "batch_analysis.py", "input_parser.py", "config.py", "LICENSE", "pyproject.toml", "example_antibodies.csv")
DOCUMENTS = ("docs/INSTALL_WINDOWS.md", "docs/ML_DEPLOYMENT_CHECKLIST.md", "docs/WINDOWS_THIRD_PARTY_AUDIT.md", "docs/WINDOWS_DELIVERY_ACCEPTANCE.md")
PROTEIN_TABLES = ("enzyme_targets", "protein_variants", "samples", "experiment_batches", "assay_results", "kinetic_timecourse", "ai_predictions", "structure_assets", "source_manifest")
PROTEIN_RESOURCES = ("FOUNDATION_STATUS.md", "PROTEIN_ENGINEERING_ROADMAP.md", "PHASE0_DATA_INTAKE.md", "DATA_DICTIONARY.md", "ANALYSIS_REQUIREMENTS.md", "PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md", "PHASE0_PACKAGE_PROVENANCE.json",
                     *("templates/" + name + "_template.csv" for name in PROTEIN_TABLES))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def snapshot(destination):
    if destination.exists():
        raise ValueError("Use a new build directory; existing builds are never deleted")
    files = [ROOT / name for name in TOP_LEVEL + DOCUMENTS]
    for package in PACKAGES:
        files += [p for p in (ROOT / package).rglob("*.py") if p.is_file() and "__pycache__" not in p.parts]
    files += [p for p in (ROOT / "packaging/windows").rglob("*") if p.is_file() and p.suffix in {".py", ".spec", ".iss", ".txt", ".json"} and "__pycache__" not in p.parts]
    # The user's preserved CLI edits are unrelated to Desktop delivery. Never
    # embed the dirty literature CLI through the package-wide hidden imports.
    files = [p for p in files if p.relative_to(ROOT).as_posix() != "literature/cli.py"]
    files += list((ROOT / "docs/images/windows").glob("*.png"))
    if (ROOT / "protein_engineering/__init__.py").is_file():
        for name in PROTEIN_RESOURCES:
            source = ROOT / "protein_engineering/resources/phase0" / name
            documentation = ROOT / "docs" / name if name == "PROTEIN_ENGINEERING_ROADMAP.md" else ROOT / "docs/protein_engineering" / name
            if source.read_bytes() != documentation.read_bytes():
                raise ValueError("Protein documentation/resource drift: " + name)
            if source.suffix == ".csv":
                with source.open(encoding="utf-8-sig", newline="") as stream:
                    if len(list(csv.reader(stream))) != 1:
                        raise ValueError("Only header-only protein templates may be packaged")
            files += [source, documentation]
    result = {}
    for source in files:
        if source.is_symlink():
            raise ValueError("Symlink in source allowlist")
        relative = source.relative_to(ROOT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        result[relative.as_posix()] = digest(target)
    return result


def is_notice_file(entry):
    path = Path(entry)
    return ("__pycache__" not in path.parts
            and path.suffix.lower() not in {".py", ".pyc", ".pyo"}
            and any(part.lower().startswith(("license", "licence", "copying", "notice"))
                    for part in path.parts))


def notices(destination):
    destination.mkdir(parents=True)
    records = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get("Name", "")):
        name = dist.metadata.get("Name", "unknown")
        folder = destination / name
        folder.mkdir()
        license_files = []
        for entry in dist.files or []:
            if is_notice_file(entry):
                source = Path(dist.locate_file(entry))
                if source.is_file() and source.stat().st_size < 5_000_000:
                    target = folder / Path(*[p for p in entry.parts if p not in {"..", "."}])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target); license_files.append(target.relative_to(destination).as_posix())
        (folder / "METADATA.txt").write_text(dist.read_text("METADATA") or dist.read_text("PKG-INFO") or name, encoding="utf-8")
        records.append({"name": name, "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", "SEE_METADATA"), "license_files": license_files})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise ValueError("CPython LICENSE.txt not found")
    shutil.copyfile(python_license, destination / "CPython-LICENSE.txt")
    (destination / "inventory.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "README.txt").write_text(
        "Third-party notices for this candidate build. Build tools may also appear in the inventory.\n"
        "Qt/PySide6/shiboken are dynamically linked under LGPLv3 (or the applicable alternative terms).\n"
        "Users may replace compatible Qt/PySide DLLs in _internal; no restriction on debugging such modifications.\n"
        "Corresponding upstream source: https://download.qt.io/official_releases/QtForPython/\n"
        "Qt source: https://download.qt.io/official_releases/qt/\n"
        "Exact source URLs, SHA256 and upstream native notices: native/source_manifest.json and native/NOTICES.txt.\n"
        "Matching Qt/PySide sources are supplied as companion prerelease assets; see docs/WINDOWS_THIRD_PARTY_AUDIT.md.\n"
        "PyInstaller bootloader distribution exception: https://pyinstaller.org/en/stable/license.html\n"
        "This inventory is not a legal certification or a grant of rights to separately supplied models.\n", encoding="utf-8")
    for license_file in (ROOT / "packaging/windows/licenses").rglob("*"):
        if license_file.is_file():
            target = destination / license_file.relative_to(ROOT / "packaging/windows/licenses")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(license_file, target)
    return records


def audit_bundle(directory):
    forbidden = []
    for path in directory.rglob("*"):
        if not path.is_file(): continue
        rel = path.relative_to(directory)
        if (path.suffix.lower() in {".joblib", ".npz", ".xlsx", ".db", ".sqlite", ".sqlite3", ".safetensors"}
                or path.name.lower().endswith((".sqlite3-journal", ".sqlite3-wal", ".sqlite3-shm"))
                or path.name in {".env", "settings.json", "model_manifest.json"}
                or path.name.startswith("protein-private-snapshot")
                or any(p in {"validation", "torch", "transformers", "gradio", "ml_models"} for p in rel.parts)):
            forbidden.append(rel.as_posix())
        if path.suffix.lower() == ".csv":
            allowed = rel.as_posix() == "_internal/examples/example_antibodies.csv"
            protein_template = rel.as_posix().startswith("_internal/protein_engineering/resources/phase0/templates/") and path.name in {kind + "_template.csv" for kind in PROTEIN_TABLES}
            if protein_template:
                with path.open(encoding="utf-8-sig", newline="") as stream:
                    allowed = len(list(csv.reader(stream))) == 1
            if not allowed:
                forbidden.append(rel.as_posix())
    if forbidden:
        raise ValueError("Forbidden files in bundle: " + ", ".join(forbidden))
    return {"forbidden_files": [], "files": sum(p.is_file() for p in directory.rglob("*")), "bytes": sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())}


def preflight():
    """Inspect the selected build interpreter. Never install or build anything."""
    import sysconfig
    if __package__:
        from .check_docx_support import check_docx_support
    else:
        from check_docx_support import check_docx_support

    expected = {}
    for line in (ROOT / "packaging/windows/requirements-build.txt").read_text(encoding="utf8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, version = line.split("==")
            expected[name] = version
    issues = []
    actual = {}
    for name, version in expected.items():
        try:
            actual[name] = metadata.version(name).strip()
        except metadata.PackageNotFoundError:
            actual[name] = None
        if actual[name] != version:
            issues.append("DEPENDENCY_VERSION_MISMATCH:" + name)
    if (sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}
            or platform.python_version() != "3.14.8"
            or sysconfig.get_config_var("Py_GIL_DISABLED")
            or (hasattr(sys, "_is_gil_enabled") and not sys._is_gil_enabled())):
        issues.append("REQUIRES_CPYTHON_3_14_8_WINDOWS_X64_STANDARD_GIL")
    imports = {}
    for name in ("PySide6.QtWidgets", "numpy", "scipy.optimize", "scipy.stats", "sqlite3", "lxml.etree"):
        try:
            __import__(name)
            imports[name] = "PASS"
        except (ImportError, OSError):
            imports[name] = "FAIL"
            issues.append("NATIVE_IMPORT_FAILED:" + name)
    try:
        docx = check_docx_support()
    except (ImportError, OSError, RuntimeError, ValueError):
        docx = {"status": "FAIL"}
        issues.append("DOCX_SUPPORT_UNAVAILABLE")
    required_sources = (
        "desktop/version.py", "desktop/integrations/case_context.py",
        "desktop/integrations/case_record.py", "desktop/integrations/case_report.py",
        "desktop/widgets/case_files.py", "desktop/widgets/research_workflow.py",
        "desktop/widgets/literature_evidence.py", "desktop/widgets/biolab_summary.py",
        "packaging/windows/launcher.py", "packaging/windows/workbench.spec",
    )
    resources = {}
    for relative in required_sources:
        source = ROOT / relative
        if not source.is_file():
            issues.append("SOURCE_RESOURCE_MISSING:" + relative)
        else:
            resources[relative] = digest(source)
    for relative in PROTEIN_RESOURCES:
        source = ROOT / "protein_engineering/resources/phase0" / relative
        if not source.is_file():
            issues.append("PROTEIN_RESOURCE_MISSING:" + relative)
        else:
            resources["protein_engineering/resources/phase0/" + relative] = digest(source)
    return dict(status="PASS" if not issues else "NOT_READY", issues=issues,
                python=platform.python_version(), architecture=platform.machine(),
                expected_versions=expected, actual_versions=actual, imports=imports,
                docx=docx, source_resources=resources,
                built_executable=False, public_distribution_allowed=False)


def main():
    import tomllib  # Build interpreter is pinned to 3.14.8; helpers also import on 3.10.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight-only", action="store_true",
                        help="Inspect dependencies and resources; do not snapshot or build")
    parser.add_argument("--iscc", type=Path)
    args = parser.parse_args()
    readiness = preflight()
    if args.preflight_only:
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
        return 0 if readiness["status"] == "PASS" else 1
    if readiness["status"] != "PASS":
        parser.error("Build preflight failed: " + ", ".join(readiness["issues"]))
    if args.output is None:
        parser.error("--output is required for a build")
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        parser.error("Build on native Windows x64")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "dist"):
        parser.error("Output must be under repository dist/")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if version != "4.1.0rc2":
        parser.error("This reviewed installer definition is for rc2 only; review stable naming and gates separately")
    output.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output / "source"
    source_hashes = snapshot(snapshot_dir)
    resources = output / "resources"; resources.mkdir()
    (resources / "VERSION.txt").write_text(version, encoding="ascii")
    (resources / "version_info.txt").write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=(4,1,0,2),prodvers=(4,1,0,2),mask=0x3f,flags=0x2,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),"
        "kids=[StringFileInfo([StringTable('040904B0',[StringStruct('FileDescription','BioResearch Workbench - Release Candidate'),"
        "StringStruct('FileVersion','4.1.0rc2'),StringStruct('ProductVersion','4.1.0rc2'),StringStruct('ProductName','BioResearch Workbench')])]),"
        "VarFileInfo([VarStruct('Translation',[1033,1200])])])", encoding="utf-8")
    inventory = notices(resources / "THIRD_PARTY_NOTICES")
    import os
    env = dict(os.environ, WORKBENCH_SOURCE=str(snapshot_dir), WORKBENCH_RESOURCES=str(resources), PYTHONPATH=str(snapshot_dir))
    # Do not accidentally redistribute DLLs from Codex/Conda/other apps on PATH.
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    env["PATH"] = os.pathsep.join(map(str, (Path(sys.executable).parent, Path(sys.base_prefix),
                                           Path(sys.base_prefix) / "DLLs", windows / "System32", windows)))
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(key, None)
    # cwd is the allowlisted snapshot, not the dirty source checkout.
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(output / "onedir"), "--workpath", str(output / "work"), str(snapshot_dir / "packaging/windows/workbench.spec")], cwd=snapshot_dir, env=env, check=True)
    bundle = output / "onedir/AntibodyResearchWorkbench"
    import ast
    toc = ast.literal_eval((output / "work/workbench/PYZ-00.toc").read_text(encoding="utf-8"))
    forbidden_prefixes = ("validation", "torch", "transformers", "ml.")
    for entry in toc[-1]:
        name = entry[0]
        if any(name == prefix or name.startswith(prefix + ".") or name.startswith("ml.") for prefix in forbidden_prefixes):
            raise ValueError("Forbidden module in executable archive: " + name)
    audit = audit_bundle(bundle)
    report = {"version": version, "stable_release": False, "python": platform.python_version(), "os": platform.platform(),
              "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "source_sha256": source_hashes, "bundle_audit": audit,
              "dependency_versions": {r["name"]: r["version"] for r in inventory},
              "clean_windows_test": "NOT_PERFORMED", "public_release": False}
    if args.iscc:
        subprocess.run([str(args.iscc.resolve()), f"/DAppVersion={version}", f"/DBundleDir={bundle}", f"/DOutputDir={output}", str(snapshot_dir / "packaging/windows/installer.iss")], check=True)
        installer = output / f"AntibodyResearchWorkbench-{version}-Windows-x64-Setup.exe"
        report["installer"] = {"filename": installer.name, "bytes": installer.stat().st_size, "sha256": digest(installer), "signed": False}
        (output / "SHA256SUMS.txt").write_text(digest(installer) + "  " + installer.name + "\n", encoding="ascii")
    (output / "build_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.get("installer", audit), indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
