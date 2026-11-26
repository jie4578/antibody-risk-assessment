"""Versioned, minimized case records. Restoring a document never opens source paths."""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import tempfile

from PySide6.QtCore import QIODevice, QSaveFile

from .case_context import Association, CaseContext, CaseSource, MATERIALS, RELATIONSHIPS, SOURCE_LABELS
from .common import _pinned_file
from .citation_groups import count_citations

MAX_CASE_BYTES = 2_000_000
LIMITATIONS = (
    "案例文件是用户可编辑研究记录；内容摘要只能核对一致性。",
    "分子和样品关系为用户声明；来源重新核验不证明实验科学有效性。",
    "规则评分为计算预测；ELISA 未完成方法学验证或未知样品定量验证。",
    "文献定位未独立核验原始 PDF；引文组不代表独立实验或科学证据强度。",
    "历史摘要与当前接入分别展示；用户研究判断和后续建议尚需实验检验。",
)
SOURCE_KEYS = {"identifier", "sha256", "summary", "origin", "snapshot_json"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def external_source(kind, summary):
    # Only values obtained through the existing verified adapters enter current state.
    counts = count_citations(summary.evidence)
    snapshot = dict(state=summary.state, source_state=summary.source_state,
                    experiment=summary.experiment, contract_revision=summary.contract_revision,
                    counts=dict(summary.counts), warnings=list(summary.warnings),
                    limitations=list(summary.limitations),
                    artifacts=[dict(name=Path(a.path).name, role=a.role, exists=a.exists,
                                    hash_status=a.hash_status, declared_sha256=a.declared_sha256,
                                    observed_sha256=a.observed_sha256) for a in summary.artifacts],
                    elisa=asdict(summary.elisa) if summary.elisa else None,
                    citation_counts=asdict(counts),
                    documents=[dict(document_id=d.document_id, title=d.title_candidate,
                                    source_content_sha256=d.source_content_sha256,
                                    state=d.state, evidence_count=d.evidence_count)
                               for d in summary.documents])
    detail = f"{summary.experiment} · {summary.state}"
    if kind == "literature":
        detail += f" · {counts.records} 条记录，{counts.groups} 个引文组，{counts.unresolved} 条未归组"
    elif summary.elisa:
        count = summary.elisa.n_fit_levels
        detail += f" · 4PL 标准水平数 {count if count is not None else '未提供'}"
    return CaseSource(summary.identifier, summary.manifest_sha256, detail, summary.manifest_path,
                      canonical(snapshot))


def association_data(value):
    if value is None:
        return None
    return dict(kind=value.kind, basis=value.basis,
                sources={kind: asdict(source) for kind, source in value.sources})


def document(context, app_version):
    now = utc_now()
    # A saved history remains available even while its source is unavailable.
    history = dict(context.historical_sources)
    history.update(context.sources)
    return dict(schema_version="1.0", case_id=context.case_id, topic=context.topic,
                material=context.material, created_at=context.created_at or now, updated_at=now,
                app_version=app_version, sources={k: asdict(s) for k, s in history.items()},
                association=association_data(context.association or context.historical_association),
                notes=context.notes, findings=context.findings, recommendations=context.recommendations,
                scientific_limitations=list(LIMITATIONS if context.scientific_limitations is None
                                            else context.scientific_limitations))


def _text(value, maximum=20000):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        raise ValueError("CASE_INVALID_TEXT")
    return value


def _bounded(value, depth=0, budget=None):
    budget = budget if budget is not None else [25000]
    budget[0] -= 1
    if depth > 12 or budget[0] < 0:
        raise ValueError("CASE_COMPLEXITY_LIMIT")
    if isinstance(value, str):
        _text(value, MAX_CASE_BYTES)
    elif isinstance(value, dict):
        for key, member in value.items():
            _text(key, 100)
            _bounded(member, depth + 1, budget)
    elif isinstance(value, list):
        for member in value:
            _bounded(member, depth + 1, budget)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("CASE_NONFINITE")
    elif value is not None and type(value) not in (int, bool):
        raise ValueError("CASE_INVALID_TYPE")


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("CASE_INVALID_FIELDS")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("CASE_DUPLICATE_FIELD")
        result[key] = value
    return result


def _json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("CASE_NONFINITE")))
        _bounded(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("CASE_INVALID_JSON") from exc


def _number(value, *, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        raise ValueError("CASE_INVALID_NUMBER")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("CASE_INVALID_NUMBER")


def _snapshot_types(snapshot, kind):
    if kind == "sequence":
        _text(snapshot["rule_version"], 100)
        _text(snapshot["risk_level"], 100)
        _number(snapshot["score"])
        _number(snapshot["sequence_length"], integer=True)
        if not isinstance(snapshot["risks"], list):
            raise ValueError("CASE_INVALID_RISKS")
        for item in snapshot["risks"]:
            _object(item, {"position", "motif", "category", "region"})
            if type(item["position"]) not in (int, str):
                raise ValueError("CASE_INVALID_RISK_POSITION")
            for key in ("motif", "category", "region"):
                _text(item[key], 4096)
        return
    for key in ("state", "source_state", "experiment", "contract_revision"):
        _text(snapshot[key], 4096)
    for key in ("warnings", "limitations"):
        if not isinstance(snapshot[key], list):
            raise ValueError("CASE_INVALID_SNAPSHOT")
        for item in snapshot[key]:
            _text(item)
    if not isinstance(snapshot["counts"], dict):
        raise ValueError("CASE_INVALID_COUNTS")
    for count in snapshot["counts"].values():
        _number(count, integer=True)
    _object(snapshot["citation_counts"], {"records", "groups", "unresolved"})
    for count in snapshot["citation_counts"].values():
        _number(count, integer=True)
    for key in ("artifacts", "documents"):
        if not isinstance(snapshot[key], list):
            raise ValueError("CASE_INVALID_SNAPSHOT")
    for artifact in snapshot["artifacts"]:
        _object(artifact, {"name", "role", "exists", "hash_status", "declared_sha256", "observed_sha256"})
        for key in ("name", "role", "hash_status"):
            _text(artifact[key], 4096)
        if type(artifact["exists"]) is not bool:
            raise ValueError("CASE_INVALID_SNAPSHOT")
        for key in ("declared_sha256", "observed_sha256"):
            if artifact[key] is not None and (not isinstance(artifact[key], str)
                    or not re.fullmatch("[0-9a-f]{64}", artifact[key])):
                raise ValueError("CASE_INVALID_HASH")
    for entry in snapshot["documents"]:
        _object(entry, {"document_id", "title", "source_content_sha256", "state", "evidence_count"})
        _text(entry["document_id"], 4096)
        _text(entry["state"], 100)
        if entry["title"] is not None:
            _text(entry["title"], 4096)
        if entry["source_content_sha256"] is not None and (
                not isinstance(entry["source_content_sha256"], str)
                or not re.fullmatch("[0-9a-f]{64}", entry["source_content_sha256"])):
            raise ValueError("CASE_INVALID_HASH")
        _number(entry["evidence_count"], integer=True)
    if snapshot["elisa"] is not None:
        from .common import ElisaReportSummary
        _object(snapshot["elisa"], set(ElisaReportSummary.__dataclass_fields__))
        for key, value in snapshot["elisa"].items():
            if key in {"curve_validated", "validated_quantification_enabled"}:
                if value is not False:
                    raise ValueError("CASE_INVALID_ELISA_LIMIT")
            elif key in {"lower_asymptote", "upper_asymptote", "midpoint_concentration",
                         "slope_magnitude", "r_squared", "rmse", "n_fit_levels"}:
                if value is not None:
                    _number(value, integer=key == "n_fit_levels")
            elif value is not None:
                _text(value, 4096)

def _source(value, kind):
    _object(value, SOURCE_KEYS)
    for key in ("identifier", "summary", "origin"):
        _text(value[key], 4096)
    if not value["identifier"] or not isinstance(value["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", value["sha256"]):
        raise ValueError("CASE_INVALID_SOURCE")
    _text(value["snapshot_json"], 600000)
    snapshot = _json(value["snapshot_json"])
    required = ({"rule_version", "score", "risk_level", "sequence_length", "risks"} if kind == "sequence"
                else {"state", "source_state", "experiment", "contract_revision", "counts", "warnings",
                      "limitations", "artifacts", "elisa", "citation_counts", "documents"})
    # Old display-only handoffs can be saved without inventing missing measurements.
    if snapshot != {}:
        _object(snapshot, required)
        _snapshot_types(snapshot, kind)
    return CaseSource(**value)


def validate(value):
    keys = {"schema_version", "case_id", "topic", "material", "created_at", "updated_at", "app_version",
            "sources", "association", "notes", "findings", "recommendations", "scientific_limitations"}
    _bounded(value)
    _object(value, keys)
    if type(value["schema_version"]) is not str or value["schema_version"] != "1.0":
        raise ValueError("CASE_UNSUPPORTED_VERSION")
    for name in ("case_id", "topic", "app_version"):
        _text(value[name], 500)
    if not value["case_id"].strip() or value["material"] not in MATERIALS:
        raise ValueError("CASE_REQUIRED_FIELDS")
    for name in ("created_at", "updated_at"):
        try:
            dt = datetime.fromisoformat(_text(value[name], 80))
            if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
                raise ValueError("CASE_INVALID_UTC")
        except (TypeError, ValueError) as exc:
            raise ValueError("CASE_INVALID_UTC") from exc
    for name in ("notes", "findings", "recommendations"):
        _text(value[name])
    limits = value["scientific_limitations"]
    if not isinstance(limits, list) or len(limits) > 30:
        raise ValueError("CASE_INVALID_LIMITATIONS")
    for item in limits:
        _text(item)
    sources = value["sources"]
    if not isinstance(sources, dict) or not set(sources) <= set(SOURCE_LABELS):
        raise ValueError("CASE_INVALID_SOURCE_KIND")
    for kind, source in sources.items():
        _source(source, kind)
    association = value["association"]
    if association is not None:
        _object(association, {"kind", "basis", "sources"})
        if association["kind"] not in RELATIONSHIPS[1:] or not _text(association["basis"], 500).strip():
            raise ValueError("CASE_INVALID_ASSOCIATION")
        members = association["sources"]
        if not isinstance(members, dict) or len(members) < 2 or not set(members) <= set(sources):
            raise ValueError("CASE_INVALID_ASSOCIATION_SOURCES")
        for kind, member in members.items():
            _source(member, kind)
    if len(canonical(value).encode("utf8")) > MAX_CASE_BYTES:
        raise ValueError("CASE_TOO_LARGE")
    return value


def restore(value):
    validate(value)
    history = {k: _source(s, k) for k, s in value["sources"].items()}
    association = value["association"]
    link = (Association(association["kind"], association["basis"],
                        tuple(sorted((k, _source(s, k)) for k, s in association["sources"].items())))
            if association else None)
    return CaseContext(case_id=value["case_id"], topic=value["topic"], material=value["material"],
                       notes=value["notes"], findings=value["findings"], recommendations=value["recommendations"],
                       created_at=value["created_at"], updated_at=value["updated_at"],
                       historical_sources=history, historical_association=link,
                       scientific_limitations=tuple(value["scientific_limitations"]))


def load_case(path):
    path = Path(os.path.abspath(path))
    with _pinned_file(path) as stream:
        raw = stream.read(MAX_CASE_BYTES + 1)
    if len(raw) > MAX_CASE_BYTES:
        raise ValueError("CASE_TOO_LARGE")
    return restore(_json(raw.decode("utf-8-sig")))


def atomic_write(path, content, *, overwrite=False):
    target = Path(os.path.abspath(path))
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("OUTPUT_NOT_REGULAR")
    if target.exists() and not overwrite:
        raise FileExistsError("OUTPUT_EXISTS_CONFIRM_REQUIRED")
    # Publish new files with atomic no-clobber semantics. QSaveFile also checks commit.
    fd, staging = tempfile.mkstemp(prefix=".biocase-", suffix=".tmp", dir=target.parent)
    os.close(fd)
    try:
        destination = target if overwrite else Path(staging)
        output = QSaveFile(str(destination))
        output.setDirectWriteFallback(False)
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError("OUTPUT_OPEN_FAILED")
        if output.write(content) != len(content):
            output.cancelWriting()
            raise OSError("OUTPUT_WRITE_FAILED")
        if not output.commit():
            raise OSError("OUTPUT_COMMIT_FAILED")
        if not overwrite:
            os.link(staging, target)
    finally:
        Path(staging).unlink(missing_ok=True)


def save_case(path, context, app_version, *, overwrite=False):
    value = validate(document(context, app_version))
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf8"),
                 overwrite=overwrite)
    return value
