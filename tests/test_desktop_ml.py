import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import QApplication

from desktop.widgets.single_analysis import SingleAnalysisPage


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSVSSYLAWYQQKPGKAPKLLIYAASTLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQYNSYPLTFGQGTKVEIK"


class FakeMLService:
    def __init__(self, status=None, result=None):
        self.status_value = status or {"status": "READY"}
        self.result = result or {
            "hic": {"predicted_hic": 1.2345},
            "developability": {"probability_not_developable": 0.42},
        }
        self.status_calls = 0
        self.predict_calls = []

    def status(self):
        self.status_calls += 1
        return self.status_value

    def predict(self, vh, vl):
        self.predict_calls.append((vh, vl))
        return self.result


def _app():
    return QApplication.instance() or QApplication([])


def _wait_for(app, predicate, timeout=2000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 20)
        if predicate():
            return True
    return predicate()


def _page(service):
    app = _app()
    page = SingleAnalysisPage(ml_service=service)
    page.sequence.setPlainText(VH)
    page.vl_sequence.setPlainText(VL)
    page.analyze()
    return app, page


def test_ml_requires_both_valid_chains_and_does_not_autorun():
    service = FakeMLService()
    app = _app()
    page = SingleAnalysisPage(ml_service=service)
    page.sequence.setPlainText(VH)
    page.analyze()
    assert not page.ml_button.isEnabled()
    assert "Both VH and VL are required" in page.ml_status.text()
    assert service.predict_calls == []
    page.deleteLater(); app.processEvents()


def test_ml_runs_explicitly_asynchronously_and_renders_research_outputs():
    service = FakeMLService()
    app, page = _page(service)
    assert page.ml_button.isEnabled()
    page.ml_button.click()
    assert not page.ml_button.isEnabled()
    assert _wait_for(app, lambda: page.ml_hic.text() == "1.23 min")
    assert service.predict_calls == [(VH, VL)]
    assert page.ml_probability.text() == "42.00%"
    assert page.ml_details_button.isEnabled()
    page.ml_details_button.click()
    details = page.ml_details.toPlainText()
    assert "Benchmark scope" in details
    assert "No categorical decision threshold" in details
    assert "experimental verification" in details.lower()
    page.deleteLater(); app.processEvents()


def test_ml_status_distinguishes_missing_artifacts_without_starting_worker():
    service = FakeMLService({"status": "MODEL_ARTIFACTS_MISSING"})
    app, page = _page(service)
    page.ml_button.click()
    assert "model artifacts are not available" in page.ml_status.text()
    assert service.predict_calls == []
    page.deleteLater(); app.processEvents()


def test_ml_input_edit_invalidates_result_and_discards_stale_completion():
    class BlockingService(FakeMLService):
        def __init__(self):
            super().__init__()
            self.release = False

        def predict(self, vh, vl):
            self.predict_calls.append((vh, vl))
            deadline = time.monotonic() + 1
            while not self.release and time.monotonic() < deadline:
                time.sleep(0.005)
            return self.result

    service = BlockingService()
    app, page = _page(service)
    page.ml_button.click()
    assert _wait_for(app, lambda: bool(service.predict_calls))
    page.sequence.setPlainText(VH[:-1] + "A")
    assert page.ml_hic.text() == "-"
    assert not page.ml_details_button.isEnabled()
    service.release = True
    assert _wait_for(app, lambda: page._ml_worker is None)
    assert page.ml_hic.text() == "-"
    page.deleteLater(); app.processEvents()


def test_ml_button_cannot_duplicate_running_request():
    class BlockingService(FakeMLService):
        def __init__(self):
            super().__init__()
            self.release = False

        def predict(self, vh, vl):
            self.predict_calls.append((vh, vl))
            while not self.release:
                time.sleep(0.005)
            return self.result

    service = BlockingService()
    app, page = _page(service)
    page.ml_button.click()
    assert _wait_for(app, lambda: bool(service.predict_calls))
    page.ml_button.click()
    assert len(service.predict_calls) == 1
    service.release = True
    assert _wait_for(app, lambda: page._ml_worker is None)
    page.deleteLater(); app.processEvents()
