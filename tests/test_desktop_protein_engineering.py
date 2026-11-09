"""Offline Desktop integration with synthetic data and isolated settings."""
import json
from pathlib import Path
import time

import pytest

from protein_engineering.resources import template_bytes


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    from desktop.settings import RuntimeLLMConfig
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.delenv("PROTEIN_ENGINEERING_DATA_DIR", raising=False)
    monkeypatch.setattr("desktop.main_window.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig)
    monkeypatch.setattr("desktop.credentials.CredentialStore.get", lambda *args: "")


def idle(page, app):
    deadline = time.monotonic() + 5
    while page._busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    app.processEvents()
    assert not page._busy, page.status.text()


def test_seventh_entry_keeps_antibody_navigation_and_no_startup_database(qt_application, tmp_path):
    from desktop.main_window import MainWindow
    window = MainWindow()
    assert window.nav.count() == window.stack.count() == 7
    assert [window.nav.item(i).text() for i in range(6)] == ["单条分析", "批量分析", "突变", "文献", "AI 助手", "设置"]
    window.nav.setCurrentRow(6)
    assert window.stack.currentWidget() is window.protein_engineering
    page = window.protein_engineering
    assert page.store is None and not Path(page.database_path.text()).exists()
    assert page.tabs.count() == 7
    assert "C.1" in page.tabs.tabText(3)
    assert all("规划中" in page.tabs.tabText(i) for i in range(4, 7))
    assert page.import_button.isEnabled() is False
    for row in range(6):
        window.nav.setCurrentRow(row)
        assert window.stack.currentIndex() == row
    window.deleteLater()


def test_manual_save_button_works_first_click_and_shows_provenance(qt_application):
    from desktop.widgets.protein_engineering import ProteinEngineeringPage
    page = ProteinEngineeringPage()
    page.open_database_button.click(); idle(page, qt_application)
    form = page.forms["enzyme_targets"]
    form.inputs["target_id"].setText("SYN-T")
    form.inputs["target_name"].setText("Synthetic fixture only")
    form.save_button.click(); idle(page, qt_application)
    assert page.store.counts()["enzyme_targets"] == 1
    form = page.forms["protein_variants"]
    for key, text in {"variant_id": "SYN-WT", "target_id": "SYN-T", "variant_name": "Synthetic WT"}.items():
        form.inputs[key].setText(text)
    form.inputs["sequence"].setPlainText(" acd EFG ")
    form.inputs["variant_role"].setCurrentText("WT")
    form.save_button.click(); idle(page, qt_application)
    assert page.store.counts()["protein_variants"] == 1
    assert page.view_kind.currentData() == "protein_variants"
    page.record_table.selectRow(0)
    data = json.loads(page.details.toPlainText())
    assert data["original"]["sequence"] == " acd EFG "
    assert data["fields"]["sequence"] == "ACDEFG"
    assert data["provenance"]["source_kind"] == "MANUAL"
    assert page.store.counts()["assay_results"] == 0
    page.deleteLater()


def test_import_preview_confirmation_stale_inputs_and_snapshot(qt_application, tmp_path):
    from desktop.widgets.protein_engineering import ProteinEngineeringPage
    page = ProteinEngineeringPage()
    page.open_database(); idle(page, qt_application)
    path = tmp_path / "synthetic.csv"
    raw = b"target_id,target_name\nSYN-T,Synthetic fixture\n"
    path.write_bytes(raw)
    page.input_path.setText(str(path)); page.sheet.addItem("CSV")
    page.validate_input(); idle(page, qt_application)
    assert page.import_button.isEnabled()
    page.import_kind.setCurrentIndex(page.import_kind.findData("samples"))
    assert page.preview is None and not page.import_button.isEnabled()
    page.import_kind.setCurrentIndex(page.import_kind.findData("enzyme_targets"))
    page.validate_input(); idle(page, qt_application)
    page.import_button.click(); idle(page, qt_application)
    assert page.store.counts()["enzyme_targets"] == 1
    assert page.preview is None and not page.import_button.isEnabled()
    record = page.store.records("enzyme_targets")[0]
    assert page.store.source_bytes(record["provenance"]["source_sha256"]) == raw
    assert path.read_bytes() == raw
    page.deleteLater()


def test_changing_database_path_drops_view_state(qt_application, tmp_path):
    from desktop.widgets.protein_engineering import ProteinEngineeringPage
    page = ProteinEngineeringPage()
    page.open_database(); idle(page, qt_application)
    page.database_path.setText(str(tmp_path / "new.sqlite3"))
    page._database_changed()
    assert page.store is None and page.record_table.rowCount() == 0
    assert not page.refresh_button.isEnabled() and not page.import_button.isEnabled()
    assert not (tmp_path / "new.sqlite3").exists()
    page.deleteLater()


def test_tabs_do_not_leave_record_browser_below_empty_form_space(qt_application):
    from desktop.widgets.protein_engineering import ProteinEngineeringPage
    page = ProteinEngineeringPage()
    page.resize(1200, 1200)
    page.show(); qt_application.processEvents()
    intake_height = page.tabs.height()
    page.tabs.setCurrentIndex(1); qt_application.processEvents()
    assert page.tabs.height() > intake_height
    page.tabs.setCurrentIndex(4); qt_application.processEvents()
    assert page.tabs.height() < intake_height
    page.close(); page.deleteLater()


def test_template_actions_do_not_open_or_modify_canonical_resource(qt_application, tmp_path, monkeypatch):
    from desktop.widgets import protein_engineering as module
    page = module.ProteinEngineeringPage()
    target = tmp_path / "saved.csv"
    monkeypatch.setattr(module.QFileDialog, "getSaveFileName", lambda *args: (str(target), "CSV"))
    page.save_template_button.click()
    assert target.read_bytes() == template_bytes("enzyme_targets")
    copy_dir = tmp_path / "copy"; copy_dir.mkdir()
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **kwargs: str(copy_dir))
    opened = []
    monkeypatch.setattr(module.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    page.open_template_button.click()
    assert len(opened) == 1 and Path(opened[0]).parent == copy_dir
    assert Path(opened[0]).read_bytes() == template_bytes("enzyme_targets")
    page.deleteLater()
