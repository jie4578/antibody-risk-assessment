# tests/test_ml.py
# ML 模块测试：特征编码 / 数据集生成 / 模型注册 / 训练管线 / 可视化。

import numpy as np
import pandas as pd
import pytest

from ml.data import BaseSequencePool, build_dataset, make_variant, mutate_sequence_random, rule_label
from ml.features import SequenceEncoder
from ml.models import available_models, make_model
from ml.train import load_bundle, train_pipeline

SAMPLES = [
    "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS",
    "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK",
]


# ---------- features ----------
def test_encoder_returns_fixed_dimension():
    enc = SequenceEncoder(k_max=3, kmer_dim=256)
    X = enc.transform(SAMPLES)
    assert X.shape == (2, enc.n_features)
    assert X.dtype == np.float32


def test_encoder_deterministic():
    enc = SequenceEncoder()
    a = enc.transform(["ACDEFGHIK"])
    b = enc.transform(["ACDEFGHIK"])
    np.testing.assert_array_equal(a, b)


def test_encoder_different_sequences_differ():
    enc = SequenceEncoder()
    x1 = enc.transform(["ACDEFGHIK"])
    x2 = enc.transform(["ACDEFGHIG"])  # 末尾一个残基不同
    assert not np.allclose(x1, x2)


def test_encoder_feature_names_length():
    enc = SequenceEncoder(k_max=2, kmer_dim=8)
    names = enc.feature_names()
    assert len(names) == enc.n_features
    assert names[0] == "length_norm"


def test_encoder_empty_sequence():
    enc = SequenceEncoder()
    v = enc.encode_one("")
    assert v.shape == (enc.n_features,)
    assert float(np.sum(v)) == 0.0


def test_encoder_rejects_invalid_aa_gracefully():
    # 非法字符在编码时按 0 处理，不应抛异常
    enc = SequenceEncoder()
    v = enc.encode_one("ACDEXZ")
    assert v.shape == (enc.n_features,)


# ---------- data ----------
def test_base_pool_loads_sequences():
    pool = BaseSequencePool()
    assert len(pool.sequences) > 0


def test_mutate_sequence_random_preserves_length():
    import random
    rng = random.Random(0)
    out = mutate_sequence_random(SAMPLES[0], rng, 3)
    assert len(out) == len(SAMPLES[0])
    assert set(out) <= set("ACDEFGHIKLMNPQRSTVWY")


def test_make_variant_returns_valid_sequence():
    import random
    rng = random.Random(1)
    pool = BaseSequencePool()
    v = make_variant(pool.sample(rng), rng)
    assert set(v) <= set("ACDEFGHIKLMNPQRSTVWY")


def test_rule_label_in_range():
    score, level = rule_label(SAMPLES[0])
    assert 0.0 <= score <= 100.0
    assert level in ("Low Risk", "Medium Risk", "High Risk")


def test_build_dataset_shape_and_columns():
    df = build_dataset(n=120, seed=7)
    assert len(df) == 120
    for col in ("sequence", "risk_score", "risk_level", "high_risk"):
        assert col in df.columns
    assert df["risk_score"].notna().all()
    assert set(df["risk_level"].unique()) <= {"Low Risk", "Medium Risk", "High Risk"}
    assert df["risk_score"].between(0, 100).all()


# ---------- models ----------
def test_available_models_classification():
    models = available_models("classification")
    assert "logistic" in models


def test_available_models_regression():
    models = available_models("regression")
    assert "ridge" in models


def test_make_model_unknown_raises():
    with pytest.raises(ValueError):
        make_model("nope", "classification")


def test_make_model_unknown_task_raises():
    with pytest.raises(ValueError):
        make_model("logistic", "nope")


# ---------- train ----------
@pytest.fixture(scope="module")
def small_df():
    return build_dataset(n=160, seed=3)


def test_train_classification_metrics(small_df):
    result = train_pipeline(small_df, task="classification", model_name="logistic", seed=1)
    assert "roc_auc" in result.metrics
    assert result.n_train > 0
    assert result.n_test > 0
    assert result.model is not None


def test_train_regression_metrics(small_df):
    result = train_pipeline(small_df, task="regression", model_name="ridge", seed=1)
    assert "r2" in result.metrics
    assert result.feature_importance is not None


def test_train_random_forest_classification(small_df):
    result = train_pipeline(small_df, task="classification", model_name="random_forest", seed=1)
    assert result.metrics["accuracy"] >= 0.0


def test_save_load_bundle(small_df, tmp_path):
    p = str(tmp_path / "m.joblib")
    result = train_pipeline(small_df, task="classification", model_name="logistic", seed=2, save_path=p)
    assert result.model is not None
    model, encoder = load_bundle(p)
    assert model is not None
    assert encoder.n_features > 0
    X = encoder.transform([small_df["sequence"].iloc[0]])
    assert X.shape[1] == encoder.n_features


# ---------- transformer (torch 可选) ----------
def test_transformer_build_when_torch_present():
    torch = pytest.importorskip("torch")
    from ml.transformer import build_transformer_classifier

    model = build_transformer_classifier(vocab_size=20, d_model=32, nhead=2, num_layers=1, max_len=64, num_classes=2)
    assert model is not None
    # 前向：随机氨基酸索引（padding=0）
    x = torch.randint(1, 20, (2, 30))
    logits = model(x)
    assert logits.shape == (2, 2)


# ---------- evaluate (matplotlib 可选) ----------
def test_visualization_plots(tmp_path):
    matplotlib = pytest.importorskip("matplotlib")
    from ml.evaluate import confusion_matrix_plot, feature_importance_plot, roc_curve_plot

    y_true = [0, 1, 0, 1, 0, 1]
    y_pred = [0, 1, 0, 0, 1, 1]
    proba = [0.1, 0.9, 0.2, 0.4, 0.7, 0.8]
    cm_path = confusion_matrix_plot(y_true, y_pred, ["Low", "High"], str(tmp_path / "cm.png"))
    roc_path = roc_curve_plot(y_true, proba, str(tmp_path / "roc.png"))
    fi_path = feature_importance_plot([("a", 0.5), ("b", 0.3), ("c", 0.2)], top_n=5, save_path=str(tmp_path / "fi.png"))
    assert cm_path.endswith("cm.png")
    assert roc_path.endswith("roc.png")
    assert fi_path.endswith("fi.png")
    assert (tmp_path / "cm.png").exists()
    assert (tmp_path / "roc.png").exists()
    assert (tmp_path / "fi.png").exists()
