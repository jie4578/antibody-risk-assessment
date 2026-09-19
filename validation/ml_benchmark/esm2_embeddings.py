"""Frozen ESM-2 representation extraction for the Phase 5B benchmark.

The module is intentionally isolated from production scientific code.  It
accepts only sequence/identity fields, never opens the sealed test-label file,
and contains no estimator, metric, scaler, PCA, or outcome-analysis logic.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from validation.ml_benchmark_spec_v1_2 import BENCHMARK_NAME, SPEC_VERSION


MODEL_NAME = "facebook/esm2_t30_150M_UR50D"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "validation/data/ml_benchmark/entity_exact_v1/embeddings"
HIDDEN_DIMENSION = 640
VH_DIMENSION = 640
VL_DIMENSION = 640
PAIRED_DIMENSION = 1280
INFERENCE_BATCH_SIZE = 8
DETERMINISTIC_SEED = 20260919
PRECISION = "float32"
CHAIN_ORDER = ("VH", "VL")
ALLOWED_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
EXPECTED_SPLIT_COUNTS = {"TRAIN": 285, "VALIDATION": 96, "TEST": 95}
SPLIT_FILES = {
    "TRAIN": "train_population.csv",
    "VALIDATION": "validation_features.csv",
    "TEST": "test_features.csv",
}
SAFE_IDENTITY_COLUMNS = (
    "dataset",
    "sequence_hash",
    "representative_record_id",
    "antibody_id",
    "VH",
    "VL",
    "record_type",
    "challenge",
    "source_record_count",
    "duplicate_resolution",
    "source_record_ids",
    "component_id",
    "split",
)
FORBIDDEN_OUTCOME_COLUMNS = frozenset(
    {
        "Tm",
        "Tagg",
        "HIC",
        "BVP",
        "AC-SINS",
        "Tm, C",
        "Tagg, C",
        "HIC RT in gradient (min)",
        "average BVP score",
        "average dPW",
        "total_developability_score",
        "composite_class",
        "derived_binary_status",
        "SPR",
        "KinExA",
        "KD",
        "KD_SPR",
        "KD_KinExA",
        "Mean KD (M)",
    }
)
AA_PATTERN = set(ALLOWED_AMINO_ACIDS)


class EmbeddingInputError(ValueError):
    """Raised when a sequence input violates the frozen extraction contract."""


class ModelProvenanceError(RuntimeError):
    """Raised when an exact model revision cannot be recorded."""


@dataclass(frozen=True)
class SplitInput:
    name: str
    frame: pd.DataFrame


@dataclass(frozen=True)
class EmbeddingResult:
    sequence_hashes: np.ndarray
    vh_embeddings: np.ndarray
    vl_embeddings: np.ndarray
    paired_embeddings: np.ndarray
    batch_size_used: int


def embedding_feature_names() -> list[str]:
    """Return the frozen paired feature names in VH-then-VL order."""

    return [f"ESM_VH_{index:04d}" for index in range(VH_DIMENSION)] + [
        f"ESM_VL_{index:04d}" for index in range(VL_DIMENSION)
    ]


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_sequence(value: object, sequence_hash: str, chain: str) -> str:
    sequence = _clean(value).upper()
    if not sequence:
        raise EmbeddingInputError(f"Missing {chain} sequence for {sequence_hash}")
    unsupported = sorted(set(sequence) - AA_PATTERN)
    if unsupported:
        raise EmbeddingInputError(
            f"Unsupported {chain} residue(s) for {sequence_hash}: {''.join(unsupported)}"
        )
    return sequence


def validate_embedding_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Guard and normalize only the sequence fields used by the extractor."""

    required = {"sequence_hash", "VH", "VL"}
    missing = required - set(frame.columns)
    if missing:
        raise EmbeddingInputError(f"Missing embedding input columns: {sorted(missing)}")
    forbidden = sorted(FORBIDDEN_OUTCOME_COLUMNS.intersection(frame.columns))
    if forbidden:
        raise EmbeddingInputError(f"Outcome fields are forbidden in embedding input: {forbidden}")
    unexpected = sorted(set(frame.columns) - set(SAFE_IDENTITY_COLUMNS))
    if unexpected:
        raise EmbeddingInputError(f"Non-identity fields are forbidden in embedding input: {unexpected}")
    result = frame.copy()
    result["sequence_hash"] = result["sequence_hash"].map(_clean)
    if (result["sequence_hash"] == "").any():
        raise EmbeddingInputError("sequence_hash cannot be empty")
    if result["sequence_hash"].duplicated().any():
        raise EmbeddingInputError("Duplicate sequence_hash in one embedding split")
    result["VH"] = [normalize_sequence(value, key, "VH") for key, value in zip(result["sequence_hash"], result["VH"])]
    result["VL"] = [normalize_sequence(value, key, "VL") for key, value in zip(result["sequence_hash"], result["VL"])]
    return result.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)


