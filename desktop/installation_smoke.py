"""Offline synthetic smoke for the actual frozen executable, not clean-OS acceptance.

Only invoked with an explicit maintainer switch. No model loading or training.
"""
def _basic_run():
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
        assert window.stack.count() == 8 and window.nav.count() == 8
        assert window.protein_engineering.store is None
        for index in range(8):
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
            from protein_engineering.storage import ProteinStore
            from protein_engineering.models import EnzymeTarget, ProteinVariant, ProteinSample, ExperimentBatch
            from protein_engineering.resources import TABLE_LABELS, template_bytes, document_text
            for kind in TABLE_LABELS:
                assert template_bytes(kind).strip().count(b"\n") == 0
            assert document_text("FOUNDATION_STATUS.md")
            store = ProteinStore(Path(folder) / "protein-synthetic.sqlite3")
            for record in (EnzymeTarget("SYN-T", "Synthetic fixture"),
                           ProteinVariant("SYN-WT", "SYN-T", "WT", "WT", "ACDEFG"),
                           ProteinSample("SYN-S", "SYN-WT"), ExperimentBatch("SYN-B", "SYN-A", "reported-only")):
                assert store.add(record)["rows"] == 1
            assert store.counts()["assay_results"] == 0
            from protein_engineering.importer import preview_bytes
            from protein_engineering.initial_rate import RateConfig
            timecourse=b'observation_id,batch_id,sample_id,time_value,time_unit,raw_signal,signal_unit\nT0,SYN-B,SYN-S,0,min,5,RFU\nT1,SYN-B,SYN-S,1,min,7,RFU\nT2,SYN-B,SYN-S,2,min,9,RFU\n'
            store.commit_preview(preview_bytes("kinetic_timecourse",timecourse,"synthetic-timecourse.csv"))
            rate=store.analyze_time_course(store.time_courses()[0]["series_id"],RateConfig(0,2,"min"))
            assert rate["status"]=="ESTIMATED" and rate["derived_initial_rate"]["slope"]==2
            store.save_initial_rate(rate)
            assert len(store.initial_rate_records())==1
        from desktop.ml_deployment import inspect_deployment
        assert inspect_deployment({})["status"] == "NOT_INSTALLED"
        window.close(); window.deleteLater(); app.processEvents()
    return {"status": "PASS", "pages": 8, "protein_data_foundation": "PASS", "protein_initial_rate": "PASS", "protein_templates": 9, "synthetic_rule": "PASS", "batch_duplicate_rows": 2,
            "xlsx_export": "PASS", "mutation": "PASS", "missing_ml_startup": "PASS",
            "model_loaded": False, "trained": False, "provider_called": False,
            "keyring_backend": "WinVaultKeyring", "provider_sdk_importable": True,
            "clean_windows_qualification": False}


