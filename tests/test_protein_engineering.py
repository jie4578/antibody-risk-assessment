"""Synthetic records only: data identity, transactional provenance and packaging."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from protein_engineering import SCHEMA_VERSION
from protein_engineering.importer import ImportFormatError, preview_bytes, preview_file, sheet_names
from protein_engineering.models import EnzymeTarget, ExperimentBatch, ProteinSample, ProteinVariant
from protein_engineering.resources import TABLE_LABELS, document_text, save_template, template_bytes
from protein_engineering.schema import columns
from protein_engineering.sequences import normalize_sequence
from protein_engineering.storage import ProteinStore, StorageError, default_database_path

ROOT = Path(__file__).resolve().parents[1]


def csv_source(kind, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns(kind))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


@pytest.fixture
def store(tmp_path):
    return ProteinStore(tmp_path / "research.sqlite3")


@pytest.fixture
def linked_store(store):
    for record in (EnzymeTarget("SYN-T", "Synthetic enzyme"),
                   ProteinVariant("SYN-WT", "SYN-T", "Synthetic WT", "WT", "ACDEFG"),
                   ProteinSample("SYN-S", "SYN-WT"), ExperimentBatch("SYN-B", "SYN-ASSAY", "reported-only")):
        store.add(record)
    return store


def test_phase0_resources_match_provenance_and_are_header_only():
    manifest = json.loads((ROOT / "docs/protein_engineering/PHASE0_PACKAGE_PROVENANCE.json").read_text(encoding="utf-8"))
    assert len(manifest["files"]) == 13
    for item in manifest["files"]:
        for key in ("local_path", "runtime_path"):
            assert hashlib.sha256((ROOT / item[key]).read_bytes()).hexdigest() == item["sha256"]
    assert len(TABLE_LABELS) == 9
    for kind in TABLE_LABELS:
        assert len(list(csv.reader(io.StringIO(template_bytes(kind).decode("utf-8-sig"))))) == 1
    assert "尚未实现" in document_text("FOUNDATION_STATUS.md")


def test_template_export_does_not_overwrite_experimental_file(tmp_path):
    original = template_bytes("samples")
    target = tmp_path / "samples.csv"
    save_template("samples", target)
    assert target.read_bytes() == original
    with pytest.raises(FileExistsError):
        save_template("protein_variants", target)
    assert target.read_bytes() == original
    with pytest.raises(ValueError):
        template_bytes("../../private")


@pytest.mark.parametrize("raw,expected,status", [(" acd\nEFG ", "ACDEFG", "VALID"), ("BXZJUO", "BXZJUO", "AMBIGUOUS"),
                                                ("", "", "INVALID"), ("A-*", "A-*", "INVALID"), ("Aß", "Aß", "INVALID")])
def test_sequence_hash_and_no_residue_invention(raw, expected, status):
    result = normalize_sequence(raw)
    assert result.normalized == expected and result.original == raw and result.status == status
    assert result.sha256 == hashlib.sha256(expected.encode()).hexdigest()
    assert normalize_sequence(raw) == result


def test_manual_record_graph_original_and_source_bytes(linked_store):
    variants = linked_store.records("protein_variants")
    assert variants[0]["fields"]["sequence"] == "ACDEFG"
    provenance = variants[0]["provenance"]
    assert provenance["source_kind"] == "MANUAL"
    raw = linked_store.source_bytes(provenance["source_sha256"])
    assert json.loads(raw)["variant_id"] == "SYN-WT"
    assert linked_store.counts()["assay_results"] == 0
    assert linked_store.counts()["ai_predictions"] == 0


def test_same_sequence_different_ids_preserved_and_original_retained(store):
    store.add(EnzymeTarget("T", "Synthetic"))
    data = csv_source("protein_variants", [dict(variant_id="V1", target_id="T", variant_name="one", variant_role="WT", sequence=" acd\nEFG "),
                                                   dict(variant_id="V2", target_id="T", variant_name="two", variant_role="DESIGNED", sequence="ACDEFG")])
    preview = preview_bytes("protein_variants", data, "synthetic.csv")
    assert preview.valid
    assert any(i.code == "DUPLICATE_SEQUENCE" for i in preview.issues)
    assert store.commit_preview(preview)["rows"] == 2
    assert store.records("protein_variants")[0]["original"]["sequence"] == " acd\nEFG "
    audit = store.sequence_audit()
    assert audit["records"] == 2 and audit["unique_sequences"] == 1 and audit["duplicate_groups"][0]["records"] == 2
    assert store.source_bytes(preview.sha256) == data


def test_missing_observations_preserved_separate_from_predictions(linked_store):
    observations = csv_source("assay_results", [dict(result_id="O1", sample_id="SYN-S", batch_id="SYN-B", metric_name="synthetic activity", metric_value="", metric_unit="U/mL")])
    linked_store.commit_preview(preview_bytes("assay_results", observations, "observations.csv"))
    predictions = csv_source("ai_predictions", [dict(prediction_id="P1", variant_id="SYN-WT", predicted_metric="synthetic activity", predicted_value="42", predicted_unit="U/mL")])
    linked_store.commit_preview(preview_bytes("ai_predictions", predictions, "predictions.csv"))
    measured = linked_store.records("assay_results")[0]
    assert measured["fields"]["metric_value"] is None
    assert measured["original"]["metric_value"] == ""
    assert linked_store.records("ai_predictions")[0]["fields"]["predicted_value"] == "42"
    assert linked_store.counts()["assay_results"] == linked_store.counts()["ai_predictions"] == 1


def test_original_assay_columns_units_and_zero_unchanged(linked_store):
    raw = b'result_id,batch_id,sample_id,metric_name,metric_value,metric_unit,custom_protocol_note\nO1,SYN-B,SYN-S,synthetic,0,arbitrary unit,as reported\n'
    preview = preview_bytes("assay_results", raw, "reported.csv")
    assert preview.valid
    linked_store.commit_preview(preview)
    record = linked_store.records("assay_results")[0]
    assert record["fields"]["metric_value"] == "0"
    assert record["fields"]["metric_unit"] == "arbitrary unit"
    assert record["original"]["custom_protocol_note"] == "as reported"
    assert record["provenance"]["source_row"] == 2


def test_atomic_import_missing_reference_no_partial_rows_or_source(store):
    store.add(EnzymeTarget("T", "Synthetic"))
    raw = csv_source("protein_variants", [dict(variant_id="GOOD", target_id="T", variant_name="one", variant_role="WT", sequence="ACD"),
                                                  dict(variant_id="BAD", target_id="MISSING", variant_name="two", variant_role="OTHER", sequence="ACD")])
    preview = preview_bytes("protein_variants", raw, "atomic.csv")
    assert preview.valid
    with pytest.raises(StorageError, match="引用"):
        store.commit_preview(preview)
    assert store.counts()["protein_variants"] == 0
    with pytest.raises(StorageError, match="来源不存在"):
        store.source_bytes(preview.sha256)


def test_duplicate_ids_and_reimport_do_not_overwrite(store):
    raw = csv_source("enzyme_targets", [dict(target_id="T", target_name="first"), dict(target_id="T", target_name="second")])
    preview = preview_bytes("enzyme_targets", raw, "duplicates.csv")
    assert not preview.valid and any(i.code == "DUPLICATE_ID" for i in preview.issues)
    with pytest.raises(StorageError):
        store.commit_preview(preview)
    assert store.counts()["enzyme_targets"] == 0
    valid = preview_bytes("enzyme_targets", csv_source("enzyme_targets", [dict(target_id="T", target_name="first")]), "ok.csv")
    store.commit_preview(valid)
    with pytest.raises(StorageError, match="已导入"):
        store.commit_preview(valid)
    with pytest.raises(StorageError, match="ID 已存在"):
        store.add(EnzymeTarget("T", "replacement"))
    assert store.records("enzyme_targets")[0]["fields"]["target_name"] == "first"


def test_parent_forward_reference_and_cycles(store):
    store.add(EnzymeTarget("T", "Synthetic"))
    raw = csv_source("protein_variants", [dict(variant_id="V", target_id="T", variant_name="child", variant_role="DESIGNED", sequence="ACD", parent_variant_id="WT"),
                                                  dict(variant_id="WT", target_id="T", variant_name="parent", variant_role="WT", sequence="ACD")])
    assert store.commit_preview(preview_bytes("protein_variants", raw, "lineage.csv"))["rows"] == 2
    cycle = csv_source("protein_variants", [dict(variant_id="C1", target_id="T", variant_name="one", variant_role="OTHER", sequence="ACD", parent_variant_id="C2"),
                                                    dict(variant_id="C2", target_id="T", variant_name="two", variant_role="OTHER", sequence="ACD", parent_variant_id="C1")])
    with pytest.raises(StorageError, match="循环"):
        store.commit_preview(preview_bytes("protein_variants", cycle, "cycle.csv"))
    assert store.counts()["protein_variants"] == 2


def test_cross_target_reference_rejected(linked_store):
    linked_store.add(EnzymeTarget("OTHER", "Another synthetic target"))
    with pytest.raises(StorageError, match="同一靶标"):
        linked_store.add(ProteinVariant("OTHER-V", "OTHER", "Synthetic", "DESIGNED", "ACD", reference_variant_id="SYN-WT"))


def test_source_change_after_preview_and_mutated_preview_blocked(store, tmp_path):
    path = tmp_path / "input.csv"
    original = csv_source("enzyme_targets", [dict(target_id="T", target_name="original")])
    path.write_bytes(original)
    preview = preview_file("enzyme_targets", path)
    preview.rows[0].fields["target_name"] = "tampered preview"
    store.commit_preview(preview)
    assert store.records("enzyme_targets")[0]["fields"]["target_name"] == "original"
    next_path = tmp_path / "next.csv"
    next_path.write_bytes(original.replace(b',T,', b',U,'))
    stale = preview_file("enzyme_targets", next_path)
    next_path.write_bytes(b"changed")
    with pytest.raises(StorageError, match="发生变化"):
        store.commit_preview(stale)
    assert path.read_bytes() == original


@pytest.mark.parametrize("value,unit,code", [("NaN", "U/mL", "FINITE_NUMBER_REQUIRED"), ("Infinity", "U/mL", "FINITE_NUMBER_REQUIRED"),
                                           ("<0.1", "U/mL", "FINITE_NUMBER_REQUIRED"), ("1.2", "", "UNIT_REQUIRED")])
def test_nonfinite_qualified_or_unitless_measurements_not_synthesized(value, unit, code):
    raw = csv_source("assay_results", [dict(result_id="R", batch_id="B", sample_id="S", metric_name="synthetic", metric_value=value, metric_unit=unit)])
    preview = preview_bytes("assay_results", raw, "bad.csv")
    assert not preview.valid and any(i.code == code for i in preview.issues)


def test_utc_not_guessed():
    raw = csv_source("samples", [dict(sample_id="S", variant_id="V", prepared_at_utc="2026-11-09T12:00:00")])
    preview = preview_bytes("samples", raw, "time.csv")
    assert not preview.valid and any(i.code == "UTC_REQUIRED" for i in preview.issues)


def test_xlsx_sheet_row_and_formula_handling(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / "synthetic.xlsx"
    book = Workbook()
    book.active.title = "README"
    book.active.append(["not a data sheet"])
    sheet = book.create_sheet("Targets")
    sheet.append(["target_id", "target_name"])
    sheet.append(["T", "Synthetic enzyme"])
    sheet.append(["X", "=1+1"])
    book.save(path)
    before = path.read_bytes()
    assert sheet_names(path) == ("README", "Targets")
    with pytest.raises(ImportFormatError, match="显式选择"):
        preview_file("enzyme_targets", path)
    preview = preview_file("enzyme_targets", path, "Targets")
    assert not preview.valid
    assert any(i.code == "FORMULA_OR_CELL_ERROR" and i.row == 3 for i in preview.issues)
    assert preview.rows[0].source_row == 2
    assert path.read_bytes() == before


def test_xlsx_numeric_id_not_reconstructed(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(["target_id", "target_name"])
    book.active.append([1, "Synthetic"])
    path = tmp_path / "numbers.xlsx"; book.save(path)
    preview = preview_file("enzyme_targets", path)
    assert not preview.valid and any(i.code == "TEXT_ID_REQUIRED" for i in preview.issues)


def test_far_right_xlsx_data_not_silently_discarded(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(["target_id", "target_name"])
    book.active.append(["T", "Synthetic"])
    book.active.cell(2, 300, "must not disappear")
    path = tmp_path / "far-right.xlsx"; book.save(path)
    preview = preview_file("enzyme_targets", path)
    assert not preview.valid and any(i.code == "ROW_WIDTH" for i in preview.issues)


def test_limits_refuse_instead_of_truncating(tmp_path, monkeypatch):
    from protein_engineering import importer
    monkeypatch.setattr(importer, "MAX_ROWS", 1)
    raw = csv_source("enzyme_targets", [dict(target_id="T1", target_name="one"), dict(target_id="T2", target_name="two")])
    with pytest.raises(ImportFormatError, match="不静默截断"):
        preview_bytes("enzyme_targets", raw, "too-many.csv")
    path = tmp_path / "size.csv"; path.write_bytes(raw)
    monkeypatch.setattr(importer, "MAX_FILE_BYTES", 10)
    with pytest.raises(ImportFormatError, match="超过"):
        preview_file("enzyme_targets", path)


def test_supplied_sequence_hash_must_match_and_target_reference_is_audited(store):
    raw = csv_source("enzyme_targets", [dict(target_id="T", target_name="Synthetic", reference_sequence_variant_id="WT")])
    store.commit_preview(preview_bytes("enzyme_targets", raw, "target.csv"))
    assert store.unresolved_target_references() == [{"target_id": "T", "reference_variant_id": "WT", "status": "UNRESOLVED_OR_CROSS_TARGET"}]
    bad = csv_source("protein_variants", [dict(variant_id="WT", target_id="T", variant_name="WT", variant_role="WT", sequence="ACD", sequence_sha256="0"*64)])
    preview = preview_bytes("protein_variants", bad, "bad-hash.csv")
    assert not preview.valid and any(i.code == "HASH_MISMATCH" for i in preview.issues)
    store.add(ProteinVariant("WT", "T", "WT", "WT", "ACD"))
    assert store.unresolved_target_references() == []


def test_header_only_and_blank_rows_are_audited(store):
    preview = preview_bytes("enzyme_targets", template_bytes("enzyme_targets") + b'\n', "empty.csv")
    assert preview.valid and len(preview.rows) == 0 and preview.blank_rows == 1
    result = store.commit_preview(preview)
    assert result["rows"] == 0 and store.counts()["enzyme_targets"] == 0
    assert store.source_bytes(result["source_sha256"]) == preview.raw_bytes


@pytest.mark.parametrize("raw", [b"target_id,target_id\nT,T\n", b"antibody_id,VH,VL\nA,NNST,ACD\n", b"\xff\xfe\x01"])
def test_wrong_schema_duplicate_headers_or_encoding_rejected(raw):
    with pytest.raises(ImportFormatError):
        preview_bytes("enzyme_targets", raw, "wrong.csv")


def test_migrations_keep_records_and_refuse_other_or_future_db(store, tmp_path):
    store.add(EnzymeTarget("LEGACY", "Synthetic persisted record"))
    with sqlite3.connect(store.path) as db:
        # Construct a genuine v1 fixture, not a v3 DB with a forged version number.
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name NOT IN ('source_no_update','source_no_delete')").fetchall():
            db.execute('DROP TRIGGER "' + name + '"')
        db.execute("DROP TABLE initial_rate_inputs")
        db.execute("DROP TABLE initial_rate_analyses")
        for name in ("variant_sequence_hash", "sample_variant", "measured_sample", "predicted_variant"):
            db.execute("DROP INDEX " + name)
        db.execute("DELETE FROM schema_migrations WHERE version>1")
        db.execute("PRAGMA user_version=1")
    upgraded = ProteinStore(store.path)
    assert upgraded.records("enzyme_targets")[0]["fields"]["target_id"] == "LEGACY"
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        db.execute("PRAGMA user_version=999")
    with pytest.raises(StorageError, match="不受支持"):
        ProteinStore(store.path)
    other = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(other) as db:
        db.execute("CREATE TABLE private_other_application(value TEXT)")
    before = other.read_bytes()
    with pytest.raises(StorageError, match="其他数据库"):
        ProteinStore(other)
    assert other.read_bytes() == before


def test_snapshot_is_immutable_in_application_connection(store):
    result = store.add(EnzymeTarget("T", "Synthetic"))
    sha = result["source_sha256"]
    with store._connection() as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE source_files SET raw_bytes=? WHERE sha256=?", (b"changed", sha))
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM source_files WHERE sha256=?", (sha,))
    assert hashlib.sha256(store.source_bytes(sha)).hexdigest() == sha


def test_view_only_foreign_database_is_not_adopted(tmp_path):
    path = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE VIEW other_application AS SELECT 1 AS value")
    before = path.read_bytes()
    with pytest.raises(StorageError, match="其他数据库"):
        ProteinStore(path)
    assert path.read_bytes() == before


def test_tampered_migration_history_refused(store):
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE schema_migrations SET sha256='modified' WHERE version=1")
    with pytest.raises(StorageError, match="摘要不匹配"):
        ProteinStore(store.path)


def test_absent_measurement_column_is_explicit_missing(linked_store):
    raw = b'result_id,batch_id,sample_id,metric_name\nO1,SYN-B,SYN-S,synthetic\n'
    preview = preview_bytes("assay_results", raw, "missing.csv")
    assert preview.valid and any(i.code == "MISSING_VALUE" for i in preview.issues)
    linked_store.commit_preview(preview)
    record = linked_store.records("assay_results")[0]
    assert record["fields"]["metric_value"] is None
    assert "metric_value" not in record["original"]


def test_database_defaults_outside_repo_and_domain_has_no_antibody_dependencies(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("PROTEIN_ENGINEERING_DATA_DIR", raising=False)
    assert default_database_path().is_relative_to(tmp_path)
    script = "import sys; sys.path.insert(0,sys.argv[1]); import protein_engineering.storage; assert not any(n.split('.')[0] in {'core','scoring','ml','ml_inference','validation','desktop'} for n in sys.modules)"
    result = subprocess.run([sys.executable, "-I", "-c", script, str(ROOT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
