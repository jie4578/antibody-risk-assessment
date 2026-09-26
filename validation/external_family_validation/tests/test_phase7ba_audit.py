"""Reproducibility and boundary tests for the Phase 7B-A audit."""

from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pandas as pd

from validation.external_family_validation.audit.embedding_audit import compare_embedding_spaces
from validation.external_family_validation.audit.report import audit_germline_columns, render_report, write_report
from validation.external_family_validation.audit.rule_audit import load_external_pairs, summarize_rule_tables
from validation.external_validation_spec import FROZEN_RULE_FEATURES
from validation.features.extract_rule_features import extract_features
from validation.ml_benchmark.esm2_embeddings import extract_paired_embeddings, sequence_hash_manifest_sha256
from validation.schemas.dataset_schema import sequence_hash


VH = "ACDEFGHIKLMNPQRSTVWY" * 6
VL = "YWVTSRQPNMLKIHGFEDCA" * 5 + "YYY"


def test_sequence_hash_population_deduplicates_without_discarding_source_rows(tmp_path):
    pair_hash = sequence_hash(" AAA ", "CCC")
    source = pd.DataFrame([
        {"dataset": "SAbDab2", "record_id": "b", "antibody_id": "x", "VH": "AAA", "VL": "CCC", "sequence_status": "VALID", "sequence_hash": pair_hash},
        {"dataset": "SAbDab2", "record_id": "a", "antibody_id": "x", "VH": "AAA", "VL": "CCC", "sequence_status": "VALID", "sequence_hash": pair_hash},
        {"dataset": "SAbDab2", "record_id": "c", "antibody_id": "y", "VH": "AAA", "VL": "", "sequence_status": "PARTIAL", "sequence_hash": sequence_hash("AAA", "")},
    ])
    path = tmp_path / "normalized.csv"
    source.to_csv(path, index=False)
    first = load_external_pairs(path)
    second = load_external_pairs(path)
    pd.testing.assert_frame_equal(first, second)
    assert len(source) == 3
    assert len(first) == 1
    assert first.iloc[0]["record_id"] == "a"
    assert sequence_hash_manifest_sha256(first["sequence_hash"]) == sequence_hash_manifest_sha256(second["sequence_hash"])


def test_frozen_rule48_extraction_and_site_summary_are_reproducible():
    frame = pd.DataFrame([{"dataset": "test", "record_id": "one", "antibody_id": "one", "VH": VH, "VL": VL, "HIC": 1.0}])
    first = extract_features(frame, dataset="test")
    frame["HIC"] = 999.0
    second = extract_features(frame, dataset="test")
    pd.testing.assert_frame_equal(first.antibody, second.antibody)
    pd.testing.assert_frame_equal(first.risk_sites, second.risk_sites)
    assert len(FROZEN_RULE_FEATURES) == 48
    summary = summarize_rule_tables(first.antibody, first.risk_sites)
    assert summary["n"] == 1
    assert summary["total_risk_sites"] == len(first.risk_sites)
    assert summary["cdr_sites"] + summary["framework_sites"] == summary["total_risk_sites"]
    assert summary["feature_prevalence"]["VH_oxidation_count"]["n"] == 1
    assert "VH_length" in summary["continuous_feature_distribution"]


class _Tensor:
    def __init__(self, data):
        self.data = np.asarray(data)

    @property
    def shape(self):
        return self.data.shape

    def to(self, _device):
        return self

    def detach(self):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.data


class _Tokenizer:
    def __call__(self, sequences, **_kwargs):
        width = max(map(len, sequences)) + 2
        ids, attention, special = [], [], []
        for sequence in sequences:
            length = len(sequence) + 2
            code = 1 if sequence.startswith("A") else 2
            ids.append([code] * length + [0] * (width - length))
            attention.append([1] * length + [0] * (width - length))
            special.append([1] + [0] * len(sequence) + [1] + [1] * (width - length))
        return {"input_ids": _Tensor(ids), "attention_mask": _Tensor(attention), "special_tokens_mask": _Tensor(special)}


class _Model:
    config = type("Config", (), {"max_position_embeddings": 128})()

    def eval(self):
        return self

    def __call__(self, input_ids, attention_mask):
        rows, width = input_ids.shape
        hidden = np.zeros((rows, width, 640), dtype=np.float32)
        hidden[:] = input_ids.data[:, 0, None, None]
        return type("Output", (), {"last_hidden_state": _Tensor(hidden)})()


class _Torch:
    @staticmethod
    @contextmanager
    def inference_mode():
        yield


