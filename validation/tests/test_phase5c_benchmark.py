from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from validation.ml_benchmark.phase5c import (
    ALPHA_GRID,
    C_GRID,
    FEATURE_BLOCKS,
    FEATURE_DIMENSIONS,
    ESM2_DIMENSION,
    Phase5CError,
    RULE_FEATURES,
    load_phase5c_data,
    make_pipeline,
    select_classification,
    select_continuous,
)


ROOT = Path(__file__).resolve().parents[2]


def test_frozen_train_validation_counts_and_no_test_label_open(monkeypatch) -> None:
    import validation.ml_benchmark.phase5c as module

    original = module.pd.read_csv

    def guarded(path, *args, **kwargs):
        assert "sealed_test_labels" not in str(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(module.pd, "read_csv", guarded)
    data = load_phase5c_data(ROOT)
    assert len(data["TRAIN"]) == 285
    assert len(data["VALIDATION"]) == 96


def test_exactly_four_feature_blocks_and_dimensions() -> None:
    assert FEATURE_BLOCKS == ("LENGTH_CONTROL", "RULE48", "ESM2", "ESM2_PLUS_RULE48")
    assert FEATURE_DIMENSIONS == {"LENGTH_CONTROL": 2, "RULE48": 48, "ESM2": 1280, "ESM2_PLUS_RULE48": 1328}
    assert len(RULE_FEATURES) == FEATURE_DIMENSIONS["RULE48"]
    assert ESM2_DIMENSION == FEATURE_DIMENSIONS["ESM2"]


def test_signed_spearman_tie_prefers_larger_alpha() -> None:
    rows = [
        {"alpha": 0.01, "validation_spearman": 0.25},
        {"alpha": 100.0, "validation_spearman": 0.25 + 1e-13},
    ]
    assert select_continuous(rows)["alpha"] == 100.0


def test_classification_tie_prefers_smaller_c() -> None:
    rows = [
        {"C": 0.01, "validation_pr_auc": 0.25},
        {"C": 1.0, "validation_pr_auc": 0.25 + 1e-13},
    ]
    assert select_classification(rows)["C"] == 0.01


def test_frozen_hyperparameter_grids() -> None:
    assert ALPHA_GRID == (0.01, 0.1, 1.0, 10.0, 100.0)
    assert C_GRID == (0.01, 0.1, 1.0, 10.0, 100.0)


def test_phase5c_source_contains_no_test_prediction_or_forbidden_modeling() -> None:
    paths = [
        ROOT / "validation/ml_benchmark/phase5c.py",
        ROOT / "validation/run_phase5c_benchmark.py",
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
        assert not imports.intersection({"xgboost", "lightgbm", "tensorflow", "torch"})
        source = path.read_text(encoding="utf-8").lower()
        assert "sealed_test_labels.csv" not in source
        assert "roc_auc" in source or path.name != "phase5c.py"
        assert "sklearn.decomposition" not in source
        assert "randomforestclassifier" not in source
        assert "randomforestregressor" not in source
        assert "xgbclassifier" not in source
        assert "xgbregressor" not in source


def test_no_test_predictions_or_outcome_selected_config_flags() -> None:
    assert not any(name.lower().startswith("test_") for name in FEATURE_BLOCKS)
    assert np.isfinite([0.01, 0.1, 1.0, 10.0, 100.0]).all()


def test_standard_scaler_can_only_be_fitted_on_supplied_train_rows() -> None:
    from sklearn.linear_model import Ridge

    pipeline = make_pipeline(Ridge(alpha=1.0))
    train = np.array([[1.0, 10.0], [3.0, 14.0]])
    pipeline.fit(train, np.array([0.0, 1.0]))
    np.testing.assert_allclose(pipeline.named_steps["scaler"].mean_, [2.0, 12.0])


def test_modeling_module_does_not_import_esm_or_production_science() -> None:
    source = (ROOT / "validation/ml_benchmark/phase5c.py").read_text(encoding="utf-8")
    assert "from transformers" not in source
    assert "import torch" not in source
    assert "from core" not in source
    assert "from scoring" not in source


def test_missing_embedding_file_is_a_clear_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        load_phase5c_data(tmp_path)
