import pytest

from desktop.mutation_adapter import MutationValidationError, compare_mutation, normalize_mutation


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"


def test_n55q_regression_and_structured_comparison():
    result = compare_mutation(VH, "N55Q", "Ab-001", "VH")
    assert result.mutation == "N55Q"
    assert result.chain == "VH"
    assert result.original_sequence == VH
    assert result.mutant_sequence[54] == "Q"
    assert (result.original_score, result.mutant_score, result.delta_score) == (66.3, 74.1, 7.8)
    assert (result.original_total_sites, result.mutant_total_sites, result.delta_total_sites) == (6, 5, -1)
    assert (result.original_cdr_sites, result.mutant_cdr_sites, result.delta_cdr_sites) == (4, 3, -1)
    assert [(r.position, r.motif, r.region) for r in result.removed_risks] == [("55-56", "NG", "CDR2")]
    assert not result.added_risks
    assert len(result.unchanged_risks) == 5


@pytest.mark.parametrize("value", ["N55Qextra", "xxxN55Q", "N55Q D102E", "N55Q,D102E", "N55", "55Q"])
def test_mutation_requires_strict_single_point_syntax(value):
    with pytest.raises(MutationValidationError):
        normalize_mutation(value)


def test_mutation_normalizes_case_and_outer_whitespace():
    assert normalize_mutation(" n55q ") == "N55Q"


@pytest.mark.parametrize("value", ["N55N", "N0Q", "N121Q", "A55Q", "X55Q", "N55X", ""])
def test_mutation_validation_errors(value):
    with pytest.raises(MutationValidationError):
        compare_mutation(VH, value)


def test_independent_candidates_do_not_change_original_baseline():
    first = compare_mutation(VH, "N55Q", chain="VH")
    second = compare_mutation(VH, "M83L", chain="VH")
    assert first.original_sequence == second.original_sequence == VH
    assert first.mutation == "N55Q"
    assert second.mutation == "M83L"


def test_chain_is_provenance_metadata_and_not_part_of_sequence_analysis():
    vh = compare_mutation(VH, "N55Q", chain="VH")
    unspecified = compare_mutation(VH, "N55Q")
    assert vh.chain == "VH"
    assert unspecified.chain == "Unspecified"
    assert vh.mutant_sequence == unspecified.mutant_sequence
    assert [r.position for r in vh.removed_risks] == [r.position for r in unspecified.removed_risks]


def test_mutation_page_renders_comparison_and_keeps_baseline(monkeypatch):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.mutation import MutationPage

    app = QApplication.instance() or QApplication([]); page = MutationPage(); started = []
    monkeypatch.setattr(page.pool, "start", lambda worker: started.append(worker))
    page.load_sequence("Ab-001", VH, "VH"); page.mutation.setText("N55Q"); page.simulate()
    assert not page.simulate_button.isEnabled(); assert len(started) == 1
    result = compare_mutation(VH, "N55Q", "Ab-001", "VH"); started[0].signals.finished.emit(result)
    assert page.simulate_button.isEnabled(); assert "66.30" in page.original_summary.text(); assert "74.10" in page.mutant_summary.text()
    assert "+7.80" in page.comparison.text(); assert page.removed_table.rowCount() == 1; assert page.added_table.rowCount() == 0
    page.add_candidate(); assert page.candidates.rowCount() == 1
    page.sequence.setPlainText(VH[:-1] + "A"); assert page.candidates.rowCount() == 0; assert page.original_summary.text().startswith("Length: -")
    page.deleteLater(); app.processEvents()


def test_main_window_exposes_single_and_batch_mutation_transfers():
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.main_window import MainWindow

    app = QApplication.instance() or QApplication([]); window = MainWindow()
    window._open_single("Ab-001", VH); assert window.single.antibody_id.text() == "Ab-001"; assert window.single.sequence.toPlainText() == VH
    window._open_mutation("Ab-001", VH, "VH"); assert window.nav.currentRow() == 2; assert window.mutation.chain.currentText() == "VH"
    window.deleteLater(); app.processEvents()


def test_real_windows_vh_input_succeeds_and_vl_mismatch_is_preserved(monkeypatch):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.mutation import MutationPage

    vl = "DIQMTQSPSSLSASVGDRVTITCRASQSISSYLAWYQQKPGKAPKLLIYAASSLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPYTFGQGTKVEIK"
    app = QApplication.instance() or QApplication([]); page = MutationPage(); started = []
    monkeypatch.setattr(page.pool, "start", lambda worker: started.append(worker))
    page.load_sequence("Ab-001", VH, "VH"); page.mutation.setText("N55Q"); page.simulate(); assert page.mutation.text() == "N55Q"
    started.pop().signals.finished.emit(compare_mutation(VH, "N55Q", "Ab-001", "VH")); assert "66.30" in page.original_summary.text(); assert "74.10" in page.mutant_summary.text()
    page.load_sequence("Ab-001", vl, "VL"); page.mutation.setText("N55Q"); page.simulate(); started.pop().signals.error.emit("Expected residue N at position 55, but found Q.")
    assert "Expected residue N at position 55, but found Q." in page.message.text(); assert "Invalid mutation format" not in page.message.text()
    page.deleteLater(); app.processEvents()
