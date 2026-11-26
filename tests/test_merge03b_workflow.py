"""Regression coverage for display-only, session-scoped workflow changes."""
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from desktop.integrations.adapters import inspect_biolab
from desktop.integrations.case_context import CaseContext, CaseSource, MATERIALS, RELATIONSHIPS
from desktop.integrations.citation_groups import CitationCounts, count_citations
from desktop.integrations.common import Evidence, IntegrationError
from integration_result_fixtures import biolab_fixture, literature_fixture, write_json
from test_desktop_research_workflow import isolated_settings, pump


def update_report(path, meta, change, *, allow_nan=False):
    data_path = path.parent / "report_data.json"
    data = json.loads(data_path.read_bytes())
    change(data)
    raw = json.dumps(data, allow_nan=allow_nan).encode()
    data_path.write_bytes(raw)
    meta["output_files"][0].update(sha256=sha256(raw).hexdigest(), size_bytes=len(raw))
    write_json(path, meta)
    return sha256(raw).hexdigest()


def populate_elisa(data):
    data["results"] = {
        "curve_parameters": dict(lower_asymptote=.1, upper_asymptote=2.1, midpoint_concentration=10,
                                 slope_magnitude=1, direction="increasing", concentration_unit="ng/mL",
                                 response_unit="AU"),
        "diagnostics": dict(n_fit_levels=9, r_squared=1.0, rmse=1.7e-16,
                            convergence_status="converged_candidate_selected"),
    }


def test_reads_verified_4pl_fields_and_limits(tmp_path):
    path, meta = biolab_fixture(tmp_path, report=True)
    observed = update_report(path, meta, populate_elisa)
    summary = inspect_biolab(path)
    result = summary.elisa
    assert result.report_data_sha256 == observed
    assert (result.lower_asymptote, result.upper_asymptote, result.midpoint_concentration,
            result.slope_magnitude) == (.1, 2.1, 10, 1)
    assert (result.direction, result.concentration_unit, result.response_unit) == ("increasing", "ng/mL", "AU")
    assert (result.n_fit_levels, result.r_squared, result.rmse) == (9, 1, 1.7e-16)
    assert result.convergence_status == "converged_candidate_selected"
    assert result.curve_validated is result.validated_quantification_enabled is False
    assert any("SYNTHETIC_QC" in item for item in summary.warnings)
    assert "SYNTHETIC upstream research-only limitation" in summary.limitations


def test_missing_fields_remain_none(tmp_path):
    path, _ = biolab_fixture(tmp_path, report=True)
    result = inspect_biolab(path).elisa
    assert result.midpoint_concentration is result.n_fit_levels is result.rmse is result.convergence_status is None


@pytest.mark.parametrize("section,name,value,error", [
    ("curve_parameters", "lower_asymptote", True, "INVALID_ELISA_FIELD"),
    ("curve_parameters", "upper_asymptote", "2.1", "INVALID_ELISA_FIELD"),
    ("curve_parameters", "direction", "unknown", "INVALID_ELISA_FIELD"),
    ("diagnostics", "n_fit_levels", False, "INVALID_ELISA_FIELD"),
    ("diagnostics", "n_fit_levels", 9.0, "INVALID_ELISA_FIELD"),
    ("diagnostics", "n_fit_levels", -1, "INVALID_ELISA_FIELD"),
    ("diagnostics", "rmse", float("inf"), "NONFINITE_JSON"),
    ("diagnostics", "r_squared", float("nan"), "NONFINITE_JSON"),
])
def test_invalid_elisa_projection_rejected_even_with_matching_hash(tmp_path, section, name, value, error):
    path, meta = biolab_fixture(tmp_path, report=True)
    def change(data):
        populate_elisa(data)
        data["results"][section][name] = value
    update_report(path, meta, change, allow_nan=True)
    with pytest.raises(IntegrationError, match=error):
        inspect_biolab(path)


