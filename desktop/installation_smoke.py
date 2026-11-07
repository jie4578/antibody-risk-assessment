"""Offline synthetic smoke for the actual frozen executable, not clean-OS acceptance.

Only invoked with an explicit maintainer switch. No model loading or fitting.
"""
def run():
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    from PySide6.QtWidgets import QApplication
    from core import analyze_sequence
    from desktop.mutation_adapter import CDR_ARGS, compare_mutation
    from desktop.batch_adapter import analyze_file
    from desktop.credentials import CredentialStore
    from desktop.settings import RuntimeLLMConfig

    with patch.object(CredentialStore, "get", return_value=""), \
         patch("desktop.widgets.settings_page.load_settings", return_value=RuntimeLLMConfig()), \
         patch("desktop.main_window.load_settings", return_value=RuntimeLLMConfig()), \
         patch("socket.socket.connect", side_effect=RuntimeError("Smoke is offline")), \
         patch("socket.getaddrinfo", side_effect=RuntimeError("Smoke is offline")):
        from desktop.main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        import keyring
        import openai
        assert "WinVaultKeyring" in type(keyring.get_keyring()).__name__
        assert openai.OpenAI is not None
        window = MainWindow()
        assert window.stack.count() == 6
        for index in range(6):
            window.nav.setCurrentRow(index); app.processEvents()
        analysis = analyze_sequence("NNST", *CDR_ARGS)
        assert {("NNS", "1-3"), ("NST", "2-4")} <= {(r.motif, str(r.position)) for r in analysis.risks}
        window.single.set_input("INSTALL-SYNTHETIC", "NNST", analyze=True)
        comparison = compare_mutation("NNST", "N1Q", "INSTALL-SYNTHETIC", "VH")
        assert comparison.original_sequence != comparison.mutant_sequence
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic.csv"
            source.write_text("antibody_id,VH,VL\nDUP,NNST,ACD\nDUP,AAANVSTT,MMM\n", encoding="utf-8")
            batch = analyze_file(source)
            assert batch.loaded == 2 and {r.vh_sequence for r in batch.records} == {"NNST", "AAANVSTT"}
            from desktop.batch_export import write_summary_xlsx
            write_summary_xlsx(batch, Path(folder) / "synthetic.xlsx")
        from desktop.ml_deployment import inspect_deployment
        assert inspect_deployment({})["status"] == "NOT_INSTALLED"
        window.close(); window.deleteLater(); app.processEvents()
    return {"status": "PASS", "pages": 6, "synthetic_rule": "PASS", "batch_duplicate_rows": 2,
            "xlsx_export": "PASS", "mutation": "PASS", "missing_ml_startup": "PASS",
            "model_loaded": False, "trained": False, "provider_called": False,
            "keyring_backend": "WinVaultKeyring", "provider_sdk_importable": True,
            "clean_windows_qualification": False}