def test_embedding_extraction_and_cosine_metrics_are_reproducible():
    frame = pd.DataFrame([
        {"sequence_hash": "a", "VH": "AAAA", "VL": "CCCC"},
        {"sequence_hash": "b", "VH": "CCCC", "VL": "AAAA"},
        {"sequence_hash": "c", "VH": "AAAC", "VL": "CCCA"},
    ])
    first = extract_paired_embeddings(frame, _Tokenizer(), _Model(), _Torch(), "cpu")
    second = extract_paired_embeddings(frame, _Tokenizer(), _Model(), _Torch(), "cpu")
    np.testing.assert_array_equal(first.paired_embeddings, second.paired_embeddings)
    report1 = compare_embedding_spaces(first.sequence_hashes, first.paired_embeddings, first.sequence_hashes[:2], first.paired_embeddings[:2], max_sample_pairs=6)
    report2 = compare_embedding_spaces(second.sequence_hashes, second.paired_embeddings, second.sequence_hashes[:2], second.paired_embeddings[:2], max_sample_pairs=6)
    assert report1 == report2
    assert report1["exact_sequence_hash_overlap_n"] == 2
    assert report1["external_vs_internal_cosine"]["n"] == 6


def _report_inputs():
    count_features = [feature for feature in FROZEN_RULE_FEATURES if feature.endswith(("_sites", "_combined", "_count"))]
    features = {feature: {"n": 1, "nonzero_n": 1, "nonzero_fraction": 1.0, "mean_count": 1.0} for feature in count_features}
    continuous = {feature: {"n": 1, "median": 1.0, "q25": 1.0, "q75": 1.0, "mean": 1.0} for feature in FROZEN_RULE_FEATURES if feature not in features}
    common = {"feature_prevalence": features, "continuous_feature_distribution": continuous, "total_risk_sites": 1, "sites_per_pair": {"median": 1, "q25": 1, "q75": 1}, "cdr_sites": 1, "framework_sites": 0, "site_category_counts": {"oxidation": 1}, "region_counts": {"CDR1": 1}}
    rule = {"feature_count": 48, "feature_order": list(FROZEN_RULE_FEATURES), "external": {"n": 2, **common}, "internal_train_validation": {"n": 381, **common}}
    metric = {"n": 1, "median": 0.5, "q25": 0.5, "q75": 0.5}
    embedding = {"external_n": 2, "internal_train_validation_n": 381, "exact_sequence_hash_overlap_n": 0, **{name: metric for name in ("external_within_cosine", "internal_train_validation_within_cosine", "external_vs_internal_cosine", "external_nearest_internal_cosine", "external_nearest_internal_cosine_excluding_exact_hash_overlap")}}
    embedding_manifest = {"model_name": "facebook/esm2_t30_150M_UR50D", "resolved_model_revision": "fixed", "representation": "paired", "row_count": 2, "embedding_file_sha256": "test", "repeatability": {"sample_n": 2, "max_absolute_difference": 0.0}}
    phase7a = {"population": {"source_records": 3, "valid_paired_records": 2, "valid_paired_unique_sequences": 2}, "clusters": {"0.7": {"clusters": 2, "largest_cluster": 1, "singleton_clusters": 2}}, "identity_distribution": {"sampled_pairs": 1, "paired_min": {"median": 0.5, "q25": 0.5, "q75": 0.5}}}
    source = {"dataset": "test", "source_url": "https://example.invalid", "publication": "test", "acquisition_date": "2026-09-25", "sha256": "test", "license_or_accessibility": "test"}
    return source, phase7a, rule, embedding, embedding_manifest


def test_germline_annotation_counts_and_report_generation(tmp_path):
    source, phase7a, rule, embedding, embedding_manifest = _report_inputs()
    germline = audit_germline_columns(["VH", "VL"])
    assert germline["status"] == "UNAVAILABLE"
    report = render_report(source=source, phase7a=phase7a, rule=rule, embedding=embedding, embedding_manifest=embedding_manifest, germline=germline)
    assert "IGHV family counts: unavailable" in report
    assert "Prediction performance: NOT CALCULATED" in report
    destination = tmp_path / "sabdab2_diversity_report.md"
    write_report(destination, report)
    first_bytes = destination.read_bytes()
    write_report(destination, render_report(source=source, phase7a=phase7a, rule=rule, embedding=embedding, embedding_manifest=embedding_manifest, germline=germline))
    assert destination.read_bytes() == first_bytes

    annotated = pd.DataFrame([{"IGHV": "IGHV1", "IGKV": "IGKV2", "IGLV": ""}, {"IGHV": "IGHV1", "IGKV": "", "IGLV": "IGLV3"}])
    # Annotation counting uses the exact source values and never sequence inference.
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "source.csv"
        annotated.to_csv(path, index=False)
        counts = audit_germline_columns(list(annotated.columns), path)
    assert counts["IGHV_family_counts"] == {"IGHV1": 2}
    assert counts["IGKV_family_counts"] == {"IGKV2": 1}