def _write(path, value):
    import json
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def _workspace(directory):
    """Explicit maintainer test directory; never read a case-provided path."""
    import json
    import stat
    from hashlib import sha256
    from pathlib import Path, PurePosixPath
    path = Path(directory)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("SMOKE_REQUIRES_EXPLICIT_ABSOLUTE_DIRECTORY")
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("SMOKE_REPARSE_DIRECTORY_REJECTED")
    root = path.resolve(strict=True)
    authorization = root / "SMOKE_AUTHORIZATION.json"
    if authorization.stat().st_size > 100_000:
        raise ValueError("SMOKE_AUTHORIZATION_TOO_LARGE")
    value = json.loads(authorization.read_text(encoding="utf-8"))
    if value["purpose"] != "frozen-installation-smoke-v1" or value["case_id"] != "AB-RD-DEMO-001":
        raise ValueError("SMOKE_SYNTHETIC_INPUT_CONTRACT_REQUIRED")
    for name, entry in value["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("SMOKE_INPUT_PATH_REJECTED")
        source = root / relative
        for item in (source, *source.parents):
            if item == root:
                break
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("SMOKE_INPUT_REPARSE_REJECTED")
        if sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("SMOKE_INPUT_DIGEST_MISMATCH")
    return root


def _wait(predicate, *, milliseconds=30_000):
    """Wait on actual terminal conditions while allowing queued GUI delivery."""
    from PySide6.QtCore import QEventLoop, QTimer
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(milliseconds)
    loop.exec()
    poll.stop()
    deadline.stop()
    if not predicate():
        raise TimeoutError("SMOKE_OPERATION_DID_NOT_REACH_TERMINAL_STATE")


def _scientific(root):
    """Same literal fixture and tolerances as the reviewed scientific tests."""
    from copy import deepcopy
    import json
    import math
    import numpy as np
    import scipy
    from scipy.optimize import least_squares, brentq, minimize_scalar
    from scipy.stats import chi2
    from protein_engineering.initial_rate import Observation, Calibration, RateConfig, analyze_initial_rate, digest
    from protein_engineering.mm_kinetics import RateRecord, FitReview, input_digest, fit_michaelis_menten
    from protein_engineering.mm_uncertainty import UncertaintyReview, analyze_mm_uncertainty
    from desktop.protein_mm import checked_result

    substrates = (2, 5, 10, 20, 40, 80, 160)
    noise = (.01, -.03, .02, -.04, .06, -.02, .03)
    stamp = "2026-11-10T00:00:00Z"
    conditions = dict(protocol_id="SYN-P", protocol_version="1", temperature_c=25, pH=7,
        buffer_composition="synthetic buffer", substrate_name="synthetic substrate", substrate_lot="SYN-LOT",
        cofactor_name="NONE", cofactor_concentration=0, cofactor_concentration_unit="dimensionless",
        enzyme_concentration=.01, enzyme_concentration_unit="uM", reaction_volume=100,
        reaction_volume_unit="uL", readout_method="SYN-FLUORESCENCE")
    records = []
    for i, (s, e) in enumerate(zip(substrates, noise)):
        v = 5*s/(20+s) + e
        observations = [Observation(f"O{i}-{t}", "B", "S", t, 1000+2*v*t, "min", "RFU",
            f"SYN-SOURCE-{i}", digest([i, s, v]), "BIO1", "TECH1", s, "uM", f"W{i}") for t in range(5)]
        calibration = Calibration("SYN-CAL", "SYN-CAL-SOURCE", digest("synthetic calibration"),
            "RFU", "uM", 2, 0, -1e10, 1e10, "none")
        c1 = analyze_initial_rate(observations, RateConfig(0, 4, "min"), calibration=calibration, calculated_at=stamp)
        assert c1["status"] == "ESTIMATED"
        records.append(RateRecord(f"R{i:03}", "V", deepcopy(conditions), c1, {"source": "SYNTHETIC_FIXTURE_NOT_ACQUIRED"}))
    review = FitReview("SYNTHETIC maintainer", stamp, "Explicit conditional synthetic fixture, not experimental validation",
                       input_digest(records), acknowledge_not_established=True)
    fitted = checked_result(fit_michaelis_menten(records, review))
    assert fitted["status"] == "FIT_WITH_LIMITATIONS"
    assert fitted["metadata"]["initial_rate_validity"] == "NOT_ESTABLISHED"
    _write(root / "C2A-native-result.json", fitted)
    assert checked_result(json.loads((root / "C2A-native-result.json").read_text(encoding="utf-8"))) == fitted
    statistical_review = UncertaintyReview("SYNTHETIC statistical reviewer", stamp, "Conditional numerical check",
        "Distinct synthetic errors; not biological replication", input_digest(records),
        fitted["metadata"]["result_sha256"], tuple((r.analysis_id, "UNIT-"+r.analysis_id) for r in records),
        conditional_independence_accepted=True, homoscedastic_normal_errors_accepted=True,
        fixed_calibration_blanks_windows_accepted=True)
    intervals = analyze_mm_uncertainty(records, review, fitted, statistical_review)
    assert intervals["status"] == "INTERVAL_ESTIMATED"
    critical = float(chi2.ppf(.95, 1))
    assert math.isclose(critical, 3.841458820694124, abs_tol=1e-13)
    linear = least_squares(lambda x: np.array([x[0]-2, 2*x[0]-4]), [0.])
    assert linear.success and math.isclose(float(linear.x[0]), 2, abs_tol=1e-12)
    # Independent physical-unit nuisance optimization and roots, as in the
    # original tests; do not use the production profile implementation.
    x = [p["substrate_concentration"] for p in fitted["predictions"]]
    y = [p["observed_rate"] for p in fitted["predictions"]]
    def k_sse(k):
        g = [s/(k+s) for s in x]
        v = sum(a*b for a,b in zip(g,y))/sum(a*a for a in g)
        return sum((b-v*a)**2 for a,b in zip(g,y))
    def v_sse(v):
        fit = minimize_scalar(lambda z: sum((b-v*a/(math.exp(z)+a))**2 for a,b in zip(x,y)),
            bounds=(math.log(.01), math.log(1e5)), method="bounded", options={"xatol":1e-12})
        assert fit.success
        return fit.fun
    reference = {}
    for name, fun in (("Km", k_sse), ("Vmax", v_sse)):
        point = fitted["parameters"][name]
        cutoff = lambda value: len(x)*math.log(fun(value)/fitted["statistics"]["sse"])-critical
        reference[name] = [brentq(cutoff, point/2, point, xtol=1e-11), brentq(cutoff, point, point*2, xtol=1e-11)]
        for key, expected in zip(("lower", "upper"), reference[name]):
            assert math.isclose(intervals["parameters"][name][key], expected, rel_tol=1e-8)
    tiny = analyze_mm_uncertainty(records, review, fitted, statistical_review, confidence_level=1e-20)
    assert tiny["status"] == "NUMERICAL_FAILURE"
    assert all(p["lower"] is None and p["upper"] is None for p in tiny["parameters"].values())
    result = dict(status="PASS", scipy=scipy.__version__, numpy=np.__version__,
        least_squares=dict(input=[0.], output=linear.x.tolist(), success=bool(linear.success)),
        chi2=dict(confidence=.95, df=1, output=critical), c2a=fitted,
        conditional_intervals=intervals, independent_reference=reference, interval_relative_tolerance=1e-8,
        unresolvable_cutoff=tiny, c1="PASS", c2a_roundtrip="PASS", synthetic_only=True)
    _write(root / "SCIPY_FROZEN_RUNTIME.json", result)
    return result


def _case_run(root, phase):
    import json
    from pathlib import Path
    from unittest.mock import patch
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QFileDialog
    from desktop.main_window import MainWindow
    from desktop.integrations.case_record import LIMITATIONS
    from desktop.integrations.citation_groups import count_citations
    from desktop.protein_mm import checked_result
    from desktop.version import project_version

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    flow = window.research_workflow
    case = flow.case
    sequence = "".join(line.strip() for line in (root/"inputs/sequence.fasta").read_text(encoding="utf-8").splitlines() if not line.startswith(">"))
    if phase == "restore":
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(root/"AB-RD-DEMO-001.biocase.json"), "")):
            assert case.files.open_case()
        assert not case.context.sources and case.context.association is None
        assert len(case.context.historical_sources) == 3
        assert case.context.historical_association.kind == "仅同属研究案例"
        assert all(case.context.source_status(k) == "未重新核验" for k in case.context.historical_sources)
        assert checked_result(json.loads((root/"C2A-native-result.json").read_text(encoding="utf-8")))["status"] == "FIT_WITH_LIMITATIONS"
    else:
        case.case_id.setText("AB-RD-DEMO-001")
        case.topic.setText("合成教学案例：序列风险、独立标准曲线及文献证据")
        case.material.setCurrentText("合成演示")
        case.notes.setPlainText("三类材料没有共同分子或样品身份；只同属教学研究案例。")
        case.findings.setPlainText("规则预测、上游曲线结果与文献记录分别展示，不推断真实结合或临床效力。")
        case.recommendations.setPlainText("后续需真实样品独立实验验证，不能据本例量化未知样品。")
        case.context.scientific_limitations = ("用户研究记录：合成教学数据没有共同分子或样品身份。",)
    window.single.set_input("AB-RD-DEMO-001-SEQ", sequence, analyze=True)
    assert window.single.case_sequence_snapshot() is not None
    case.attach_sequence.click()
    flow.biolab.import_manifest(root/"inputs/biolab/report_manifest.json")
    flow.literature.import_manifest(root/"inputs/literature/batch_manifest.json")
    _wait(lambda: not flow.biolab._busy and not flow.literature._busy)
    assert flow.biolab.summary is not None and flow.literature.summary is not None
    assert len(case.context.sources) == 3 and case.context.association is None
    counts = count_citations(flow.literature.summary.evidence)
    assert (counts.records, counts.groups, counts.unresolved) == (3, 2, 0)
    assert any(q.page_start is not None for q in flow.literature.summary.evidence)
    if phase == "restore":
        assert all(case.context.source_status(k) == "当前来源与保存记录匹配" for k in case.context.sources)
    case.relationship.setCurrentText("仅同属研究案例")
    case.basis.setText("明确审核：三类材料仅同属教学案例，没有共同分子或样品身份。")
    case.apply_button.click()
    assert case.context.association.kind == "仅同属研究案例"
    target = root/("AB-RD-DEMO-001-restored.biocase.json" if phase == "restore" else "AB-RD-DEMO-001.biocase.json")
    assert case.files._save_to(target)
    if phase == "restore":
        for i in range(case.files.quote_list.count()):
            case.files.quote_list.item(i).setCheckState(Qt.CheckState.Checked)
        for kind, suffix in (("md","md"), ("docx","docx")):
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(root/("AB-RD-DEMO-001-report."+suffix)), "")):
                assert case.files.export(kind)
        from docx import Document
        from zipfile import ZipFile
        from lxml import etree
        from importlib import metadata, resources
        from hashlib import sha256
        import sys
        text = "\n".join(p.text for p in Document(root/"AB-RD-DEMO-001-report.docx").paragraphs)
        md = (root/"AB-RD-DEMO-001-report.md").read_text(encoding="utf-8")
        for value in (*LIMITATIONS, *case.context.scientific_limitations, "AB-RD-DEMO-001", "PDF 物理页码", "仅同属研究案例", "4.1.0rc2"):
            assert value in text and value in md
        assert str(root) not in text and str(root).replace("\\","/") not in text
        external = []
        with ZipFile(root/"AB-RD-DEMO-001-report.docx") as z:
            for name in z.namelist():
                if name.endswith(".rels"):
                    external.extend(x.get("Target") for x in etree.fromstring(z.read(name)) if x.get("TargetMode") == "External")
        assert not external
        template = resources.files("docx").joinpath("templates", "default.docx")
        assert template.is_file()
        _write(root/"DOCX_FROZEN_RUNTIME.json", dict(status="PASS",
            support=dict(python_docx=metadata.version("python-docx"), lxml=metadata.version("lxml"),
                         template_sha256=sha256(template.read_bytes()).hexdigest()),
            external_relationships=external, mandatory_limitations_preserved=True, user_limitations_preserved=True,
            generated_by_frozen_exe=bool(getattr(sys, "frozen", False)), word_rendering="NOT_YET_PERFORMED"))
    screenshots = root/("screenshots-"+phase)
    screenshots.mkdir()
    window.nav.setCurrentRow(7)
    for width, height in ((1280,720),(1920,1080)):
        window.resize(width,height)
        flow.tabs.setCurrentWidget(flow.literature)
        app.processEvents()
        assert window.grab().save(str(screenshots/f"literature-{width}.png"))
        flow.tabs.setCurrentWidget(case)
        app.processEvents()
        assert window.grab().save(str(screenshots/f"case-{width}.png"))
    result = dict(status="PASS", phase=phase, history_not_promoted=True if phase=="restore" else None,
        source_states={k:case.context.source_status(k) for k in case.context.sources},
        association=case.context.association.kind, source_sha256={k:v.sha256 for k,v in case.context.sources.items()},
        literature_counts=dict(records=counts.records, groups=counts.groups, unresolved=counts.unresolved),
        evidence=[dict(document=q.document_id, page_start=q.page_start,page_end=q.page_end) for q in flow.literature.summary.evidence],
        biolab=flow.biolab.summary.as_dict(), app_version=project_version())
    assert not case.files.dirty()
    window.close()
    window.deleteLater()
    app.processEvents()
    return result


