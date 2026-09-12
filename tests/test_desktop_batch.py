import os

import pandas as pd
import pytest

from desktop.batch_adapter import BatchRecord, BatchResult, analyze_file
from desktop.batch_adapter import fasta_requires_chain, input_mapping
from desktop.column_mapping import apply_mapping, infer_mapping
from desktop.batch_export import EXPORT_COLUMNS, summary_frame, write_summary_csv, write_summary_xlsx, write_template


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSVSSYLAWYQQKPGKAPKLLIYAASTLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQYNSYPLTFGQGTKVEIK"


def write_csv(tmp_path, rows, name="input.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_single_sequence_adapter_reuses_batch_analysis_and_preserves_facts(tmp_path):
    path = write_csv(tmp_path, [{"antibody_id": "TEST", "Sequence": VH}])
    result = analyze_file(path)
    record = result.records[0]
    assert (result.loaded, result.partial, result.invalid) == (1, 1, 0)
    assert record.antibody_id == "TEST"
    assert (record.vh_length, record.vl_length) == (120, 0)
    assert (record.total_sites, record.risk_score, record.risk_level) == (6, 66.3, "Medium Risk")
    assert record.status == "PARTIAL"


def test_canonical_dual_chain_and_fasta_inputs(tmp_path):
    csv_path = write_csv(tmp_path, [{"antibody_id": "AB-1", "VH": VH, "VL": VL}])
    csv_result = analyze_file(csv_path)
    assert csv_result.records[0].status == "SUCCESS"
    assert (csv_result.records[0].vh_length, csv_result.records[0].vl_length) == (120, len(VL))

    fasta = tmp_path / "input.fasta"
    fasta.write_text(f">AB-1_VH\n{VH}\n>AB-1_VL\n{VL}\n", encoding="utf-8")
    fasta_result = analyze_file(fasta)
    assert [(r.antibody_id, r.vh_length, r.vl_length) for r in fasta_result.records] == [("AB-1", 120, len(VL))]


def test_blank_and_duplicate_ids_are_preserved_with_warnings(tmp_path):
    path = write_csv(tmp_path, [
        {"antibody_id": "", "VH": VH, "VL": ""},
        {"antibody_id": "dup", "VH": VH, "VL": ""},
        {"antibody_id": "dup", "VH": VH, "VL": ""},
    ])
    result = analyze_file(path)
    assert [r.antibody_id for r in result.records] == ["Unnamed-001", "dup", "dup"]
    assert all(r.warnings for r in result.records)
    assert all(r.status == "PARTIAL" for r in result.records)


def test_mixed_rows_are_sorted_with_invalid_last(tmp_path):
    path = write_csv(tmp_path, [
        {"antibody_id": "invalid", "VH": "NOTAA", "VL": ""},
        {"antibody_id": "valid", "VH": VH, "VL": ""},
        {"antibody_id": "empty", "VH": "", "VL": ""},
    ])
    result = analyze_file(path)
    assert [r.antibody_id for r in result.records] == ["valid", "invalid", "empty"]
    assert result.records[0].status == "PARTIAL"
    assert all(r.status == "INVALID" for r in result.records[1:])


def test_duplicate_same_chain_fasta_remains_parse_error(tmp_path):
    path = tmp_path / "duplicate.fasta"
    path.write_text(f">AB_VH\n{VH}\n>AB_VH\n{VH}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重复"):
        analyze_file(path)


def test_batch_detail_keeps_chain_and_category_summary(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.batch_analysis import BatchAnalysisPage
    from models import RiskItem

    app = QApplication.instance() or QApplication([])
    record = BatchRecord("AB-1", 120, 0, 66.3, "Medium Risk", 2, 1, 1, 1, "PARTIAL", [], [
        ("VH", RiskItem(category="脱酰胺", motif="NG", position="55-56", region="CDR2")),
        ("VL", RiskItem(category="N-糖基化", motif="NXS", position="10-12", region="FW")),
    ])
    other = BatchRecord("AB-2", 120, 0, 20.0, "Low Risk", 0, 0, 0, 0, "PARTIAL")
    page = BatchAnalysisPage()
    page._done(BatchResult([record, other], "input.csv"))
    assert page.table.rowCount() == 2
    page.risk_filter.setCurrentText("Low")
    assert page.table.rowCount() == 1
    page.search.setText("AB-1")
    assert page.table.rowCount() == 0
    page.risk_filter.setCurrentText("All")
    page.table.selectRow(0)
    assert page.detail_table.item(0, 0).text() == "VH"
    assert page.detail_table.item(1, 0).text() == "VL"
    assert "脱酰胺: 1" in page.detail.text()
    assert "N-糖基化: 1" in page.detail.text()
    page.deleteLater(); app.processEvents()


def test_template_and_summary_exports_are_stable(tmp_path):
    template = tmp_path / "antibody_batch_template.xlsx"
    write_template(template)
    assert list(pd.read_excel(template).columns) == ["antibody_id", "VH", "VL"]
    assert VH not in template.read_bytes().decode("latin1", errors="ignore")

    result = analyze_file(write_csv(tmp_path, [
        {"antibody_id": "valid", "VH": VH, "VL": ""},
        {"antibody_id": "invalid", "VH": "NOTAA", "VL": ""},
    ]))
    csv_path = tmp_path / "results.csv"; xlsx_path = tmp_path / "results.xlsx"
    write_summary_csv(result, csv_path); write_summary_xlsx(result, xlsx_path)
    csv_frame = pd.read_csv(csv_path); xlsx_frame = pd.read_excel(xlsx_path, sheet_name="Batch Summary")
    assert list(csv_frame.columns) == EXPORT_COLUMNS
    assert list(xlsx_frame.columns) == EXPORT_COLUMNS
    assert list(csv_frame["analysis_status"]) == ["PARTIAL", "INVALID"]
    assert csv_frame.fillna("").to_dict("records") == xlsx_frame.fillna("").to_dict("records")
    assert csv_frame.loc[0, "risk_score"] == 66.3
    assert pd.isna(csv_frame.loc[1, "risk_score"])


def test_batch_to_single_prefers_vh_and_falls_back_to_vl():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.batch_analysis import BatchAnalysisPage

    app = QApplication.instance() or QApplication([]); opened = []
    page = BatchAnalysisPage(open_single=lambda antibody_id, sequence: opened.append((antibody_id, sequence)))
    vh_record = BatchRecord("VH-first", 120, 5, 1, "Low Risk", 0, 0, 0, 0, "SUCCESS", [], [], VH, VL)
    vl_record = BatchRecord("VL-only", 0, len(VL), 1, "Low Risk", 0, 0, 0, 0, "SUCCESS", [], [], "", VL)
    invalid = BatchRecord("invalid", 0, 0, float("nan"), "N/A", 0, 0, 0, 0, "INVALID")
    page._done(BatchResult([vh_record, vl_record, invalid], "input.csv"))
    page.table.selectRow(0); page.open_in_single()
    assert opened == [("VH-first", VH)]
    page.table.selectRow(1); page.open_in_single()
    assert opened[-1] == ("VL-only", VL)
    page.table.selectRow(2); assert not page.open_single_button.isEnabled()
    page.deleteLater(); app.processEvents()


def test_batch_transfer_eligibility_uses_validation_and_refreshes_chain():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.batch_analysis import BatchAnalysisPage

    app = QApplication.instance() or QApplication([]); single_calls = []; mutation_calls = []
    page = BatchAnalysisPage(open_single=lambda *args: single_calls.append(args), open_mutation=lambda *args: mutation_calls.append(args))
    vh_valid = BatchRecord("vh", 10, 0, 80, "Low Risk", 0, 0, 0, 0, "PARTIAL", [], [], "A" * 10, "")
    vl_fallback = BatchRecord("fallback", 0, 10, 80, "Low Risk", 0, 0, 0, 0, "PARTIAL", [], [], "NOTAA", "C" * 10)
    both_valid = BatchRecord("both", 10, 10, 80, "Low Risk", 0, 0, 0, 0, "SUCCESS", [], [], "A" * 10, "C" * 10)
    both_invalid = BatchRecord("invalid", 0, 0, float("nan"), "N/A", 0, 0, 0, 0, "INVALID", [], [], "NOTAA", "BAD")
    page._done(BatchResult([vh_valid, vl_fallback, both_valid, both_invalid], "input.csv"))

    page.table.selectRow(1); page.open_in_single()
    assert single_calls[-1] == ("fallback", "C" * 10)
    assert page.mutation_chain.currentText() == "VH"; assert not page.send_mutation_button.isEnabled()
    page.mutation_chain.setCurrentText("VL"); assert page.send_mutation_button.isEnabled(); page.send_to_mutation()
    assert mutation_calls[-1] == ("fallback", "C" * 10, "VL")

    page.table.selectRow(0); page.mutation_chain.setCurrentText("VH"); assert page.send_mutation_button.isEnabled()
    page.mutation_chain.setCurrentText("VL"); assert not page.send_mutation_button.isEnabled()
    page.mutation_chain.setCurrentText("VH"); assert page.send_mutation_button.isEnabled()
    page.table.selectRow(2); page.mutation_chain.setCurrentText("VH"); assert page.send_mutation_button.isEnabled(); page.mutation_chain.setCurrentText("VL"); assert page.send_mutation_button.isEnabled()
    page.table.selectRow(3); assert not page.open_single_button.isEnabled(); assert not page.send_mutation_button.isEnabled()
    page.deleteLater(); app.processEvents()


@pytest.mark.parametrize("columns", [
    ["ID", "Heavy Chain", "Light Chain"],
    ["Clone", "HC", "LC"],
    ["抗体编号", "重链序列", "轻链序列"],
    ["sample", "vh", "LIGHT CHAIN"],
])
def test_smart_alias_mapping_is_deterministic(columns):
    mapping, ambiguous, _ = infer_mapping(columns)
    assert not ambiguous
    assert mapping.get("antibody_id") in {"ID", "Clone", "抗体编号", "sample"}
    assert mapping["VH"] in {"Heavy Chain", "HC", "重链序列", "vh"}
    assert mapping["VL"] in {"Light Chain", "LC", "轻链序列", "LIGHT CHAIN"}


def test_smart_single_sequence_alias_maps_only_to_vh():
    frame = pd.DataFrame({"ID": ["A"], "Sequence": [VH]})
    mapping, ambiguous, _ = infer_mapping(frame.columns)
    assert not ambiguous
    canonical = apply_mapping(frame, mapping)
    assert list(canonical.columns) == ["antibody_id", "VH", "VL"]
    assert canonical.iloc[0]["antibody_id"] == "A" and canonical.iloc[0]["VH"] == VH and canonical.iloc[0]["VL"] == ""


def test_smart_alias_mapping_reads_xlsx(tmp_path):
    path = tmp_path / "aliases.xlsx"
    pd.DataFrame({"ID": ["A"], "Heavy Chain": [VH], "Light Chain": [""]}).to_excel(path, index=False)
    record = analyze_file(path).records[0]
    assert record.antibody_id == "A" and record.vh_length == 120 and record.vl_length == 0


@pytest.mark.parametrize("columns", [["VH", "Heavy Chain", "VL"], ["ID", "Clone ID", "VH", "VL"], ["Sample", "Seq_A", "Seq_B"]])
def test_conflicting_or_unknown_columns_require_manual_mapping(columns):
    _, ambiguous, _ = infer_mapping(columns)
    assert ambiguous


@pytest.mark.parametrize("label", ["_VH", "_VL", "_H", "_L", "_HC", "_LC", "_heavy", "_light"])
def test_fasta_chain_aliases_are_supported(tmp_path, label):
    path = tmp_path / "aliases.fasta"; path.write_text(f">Ab001{label}\n{VH}\n", encoding="utf-8")
    result = analyze_file(path)
    expected = "VH" if label.lower() in {"_vh", "_h", "_hc", "_heavy"} else "VL"
    record = result.records[0]
    assert (record.vh_length if expected == "VH" else record.vl_length) == 120


def test_chainless_fasta_requires_explicit_chain_choice(tmp_path):
    path = tmp_path / "plain.fasta"; path.write_text(f">Ab001\n{VH}\n", encoding="utf-8")
    assert not fasta_requires_chain(path)
    assert analyze_file(path).records[0].vh_length == 120
    assert analyze_file(path, chain="VL").records[0].vl_length == 120


def test_column_mapping_dialog_populates_and_rejects_duplicate_assignment():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.column_mapping_dialog import ColumnMappingDialog
    app = QApplication.instance() or QApplication([]); dialog = ColumnMappingDialog(["Sample", "Seq_A", "Seq_B"])
    assert dialog.fields["Antibody ID"].findText("Sample") >= 0
    dialog.fields["Antibody ID"].setCurrentText("Sample"); dialog.fields["VH"].setCurrentText("Seq_A"); dialog.fields["VL"].setCurrentText("Seq_A")
    dialog._accept(); assert dialog.result() == 0
    dialog.deleteLater(); app.processEvents()


def test_column_mapping_dialog_prefills_known_fields_but_keeps_conflicts_unresolved():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.column_mapping_dialog import ColumnMappingDialog

    app = QApplication.instance() or QApplication([])
    mapping, ambiguous, _ = infer_mapping(["ID", "Clone ID", "VH", "VL"]); assert ambiguous
    dialog = ColumnMappingDialog(["ID", "Clone ID", "VH", "VL"], initial_mapping=mapping)
    assert dialog.fields["Antibody ID"].currentText() == "None"
    assert dialog.fields["Antibody ID"].currentData() is None
    assert dialog.fields["VH"].currentText() == "VH"; assert dialog.fields["VL"].currentText() == "VL"; assert dialog.fields["Sequence"].currentText() == "None"
    dialog.deleteLater()
    mapping, ambiguous, _ = infer_mapping(["Sample", "Seq_A", "Seq_B"]); assert ambiguous
    dialog = ColumnMappingDialog(["Sample", "Seq_A", "Seq_B"], initial_mapping=mapping)
    assert dialog.fields["Antibody ID"].currentText() == "Sample"
    assert dialog.fields["VH"].currentText() == "None"; assert dialog.fields["VL"].currentText() == "None"
    assert dialog.fields["VH"].currentData() is None; assert dialog.fields["VL"].currentData() is None
    dialog.fields["VH"].setCurrentText("Seq_A"); dialog.fields["VL"].setCurrentText("Seq_B"); dialog._accept()
    assert dialog.mapping() == {"antibody_id": "Sample", "VH": "Seq_A", "VL": "Seq_B"}
    dialog.deleteLater(); app.processEvents()


def test_cancel_mapping_does_not_replace_existing_batch_state(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.batch_analysis import BatchAnalysisPage

    app = QApplication.instance() or QApplication([]); page = BatchAnalysisPage(); existing = BatchResult([BatchRecord("old")], "old.csv"); page._done(existing)
    page._path = "new.csv"; monkeypatch.setattr(page, "_resolve_input", lambda: (False, None)); page.analyze()
    assert page.records == existing.records; assert page.source.text() == "No file selected"
    page.deleteLater(); app.processEvents()