def sequence_hash_manifest_sha256(sequence_hashes: Iterable[str]) -> str:
    ordered = [str(value) for value in sequence_hashes]
    return hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_pool_residue_tokens(
    hidden_states: np.ndarray,
    attention_mask: np.ndarray,
    special_tokens_mask: np.ndarray,
) -> np.ndarray:
    """Mean-pool only attended non-special residue tokens."""

    hidden = np.asarray(hidden_states, dtype=np.float32)
    attention = np.asarray(attention_mask, dtype=bool)
    special = np.asarray(special_tokens_mask, dtype=bool)
    if hidden.ndim != 3 or attention.ndim != 2 or special.ndim != 2:
        raise EmbeddingInputError("Unexpected tokenizer/model tensor dimensions")
    if hidden.shape[:2] != attention.shape or attention.shape != special.shape:
        raise EmbeddingInputError("Tokenizer masks do not match hidden states")
    residue_mask = attention & ~special
    counts = residue_mask.sum(axis=1)
    if (counts == 0).any():
        raise EmbeddingInputError("A tokenized sequence has no residue tokens")
    pooled = (hidden * residue_mask[:, :, None]).sum(axis=1) / counts[:, None]
    return np.asarray(pooled, dtype=np.float32)


def _torch_from_module(value: Any, device: Any) -> Any:
    return value.to(device) if hasattr(value, "to") else value


