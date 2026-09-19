import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from desktop.ml_adapter import DesktopMLService, build_mutation_pairs, compare_mutation_ml, prediction_cache_key
from desktop.mutation_adapter import compare_mutation
from desktop.widgets.mutation import MutationPage


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSVSSYLAWYQQKPGKAPKLLIYAASTLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQYNSYPLTFGQGTKVEIK"


class FakeMLService:
    def __init__(self, fail=False):
        self.fail = fail
        self.predict_calls = []
        self.status_calls = 0

    def status(self):
        self.status_calls += 1
        return {"status": "READY", "device": "cpu"}

    def predict(self, vh, vl):
        self.predict_calls.append((vh, vl))
        if self.fail:
            raise RuntimeError("synthetic local prediction failure")
        mutant = vh != VH or vl != VL
        return {
            "hic": {"predicted_value": 4.75 if mutant else 5.00},
            "developability": {"probability_not_developable": 0.37 if mutant else 0.42},
        }


def _app():
    return QApplication.instance() or QApplication([])


def _page(service, vh=VH, vl=VL):
    app = _app()
    page = MutationPage(ml_service=service)
    page.load_sequence("Ab-001", vh, "VH", vl_sequence=vl)
    return app, page


def _comparison():
    return compare_mutation(VH, "N55Q", "Ab-001", "VH")


def test_vh_and_vl_mutation_pair_construction_preserves_untouched_partner():
    vh_result = compare_mutation(VH, "N55Q", chain="VH")
    assert build_mutation_pairs("VH", VH, VL, vh_result.original_sequence, vh_result.mutant_sequence) == (VH, VL, vh_result.mutant_sequence, VL)
    vl_result = compare_mutation(VL, "Q55N", chain="VL")
    assert build_mutation_pairs("VL", VH, VL, vl_result.original_sequence, vl_result.mutant_sequence) == (VH, VL, VH, vl_result.mutant_sequence)


def test_pair_cache_key_is_sequence_and_model_aware():
    assert prediction_cache_key(VH, VL) != prediction_cache_key(VH, VL[:-1] + "A")
    service = DesktopMLService()
    calls = []

    class Predictor:
        def predict_supported_tasks(self, vh, vl):
            calls.append((vh, vl))
            return {"hic": {"predicted_value": 1}, "developability": {"probability_not_developable": 0.2}}

    service._predictor = Predictor()
    service.predict(VH, VL); service.predict(VH, VL)
    assert len(calls) == 1


def test_mutation_ml_comparison_arithmetic_has_no_sign_reversal():
    result = compare_mutation_ml(FakeMLService(), VH, VL, VH[:-1] + "A", VL)
    assert (result.baseline_hic, result.mutant_hic, result.delta_hic) == (5.0, 4.75, -0.25)
    assert result.baseline_probability == pytest.approx(0.42)
    assert result.mutant_probability == pytest.approx(0.37)
    assert result.delta_probability == pytest.approx(-0.05)
    assert result.metadata["mutation_effect_validation"] == "not_validated"


def test_mutation_ml_is_explicit_async_and_displays_neutral_comparison(monkeypatch):
    service = FakeMLService(); app, page = _page(service); page._done(_comparison())
    started = []
    monkeypatch.setattr(page.pool, "start", lambda worker: started.append(worker))
    assert page.ml_run_button.isEnabled()
    page.ml_run_button.click()
    assert len(started) == 1
    assert service.predict_calls == []
    started[0].run(); app.processEvents()
    assert page.ml_hic_baseline.text() == "5.00 min"
    assert page.ml_hic_mutant.text() == "4.75 min"
    assert page.ml_hic_delta.text() == "-0.25 min"
    assert page.ml_probability_baseline.text() == "42.0%"
    assert page.ml_probability_mutant.text() == "37.0%"
    assert page.ml_probability_delta.text() == "-5.0 pp"
    assert not page.ml_warning.isHidden()
    page.ml_details_button.click()
    details = page.ml_details.toPlainText().lower()
    assert "model-estimated differences" in page.ml_warning.text().lower()
    assert "not validated experimental mutation-effect" in page.ml_warning.text().lower()
    assert all(term not in details for term in ("recommended", "improved", "better", "success probability"))
    assert service.status_calls == 1
    page.deleteLater(); app.processEvents()


def test_missing_partner_disables_ml_without_provider_or_model_call(monkeypatch):
    service = FakeMLService(); app, page = _page(service, vl="")
    page._done(_comparison())
    assert not page.ml_run_button.isEnabled()
    assert "Both VH and VL are required" in page.ml_status.text()
    page.ml_run_button.click()
    assert service.status_calls == 0 and service.predict_calls == []
    page.deleteLater(); app.processEvents()


def test_ml_failure_preserves_existing_rule_comparison(monkeypatch):
    service = FakeMLService(fail=True); app, page = _page(service); result = _comparison(); page._done(result)
    started = []
    monkeypatch.setattr(page.pool, "start", lambda worker: started.append(worker))
    page.ml_run_button.click(); started[0].run(); app.processEvents()
    assert "66.30" in page.original_summary.text()
    assert "rule-based mutation results are preserved" in page.ml_status.text()
    assert page.ml_run_button.isEnabled()
    page.deleteLater(); app.processEvents()


def test_ml_comparison_clears_on_mutation_or_baseline_edit_and_candidate_switch(monkeypatch):
    service = FakeMLService(); app, page = _page(service); first = _comparison(); page._done(first)
    started = []
    monkeypatch.setattr(page.pool, "start", lambda worker: started.append(worker))
    page.ml_run_button.click(); started.pop().run(); app.processEvents()
    assert page.ml_hic_baseline.text() != "-"
    page.mutation.setText("M83L")
    assert page.ml_hic_baseline.text() == "-"
    page._done(first); page.add_candidate()
    second = compare_mutation(VH, "M83L", "Ab-001", "VH")
    page._done(second); page.add_candidate(); page.candidates.selectRow(0)
    assert page.ml_hic_baseline.text() == "-"
    page.vl_sequence.setPlainText(VL[:-1] + "A")
    assert page.ml_hic_baseline.text() == "-"
    page.deleteLater(); app.processEvents()
