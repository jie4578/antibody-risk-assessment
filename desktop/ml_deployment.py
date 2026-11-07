"""Offline deployment prerequisites. Never deserialize, download, fit or predict."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

from desktop.ml_metadata import BENCHMARK_ID, MODEL_MANIFEST_ID, ESM_MODEL_NAME, ESM_MODEL_REVISION

MESSAGES = {
    "NOT_INSTALLED": "尚未安装可选 ML 模型。基础功能可直接使用；请到“设置 → 可选 ML 部署检查”查看说明。",
    "DEPENDENCIES_MISSING": "缺少推理依赖。基础安装版不包含 ESM2；请使用经单独验收的高级源码环境，勿向安装目录运行 pip。",
    "ARTIFACT_MISSING": "缺少冻结模型文件或 manifest。请向维护者取得可信的现有模型包，不要重新训练或重建。",
    "TRUST_REQUIRED": "请填写从独立可信渠道取得的 manifest SHA256。与文件一起提供的摘要不能自行证明来源可信。",
    "HASH_MISMATCH": "模型完整性验证失败，已拒绝使用。请核对独立可信摘要和原始文件。",
    "MANIFEST_INVALID": "模型描述不符合冻结部署定义，已拒绝使用。",
    "ESM_CACHE_MISSING": "缺少冻结 revision 的完整 ESM2 权重缓存。本检查不会自动下载。",
    "READY": "ML 静态部署检查通过；尚未执行模型加载或推理验收。",
    "ERROR": "无法完成部署检查。请检查目录访问权限；基础功能仍可使用。",
}
REQUIRED_DEPENDENCIES = {"torch": "torch", "transformers": "transformers", "huggingface_hub": "huggingface-hub", "joblib": "joblib", "numpy": "numpy", "sklearn": "scikit-learn"}
MODEL_IDS = ("hic_esm2_v1", "developability_esm2_v1")


def deployment_notice():
    if not load_config().get("artifact_dir"):
        return MESSAGES["NOT_INSTALLED"]
    return "已配置可选 ML 位置；请在“设置 → 可选 ML 部署检查”核对。基础安装版不含 ESM2 依赖。"


def config_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "AntibodyAI" / "ml_deployment.json"


def load_config(path: Path | None = None) -> dict:
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
        return {key: value for key, value in data.items() if key in {"artifact_dir", "hf_home", "trusted_manifest_sha256"} and isinstance(value, str)}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def save_config(data: dict, path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    allowed = {key: str(data.get(key, "")).strip() for key in ("artifact_dir", "hf_home", "trusted_manifest_sha256")}
    target.write_text(json.dumps(allowed, ensure_ascii=False, indent=2), encoding="utf-8")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dependencies() -> dict:
    result = {}
    for module, distribution in REQUIRED_DEPENDENCIES.items():
        try:
            result[distribution] = importlib.metadata.version(distribution) if importlib.util.find_spec(module) else None
        except (ImportError, ValueError, importlib.metadata.PackageNotFoundError):
            result[distribution] = None
    return result


def inspect_deployment(config: dict | None = None, *, dependency_versions: dict | None = None) -> dict:
    """Static availability only; READY is not a model/prediction qualification."""
    config = load_config() if config is None else config
    versions = dependencies() if dependency_versions is None else dependency_versions
    report = {"dependencies": versions, "predicted": False, "trained": False, "deserialized": False,
              "status": "NOT_INSTALLED", "esm_revision": ESM_MODEL_REVISION,
              "frozen_basic_installer": bool(getattr(sys, "frozen", False))}
    def result(code):
        return dict(report, status=code, message=MESSAGES[code])
    directory_text = config.get("artifact_dir", "")
    if not directory_text:
        return result("NOT_INSTALLED")
    directory = Path(directory_text)
    manifest_path = directory / "model_manifest.json"
    try:
        paths = [manifest_path] + [directory / (key + ".joblib") for key in MODEL_IDS]
        if not all(p.is_file() for p in paths):
            return result("ARTIFACT_MISSING")
        if any(p.is_symlink() or p.resolve().parent != directory.resolve() for p in paths):
            return result("MANIFEST_INVALID")
        trust = str(config.get("trusted_manifest_sha256", "")).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", trust):
            return result("TRUST_REQUIRED")
        if manifest_path.stat().st_size > 1024 * 1024 or file_hash(manifest_path) != trust:
            return result("HASH_MISMATCH")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {"benchmark": BENCHMARK_ID, "phase5_finalization_commit": MODEL_MANIFEST_ID,
                    "esm_model_name": ESM_MODEL_NAME, "esm_model_revision": ESM_MODEL_REVISION,
                    "test_rows_used_for_training": 0}
        if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in expected.items()):
            return result("MANIFEST_INVALID")
        models = manifest.get("models")
        if not isinstance(models, dict) or set(models) != set(MODEL_IDS):
            return result("MANIFEST_INVALID")
        for index, key in enumerate(MODEL_IDS):
            details = models[key]
            parameter = {"alpha": 100.0} if index == 0 else {"C": 1.0, "penalty": "l2", "solver": "lbfgs"}
            if (not isinstance(details, dict) or details.get("artifact") != key + ".joblib"
                    or details.get("feature_dimension") != 1280 or details.get("model_version") != "phase5-frozen-v1"
                    or details.get("hyperparameter") != parameter or details.get("training_row_count") != (355 if index == 0 else 378)):
                return result("MANIFEST_INVALID")
            if file_hash(directory / (key + ".joblib")) != details.get("artifact_sha256"):
                return result("HASH_MISMATCH")
        if not all(versions.get(name) for name in REQUIRED_DEPENDENCIES.values()):
            return result("DEPENDENCIES_MISSING")
        hf_home = Path(config.get("hf_home") or os.environ.get("HF_HOME") or (Path.home() / ".cache/huggingface"))
        snapshot = hf_home / "hub/models--facebook--esm2_t30_150M_UR50D/snapshots" / ESM_MODEL_REVISION
        required = [snapshot / name for name in ("config.json", "tokenizer_config.json", "vocab.txt")]
        weights = [snapshot / name for name in ("model.safetensors", "pytorch_model.bin")]
        if not all(p.is_file() and p.stat().st_size > 0 for p in required) or not any(p.is_file() and p.stat().st_size > 0 for p in weights):
            return result("ESM_CACHE_MISSING")
        return result("READY")
    except (OSError, ValueError, TypeError, AttributeError):
        return result("ERROR")
