"""Frozen ESM2 representation extraction and outcome-blind cosine audits."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from validation.external_family_validation.diversity.sequence_identity import sample_pair_indices
from validation.ml_benchmark.esm2_embeddings import (
    MODEL_NAME,
    PAIRED_DIMENSION,
    EmbeddingResult,
    extract_paired_embeddings,
    file_sha256,
    load_frozen_model,
    repeatability_audit,
    sequence_hash_manifest_sha256,
    validate_embedding_input,
    write_embedding_file,
)


ROOT = Path(__file__).resolve().parents[3]
FROZEN_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
INTERNAL_DIR = ROOT / "validation/data/ml_benchmark/entity_exact_v1/embeddings"
EXTERNAL_DIR = ROOT / "validation/external_family_validation/data/processed/embeddings"
SHARD_ROWS = 64


def _read_npz(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        hashes = data["sequence_hashes"].astype(str)
        vectors = np.asarray(data["paired_embeddings"], dtype=np.float32)
    if vectors.shape != (len(hashes), PAIRED_DIMENSION) or not np.isfinite(vectors).all():
        raise ValueError(f"Invalid frozen paired embedding shape/content: {path.name}")
    if len(set(hashes)) != len(hashes):
        raise ValueError(f"Duplicate embedding hashes: {path.name}")
    return hashes, vectors


def load_internal_embeddings(
    expected_hashes: set[str],
    directory: str | Path = INTERNAL_DIR,
) -> tuple[np.ndarray, np.ndarray]:
    """Load only TRAIN and VALIDATION embedding files; verify frozen hashes."""

    base = Path(directory)
    manifest = json.loads((base / "embedding_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("model_name") != MODEL_NAME or manifest.get("resolved_model_revision") != FROZEN_REVISION:
        raise ValueError("Internal ESM2 model revision differs from the frozen representation")
    parts = []
    for split, filename in (("TRAIN", "train_esm2_embeddings.npz"), ("VALIDATION", "validation_esm2_embeddings.npz")):
        path = base / filename
        frozen = manifest["splits"][split]
        if file_sha256(path) != frozen["embedding_file_sha256"]:
            raise ValueError(f"Frozen {split} embedding checksum mismatch")
        hashes, vectors = _read_npz(path)
        if sequence_hash_manifest_sha256(hashes) != frozen["sequence_hash_manifest_sha256"]:
            raise ValueError(f"Frozen {split} sequence-hash manifest mismatch")
        parts.append((hashes, vectors))
    hashes = np.concatenate([part[0] for part in parts])
    vectors = np.concatenate([part[1] for part in parts])
    if len(hashes) != 381 or set(hashes) != expected_hashes:
        raise ValueError("Frozen TRAIN/VALIDATION embedding population mismatch")
    order = np.argsort(hashes, kind="stable")
    return hashes[order], vectors[order]


def extract_external_embeddings(
    pairs: pd.DataFrame,
    *,
    output_dir: str | Path = EXTERNAL_DIR,
    progress: Callable[[str], None] | None = None,
    shard_rows: int = SHARD_ROWS,
) -> dict[str, Any]:
    """Extract every valid unique pair with the unchanged Phase 5B model path.

    Shards are verified before reuse so an interrupted run can be resumed.
    All outputs are in the ignored processed-data directory.
    """

    if shard_rows < 1:
        raise ValueError("shard_rows must be positive")
    safe = validate_embedding_input(pairs.loc[:, ["sequence_hash", "VH", "VL"]])
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    expected_hashes = safe["sequence_hash"].to_numpy(dtype=str)
    sequence_manifest_hash = sequence_hash_manifest_sha256(expected_hashes)
    final_path = output / "sabdab2_esm2_embeddings.npz"
    manifest_path = output / "external_embedding_manifest.json"
    if final_path.exists() and manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        hashes, _ = _read_npz(final_path)
        if (
            previous.get("model_name") == MODEL_NAME
            and previous.get("resolved_model_revision") == FROZEN_REVISION
            and previous.get("sequence_hash_manifest_sha256") == sequence_manifest_hash
            and previous.get("embedding_file_sha256") == file_sha256(final_path)
            and np.array_equal(hashes, expected_hashes)
        ):
            return previous
        raise ValueError("Existing external embedding output does not match the frozen input")

    # This audit uses the already cached immutable model revision. Sequence
    # contents are never sent to a provider or the Hub.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    tokenizer, model, revision, provenance = load_frozen_model(MODEL_NAME, revision=FROZEN_REVISION)
    import torch

    device = next(model.parameters()).device
    shards = []
    for start in range(0, len(safe), shard_rows):
        stop = min(start + shard_rows, len(safe))
        shard_number = start // shard_rows
        path = output / f"shard_{shard_number:04d}.npz"
        expected_shard = expected_hashes[start:stop]
        if path.exists():
            observed, _ = _read_npz(path)
            if not np.array_equal(observed, expected_shard):
                raise ValueError(f"Existing embedding shard {shard_number} has wrong sequence hashes")
        else:
            result = extract_paired_embeddings(safe.iloc[start:stop], tokenizer, model, torch, device)
            if not np.array_equal(result.sequence_hashes, expected_shard):
                raise ValueError(f"Embedding shard {shard_number} changed row order")
            temporary = output / f"shard_{shard_number:04d}.tmp.npz"
            write_embedding_file(temporary, result)
            temporary.replace(path)
        shards.append(path)
        if progress:
            progress(f"ESM2 {stop}/{len(safe)} unique paired sequences")

    combined = {key: [] for key in ("vh_embeddings", "vl_embeddings", "paired_embeddings")}
    for path in shards:
        with np.load(path, allow_pickle=False) as data:
            for key in combined:
                combined[key].append(np.asarray(data[key], dtype=np.float32))
    final_result = EmbeddingResult(
        sequence_hashes=expected_hashes,
        vh_embeddings=np.concatenate(combined["vh_embeddings"]),
        vl_embeddings=np.concatenate(combined["vl_embeddings"]),
        paired_embeddings=np.concatenate(combined["paired_embeddings"]),
        batch_size_used=8,
    )
    repeatability = repeatability_audit(safe, tokenizer, model, torch, device, sample_size=min(10, len(safe)))
    if not repeatability["passed"]:
        raise ValueError("External ESM2 repeatability audit failed")
    temporary = output / "sabdab2_esm2_embeddings.tmp.npz"
    write_embedding_file(temporary, final_result)
    temporary.replace(final_path)
    manifest = {
        "model_name": MODEL_NAME,
        "resolved_model_revision": revision,
        "representation": "VH/VL final hidden state residue mean pooling; 640 + 640 float32",
        "population": "SAbDab2 unique valid paired VH/VL hashes",
        "row_count": len(safe),
        "sequence_hash_manifest_sha256": sequence_manifest_hash,
        "embedding_file": final_path.name,
        "embedding_file_sha256": file_sha256(final_path),
        "paired_shape": list(final_result.paired_embeddings.shape),
        "shard_rows": shard_rows,
        "shard_count": len(shards),
        "repeatability": repeatability,
        "runtime": provenance,
        "provider_calls": 0,
        "training": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _unit_vectors(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[1] != PAIRED_DIMENSION or not np.isfinite(vectors).all():
        raise ValueError("Expected finite paired 1280-dimensional embeddings")
    norms = np.linalg.norm(vectors, axis=1)
    if (norms <= 0).any() or not np.isfinite(norms).all():
        raise ValueError("Embedding vectors must have positive finite norms")
    return vectors / norms[:, None]


def _summarize(values: np.ndarray) -> dict[str, float | int | None]:
    if not len(values):
        return {"n": 0, "min": None, "q25": None, "median": None, "q75": None, "max": None, "mean": None}
    return {
        "n": int(len(values)),
        "min": float(np.min(values)),
        "q25": float(np.quantile(values, 0.25)),
        "median": float(np.median(values)),
        "q75": float(np.quantile(values, 0.75)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
    }


def _within_sample(unit: np.ndarray, max_pairs: int, seed: int) -> dict[str, float | int | None]:
    indices = sample_pair_indices(len(unit), max_pairs=max_pairs, seed=seed)
    values = np.asarray([float(np.dot(unit[i], unit[j])) for i, j in indices], dtype=np.float32)
    return _summarize(values)


def compare_embedding_spaces(
    external_hashes: np.ndarray,
    external_vectors: np.ndarray,
    internal_hashes: np.ndarray,
    internal_vectors: np.ndarray,
    *,
    max_sample_pairs: int = 10_000,
    seed: int = 17,
) -> dict[str, Any]:
    """Descriptive cosine distributions and exact cross-space nearest neighbors."""

    external_hashes = np.asarray(external_hashes, dtype=str)
    internal_hashes = np.asarray(internal_hashes, dtype=str)
    if len(set(external_hashes)) != len(external_hashes) or len(set(internal_hashes)) != len(internal_hashes):
        raise ValueError("Embedding comparison requires unique sequence hashes")
    if len(external_vectors) != len(external_hashes) or len(internal_vectors) != len(internal_hashes):
        raise ValueError("Embedding hashes and vectors differ in length")
    external = _unit_vectors(external_vectors)
    internal = _unit_vectors(internal_vectors)
    rng = np.random.default_rng(seed)
    sampled = set()
    maximum = min(max_sample_pairs, len(external) * len(internal))
    while len(sampled) < maximum:
        sampled.add((int(rng.integers(len(external))), int(rng.integers(len(internal)))))
    cross = np.asarray([float(np.dot(external[i], internal[j])) for i, j in sorted(sampled)], dtype=np.float32)
    nearest = []
    for start in range(0, len(external), 256):
        similarities = external[start:start + 256] @ internal.T
        nearest.extend(np.max(similarities, axis=1).tolist())
    overlap = set(external_hashes) & set(internal_hashes)
    nonoverlap = np.asarray([value for value, key in zip(nearest, external_hashes) if key not in overlap], dtype=np.float32)
    return {
        "representation": "frozen paired ESM2 1280-dimensional residue mean pooling",
        "external_n": int(len(external)),
        "internal_train_validation_n": int(len(internal)),
        "exact_sequence_hash_overlap_n": len(overlap),
        "sample_seed": seed,
        "max_sample_pairs": max_sample_pairs,
        "external_within_cosine": _within_sample(external, max_sample_pairs, seed),
        "internal_train_validation_within_cosine": _within_sample(internal, max_sample_pairs, seed),
        "external_vs_internal_cosine": _summarize(cross),
        "external_nearest_internal_cosine": _summarize(np.asarray(nearest, dtype=np.float32)),
        "external_nearest_internal_cosine_excluding_exact_hash_overlap": _summarize(nonoverlap),
        "limitations": [
            "Cosine similarity is descriptive representation geometry, not sequence identity or predictive performance.",
            "Pairwise cosine distributions are deterministic samples; nearest internal neighbor is exhaustive over 381 TRAIN/VALIDATION vectors.",
            "TEST embeddings and all experimental labels were excluded.",
        ],
    }
