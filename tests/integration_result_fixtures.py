"""Purely synthetic exports shaped from the pinned upstream producers."""
import hashlib
import json

HASH = "a" * 64
NOW = "2026-11-23T00:00:00+00:00"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf8")
    return path


def biolab_fixture(root, status="COMPLETED", report=False, absolute=False):
    root.mkdir(parents=True, exist_ok=True)
    output = root / "report_data.json"
    payload = dict(SIMULATED=True, curve_validated=False)
    if report:
        payload = dict(schema_version="1.0", report_version="1.0", report_id="SYNTHETIC-REPORT", report_type="elisa_4pl",
                       title="SYNTHETIC report", scope="Research only", source={"source_sha256":HASH},
                       methods={"curve_validated":False,"validated_quantification_enabled":False},
                       qc={"warning_counts":{"warning":1},"issues":[dict(severity="warning",code="SYNTHETIC_QC",message="Synthetic QC only")]},
                       results={}, charts=[], limitations=["SYNTHETIC upstream research-only limitation"])
    write_json(output, payload)
    data = output.read_bytes()
    m = dict(schema_version="1.0", status=status, created_at=NOW, configuration={},
             software_versions={"biolab_copilot": "0.1.0"}, warnings=[],
             output_files=[dict(schema_version="1.0", path=str(output) if absolute else output.name,
                                sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), artifact_type="report_data" if report else "curve_fit_result")])
    if report:
        m.update(report_id="SYNTHETIC-REPORT", report_version="1.0", report_type="elisa_4pl",
                 source_manifests={"upstream": HASH}, source_artifacts={"source_file": HASH})
    else:
        m.update(run_id="SYNTHETIC-RUN", experiment_id="SYNTHETIC-EXPERIMENT", assay_type="elisa_standard_curve",
                 method="four_parameter_logistic", curve_validated=False, quantification_enabled=False,
                 analysis_ready=True, input_files=[dict(path="C:/UNAUTHORIZED/source.csv", sha256=HASH, size_bytes=10)])
    return write_json(root / ("report_manifest.json" if report else "run_manifest.json"), m), m


def literature_fixture(root, status="completed", document_status=None, duplicate=False):
    ds = document_status or ("failed" if status == "completed_with_errors" else "pending" if status in {"running", "paused"} else "completed")
    did = "doc_" + HASH
    inputs = [dict(input_id="input_SYN1", display_name="SYNTHETIC.pdf", source_alias="synthetic/SYNTHETIC.pdf",
                   content_sha256=HASH, document_id=did, status=ds, duplicate_of=None)]
    if duplicate:
        inputs.append({**inputs[0], "input_id": "input_SYN2", "status": "duplicate", "duplicate_of": "input_SYN1"})
    docs = [dict(document_id=did, content_sha256=HASH, display_name="SYNTHETIC.pdf", source_alias="synthetic/SYNTHETIC.pdf",
                 input_ids=[x["input_id"] for x in inputs], status=ds, result_file="documents/synthetic.json",
                 errors=["SYNTHETIC extraction failure"] if ds == "failed" else [], individual_report="individual/SYNTHETIC.docx")]
    m = dict(schema_version=2, task_id="local_SYNTHETIC", status=status, report_mode="Local Offline", created_at=NOW,
             updated_at=NOW, inputs=inputs, documents=docs, input_count=len(inputs), document_count=1,
             duplicate_count=int(duplicate), completed_count=int(ds == "completed"), failed_count=int(ds == "failed"), skipped_count=0)
    paper = dict(document_id=did, content_sha256=HASH, file_name="SYNTHETIC.pdf", errors=docs[0]["errors"], warnings=[],
                 pages=[dict(page_number=2, text="SYNTHETIC original text not copied into summary")],
                 facts=[dict(category="synthetic", evidence_quote_raw="SYNTHETIC location only <b>&quote</b>",
                             source_file="SYNTHETIC.pdf", pdf_page_start=2, pdf_page_end=2, verified=True, quality_flags=[])])
    write_json(root / "documents/synthetic.json", paper)
    (root / "individual").mkdir(exist_ok=True)
    (root / "individual/SYNTHETIC.docx").write_bytes(b"SIMULATED report inventory only, not a DOCX parser test")
    write_json(root / "status.json", {k:m[k] for k in ("schema_version", "task_id", "status", "report_mode", "input_count", "document_count", "duplicate_count", "completed_count", "failed_count", "skipped_count", "updated_at")})
    return write_json(root / "batch_manifest.json", m), m
