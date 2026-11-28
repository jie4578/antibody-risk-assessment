"""Offline maintainer smoke contract; no science changes or external engines."""
import json
from hashlib import sha256
from pathlib import Path

import pytest

from desktop import installation_smoke as smoke


def authorized(tmp_path):
    source = tmp_path / "input.json"
    source.write_text("{}", encoding="utf-8")
    (tmp_path / "SMOKE_AUTHORIZATION.json").write_text(json.dumps({
        "purpose": "frozen-installation-smoke-v1", "case_id": "AB-RD-DEMO-001",
        "files": {"input.json": {"sha256": sha256(source.read_bytes()).hexdigest()}},
    }), encoding="utf-8")
    return tmp_path


def test_fixed_workspace_accepts_declared_synthetic_bytes(tmp_path):
    assert smoke._workspace(authorized(tmp_path)) == tmp_path.resolve()


def test_changed_fixture_is_rejected_before_execution(tmp_path):
    root = authorized(tmp_path)
    (root / "input.json").write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        smoke._workspace(root)


@pytest.mark.parametrize("path", ["../outside", "/outside", "C:/outside", "input\\other"])
def test_fixture_cannot_authorize_arbitrary_path(tmp_path, path):
    root = authorized(tmp_path)
    manifest = root / "SMOKE_AUTHORIZATION.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["files"] = {path: {"sha256": "0"*64}}
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="PATH_REJECTED"):
        smoke._workspace(root)


def test_rejects_non_demo_authorization(tmp_path):
    root = authorized(tmp_path)
    (root / "SMOKE_AUTHORIZATION.json").write_text('{"purpose":"other","case_id":"other"}', encoding="utf-8")
    with pytest.raises(ValueError, match="CONTRACT_REQUIRED"):
        smoke._workspace(root)


def test_result_writer_does_not_replace_existing_evidence(tmp_path):
    path = tmp_path / "result.json"
    smoke._write(path, {"first": True})
    old = path.read_bytes()
    with pytest.raises(FileExistsError):
        smoke._write(path, {"second": True})
    assert path.read_bytes() == old


def test_scientific_smoke_computes_and_reloads_original_contract(tmp_path):
    value = smoke._scientific(tmp_path)
    assert value["status"] == "PASS"
    assert value["c2a"]["metadata"]["initial_rate_validity"] == "NOT_ESTABLISHED"
    assert value["chi2"]["output"] == pytest.approx(3.841458820694124, abs=1e-13)
    for name in ("Km", "Vmax"):
        actual = value["conditional_intervals"]["parameters"][name]
        assert actual["lower"] == pytest.approx(value["independent_reference"][name][0], rel=1e-8)
        assert actual["upper"] == pytest.approx(value["independent_reference"][name][1], rel=1e-8)


def test_launcher_only_accepts_fixed_smoke_phases():
    import ast
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "packaging/windows/launcher.py").read_text(encoding="utf-8"))
    allowed = [node for node in ast.walk(tree) if isinstance(node, ast.keyword) and node.arg == "choices"]
    assert len(allowed) == 1
    assert ast.literal_eval(allowed[0].value) == ("basic", "create", "restore")
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval","exec"}
                   for node in ast.walk(tree))