def test_elisa_declared_hash_still_gates_projection(tmp_path):
    path, meta = biolab_fixture(tmp_path, report=True)
    update_report(path, meta, populate_elisa)
    meta["output_files"][0]["sha256"] = "b" * 64
    write_json(path, meta)
    with pytest.raises(IntegrationError, match="HASH_MISMATCH"):
        inspect_biolab(path)


@pytest.mark.parametrize("kind", ["generic_grouped", "welch_two_group", "run_manifest"])
def test_older_biolab_types_keep_their_contract(tmp_path, kind):
    path, meta = biolab_fixture(tmp_path, report=kind != "run_manifest")
    if kind != "run_manifest":
        meta["report_type"] = kind
        def change(data):
            data["report_type"] = kind
            data["methods"] = {"model": "fixture"}
            data["results"] = {"descriptive": []}
        update_report(path, meta, change)
    summary = inspect_biolab(path)
    assert summary.state == "COMPLETED_SOURCE_REPORTED"
    assert summary.elisa is None


def test_incomplete_report_cannot_show_elisa_projection(tmp_path):
    path, meta = biolab_fixture(tmp_path, status="FAILED", report=True)
    update_report(path, meta, populate_elisa)
    assert inspect_biolab(path).elisa is None


def test_citations_group_only_exact_document_page_text_and_source():
    ref = Evidence("doc-1", "a"*64, "SYNTHETIC quote", 2, 2, True, ("sample flag",),
                   batch_id="batch-a", location_status="RESULT_TEXT_MATCH", category="p_value", has_raw_quote=True)
    rows = (ref, replace(ref, category="sample_size"), replace(ref, document_id="doc-2"),
            replace(ref, page_start=3, page_end=3), replace(ref, source_content_sha256="b"*64),
            replace(ref, batch_id="batch-b"), replace(ref, quote="SYNTHETIC quote."),
            replace(ref, page_start=None), replace(ref, has_raw_quote=False),
            replace(ref, location_status="LOCATION_NOT_REPRODUCED"),
            replace(ref, source_content_sha256=None))
    assert count_citations(rows) == CitationCounts(11, 6, 4)
    assert ref.upstream_verified and ref.quality_flags == ("sample flag",)


def test_case_model_explicit_declarations_and_source_revision():
    model = CaseContext(case_id="DEMO", material=MATERIALS[0], notes="keep notes")
    first = CaseSource("same id", "a"*64, "SYNTHETIC", "first")
    second = CaseSource("same id", "b"*64, "SYNTHETIC", "second")
    model.set_source("biolab", first)
    model.set_source("sequence", second)
    assert model.association is None
    with pytest.raises(ValueError):
        model.associate(RELATIONSHIPS[2], " ")
    model.associate(RELATIONSHIPS[3], "User declaration")
    saved = model.association
    assert saved.kind == "用户声明属于同一实验样品" and len(saved.sources) == 2
    model.associate(RELATIONSHIPS[1], "Case only")
    assert model.association.basis == "Case only"
    model.set_source("biolab", first)  # Even reaccepting the same manifest requires confirmation.
    assert model.association is None and model.notes == "keep notes"


