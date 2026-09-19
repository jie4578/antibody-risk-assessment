from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from validation.ml_benchmark.phase5d import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    EXPECTED_TEST_LABEL_SHA256,
    FEATURE_BLOCKS,
    NOVELTY_BIN_COUNTS,
    TEST_N,
    Phase5DSealMismatch,
    _bootstrap_classification,
    _bootstrap_continuous,
    _load_selected_config,
    verify_test_seal,
)


ROOT = Path(__file__).resolve().parents[2]


def test_test_seal_sha256_and_population_are_frozen() -> None:
    path = ROOT / "validation/data/ml_benchmark/entity_exact_v1/sealed_test_labels.csv"
    assert verify_test_seal(path) == EXPECTED_TEST_LABEL_SHA256
    features = (ROOT / "validation/data/ml_benchmark/entity_exact_v1/test_features.csv").read_text(encoding="utf-8").splitlines()
    assert len(features) == TEST_N + 1


def test_selected_config_is_unchanged_and_exact() -> None:
    config = _load_selected_config(ROOT)
    assert len(config["continuous_selected"]) == 20
    assert len(config["classification_selected"]) == 4
    assert tuple(config["feature_blocks"]) == FEATURE_BLOCKS
    assert config["test_labels_accessed"] is False
    assert config["test_predictions_created"] is False


def test_frozen_novelty_bins() -> None:
    import pandas as pd

    frame = pd.read_csv(ROOT / "validation/data/ml_benchmark/entity_exact_v1/test_similarity_audit.csv")
    assert frame.groupby("novelty_bin").size().to_dict() == NOVELTY_BIN_COUNTS


def test_bootstrap_is_deterministic_and_uses_frozen_design() -> None:
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    prediction = np.array([0.1, 1.1, 1.9, 3.2, 3.8, 5.1])
    first = _bootstrap_continuous(y, prediction)
    second = _bootstrap_continuous(y, prediction)
    assert first == second
    assert BOOTSTRAP_SEED == 20260919
    assert BOOTSTRAP_RESAMPLES == 2000
    assert all(0 < item["bootstrap_valid_n"] <= BOOTSTRAP_RESAMPLES for item in first)

    labels = np.array([0, 0, 0, 1, 1, 1])
    probabilities = np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])
    result = _bootstrap_classification(labels, probabilities)
    assert all(item["bootstrap_valid_n"] == BOOTSTRAP_RESAMPLES for item in result)


def test_phase5d_source_has_no_grid_search_or_esm_inference() -> None:
    paths = [ROOT / "validation/ml_benchmark/phase5d.py", ROOT / "validation/run_phase5d_evaluation.py"]
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
        assert not imports.intersection({"torch", "transformers", "xgboost", "tensorflow"})
        source = path.read_text(encoding="utf-8").lower()
        assert "randomforest" not in source
        assert "pca(" not in source
        if path.name == "phase5d.py":
            assert "threshold_optimization" in source


def test_seal_mismatch_stops_before_evaluation(tmp_path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("not-the-sealed-file\n", encoding="utf-8")
    with pytest.raises(Phase5DSealMismatch, match="TEST_SEAL_MISMATCH"):
        verify_test_seal(bad)
