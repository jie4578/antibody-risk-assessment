"""Synthetic files only: verify trust gates without loading models or labels."""
import json
from pathlib import Path

import pytest

from desktop import ml_deployment as deployment


@pytest.fixture
def config(tmp_path):
    directory = tmp_path / "models"; directory.mkdir()
    models = {}
    for i, key in enumerate(deployment.MODEL_IDS):
        file = directory / (key + ".joblib")
        file.write_bytes(b"synthetic non-pickle: never deserialize")
        models[key] = {"artifact": file.name, "artifact_sha256": deployment.file_hash(file),
                       "model_version": "phase5-frozen-v1", "feature_dimension": 1280,
                       "hyperparameter": {"alpha": 100.0} if i == 0 else {"C": 1.0, "penalty": "l2", "solver": "lbfgs"},
                       "training_row_count": 355 if i == 0 else 378}
    manifest = {"benchmark": deployment.BENCHMARK_ID, "phase5_finalization_commit": deployment.MODEL_MANIFEST_ID,
                "esm_model_name": deployment.ESM_MODEL_NAME, "esm_model_revision": deployment.ESM_MODEL_REVISION,
                "test_rows_used_for_training": 0, "models": models}
    path = directory / "model_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    hf = tmp_path / "hf"
    snapshot = hf / "hub/models--facebook--esm2_t30_150M_UR50D/snapshots" / deployment.ESM_MODEL_REVISION
    snapshot.mkdir(parents=True)
    for name in ("config.json", "tokenizer_config.json", "vocab.txt", "model.safetensors"):
        (snapshot / name).write_bytes(b"synthetic inventory only")
    return {"artifact_dir": str(directory), "hf_home": str(hf), "trusted_manifest_sha256": deployment.file_hash(path)}


def inspect(config):
    return deployment.inspect_deployment(config, dependency_versions={k: "synthetic" for k in deployment.REQUIRED_DEPENDENCIES.values()})


def test_not_installed_and_absent_dependencies_do_not_break_base():
    assert inspect({})["status"] == "NOT_INSTALLED"


def test_static_ready_never_deserializes(config, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Unexpected network"))
    first = inspect(config)
    assert first == inspect(config)
    assert first["status"] == "READY"
    assert first["deserialized"] is first["trained"] is first["predicted"] is False


@pytest.mark.parametrize("field,value,expected", [("artifact_dir", "missing", "ARTIFACT_MISSING"),
    ("trusted_manifest_sha256", "", "TRUST_REQUIRED"), ("trusted_manifest_sha256", "0" * 64, "HASH_MISMATCH"),
    ("hf_home", "missing", "ESM_CACHE_MISSING")])
def test_missing_or_untrusted_prerequisites(config, field, value, expected):
    config[field] = value
    assert inspect(config)["status"] == expected


def test_dependency_missing_is_not_ready(config):
    report = deployment.inspect_deployment(config, dependency_versions={})
    assert report["status"] == "DEPENDENCIES_MISSING"


def test_tampering_rejected_even_when_manifest_is_unchanged(config):
    (Path(config["artifact_dir"]) / "hic_esm2_v1.joblib").write_bytes(b"changed")
    assert inspect(config)["status"] == "HASH_MISMATCH"


@pytest.mark.parametrize("field,value", [("artifact", "../outside.joblib"), ("training_row_count", 999), ("hyperparameter", {"alpha": 1.0})])
def test_frozen_definitions_and_paths_fail_closed(config, field, value):
    path = Path(config["artifact_dir"]) / "model_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["models"]["hic_esm2_v1"][field] = value
    path.write_text(json.dumps(manifest))
    config["trusted_manifest_sha256"] = deployment.file_hash(path)
    assert inspect(config)["status"] == "MANIFEST_INVALID"


def test_settings_save_only_locations_and_digest(tmp_path):
    path = tmp_path / "config.json"
    deployment.save_config({"artifact_dir": "local", "api_key": "must-not-persist"}, path)
    assert "api_key" not in path.read_text()
    assert deployment.load_config(path)["artifact_dir"] == "local"


def test_panel_rejects_stale_completion(qt_application, tmp_path, monkeypatch):
    from desktop.widgets.ml_deployment import MLDeploymentPanel
    monkeypatch.setenv("APPDATA", str(tmp_path))
    page = MLDeploymentPanel()
    snapshot = page.values()
    page.artifact_dir.setText("changed")
    page._done(snapshot, {"status": "READY", "message": "ready"})
    assert "失效" in page.status.text()
    assert not deployment.config_path().exists()
    page.deleteLater()


def test_service_refuses_untrusted_real_predictor(monkeypatch):
    from desktop import ml_adapter
    monkeypatch.setattr(ml_adapter, "load_config", lambda: {})
    service = ml_adapter.DesktopMLService()
    with pytest.raises(ValueError, match="尚未安装"):
        service.predict("NNST", "ACD")
    assert service._predictor is None


def test_deployment_change_clears_summary_ml_evidence(qt_application):
    from desktop.widgets.single_analysis import SingleAnalysisPage
    page = SingleAnalysisPage()
    page._ml_result = {"old": "evidence"}
    generation = page._ml_generation
    page.notify_deployment_changed()
    assert page._ml_result is None
    assert page._ml_generation > generation
    page.deleteLater()


def test_frozen_science_unchanged():
    root = Path(__file__).resolve().parents[1]
    # LF-normalized c2b6d19 contents; works with a shallow CI checkout too.
    import hashlib
    baseline = {
        "core.py": "3be81969450ad7766519396373f56cfeac69c8590d06c1e33a6ebabbe6623e74",
        "scoring.py": "7139918dfe4f45afbc3149a598ec9c80255547d0fa6f0662a71b917ba86a3af0",
        "ml_inference/predictor.py": "fc51605d270954adf3625e245f82460bb74665aecffdffa6639cce1fb032f03a",
        "ml_inference/esm2_runtime.py": "b82328748fa0ee626feb18df6fe9d2d7152659c37840731a18e1c64318b931e6",
    }
    for name, digest in baseline.items():
        assert hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