def test_gui_case_preserves_failed_literature_and_invalidates_successful_reload(qt_application, tmp_path):
    from desktop.main_window import MainWindow
    win = MainWindow()
    workflow = win.research_workflow
    case = workflow.case
    case.case_id.setText("SYNTHETIC-CASE")
    case.topic.setText("SYNTHETIC")
    case.material.setCurrentIndex(1)
    case.notes.setPlainText("retain")
    win.single.set_input("SYNTHETIC", "A" * 120)
    case.attach_sequence.click()
    assert case.context.sources["sequence"].sha256 == sha256(b"A" * 120).hexdigest()
    path, _ = literature_fixture(tmp_path / "good")
    bad, _ = literature_fixture(tmp_path / "bad")
    (bad.parent / "status.json").unlink()
    workflow.literature.import_manifest(path)
    pump(qt_application, lambda: not workflow.literature._busy)
    assert set(case.context.sources) == {"sequence", "literature"} and case.context.association is None
    case.relationship.setCurrentIndex(1)
    case.basis.setText("合成材料无共同分子或样品")
    case.apply_button.click()
    previous = case.context.association
    assert previous and "未建立共同分子或样品身份" in case.status.text()
    lit = workflow.literature
    snapshot = lit.summary, lit.quote.toPlainText(), lit.count_label.text(), lit.document_table.currentRow()
    lit.import_manifest(bad)
    pump(qt_application, lambda: not lit._busy)
    assert snapshot == (lit.summary, lit.quote.toPlainText(), lit.count_label.text(), lit.document_table.currentRow())
    assert case.context.association is previous
    lit.import_manifest(path)
    pump(qt_application, lambda: not lit._busy)
    assert case.context.association is None and not case.basis.text() and "重新确认" in case.status.text()
    case.relationship.setCurrentIndex(2)
    case.basis.setText("明确的声明")
    case.apply_button.click()
    assert "用户声明" in case.status.text() and "未经系统验证" in case.status.text()
    win.single.antibody_id.setText("CHANGED")
    assert case.context.association is None and "sequence" not in case.context.sources
    case.attach_sequence.click()
    assert "sequence" not in case.context.sources and case.context.notes == "retain"
    lit.clear_button.click()
    assert not case.context.sources
    win.close()


def test_gui_biolab_summary_and_clearing(qt_application, tmp_path):
    from desktop.widgets.biolab_summary import BioLabSummaryPanel
    panel = BioLabSummaryPanel()
    path, meta = biolab_fixture(tmp_path, report=True)
    update_report(path, meta, populate_elisa)
    panel.import_manifest(path)
    pump(qt_application, lambda: not panel._busy)
    assert panel.metrics["midpoint_concentration"].text() == "10"
    assert panel.metrics["units"].text() == "ng/mL / AU"
    assert "validated_quantification_enabled=false" in panel.summary_notice.text()
    assert "SYNTHETIC_QC" in panel.qc.toPlainText()
    assert json.loads(panel.details.toPlainText())["elisa"]["n_fit_levels"] == 9
    panel.clear_button.click()
    assert panel.metrics["midpoint_concentration"].text() == "未提供"
    assert not panel.qc.toPlainText()
    panel.close()


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
def test_reader_shares_first_viewport_with_documents(qt_application, tmp_path, size):
    from PySide6.QtCore import QPoint
    from desktop.main_window import MainWindow
    win = MainWindow()
    win.resize(*size)
    win.show()
    win.nav.setCurrentRow(7)
    win.research_workflow.tabs.setCurrentIndex(1)
    reader = win.research_workflow.literature
    path, _ = literature_fixture(tmp_path)
    reader.import_manifest(path)
    pump(qt_application, lambda: not reader._busy)
    win.content_scroll.verticalScrollBar().setValue(0)
    qt_application.processEvents()
    viewport = win.content_scroll.viewport()
    for widget in (reader.document_table, reader.evidence_table, reader.quote):
        assert viewport.rect().contains(widget.mapTo(viewport, QPoint(10, 36)))
    assert reader.document_details.isHidden()
    reader.reader_tabs.setCurrentWidget(reader.document_details)
    assert "PDF SHA256" in reader.document_details.toPlainText()
    win.close()


def test_source_title_ignores_unrelated_installed_metadata(tmp_path, monkeypatch):
    import desktop.version as app_version
    root = tmp_path / "checkout"
    (root / "desktop").mkdir(parents=True)
    monkeypatch.setattr(app_version, "__file__", str(root / "desktop/version.py"))
    monkeypatch.setattr(app_version, "version", lambda package: "0.1.0")
    assert app_version.project_version() == "0.1.0"
    (root / "pyproject.toml").write_text('[project]\nname = "antibody-risk"\nversion = "4.1.0rc2"\n', encoding="utf8")
    assert app_version.project_version() == "4.1.0rc2"
    monkeypatch.setattr(app_version.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_version.sys, "_MEIPASS", str(root), raising=False)
    (root / "VERSION.txt").write_text("4.0.0", encoding="ascii")
    assert app_version.project_version() == "4.0.0"
