from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import openpyxl
import pandas as pd

from validation.acquisition.inspect_aintibody import inspect_aintibody
from validation.acquisition.inspect_jain import inspect_jain
from validation.acquisition.provenance import build_entry, sha256_file, verify_manifest, write_manifest
from validation.preprocessing.normalize_aintibody import normalize_aintibody
from validation.preprocessing.normalize_jain import normalize_jain
from validation.schemas.dataset_schema import assess_sequences, sequence_hash

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_hash_is_deterministic_and_required(tmp_path):
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"test workbook bytes")
    entry = build_entry(
        dataset="test", article_title="title", doi="10.0000/test",
        publisher_or_repository="official", source_filename=source.name,
        supplementary_dataset_number="S1", local_raw_path=source,
        source_url="https://example.invalid/source.xlsx",
        data_availability_note="test note",
    )
    manifest = tmp_path / "manifest.json"
    write_manifest([entry], manifest)
    assert entry["sha256"] == sha256_file(source)
    assert verify_manifest(manifest) == []


def test_aintibody_official_workbook_is_parsed_and_preserved():
    path = ROOT / "data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx"
    inspection = inspect_aintibody(path)
    assert [sheet["name"] for sheet in inspection["sheets"]] == ["Dataset 1", "Dataset 2", "Dataset 3"]
    assert inspection["sheets"][2]["rows"] == 717
    frame, audit = normalize_aintibody(path)
    assert len(frame) == 715
    assert {"VH", "VL", "KD_SPR", "KD_KinExA", "average BVP score", "Tm, C", "Tagg, C", "total_developability_score"}.issubset(frame.columns)
    assert audit["duplicate_sequence_pair_rows"] >= 0
    assert set(audit["sequence_status_counts"]) <= {"VALID", "PARTIAL", "INVALID"}


def test_aintibody_processing_is_deterministic_and_does_not_synthesize_values():
    path = ROOT / "data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx"
    first, _ = normalize_aintibody(path)
    second, _ = normalize_aintibody(path)
    pd.testing.assert_frame_equal(first, second, check_dtype=False)
    source = pd.read_excel(path, sheet_name="Dataset 3", header=1, engine="openpyxl").dropna(axis=0, how="all").reset_index(drop=True)
    for column in source.columns:
        if column in first.columns:
            source_non_missing = int(source[column].notna().sum())
            output_non_missing = int(first[column].notna().sum())
            assert output_non_missing == source_non_missing, column


def test_raw_hash_unchanged_after_processing():
    path = ROOT / "data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx"
    before = sha256_file(path)
    normalize_aintibody(path)
    assert sha256_file(path) == before


def test_sequence_validation_delegates_and_hashes_deterministically():
    vh, vl, status, reason = assess_sequences(" acd ", "")
    assert (vh, vl, status) == ("ACD", "", "PARTIAL")
    assert "VL missing" in reason
    assert sequence_hash(" acd ", "") == sequence_hash("ACD", "")
    assert assess_sequences("ACD汉", "EFG")[2] == "INVALID"
    assert len(sequence_hash("ACD汉", "EFG")) == 64


def _write_fixture(path: Path, rows: list[list[object]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_jain_outer_join_preserves_unmatched_ids_and_mapping(tmp_path):
    raw = tmp_path / "jain"
    raw.mkdir()
    _write_fixture(raw / "pnas.1616408114.sd01.xlsx", [["Metadata", None], ["Antibody ID", "Clinical"], ["A", "yes"], ["ONLY_S1", "yes"]])
    _write_fixture(raw / "pnas.1616408114.sd02.xlsx", [["Sequences", None, None], ["Antibody ID", "VH", "VL"], ["A", "ACD", "EFG"], ["ONLY_S2", "ACD", "EFG"]])
    _write_fixture(raw / "pnas.1616408114.sd03.xlsx", [["Measurements", None], ["Antibody ID", "HIC"], ["A", 1.2], ["ONLY_S3", None]])
    frame, audit, dictionary = normalize_jain(raw)
    assert set(frame["antibody_id"]) == {"A", "ONLY_S1", "ONLY_S2", "ONLY_S3"}
    assert audit["unmatched_ids"]["metadata_only_ids"] >= 1
    assert "HIC" in frame.columns
    assert pd.isna(frame.loc[frame["antibody_id"] == "ONLY_S3", "HIC"].item())
    assert dictionary.loc[dictionary["original_name"] == "HIC", "direction_of_unfavorable_value"].item() == "UNKNOWN"


def test_jain_official_normalization_is_deterministic_and_raw_is_immutable():
    raw = ROOT / "data/raw/jain_2017"
    before = {path.name: sha256_file(path) for path in raw.glob("*.xlsx")}
    first, _, _ = normalize_jain(raw)
    second, _, _ = normalize_jain(raw)
    pd.testing.assert_frame_equal(first, second, check_dtype=False)
    assert len(first) == 137
    assert {path.name: sha256_file(path) for path in raw.glob("*.xlsx")} == before


def test_jain_inspection_reports_missing_files_without_fabrication(tmp_path):
    result = inspect_jain(tmp_path)
    assert all(item["status"] == "missing" for item in result["files"])


def test_core_and_scoring_match_frozen_baseline():
    repo = ROOT.parent
    baseline = "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d"
    for name in ("core.py", "scoring.py"):
        current = (repo / name).read_bytes()
        expected = subprocess.check_output(["git", "show", f"{baseline}:{name}"], cwd=repo)
        assert hashlib.sha256(current).digest() == hashlib.sha256(expected).digest(), name
