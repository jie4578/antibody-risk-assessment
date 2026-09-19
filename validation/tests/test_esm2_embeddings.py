from __future__ import annotations

import ast
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from validation.ml_benchmark.esm2_embeddings import (
    ALLOWED_AMINO_ACIDS,
    EXPECTED_SPLIT_COUNTS,
    HIDDEN_DIMENSION,
    MODEL_NAME,
    PAIRED_DIMENSION,
    VH_DIMENSION,
    VL_DIMENSION,
    EmbeddingInputError,
    extract_paired_embeddings,
    load_frozen_split_inputs,
    mean_pool_residue_tokens,
    sequence_hash_manifest_sha256,
    embedding_feature_names,
    validate_embedding_input,
    verify_length_control_alignment,
    verify_frozen_hash_alignment,
    verify_rule48_alignment,
)


ROOT = Path(__file__).resolve().parents[2]


class _ArrayTensor:
    def __init__(self, value):
        self.value = np.asarray(value)

    @property
    def shape(self):
        return self.value.shape

    def to(self, _device):
        return self

    def detach(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.value


class _FakeTokenizer:
    def __call__(self, sequences, **kwargs):
        assert kwargs["padding"] is True
        assert kwargs["truncation"] is False
        assert kwargs["return_special_tokens_mask"] is True
        width = max(len(sequence) for sequence in sequences) + 2
        ids = []
        special = []
        attention = []
        for sequence in sequences:
            code = 1 if sequence.startswith("A") else 2
            length = len(sequence) + 2
            ids.append([code] * length + [0] * (width - length))
            attention.append([1] * length + [0] * (width - length))
            special.append([1] + [0] * len(sequence) + [1] + [1] * (width - length))
        return {
            "input_ids": _ArrayTensor(ids),
            "attention_mask": _ArrayTensor(attention),
            "special_tokens_mask": _ArrayTensor(special),
        }


class _FakeModel:
    class Config:
        hidden_size = HIDDEN_DIMENSION
        max_position_embeddings = 128

    config = Config()

    def eval(self):
        return self

    def __call__(self, input_ids, attention_mask):
        values = input_ids.value[:, 0].astype(np.float32)
        hidden = np.zeros((input_ids.shape[0], input_ids.shape[1], HIDDEN_DIMENSION), dtype=np.float32)
        hidden[:] = values[:, None, None]
        return type("Output", (), {"last_hidden_state": _ArrayTensor(hidden)})()


class _FakeTorch:
    @staticmethod
    @contextmanager
    def inference_mode():
        yield


def test_frozen_model_contract_and_dimensions() -> None:
    assert MODEL_NAME == "facebook/esm2_t30_150M_UR50D"
    assert HIDDEN_DIMENSION == 640
    assert VH_DIMENSION == 640
    assert VL_DIMENSION == 640
    assert PAIRED_DIMENSION == 1280
    assert len(ALLOWED_AMINO_ACIDS) == 20
    names = embedding_feature_names()
    assert names[0] == "ESM_VH_0000"
    assert names[HIDDEN_DIMENSION - 1] == "ESM_VH_0639"
    assert names[HIDDEN_DIMENSION] == "ESM_VL_0000"
    assert names[-1] == "ESM_VL_0639"


def test_pooling_excludes_special_tokens_and_padding() -> None:
    hidden = np.array([[[100.0, 100.0], [1.0, 3.0], [5.0, 7.0], [999.0, 999.0]]], dtype=np.float32)
    attention = np.array([[1, 1, 1, 0]], dtype=np.int64)
    special = np.array([[1, 0, 0, 1]], dtype=np.int64)
    np.testing.assert_allclose(mean_pool_residue_tokens(hidden, attention, special), [[3.0, 5.0]])


def test_paired_extraction_is_separate_and_vh_precedes_vl() -> None:
    frame = pd.DataFrame(
        [
            {"sequence_hash": "a", "VH": "AAAA", "VL": "GGGG"},
            {"sequence_hash": "b", "VH": "AAAC", "VL": "GGGC"},
        ]
    )
    result = extract_paired_embeddings(frame, _FakeTokenizer(), _FakeModel(), _FakeTorch(), "cpu", batch_size=8)
    assert result.vh_embeddings.shape == (2, VH_DIMENSION)
    assert result.vl_embeddings.shape == (2, VL_DIMENSION)
    assert result.paired_embeddings.shape == (2, PAIRED_DIMENSION)
    assert np.all(result.paired_embeddings[:, :VH_DIMENSION] == 1.0)
    assert np.all(result.paired_embeddings[:, VH_DIMENSION:] == 2.0)
    assert np.isfinite(result.paired_embeddings).all()


def test_outcome_firewall_rejects_outcome_columns() -> None:
    frame = pd.DataFrame([{"sequence_hash": "a", "VH": "AAAA", "VL": "GGGG", "HIC": "9.0"}])
    with pytest.raises(EmbeddingInputError, match="Outcome fields"):
        validate_embedding_input(frame)


def test_embedding_input_rejects_unapproved_feature_columns() -> None:
    frame = pd.DataFrame([{"sequence_hash": "a", "VH": "AAAA", "VL": "GGGG", "VH_oxidation_count": "1"}])
    with pytest.raises(EmbeddingInputError, match="Non-identity fields"):
        validate_embedding_input(frame)


def test_sequence_normalization_and_unsupported_residue_are_deterministic() -> None:
    valid = validate_embedding_input(pd.DataFrame([{"sequence_hash": "a", "VH": " aaaA ", "VL": "gggg"}]))
    assert valid.loc[0, "VH"] == "AAAA"
    assert valid.loc[0, "VL"] == "GGGG"
    invalid = pd.DataFrame([{"sequence_hash": "a", "VH": "AAAX", "VL": "GGGG"}])
    with pytest.raises(EmbeddingInputError, match="X"):
        validate_embedding_input(invalid)


def test_frozen_split_counts_hashes_and_rule48_alignment() -> None:
    inputs = load_frozen_split_inputs(ROOT)
    verify_frozen_hash_alignment(ROOT, inputs)
    assert {name: len(value.frame) for name, value in inputs.items()} == EXPECTED_SPLIT_COUNTS
    alignment = verify_rule48_alignment(ROOT, inputs)
    assert alignment == {"TRAIN": 285, "VALIDATION": 96, "TEST": 95, "unmatched": 0}
    assert not any("sealed_test_labels" in column for value in inputs.values() for column in value.frame.columns)


def test_length_control_alignment_uses_sequences_not_outcomes(tmp_path) -> None:
    inputs = load_frozen_split_inputs(ROOT)
    index_path = tmp_path / "embedding_index.csv"
    from validation.ml_benchmark.esm2_embeddings import write_embedding_index

    write_embedding_index(index_path, inputs)
    assert verify_length_control_alignment(index_path, inputs) == {
        "TRAIN": 285,
        "VALIDATION": 96,
        "TEST": 95,
        "mismatched": 0,
    }


def test_loading_does_not_open_sealed_test_labels(monkeypatch) -> None:
    import validation.ml_benchmark.esm2_embeddings as module

    original = module.pd.read_csv

    def guarded_read_csv(path, *args, **kwargs):
        assert "sealed_test_labels" not in str(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(module.pd, "read_csv", guarded_read_csv)
    inputs = load_frozen_split_inputs(ROOT)
    assert len(inputs["TEST"].frame) == 95


def test_hash_manifest_is_order_sensitive_and_no_model_code_is_present() -> None:
    assert sequence_hash_manifest_sha256(["a", "b"]) != sequence_hash_manifest_sha256(["b", "a"])
    paths = [
        ROOT / "validation/ml_benchmark/esm2_embeddings.py",
        ROOT / "validation/run_esm2_embedding_extraction.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not imports.intersection({"sklearn", "scipy", "core", "scoring"})
        source = path.read_text(encoding="utf-8").lower()
        assert ".fit(" not in source
        assert "roc_auc" not in source
        assert "sealed_test_labels.csv" not in source