def _run_model_batch(
    sequences: list[str],
    tokenizer: Any,
    model: Any,
    torch_module: Any,
    device: Any,
) -> np.ndarray:
    encoded = tokenizer(
        sequences,
        padding=True,
        truncation=False,
        return_attention_mask=True,
        return_special_tokens_mask=True,
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    special_tokens_mask = encoded["special_tokens_mask"]
    max_positions = getattr(getattr(model, "config", None), "max_position_embeddings", None)
    if max_positions is not None and int(input_ids.shape[1]) > int(max_positions):
        raise EmbeddingInputError(
            f"Tokenized sequence batch length {int(input_ids.shape[1])} exceeds model limit {int(max_positions)}"
        )
    model_inputs = {
        "input_ids": _torch_from_module(input_ids, device),
        "attention_mask": _torch_from_module(attention_mask, device),
    }
    with torch_module.inference_mode():
        outputs = model(**model_inputs)
    hidden = outputs.last_hidden_state if hasattr(outputs, "last_hidden_state") else outputs[0]
    hidden = hidden.detach().float().cpu().numpy()
    attention = attention_mask.detach().cpu().numpy()
    special = special_tokens_mask.detach().cpu().numpy()
    return mean_pool_residue_tokens(hidden, attention, special)


def embed_chain(
    sequences: list[str],
    tokenizer: Any,
    model: Any,
    torch_module: Any,
    device: Any,
    batch_size: int = INFERENCE_BATCH_SIZE,
) -> tuple[np.ndarray, int]:
    """Embed one chain, reducing only computational batch size after OOM."""

    current = int(batch_size)
    while current >= 1:
        try:
            batches = []
            for start in range(0, len(sequences), current):
                batches.append(_run_model_batch(sequences[start : start + current], tokenizer, model, torch_module, device))
            output = np.concatenate(batches, axis=0) if batches else np.empty((0, HIDDEN_DIMENSION), dtype=np.float32)
            if output.shape[1] != HIDDEN_DIMENSION:
                raise EmbeddingInputError(f"Expected hidden dimension {HIDDEN_DIMENSION}, got {output.shape[1]}")
            return output.astype(np.float32, copy=False), current
        except RuntimeError as error:
            message = str(error).lower()
            if "out of memory" not in message or current == 1:
                raise
            if hasattr(torch_module, "cuda") and getattr(torch_module.cuda, "is_available", lambda: False)():
                torch_module.cuda.empty_cache()
            current = max(1, current // 2)
    raise RuntimeError("Unable to embed chain")


def extract_paired_embeddings(
    frame: pd.DataFrame,
    tokenizer: Any,
    model: Any,
    torch_module: Any,
    device: Any,
    batch_size: int = INFERENCE_BATCH_SIZE,
) -> EmbeddingResult:
    """Extract VH and VL separately, then concatenate VH before VL."""

    safe = validate_embedding_input(frame)
    model.eval()
    vh, vh_batch = embed_chain(safe["VH"].tolist(), tokenizer, model, torch_module, device, batch_size)
    vl, vl_batch = embed_chain(safe["VL"].tolist(), tokenizer, model, torch_module, device, batch_size)
    if vh.shape != (len(safe), VH_DIMENSION) or vl.shape != (len(safe), VL_DIMENSION):
        raise EmbeddingInputError("Unexpected VH/VL embedding shape")
    paired = np.concatenate([vh, vl], axis=1).astype(np.float32, copy=False)
    if paired.shape != (len(safe), PAIRED_DIMENSION):
        raise EmbeddingInputError("Unexpected paired embedding shape")
    if not np.isfinite(paired).all() or not np.isfinite(vh).all() or not np.isfinite(vl).all():
        raise EmbeddingInputError("Embedding output contains NaN or Inf")
    norms = np.linalg.norm(paired, axis=1)
    if not np.isfinite(norms).all() or (norms <= 0).any():
        raise EmbeddingInputError("Embedding output contains a zero or non-finite norm")
    if len(paired) > 1 and float(np.var(paired)) <= 0.0:
        raise EmbeddingInputError("Embedding output has zero variance across the dataset")
    return EmbeddingResult(
        sequence_hashes=safe["sequence_hash"].to_numpy(dtype=str),
        vh_embeddings=vh,
        vl_embeddings=vl,
        paired_embeddings=paired,
        batch_size_used=min(vh_batch, vl_batch),
    )


def set_deterministic_seed(torch_module: Any, seed: int = DETERMINISTIC_SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch_module.manual_seed(seed)
    if hasattr(torch_module, "cuda") and torch_module.cuda.is_available():
        torch_module.cuda.manual_seed_all(seed)
    torch_module.use_deterministic_algorithms(True)


def choose_device(torch_module: Any) -> tuple[Any, str, str | None, str | None]:
    if torch_module.cuda.is_available():
        device = torch_module.device("cuda")
        return device, "cuda", torch_module.cuda.get_device_name(device), torch_module.version.cuda
    return torch_module.device("cpu"), "cpu", None, None


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def runtime_provenance(torch_module: Any, device_name: str, gpu_name: str | None, cuda_version: str | None) -> dict[str, Any]:
    return {
        "python_version": platform.python_version(),
        "torch_version": _package_version("torch"),
        "transformers_version": _package_version("transformers"),
        "huggingface_hub_version": _package_version("huggingface-hub"),
        "device": device_name,
        "gpu_name": gpu_name,
        "cuda_version": cuda_version,
        "torch_float32": True,
    }


def resolve_model_revision(model_name: str = MODEL_NAME) -> str:
    """Resolve and require an immutable Hub commit SHA."""

    try:
        from huggingface_hub import model_info
    except ImportError as error:
        raise ModelProvenanceError("huggingface_hub is required to resolve model provenance") from error
    info = model_info(model_name)
    revision = getattr(info, "sha", None)
    if not revision or len(str(revision)) < 20:
        raise ModelProvenanceError(f"Could not resolve immutable revision for {model_name}")
    return str(revision)


def load_frozen_model(model_name: str = MODEL_NAME, revision: str | None = None) -> tuple[Any, Any, str, dict[str, Any]]:
    """Load the tokenizer/model at a resolved immutable revision."""

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as error:
        raise ModelProvenanceError("torch and transformers are required for live ESM-2 extraction") from error
    resolved = revision or resolve_model_revision(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=resolved)
    model = AutoModel.from_pretrained(model_name, revision=resolved, torch_dtype=torch.float32)
    if int(getattr(model.config, "hidden_size", -1)) != HIDDEN_DIMENSION:
        raise ModelProvenanceError(f"Expected hidden size {HIDDEN_DIMENSION}, got {model.config.hidden_size}")
    device, device_name, gpu_name, cuda_version = choose_device(torch)
    model = model.to(device)
    model.eval()
    set_deterministic_seed(torch)
    provenance = runtime_provenance(torch, device_name, gpu_name, cuda_version)
    provenance.update(
        {
            "repository": model_name,
            "resolved_model_revision": resolved,
            "model_class": model.__class__.__name__,
            "tokenizer_class": tokenizer.__class__.__name__,
            "model_name": model_name,
        }
    )
    return tokenizer, model, resolved, provenance


def _read_safe_csv(path: Path) -> pd.DataFrame:
    header = pd.read_csv(path, dtype=str, nrows=0)
    usecols = [column for column in SAFE_IDENTITY_COLUMNS if column in header.columns]
    return pd.read_csv(path, dtype=str, usecols=usecols)


def load_frozen_split_inputs(root: str | Path) -> dict[str, SplitInput]:
    """Read only frozen split feature inputs; never open sealed labels."""

    base = Path(root) / "validation/data/ml_benchmark/entity_exact_v1"
    result: dict[str, SplitInput] = {}
    for split, filename in SPLIT_FILES.items():
        frame = validate_embedding_input(_read_safe_csv(base / filename))
        if len(frame) != EXPECTED_SPLIT_COUNTS[split]:
            raise EmbeddingInputError(f"{split} expected {EXPECTED_SPLIT_COUNTS[split]} rows, got {len(frame)}")
        if "split" in frame.columns and set(frame["split"].dropna()) != {split}:
            raise EmbeddingInputError(f"{split} input has an unexpected split value")
        result[split] = SplitInput(split, frame)
    return result


def verify_frozen_hash_alignment(root: str | Path, inputs: Mapping[str, SplitInput]) -> None:
    base = Path(root) / "validation/data/ml_benchmark/entity_exact_v1"
    manifest = pd.read_csv(base / "split_manifest.csv", dtype=str, usecols=["sequence_hash", "split"])
    for split, item in inputs.items():
        expected = sorted(manifest.loc[manifest["split"] == split, "sequence_hash"].tolist())
        actual = item.frame["sequence_hash"].tolist()
        if actual != expected:
            raise EmbeddingInputError(f"{split} sequence hashes do not match frozen split manifest")


def verify_rule48_alignment(root: str | Path, inputs: Mapping[str, SplitInput]) -> dict[str, int]:
    path = Path(root) / "validation/data/features/aintibody_rule_features.csv"
    rule = pd.read_csv(path, dtype=str, usecols=["sequence_hash"])
    known = set(rule["sequence_hash"].dropna().astype(str))
    result = {}
    for split, item in inputs.items():
        matched = sum(value in known for value in item.frame["sequence_hash"])
        result[split] = int(matched)
        if matched != len(item.frame):
            raise EmbeddingInputError(f"RULE48 alignment failed for {split}: {matched}/{len(item.frame)}")
    result["unmatched"] = 0
    return result


def write_embedding_file(path: str | Path, result: EmbeddingResult) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        sequence_hashes=result.sequence_hashes,
        vh_embeddings=result.vh_embeddings.astype(np.float32, copy=False),
        vl_embeddings=result.vl_embeddings.astype(np.float32, copy=False),
        paired_embeddings=result.paired_embeddings.astype(np.float32, copy=False),
    )


def write_embedding_index(path: str | Path, inputs: Mapping[str, SplitInput]) -> None:
    rows = []
    for split in ("TRAIN", "VALIDATION", "TEST"):
        frame = inputs[split].frame
        for row_index, row in enumerate(frame.itertuples(index=False)):
            rows.append(
                {
                    "sequence_hash": row.sequence_hash,
                    "split": split,
                    "row_index": row_index,
                    "VH_length": len(row.VH),
                    "VL_length": len(row.VL),
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")


def verify_length_control_alignment(index_path: str | Path, inputs: Mapping[str, SplitInput]) -> dict[str, int]:
    """Verify index lengths are reproducible directly from canonical sequences."""

    index = pd.read_csv(index_path, dtype={"sequence_hash": str, "split": str})
    required = {"sequence_hash", "split", "row_index", "VH_length", "VL_length"}
    if not required.issubset(index.columns):
        raise EmbeddingInputError(f"Embedding index is missing length fields: {sorted(required - set(index.columns))}")
    result: dict[str, int] = {}
    for split, item in inputs.items():
        expected = item.frame[["sequence_hash", "VH", "VL"]].copy()
        observed = index.loc[index["split"] == split].sort_values("row_index", kind="mergesort")
        if len(observed) != len(expected):
            raise EmbeddingInputError(f"Length-control row count mismatch for {split}")
        if observed["sequence_hash"].tolist() != expected["sequence_hash"].tolist():
            raise EmbeddingInputError(f"Length-control hash mismatch for {split}")
        vh_expected = expected["VH"].map(len).tolist()
        vl_expected = expected["VL"].map(len).tolist()
        if observed["VH_length"].astype(int).tolist() != vh_expected:
            raise EmbeddingInputError(f"VH length-control mismatch for {split}")
        if observed["VL_length"].astype(int).tolist() != vl_expected:
            raise EmbeddingInputError(f"VL length-control mismatch for {split}")
        result[split] = len(expected)
    result["mismatched"] = 0
    return result


def repeatability_audit(
    frame: pd.DataFrame,
    tokenizer: Any,
    model: Any,
    torch_module: Any,
    device: Any,
    sample_size: int = 10,
) -> dict[str, Any]:
    subset = validate_embedding_input(frame).head(sample_size)
    first = extract_paired_embeddings(subset, tokenizer, model, torch_module, device)
    second = extract_paired_embeddings(subset, tokenizer, model, torch_module, device)
    difference = np.abs(first.paired_embeddings - second.paired_embeddings)
    maximum = float(difference.max()) if difference.size else 0.0
    mean = float(difference.mean()) if difference.size else 0.0
    return {
        "sample_n": int(len(subset)),
        "max_absolute_difference": maximum,
        "mean_absolute_difference": mean,
        "tolerance": 1e-5,
        "passed": bool(maximum <= 1e-5),
    }


def build_manifest(
    outputs: Mapping[str, Path],
    results: Mapping[str, EmbeddingResult],
    provenance: Mapping[str, Any],
    rule48_alignment: Mapping[str, int],
    length_control_alignment: Mapping[str, int],
    repeatability: Mapping[str, Any],
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "benchmark_name": BENCHMARK_NAME,
        "benchmark_spec_version": SPEC_VERSION,
        "model_name": MODEL_NAME,
        "resolved_model_revision": provenance["resolved_model_revision"],
        "hidden_dimension": HIDDEN_DIMENSION,
        "VH_dimension": VH_DIMENSION,
        "VL_dimension": VL_DIMENSION,
        "paired_dimension": PAIRED_DIMENSION,
        "pooling": "final hidden state; exclude BOS/EOS/special/padding; mean-pool residue tokens",
        "chain_order": list(CHAIN_ORDER),
        "feature_names": embedding_feature_names(),
        "precision": PRECISION,
        "batch_size": max(result.batch_size_used for result in results.values()),
        "seed": DETERMINISTIC_SEED,
        "rule48_alignment": dict(rule48_alignment),
        "length_control_alignment": dict(length_control_alignment),
        "repeatability": dict(repeatability),
        "test_labels_accessed": False,
        "embedding_files_contain_outcomes": False,
        "scaler_fitted": False,
        "pca_performed": False,
        "ml_model_trained": False,
        "ml_performance_calculated": False,
        "provenance": dict(provenance),
        "splits": {},
    }
    for field in (
        "device",
        "gpu_name",
        "cuda_version",
        "transformers_version",
        "torch_version",
        "python_version",
    ):
        manifest[field] = provenance.get(field)
    for split in ("TRAIN", "VALIDATION", "TEST"):
        result = results[split]
        path = outputs[split]
        manifest["splits"][split] = {
            "row_count": int(len(result.sequence_hashes)),
            "sequence_hash_manifest_sha256": sequence_hash_manifest_sha256(result.sequence_hashes),
            "embedding_file": path.name,
            "embedding_file_sha256": file_sha256(path),
            "vh_shape": list(result.vh_embeddings.shape),
            "vl_shape": list(result.vl_embeddings.shape),
            "paired_shape": list(result.paired_embeddings.shape),
        }
    return manifest
