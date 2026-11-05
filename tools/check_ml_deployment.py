"""Read-only, offline checks for trusted existing frozen ML deployment files.

Default: hashes/metadata/dependency/cache inventory only. No deserialization,
fit, label access, network download or prediction. An optional, explicitly
trusted synthetic smoke uses existing estimators; it never reports accuracy.
Run from the source checkout or sdist, not an assumed wheel console command.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import warnings
from unittest.mock import patch


REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
MODEL = "facebook/esm2_t30_150M_UR50D"
BENCHMARK = "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
PHASE5 = "7826881c04887d274f73e737caf35d83e7b62dd2"
MODEL_IDS = ("hic_esm2_v1", "developability_esm2_v1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_artifacts(directory: Path) -> dict:
    manifest_path = directory / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid manifest object")
    expected = {"benchmark": BENCHMARK, "phase5_finalization_commit": PHASE5,
                "esm_model_name": MODEL, "esm_model_revision": REVISION,
                "test_rows_used_for_training": 0}
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Frozen provenance mismatch")
    models = manifest.get("models")
    if not isinstance(models, dict) or set(models) != set(MODEL_IDS):
        raise ValueError("Expected exactly the two frozen model IDs")
    result = {}
    for model_id in MODEL_IDS:
        details = models[model_id]
        filename = model_id + ".joblib"
        if not isinstance(details, dict) or details.get("artifact") != filename:
            raise ValueError("Artifact must use its exact local basename")
        path = directory / filename
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise ValueError("Artifact must remain within the trusted directory")
        digest = sha256(path)
        if digest != details.get("artifact_sha256"):
            raise ValueError("Artifact checksum mismatch: " + model_id)
        expected_parameter = {"alpha": 100.0} if model_id == MODEL_IDS[0] else {"C": 1.0, "penalty": "l2", "solver": "lbfgs"}
        expected_n = 355 if model_id == MODEL_IDS[0] else 378
        if (details.get("feature_dimension") != 1280
                or details.get("model_version") != "phase5-frozen-v1"
                or details.get("hyperparameter") != expected_parameter
                or details.get("training_row_count") != expected_n):
            raise ValueError("Frozen model definition mismatch: " + model_id)
        result[model_id] = {"sha256": digest, "bytes": path.stat().st_size,
                            "feature_dimension": 1280, "training_n": expected_n}
    return {"manifest_sha256": sha256(manifest_path), "models": result}


def inspect_cache(hf_home: Path) -> dict:
    snapshot = hf_home / "hub" / "models--facebook--esm2_t30_150M_UR50D" / "snapshots" / REVISION
    names = ("config.json", "tokenizer_config.json", "vocab.txt")
    readable = {name: (snapshot / name).is_file() and (snapshot / name).stat().st_size > 0 for name in names}
    weights = any((snapshot / name).is_file() and (snapshot / name).stat().st_size > 0
                  for name in ("model.safetensors", "pytorch_model.bin"))
    return {"revision": REVISION, "required_files_nonempty": readable,
            "nonempty_single_file_weights": weights, "ready": all(readable.values()) and weights,
            "sharded_weights_qualified": False}


def dependency_inventory() -> dict:
    packages = ("torch", "transformers", "huggingface-hub", "numpy", "scikit-learn", "joblib")
    result = {}
    for name in packages:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def _synthetic_smoke(directory: Path, trust: str, *, esm: bool = False, hf_home: Path | None = None) -> dict:
    # A digest supplied by the same untrusted download is not proof of trust.
    # The caller must obtain it separately from its approved local provenance.
    checked = inspect_artifacts(directory)
    if not trust or trust.lower() != checked["manifest_sha256"]:
        raise ValueError("A separately trusted manifest SHA256 is required before loading pickle/joblib")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if hf_home is not None:
        os.environ["HF_HOME"] = str(hf_home)
    import joblib
    import numpy as np
    # Do not silently claim serialization compatibility across sklearn releases.
    from sklearn.exceptions import InconsistentVersionWarning
    with warnings.catch_warnings():
        warnings.simplefilter("error", InconsistentVersionWarning)
        loaded = {key: joblib.load(directory / (key + ".joblib")) for key in MODEL_IDS}
    representation = np.zeros((1, 1280), dtype=np.float32)
    runtime_origin = "not_loaded"
    if esm:
        if hf_home is None or not inspect_cache(hf_home)["ready"]:
            raise ValueError("Frozen ESM cache incomplete; downloading is not permitted")
        import torch
        # Prefer the installed wheel. Use source only if no installation exists,
        # and report that distinction instead of silently claiming wheel coverage.
        if importlib.util.find_spec("ml_inference") is None:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import ml_inference.esm2_runtime as runtime
        runtime_origin = "installed" if "site-packages" in Path(runtime.__file__).parts else "source"
        from ml_inference.esm2_runtime import extract_pair, load_frozen_model
        tokenizer, model, revision, meta = load_frozen_model(MODEL, REVISION)
        representation = extract_pair("NNSTACDEFGHIK", "ACDEFGHIKLMNP", tokenizer, model, torch, torch.device(meta["device"]))
        repeated = extract_pair("NNSTACDEFGHIK", "ACDEFGHIKLMNP", tokenizer, model, torch, torch.device(meta["device"]))
        if revision != REVISION or not np.array_equal(representation, repeated):
            raise ValueError("Frozen representation repeatability check failed")
    hic = np.asarray(loaded[MODEL_IDS[0]].predict(representation))
    classifier = loaded[MODEL_IDS[1]]
    probability = np.asarray(classifier.predict_proba(representation))
    if (hic.shape != (1,) or not np.isfinite(hic).all()
            or probability.shape != (1, 2) or not np.isfinite(probability).all()
            or not ((probability >= 0) & (probability <= 1)).all()
            or not np.allclose(probability.sum(axis=1), 1.0)
            or list(classifier.classes_) != [0, 1]):
        raise ValueError("Synthetic estimator output contract failed")
    return {"loaded_models": list(loaded), "input": "synthetic_only", "esm_executed": esm,
            "runtime_origin": runtime_origin,
            "representation_shape": list(representation.shape), "output_contract": "PASS",
            "performance_calculated": False, "trained": False}


def synthetic_smoke(directory: Path, trust: str, *, esm: bool = False, hf_home: Path | None = None) -> dict:
    # Process-local network guard, not a change to system/provider settings.
    with patch("socket.socket.connect", side_effect=RuntimeError("Offline smoke forbids networking")), \
         patch("socket.socket.connect_ex", side_effect=RuntimeError("Offline smoke forbids networking")), \
         patch("socket.create_connection", side_effect=RuntimeError("Offline smoke forbids networking")), \
         patch("socket.getaddrinfo", side_effect=RuntimeError("Offline smoke forbids networking")):
        result = _synthetic_smoke(directory, trust, esm=esm, hf_home=hf_home)
    return dict(result, network_connections_blocked=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--hf-home", type=Path, default=Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")))
    parser.add_argument("--synthetic-smoke", action="store_true")
    parser.add_argument("--esm-offline-smoke", action="store_true")
    parser.add_argument("--trusted-manifest-sha256", default="")
    args = parser.parse_args(argv)
    report = {"python": platform.python_version(), "platform": platform.system(),
              "dependencies": dependency_inventory(), "trained": False,
              "performance_calculated": False, "test_labels_accessed": False}
    try:
        report["artifacts"] = inspect_artifacts(args.artifact_dir)
        report["cache"] = inspect_cache(args.hf_home)
        if args.synthetic_smoke or args.esm_offline_smoke:
            report["smoke"] = synthetic_smoke(args.artifact_dir, args.trusted_manifest_sha256,
                                               esm=args.esm_offline_smoke, hf_home=args.hf_home)
        report["status"] = "PASS" if report["cache"]["ready"] and all(report["dependencies"].values()) else "INCOMPLETE_ENVIRONMENT"
    except Exception as error:
        # Public report omits paths/credentials and raw exception messages.
        report.update(status="FAIL", error_type=type(error).__name__)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
