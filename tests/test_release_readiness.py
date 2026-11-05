"""No-training regression for the read-only deployment inspector."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deployment_check", ROOT / "tools/check_ml_deployment.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


@pytest.fixture
def artifacts(tmp_path):
    models = {}
    for index, key in enumerate(check.MODEL_IDS):
        path = tmp_path / (key + ".joblib")
        path.write_bytes(b"not a pickle: inventory must never deserialize this")
        models[key] = {"artifact": path.name, "artifact_sha256": check.sha256(path),
                       "feature_dimension": 1280, "model_version": "phase5-frozen-v1",
                       "hyperparameter": {"alpha": 100.0} if index == 0 else {"C": 1.0, "penalty": "l2", "solver": "lbfgs"},
                       "training_row_count": 355 if index == 0 else 378}
    manifest = {"benchmark": check.BENCHMARK, "phase5_finalization_commit": check.PHASE5,
                "esm_model_name": check.MODEL, "esm_model_revision": check.REVISION,
                "test_rows_used_for_training": 0, "models": models}
    (tmp_path / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path, manifest


def rewrite(directory, manifest):
    (directory / "model_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_inventory_is_deterministic_and_does_not_deserialize(artifacts):
    directory, _ = artifacts
    first = check.inspect_artifacts(directory)
    assert first == check.inspect_artifacts(directory)
    assert first["manifest_sha256"] == hashlib.sha256((directory / "model_manifest.json").read_bytes()).hexdigest()
    assert set(first["models"]) == set(check.MODEL_IDS)


@pytest.mark.parametrize("field,value", [("esm_model_revision", "wrong"), ("benchmark", "wrong"), ("test_rows_used_for_training", 1)])
def test_manifest_provenance_fails_closed(artifacts, field, value):
    directory, manifest = artifacts
    manifest[field] = value
    rewrite(directory, manifest)
    with pytest.raises(ValueError, match="provenance"):
        check.inspect_artifacts(directory)


@pytest.mark.parametrize("filename", ["../outside.joblib", "/absolute.joblib", "another.joblib"])
def test_artifact_path_is_exact_basename(artifacts, filename):
    directory, manifest = artifacts
    manifest["models"][check.MODEL_IDS[0]]["artifact"] = filename
    rewrite(directory, manifest)
    with pytest.raises(ValueError, match="basename"):
        check.inspect_artifacts(directory)


def test_corrupted_artifact_is_rejected(artifacts):
    directory, _ = artifacts
    (directory / (check.MODEL_IDS[0] + ".joblib")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        check.inspect_artifacts(directory)


def test_load_requires_independent_trust_before_joblib_import(artifacts):
    directory, _ = artifacts
    with pytest.raises(ValueError, match="trusted"):
        check.synthetic_smoke(directory, "")


def test_zero_size_cache_does_not_claim_ready(tmp_path):
    snapshot = tmp_path / "hub/models--facebook--esm2_t30_150M_UR50D/snapshots" / check.REVISION
    snapshot.mkdir(parents=True)
    for name in ("config.json", "tokenizer_config.json", "vocab.txt", "model.safetensors"):
        (snapshot / name).touch()
    assert not check.inspect_cache(tmp_path)["ready"]
    for file in snapshot.iterdir():
        file.write_text("synthetic file for inventory only", encoding="utf-8")
    assert check.inspect_cache(tmp_path)["ready"]


def test_frozen_definition_changes_are_rejected(artifacts):
    directory, manifest = artifacts
    manifest["models"][check.MODEL_IDS[0]]["hyperparameter"] = {"alpha": 1.0}
    rewrite(directory, manifest)
    with pytest.raises(ValueError, match="definition"):
        check.inspect_artifacts(directory)


def test_public_inspector_failure_does_not_leak_local_paths(tmp_path, capsys):
    assert check.main(["--artifact-dir", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert str(tmp_path) not in output
    report = json.loads(output)
    assert report["trained"] is report["performance_calculated"] is report["test_labels_accessed"] is False
    assert report["status"] == "FAIL"


def test_optional_smoke_blocks_network_before_any_model_work(monkeypatch, tmp_path):
    import socket

    def attempted_connection(*args, **kwargs):
        socket.create_connection(("example.invalid", 443))

    monkeypatch.setattr(check, "_synthetic_smoke", attempted_connection)
    with pytest.raises(RuntimeError, match="forbids networking"):
        check.synthetic_smoke(tmp_path, "not-used")