def _loaded_modules():
    """Read actual process module paths; not a DLL directory-presence claim."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    process = kernel.GetCurrentProcess()
    handles = (wintypes.HMODULE*4096)()
    needed = wintypes.DWORD()
    assert psapi.EnumProcessModulesEx(process, handles, ctypes.sizeof(handles), ctypes.byref(needed), 3)
    assert needed.value < ctypes.sizeof(handles)
    paths = []
    for i in range(needed.value//ctypes.sizeof(wintypes.HMODULE)):
        name = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(process, handles[i], name, len(name)):
            paths.append(name.value)
    return paths


def run(*, phase="basic", directory=None):
    """Fixed synthetic stages only; never execute commands supplied by fixtures."""
    import os
    import sys
    from datetime import datetime, timezone
    from unittest.mock import patch
    from desktop.credentials import CredentialStore
    from desktop.settings import RuntimeLLMConfig
    if phase not in {"basic", "create", "restore"}:
        raise ValueError("SMOKE_PHASE_UNSUPPORTED")
    root = _workspace(directory) if phase != "basic" else None
    with patch.object(CredentialStore, "get", return_value=""), \
         patch("desktop.widgets.settings_page.load_settings", return_value=RuntimeLLMConfig()), \
         patch("desktop.main_window.load_settings", return_value=RuntimeLLMConfig()), \
         patch("socket.socket.connect", side_effect=RuntimeError("Smoke is offline")) as network, \
         patch("socket.getaddrinfo", side_effect=RuntimeError("Smoke is offline")) as dns:
        result = _basic_run()
        if phase == "create":
            _scientific(root)
        if root is not None:
            result["research_workflow"] = _case_run(root, phase)
        assert network.call_count == dns.call_count == 0
        result.update(phase=phase, pid=os.getpid(), frozen=bool(getattr(sys,"frozen",False)),
            executable=sys.executable, runtime_directory=getattr(sys,"_MEIPASS",None),
            finished_utc=datetime.now(timezone.utc).isoformat(),
            loaded_modules=_loaded_modules() if sys.platform == "win32" else [],
            network_attempts=0, source_mode=not bool(getattr(sys,"frozen",False)))
        if root is not None:
            _write(root/("CASE_PROCESS_A.json" if phase=="create" else "CASE_PROCESS_B.json"), result)
        return result
