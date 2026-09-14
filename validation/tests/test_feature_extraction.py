from __future__ import annotations

from pathlib import Path

import pandas as pd

from core import analyze_sequence
from scoring import compute_risk_score
from validation.features.extract_rule_features import extract_features, write_feature_outputs
from validation.features.feature_schema import (
    ANTIBODY_COLUMNS,
    CHAIN_COLUMNS,
    RISK_SITE_COLUMNS,
    feature_dictionary_frame,
)


ROOT = Path(__file__).resolve().parents[1]
REGRESSION_VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"


def test_regression_sequence_matches_frozen_production_output():
    tables = extract_features(pd.DataFrame([{
        "dataset": "test",
        "record_id": "regression",
        "antibody_id": "regression",
        "VH": REGRESSION_VH,
        "VL": "",
    }]), dataset="test")
    vh = tables.chain.loc[tables.chain["chain"] == "VH"].iloc[0]
    assert vh["sequence_length"] == 120
    assert vh["calculated_score"] == 66.3
    assert vh["risk_level"] == "Medium Risk"
    assert vh["total_sites"] == 6
    assert vh["cdr_sites"] == 4
    assert vh["rule_penalty"] == 33.7
    assert tables.risk_sites[["motif", "position", "category", "region"]].to_dict("records") == [
        {"motif": "NG", "position": "55-56", "category": "脱酰胺化", "region": "CDR2"},
        {"motif": "NS", "position": "84-85", "category": "脱酰胺化", "region": "FW"},
        {"motif": "DG", "position": "102-103", "category": "异构化", "region": "CDR3"},
        {"motif": "DS", "position": "62-63", "category": "异构化", "region": "CDR2"},
        {"motif": "M", "position": 83, "category": "氧化", "region": "FW"},
        {"motif": "M", "position": 107, "category": "氧化", "region": "CDR3"},
    ]


def test_jain_rows_are_preserved_and_successful():
    frame = pd.read_csv(ROOT / "data/processed/jain_137.csv")
    tables = extract_features(frame, dataset="jain_2017")
    assert len(frame) == 137
    assert len(tables.antibody) == 137
    assert len(tables.chain) == 274
    assert tables.audit["successful_analyses"] == 137
    assert tables.audit["failed_analyses"] == 0


def test_aintibody_rows_and_duplicate_sequences_are_preserved():
    frame = pd.read_csv(ROOT / "data/processed/aintibody_2026.csv")
    tables = extract_features(frame, dataset="aintibody_2026")
    assert len(frame) == 715
    assert len(tables.antibody) == 715
    assert tables.audit["unique_sequence_hashes"] == 686
    assert tables.audit["duplicate_sequence_records"] == 54
    assert tables.audit["duplicate_sequence_excess_rows"] == 29
    assert int(frame["sequence_hash"].duplicated(keep=False).sum()) == 54
    assert tables.audit["failed_analyses"] == 0


def test_vh_and_vl_are_analyzed_independently():
    frame = pd.read_csv(ROOT / "data/processed/jain_137.csv").iloc[[0]].copy()
    tables = extract_features(frame, dataset="jain_2017")
    for chain in ("VH", "VL"):
        sequence = frame.iloc[0][chain]
        expected = analyze_sequence(sequence, 31, 35, 50, 65, 99, 110)
        expected_score = compute_risk_score([(chain, expected)])
        actual = tables.chain.loc[tables.chain["chain"] == chain].iloc[0]
        assert actual["sequence_length"] == expected.sequence_length
        assert actual["calculated_score"] == expected_score.overall_score
        assert actual["total_sites"] == len(expected.risks)


def test_rule_penalty_is_derived_without_combining_scores():
    frame = pd.read_csv(ROOT / "data/processed/jain_137.csv").iloc[:5].copy()
    tables = extract_features(frame, dataset="jain_2017")
    for value, penalty in zip(tables.chain["calculated_score"], tables.chain["rule_penalty"]):
        assert penalty == 100.0 - value
    assert "calculated_score" not in [column for column in tables.antibody.columns if column == "calculated_score"]
    assert "VH_calculated_score" in tables.antibody.columns
    assert "VL_calculated_score" in tables.antibody.columns


def test_feature_extraction_is_deterministic_and_ignores_assay_values():
    frame = pd.read_csv(ROOT / "data/processed/aintibody_2026.csv").iloc[:4].copy()
    first = extract_features(frame, dataset="aintibody_2026")
    changed = frame.copy()
    for column in ("Tm, C", "KD_SPR", "HIC RT in gradient (min)"):
        if column in changed:
            changed[column] = 999999.0
    second = extract_features(changed, dataset="aintibody_2026")
    pd.testing.assert_frame_equal(first.chain, second.chain)
    pd.testing.assert_frame_equal(first.antibody, second.antibody)
    pd.testing.assert_frame_equal(first.risk_sites, second.risk_sites)
    pd.testing.assert_frame_equal(first.chain, extract_features(frame, dataset="aintibody_2026").chain)


def test_risk_site_schema_and_counts_match_chain_features():
    frame = pd.read_csv(ROOT / "data/processed/jain_137.csv").iloc[:3].copy()
    tables = extract_features(frame, dataset="jain_2017")
    assert list(tables.risk_sites.columns) == list(RISK_SITE_COLUMNS)
    for chain in ("VH", "VL"):
        chain_row = tables.chain.loc[tables.chain["chain"] == chain]
        site_count = len(tables.risk_sites.loc[tables.risk_sites["chain"] == chain])
        assert int(chain_row["total_sites"].sum()) == site_count


def test_feature_dictionary_covers_all_output_columns():
    dictionary = feature_dictionary_frame()
    assert set(CHAIN_COLUMNS) <= set(dictionary["feature_name"])
    assert set(ANTIBODY_COLUMNS) <= set(dictionary["feature_name"])
    assert set(RISK_SITE_COLUMNS) <= set(dictionary["feature_name"])
    assert {"calculated_score", "rule_penalty"} <= set(dictionary["feature_name"])


def test_missing_or_invalid_sequences_remain_visible():
    frame = pd.DataFrame([{
        "dataset": "test",
        "record_id": "bad-1",
        "antibody_id": "bad-1",
        "VH": "ACD1",
        "VL": "",
    }])
    tables = extract_features(frame, dataset="test")
    assert len(tables.antibody) == 1
    assert len(tables.chain) == 2
    assert tables.antibody.iloc[0]["analysis_status"] == "FAILED"
    assert tables.antibody.iloc[0]["analysis_error"]
    assert set(tables.chain["sequence_status"]) == {"INVALID", "MISSING"}
    assert tables.audit["failed_analyses"] == 1


def test_feature_outputs_are_generated_without_touching_source_tables(tmp_path):
    input_paths = {
        "jain_2017": ROOT / "data/processed/jain_137.csv",
        "aintibody_2026": ROOT / "data/processed/aintibody_2026.csv",
    }
    before = {path: path.read_bytes() for path in input_paths.values()}
    output_dir = tmp_path / "features"
    report_dir = tmp_path / "reports"
    results = write_feature_outputs(input_paths, output_dir=output_dir, report_dir=report_dir)
    assert set(results) == {"jain_2017", "aintibody_2026"}
    assert (output_dir / "jain_rule_features.csv").exists()
    assert (output_dir / "aintibody_rule_features.csv").exists()
    assert (output_dir / "risk_sites.csv").exists()
    assert (output_dir / "rule_feature_dictionary.csv").exists()
    assert {path: path.read_bytes() for path in input_paths.values()} == before
