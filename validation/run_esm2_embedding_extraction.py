"""Run the frozen Phase 5B ESM-2 extraction without opening test labels."""

from __future__ import annotations

import json
from pathlib import Path

from validation.ml_benchmark.esm2_embeddings import (
    DEFAULT_OUTPUT_DIR,
    MODEL_NAME,
    EXPECTED_SPLIT_COUNTS,
    build_manifest,
    extract_paired_embeddings,
    verify_length_control_alignment,
    load_frozen_model,
    load_frozen_split_inputs,
    repeatability_audit,
    verify_frozen_hash_alignment,
    verify_rule48_alignment,
    write_embedding_file,
    write_embedding_index,
)


ROOT = Path(__file__).resolve().parents[1]


def run_extraction(root: str | Path = ROOT, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    root = Path(root)
    output = Path(output_dir)
    inputs = load_frozen_split_inputs(root)
    verify_frozen_hash_alignment(root, inputs)
    rule48_alignment = verify_rule48_alignment(root, inputs)
    tokenizer, model, revision, provenance = load_frozen_model(MODEL_NAME)
    import torch

    device = next(model.parameters()).device
    output.mkdir(parents=True, exist_ok=True)

    results = {}
    output_paths = {
        "TRAIN": output / "train_esm2_embeddings.npz",
        "VALIDATION": output / "validation_esm2_embeddings.npz",
        "TEST": output / "test_esm2_embeddings.npz",
    }
    for split in ("TRAIN", "VALIDATION", "TEST"):
        if len(inputs[split].frame) != EXPECTED_SPLIT_COUNTS[split]:
            raise ValueError(f"Unexpected {split} row count")
        result = extract_paired_embeddings(
            inputs[split].frame,
            tokenizer,
            model,
            torch,
            device,
        )
        if result.sequence_hashes.tolist() != inputs[split].frame["sequence_hash"].tolist():
            raise ValueError(f"Embedding row order changed for {split}")
        write_embedding_file(output_paths[split], result)
        results[split] = result

    index_path = output / "embedding_index.csv"
    write_embedding_index(index_path, inputs)
    length_control_alignment = verify_length_control_alignment(index_path, inputs)
    repeatability = repeatability_audit(
        inputs["TRAIN"].frame,
        tokenizer,
        model,
        torch,
        device,
        sample_size=10,
    )
    if not repeatability["passed"]:
        raise RuntimeError("Phase 5B repeatability audit failed")
    manifest = build_manifest(
        output_paths,
        results,
        provenance,
        rule48_alignment,
        length_control_alignment,
        repeatability,
    )
    manifest["model_name"] = MODEL_NAME
    manifest["resolved_model_revision"] = revision
    manifest["embedding_index_file"] = index_path.name
    manifest_path = output / "embedding_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "train": output_paths["TRAIN"],
        "validation": output_paths["VALIDATION"],
        "test": output_paths["TEST"],
        "index": index_path,
        "manifest": manifest_path,
    }


def main() -> None:
    run_extraction()


if __name__ == "__main__":
    main()
