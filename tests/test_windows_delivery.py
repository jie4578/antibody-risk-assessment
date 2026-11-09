"""Offline packaging tests; synthetic bytes, no installers or models executed."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

from tools.build_windows import audit_bundle, is_notice_file
from tools.collect_native_notices import archive_notices, collect
from tools.make_windows_portable import package


@pytest.mark.parametrize("name", ["openpyxl.dist-info/LICENCE.rst", "licenses/Apache-2.0.txt",
                                  "COPYING", "notice.txt"])
def test_notice_spellings(name):
    assert is_notice_file(name)


@pytest.mark.parametrize("name", ["licenses/__pycache__/__init__.pyc", "licenses/__init__.py",
                                  "package/core.py"])
def test_notices_exclude_code(name):
    assert not is_notice_file(name)


def test_snapshot_excludes_preserved_cli(monkeypatch, tmp_path):
    from tools import build_windows
    source = tmp_path / "source"
    (source / "literature").mkdir(parents=True)
    (source / "literature/cli.py").write_text("preserved local changes")
    (source / "literature/__init__.py").write_text("# public package")
    (source / "cli.py").write_text("preserved root CLI")
    monkeypatch.setattr(build_windows, "ROOT", source)
    monkeypatch.setattr(build_windows, "TOP_LEVEL", ())
    monkeypatch.setattr(build_windows, "DOCUMENTS", ())
    monkeypatch.setattr(build_windows, "PACKAGES", ("literature",))
    result = build_windows.snapshot(tmp_path / "snapshot")
    assert set(result) == {"literature/__init__.py"}


def test_upstream_comments_and_hashes_preserved(tmp_path):
    source = tmp_path / "source.tar.xz"
    payload = b'{\n// upstream comment\n"Copyright": "Example"\n}'
    with tarfile.open(source, "w:xz") as archive:
        member = tarfile.TarInfo("upstream/src/qt_attribution.json")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
        link = tarfile.TarInfo("upstream/LICENSE-link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/never/read/outside/archive"
        archive.addfile(link)
    assert archive_notices(source) == [("upstream/src/qt_attribution.json", payload.decode())]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"filename": source.name, "kind": "tar",
                        "url": "https://example.invalid/source", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}))
    first = collect(tmp_path, manifest)
    assert payload.decode() in first
    assert collect(tmp_path, manifest) == first
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        collect(tmp_path, manifest)


@pytest.fixture
def bundle(tmp_path):
    folder = tmp_path / "bundle"
    for name in ("AntibodyResearchWorkbench.exe", "_internal/THIRD_PARTY_NOTICES/native/NOTICES.txt",
                 "_internal/THIRD_PARTY_NOTICES/native/source_manifest.json",
                 "_internal/THIRD_PARTY_NOTICES/LGPL-3.0.txt"):
        file = folder / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"synthetic-not-executable")
    return folder


def test_portable_deterministic_and_content_preserved(bundle, tmp_path):
    a, b = tmp_path / "first.zip", tmp_path / "second.zip"
    first, second = package(bundle, a), package(bundle, b)
    assert first["sha256"] == second["sha256"]
    assert first["all_bundle_file_hashes_preserved"]
    with zipfile.ZipFile(a) as archive:
        assert archive.read("AntibodyResearchWorkbench/AntibodyResearchWorkbench.exe") == b"synthetic-not-executable"
        assert archive.testzip() is None
        assert all(not n.startswith("/") and ".." not in Path(n).parts for n in archive.namelist())
    with pytest.raises(ValueError, match="overwrite"):
        package(bundle, a)


def test_portable_requires_notices(bundle, tmp_path):
    (bundle / "_internal/THIRD_PARTY_NOTICES/native/NOTICES.txt").unlink()
    with pytest.raises(ValueError, match="notice missing"):
        package(bundle, tmp_path / "bad.zip")


@pytest.mark.parametrize("name", ["model.joblib", "labels.xlsx", ".env", "settings.json", "private.csv", "research.sqlite3", "research.sqlite3-wal", "research.sqlite3-shm", "research.sqlite3-journal", "protein-private-snapshot.json"])
def test_private_or_model_data_rejected(bundle, tmp_path, name):
    (bundle / name).write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="Forbidden files"):
        audit_bundle(bundle)
    with pytest.raises(ValueError, match="Forbidden files"):
        package(bundle, tmp_path / "bad.zip")
