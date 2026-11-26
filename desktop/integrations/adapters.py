"""Adapters pinned to reviewed external schemas, not their Python environments."""
from math import isfinite

from .common import (Artifact, ElisaReportSummary, Evidence, IntegrationError, LiteratureDocument, ResultDirectory, ResultSummary,
                     array, artifact, integer, mapping, require, sha, text)

BIOLAB_REVISION = "dcc7ac4a9accae4a03ad7857950169e0f2ed640c"
LITERATURE_REVISION = "99ac4a54de687239b68b57ace19b24ecb32c6269"
COMMON_LIMITATIONS = (
    "只读接入上游结果；未重新执行科学计算、未调用 Provider、未写入 SQLite。",
    "SHA256 仅核对本次读取的内容一致性；没有外部可信锚点，不能证明来源真实性。",
    "原始实验文件/PDF 未读取或复制；上游声明的原始来源哈希未独立复核。",
)


def _version(value, expected):
    require(type(value) is type(expected) and value == expected, "UNSUPPORTED_VERSION", "不支持此 manifest 版本")


def _warnings(items):
    result = []
    for item in array(items):
        item = mapping(item)
        severity = text(item.get("severity"))
        require(severity in {"info", "warning", "error", "blocking"},
                "UNSUPPORTED_QC_SEVERITY", "QC 严重度不符合 BioLab 1.0 合同")
        result.append(severity + " / " + text(item.get("code")) + ": " + text(item.get("message")))
    return result


def _result_artifact(directory, location, role, expected=None, size=None):
    """Approve purpose/format before any artifact handle, hash or parser access."""
    path = directory.path(location)  # Preserve the existing path authorization checks.
    suffix = path.suffix.lower()
    require(suffix != ".pdf", "UNSUPPORTED_ARTIFACT_FORMAT", "结果接入不允许打开原始 PDF")
    raw = role in {"imported_data", "input_artifact", "sample_artifact", "source_file"}
    if not raw:
        json_roles = {"analysis_plan", "analysis_result", "experimental_units", "standards_preview",
                      "curve_fit_result", "sample_concentrations", "analysis_issues", "validation_issues",
                      "report_data", "paper_result"}
        formats = {"report": {".docx", ".xlsx"}, "chart": {".png"}, "individual_report": {".docx"}}
        allowed = {".json"} if role in json_roles else formats.get(role, set())
        require(suffix in allowed, "UNSUPPORTED_ARTIFACT_FORMAT", "产物类型与已审核结果角色不匹配")
    # Raw snapshots remain metadata-only; no JSON branch is allowed for their role.
    return artifact(directory, location, role, expected, size, read_bytes=not raw)


def _literature_identity(value, doc, task):
    """Validate declared identity independently of the number of evidence items."""
    for key, expected in (("document_id", doc["document_id"]), ("content_sha256", doc["content_sha256"]),
                          ("task_id", task), ("source_alias", doc["source_alias"])):
        require(key not in value or value[key] == expected,
                "CITATION_SOURCE_MISMATCH", "引文或结果身份与当前批次来源不一致")


def _citation_source(fact, result, doc, input_map, documents, task):
    """Check the declared chain, never infer identity from a filename alone or open it."""
    name = doc["display_name"]
    source = fact.get("source_file")
    require(isinstance(source, str) and source == name and result.get("file_name") == name,
            "CITATION_SOURCE_MISMATCH", "引文来源缺失或与所属文档不一致")
    require(any(input_map[iid]["display_name"] == name
                and input_map[iid]["source_alias"] == doc["source_alias"] for iid in doc["input_ids"]),
            "CITATION_SOURCE_MISMATCH", "文档与批次输入来源关联不完整")
    # The upstream fact format only carries a filename. It cannot disambiguate
    # different document hashes sharing that name, so fail closed in that case.
    require(not any(other["document_id"] != doc["document_id"] and other["display_name"] == name
                    for other in documents), "AMBIGUOUS_CITATION_SOURCE", "同名不同文档不能据文件名绑定引文")
    _literature_identity(fact, doc, task)
    return source


def _safe_call(function, selected):
    try:
        return function(ResultDirectory(selected))
    except IntegrationError:
        raise
    except OSError as exc:
        raise IntegrationError("SOURCE_UNAVAILABLE", "无法安全读取所选本地结果；请检查权限、锁定及链接") from exc
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError) as exc:
        raise IntegrationError("INVALID_STRUCTURE", "结果字段类型或结构不符合已审核合同") from exc


def inspect_biolab(selected):
    """Explicit manifest selection authorizes only its enclosing result directory."""
    return _safe_call(_biolab, selected)


def _elisa_summary(data, methods, fingerprint):
    """BioLab 0.1.0 report renderer: curve_parameters and diagnostics."""
    def section(value, name):
        item = value.get(name)
        require(item is None or isinstance(item, dict), "INVALID_ELISA_FIELD", name + " 格式无效")
        return item if item is not None else {}

    def number(record, name):
        value = record.get(name)
        if value is None:
            return None
        require(type(value) in (int, float), "INVALID_ELISA_FIELD", name + " 必须为有限数值")
        try:
            converted = float(value)
        except OverflowError:
            raise IntegrationError("INVALID_ELISA_FIELD", name + " 超出有限数值范围") from None
        require(isfinite(converted), "INVALID_ELISA_FIELD", name + " 必须为有限数值")
        return converted

    def label(record, name):
        value = record.get(name)
        return None if value is None else text(value)

    results = section(data, "results")
    curve = section(results, "curve_parameters")
    diag = section(results, "diagnostics")
    count = diag.get("n_fit_levels")
    require(count is None or (type(count) is int and count >= 0),
            "INVALID_ELISA_FIELD", "n_fit_levels 必须为非负整数")
    labels = {}
    for name in ("direction", "concentration_unit", "response_unit"):
        value = label(curve, name)
        declared = label(methods, name)
        require(value is None or declared is None or value == declared,
                "INVALID_ELISA_FIELD", name + " 与方法声明不一致")
        labels[name] = value if value is not None else declared
    require(labels["direction"] in {None, "increasing", "decreasing"},
            "INVALID_ELISA_FIELD", "direction 不符合 4PL 报告合同")
    return ElisaReportSummary(
        report_data_sha256=fingerprint,
        **{name: number(curve, name) for name in (
            "lower_asymptote", "upper_asymptote", "midpoint_concentration", "slope_magnitude")},
        **labels, n_fit_levels=count, r_squared=number(diag, "r_squared"), rmse=number(diag, "rmse"),
        convergence_status=label(diag, "convergence_status"), curve_validated=methods["curve_validated"],
        validated_quantification_enabled=methods["validated_quantification_enabled"],
    )


def _biolab(directory):
    require(directory.manifest.name in {"run_manifest.json", "report_manifest.json"},
            "UNSUPPORTED_FORMAT", "请选择 run_manifest.json 或 report_manifest.json")
    m = directory.json(directory.manifest)
    _version(m.get("schema_version"), "1.0")
    is_report = directory.manifest.name == "report_manifest.json"
    identifier = text(m.get("report_id" if is_report else "run_id"))
    text(m.get("created_at"))
    source_state = text(m.get("status"))
    allowed = {"COMPLETED", "FAILED"} if is_report else {
        "CREATED", "VALIDATING", "NEEDS_CONFIRMATION", "READY", "ANALYZING", "REPORTING", "COMPLETED", "PARTIAL", "FAILED"}
    require(source_state in allowed, "UNSUPPORTED_STATE", "上游任务状态不受支持")
    mapping(m.get("configuration"))
    producer_versions = tuple((text(k), text(v)) for k, v in mapping(m.get("software_versions")).items())
    warnings = _warnings(m.get("warnings"))
    upstream_limitations = []
    sources = []
    if is_report:
        _version(m.get("report_version"), "1.0")
        experiment = text(m.get("report_type"))
        require(experiment in {"generic_grouped", "welch_two_group", "elisa_4pl"})
        for key in ("source_manifests", "source_artifacts"):
            for role, fingerprint in mapping(m.get(key)).items():
                sources.append(text(role) + ": " + sha(fingerprint) + " [DECLARED_NOT_VERIFIED]")
    else:
        text(m.get("experiment_id"))
        experiment = m.get("assay_type") or "NOT_DECLARED"
        require(experiment in {"generic_grouped", "elisa_standard_curve", "NOT_DECLARED"})
        method = m.get("method")
        require(method in {None, "welch_t", "four_parameter_logistic", "four_parameter_logistic_inverse"})
        experiment += " / " + (method or "NOT_DECLARED")
        for item in array(m.get("input_files")):
            item = mapping(item)
            # Source paths are inert labels, never resolved, opened, copied or executed.
            text(item.get("path")); integer(item.get("size_bytes"))
            sources.append(sha(item.get("sha256")) + " [RAW_INPUT_DECLARED_NOT_VERIFIED]")
        for key in ("source_sha256", "input_artifact_sha256", "analysis_plan_sha256", "preview_sha256",
                    "standards_preview_sha256", "curve_fit_result_sha256", "sample_artifact_sha256", "sample_result_sha256"):
            if m.get(key) is not None:
                sources.append(key + ": " + sha(m[key]) + " [DECLARED_NOT_VERIFIED]")
        for key in ("curve_validated", "quantification_enabled", "validated_quantification_enabled"):
            require(m.get(key) is None or m[key] is False, "SCIENTIFIC_CONTRACT_MISMATCH", "本合同不允许声称已验证 ELISA 定量")
            if key in m:
                warnings.append(key + "=" + str(m[key]).lower())
        if method in {"four_parameter_logistic", "four_parameter_logistic_inverse"}:
            require(m.get("curve_validated") is False and m.get("quantification_enabled") is False,
                    "SCIENTIFIC_CONTRACT_MISMATCH", "ELISA 计算结果缺少明确的未验证限制")
        require(m.get("intended_use") in {None, "research_only"}, "SCIENTIFIC_CONTRACT_MISMATCH", "仅支持科研用途结果")
        warnings.append("independence_status=" + str(m.get("independence_status", "NOT_DECLARED")))
    artifacts = []
    elisa = None
    for item in array(m.get("output_files")):
        item = mapping(item)
        if "schema_version" in item:
            _version(item["schema_version"], "1.0")
        role = text(item.get("artifact_type"))
        location = text(item.get("path"))
        entry = _result_artifact(directory, location, role, sha(item.get("sha256")), integer(item.get("size_bytes")))
        artifacts.append(entry)
        if entry.exists and role in {"analysis_issues", "validation_issues"}:
            warnings.extend(_warnings(directory.json(directory.path(location), object_only=False)))
        if is_report and entry.exists and role == "report_data":
            data = directory.json(directory.path(location))
            _version(data.get("schema_version"), "1.0")
            _version(data.get("report_version"), "1.0")
            require(data.get("report_id") == identifier and data.get("report_type") == experiment,
                    "INTEGRITY_MISMATCH", "报告数据与报告 manifest 身份不一致")
            warnings.extend(_warnings(mapping(data.get("qc")).get("issues")))
            upstream_limitations.extend(text(x) for x in array(data.get("limitations")))
            methods = mapping(data.get("methods"))
            if experiment == "elisa_4pl":
                require(methods.get("curve_validated") is False and methods.get("validated_quantification_enabled") is False,
                        "SCIENTIFIC_CONTRACT_MISMATCH", "ELISA 报告缺少明确的未验证限制")
                require(entry.hash_status == "CONTENT_HASH_MATCH" and elisa is None,
                        "INTEGRITY_MISMATCH", "ELISA report_data 摘要必须匹配且只可声明一次")
                elisa = _elisa_summary(data, methods, entry.observed_sha256)
            for key in ("curve_validated", "validated_quantification_enabled"):
                if key in methods:
                    require(methods[key] is False, "SCIENTIFIC_CONTRACT_MISMATCH", "不能将未验证的 ELISA 报告升级为已验证")
                    warnings.append(key + "=false")
    state = {"COMPLETED": "COMPLETED_SOURCE_REPORTED", "FAILED": "FAILED", "PARTIAL": "PARTIAL"}.get(source_state, "INCOMPLETE")
    if state == "COMPLETED_SOURCE_REPORTED":
        if not artifacts or any(not a.exists for a in artifacts) or (is_report and not any(a.role == "report_data" for a in artifacts)):
            state = "INCOMPLETE_ARTIFACTS"
        elif any(w.startswith(("error /", "blocking /")) for w in warnings):
            state = "NEEDS_REVIEW"
    warnings.append("QC 为 manifest、列出的 issues 及报告数据声明；未据此认定分析或实验有效。")
    limitations = COMMON_LIMITATIONS + (
        "BioLab 结果仅供科研；ELISA curve_validated=false 不得改写为有效定量或诊断结论。",
        "未重新计算 Welch、4PL 或逆向浓度；COMPLETED 只表示上游流程状态。",
        "运行 manifest 的绝对产物路径仅在本次明确授权目录内接受；越界或迁移后的旧绝对路径拒绝，不猜测重映射。",
    ) + tuple(upstream_limitations)
    directory.finish()
    return ResultSummary("BioLab-Copilot", BIOLAB_REVISION, "1.0", identifier, state, source_state, experiment,
                         str(directory.manifest), directory.ledger[directory.manifest][1], tuple(artifacts),
                         tuple(sources), tuple(warnings), limitations, producer_versions=producer_versions,
                         elisa=elisa if state == "COMPLETED_SOURCE_REPORTED" else None)


def inspect_literature(selected):
    return _safe_call(_literature, selected)


def inspect_literature_evidence(selected):
    """v0.4 batch-v2 reader; atomically validate before committing a UI snapshot."""
    return _safe_call(lambda directory: _literature(directory, for_reader=True), selected)


def _page_inventory(result):
    pages = {}
    for page in array(result.get("pages", [])):
        mapping(page)
        number = page.get("page_number")
        require(type(number) is int and number > 0 and number not in pages,
                "INVALID_PAGE", "结果中的 PDF 物理页码缺失、重复或无效")
        raw = page.get("raw_text", page.get("text", ""))
        require(isinstance(raw, str), "INVALID_STRUCTURE", "页面原文必须为文本")
        if "source_file" in page:
            require(page["source_file"] == result.get("file_name"),
                    "CITATION_SOURCE_MISMATCH", "页面来源与文献结果不一致")
        pages[number] = raw
    return pages


def _reader_location(start, end, quote, upstream_verified, pages):
    require((start is None) == (end is None), "INVALID_PAGE", "物理页码范围不完整")
    if start is None or not pages:
        return "INSUFFICIENT_LOCATION"
    # Check membership without iterating over an untrusted, potentially huge range.
    members = [number for number in sorted(pages) if start <= number <= end]
    require(len(members) == end - start + 1, "INVALID_PAGE", "引文超出已有结果的物理页码范围")
    if not upstream_verified:
        return "UPSTREAM_UNVERIFIED"
    return ("RESULT_TEXT_MATCH" if quote in "\n".join(pages[n] for n in members)
            else "LOCATION_NOT_REPRODUCED")


def _literature(directory, for_reader=False):
    require(directory.manifest.name == "batch_manifest.json", "UNSUPPORTED_FORMAT", "仅支持 batch_manifest.json schema v2")
    m = directory.json(directory.manifest)
    _version(m.get("schema_version"), 2)
    task = text(m.get("task_id")); source_state = text(m.get("status"))
    require(source_state in {"running", "paused", "completed", "completed_with_errors"}, "UNSUPPORTED_STATE", "不支持此批次状态")
    mode = text(m.get("report_mode")); text(m.get("created_at")); text(m.get("updated_at"))
    inputs = array(m.get("inputs")); documents = array(m.get("documents"))
    input_map = {}; doc_map = {}; warnings = []; sources = []; artifacts = []; evidence = []
    document_views = []
    for item in inputs:
        item = mapping(item); iid = text(item.get("input_id"))
        require(iid not in input_map, "IDENTITY_MISMATCH", "输入 ID 重复")
        text(item.get("display_name")); text(item.get("source_alias")); text(item.get("document_id"))
        require(item.get("status") in {"pending", "running", "completed", "failed", "duplicate", "skipped"})
        if item.get("content_sha256") is not None:
            sha(item["content_sha256"])
        input_map[iid] = item
    for doc in documents:
        doc = mapping(doc); did = text(doc.get("document_id"))
        require(did not in doc_map, "IDENTITY_MISMATCH", "文档 ID 重复")
        text(doc.get("display_name")); text(doc.get("source_alias"))
        require(doc.get("status") in {"pending", "running", "completed", "failed"})
        fingerprint = sha(doc["content_sha256"]) if doc.get("content_sha256") is not None else None
        ids = array(doc.get("input_ids"))
        require(bool(ids) and len(set(ids)) == len(ids), "IDENTITY_MISMATCH", "文档输入关联缺失或重复")
        for iid in ids:
            require(iid in input_map and input_map[iid]["document_id"] == did and input_map[iid].get("content_sha256") == doc.get("content_sha256"),
                    "IDENTITY_MISMATCH", "文档与输入来源不一致")
        if fingerprint:
            require(did == "doc_" + fingerprint, "IDENTITY_MISMATCH", "文档 ID 与内容 SHA256 不一致")
            sources.append(did + ": " + fingerprint + " [PDF_DECLARED_NOT_VERIFIED]")
        else:
            require(doc["status"] != "completed", "IDENTITY_MISMATCH", "缺少来源身份的文档不能标为完成")
        warnings.extend(text(x) for x in array(doc.get("errors")))
        result_file = text(doc.get("result_file"))
        entry = _result_artifact(directory, result_file, "paper_result")
        artifacts.append(entry)
        if for_reader:
            require(doc["status"] != "completed" or entry.exists,
                    "MISSING_RESULT", "已完成文档的结构化结果文件缺失：" + result_file)
        result = {}; pages = {}; first_evidence = len(evidence)
        # Failed/in-progress results never become usable scientific evidence.
        if entry.exists and doc["status"] == "completed":
            result = directory.json(directory.path(result_file))
            require(result.get("document_id") == did and result.get("content_sha256") == doc.get("content_sha256"),
                    "INTEGRITY_MISMATCH", "文献结果与 manifest 文档身份不一致")
            _literature_identity(result, doc, task)
            require(not array(result.get("errors", [])), "INTEGRITY_MISMATCH", "完成文档仍含处理错误")
            warnings.extend(text(x) for x in array(result.get("warnings", [])))
            if for_reader:
                require(result.get("file_name") == doc["display_name"],
                        "CITATION_SOURCE_MISMATCH", "文献结果文件名与当前来源身份不一致")
                pages = _page_inventory(result)
            for key in ("facts", "evidence"):
                for fact in array(result.get(key, [])):
                    mapping(fact)
                    source = _citation_source(fact, result, doc, input_map, documents, task)
                    raw_quote = fact.get("evidence_quote_raw")
                    quote = raw_quote or fact.get("evidence_quote")
                    quote = text(quote)
                    start, end = fact.get("pdf_page_start"), fact.get("pdf_page_end")
                    require(start is None or (type(start) is int and start > 0))
                    require(end is None or (type(end) is int and end > 0 and (start is None or end >= start)))
                    flag = fact.get("verified", False)
                    require(type(flag) is bool)
                    require(not flag or (start is not None and end is not None), "INVALID_STRUCTURE", "定位声明缺少页码")
                    flags = tuple(text(x) for x in array(fact.get("quality_flags", [])))
                    location = (_reader_location(start, end, quote, flag, pages)
                                if for_reader else "UPSTREAM_CLAIM_ONLY")
                    category = fact.get("category")
                    evidence.append(Evidence(did, fingerprint, quote, start, end, flag, flags,
                                             source_file=source, source_alias=doc["source_alias"], batch_id=task,
                                             location_status=location,
                                             category=category if isinstance(category, str) and 0 < len(category) <= 4096 else None,
                                             has_raw_quote=bool(raw_quote)))
                    require(len(evidence) <= 2000, "RESULT_LIMIT", "证据条数超过本轮展示范围")
        if doc.get("individual_report"):
            report = _result_artifact(directory, doc["individual_report"], "individual_report")
            if for_reader:
                require(report.exists, "MISSING_REPORT", "已声明报告文件缺失：" + doc["individual_report"])
            artifacts.append(report)
        doc_map[did] = doc
        if for_reader:
            title = result.get("title_candidate")
            title_source = result.get("title_source")
            doi = result.get("doi")
            document_views.append(LiteratureDocument(
                did, doc["display_name"], doc["source_alias"], fingerprint, doc["status"], result_file,
                text(title) if title is not None else None,
                text(title_source) if title_source is not None else None,
                text(doi) if doi is not None else None, tuple(sorted(pages)), len(evidence) - first_evidence))
    for iid, item in input_map.items():
        require(item["document_id"] in doc_map and iid in doc_map[item["document_id"]]["input_ids"], "IDENTITY_MISMATCH", "输入没有对应文档")
        if item["status"] == "duplicate":
            original = input_map.get(item.get("duplicate_of"))
            require(original is not None and original["document_id"] == item["document_id"] and original is not item,
                    "IDENTITY_MISMATCH", "重复输入身份不一致")
        elif item["status"] != "skipped":
            require(item["status"] == doc_map[item["document_id"]]["status"], "INCONSISTENT_STATUS", "输入与文档状态不一致")
    counts = dict(input_count=len(inputs), document_count=len(documents),
                  duplicate_count=sum(x["status"] == "duplicate" for x in inputs),
                  completed_count=sum(x["status"] == "completed" for x in documents),
                  failed_count=sum(x["status"] == "failed" for x in documents),
                  skipped_count=sum(x["status"] == "skipped" for x in inputs))
    for key, count in counts.items():
        require(integer(m.get(key)) == count, "INCONSISTENT_COUNTS", "批次计数与逐条状态不符")
    if source_state in {"completed", "completed_with_errors"}:
        require(all(d["status"] in {"completed", "failed"} for d in documents), "INCONSISTENT_STATUS", "终态批次仍有未完成文档")
        require((source_state == "completed_with_errors") == bool(counts["failed_count"]), "INCONSISTENT_STATUS", "失败文档与批次终态不一致")
    status_path = directory.path("status.json")
    try:
        status = directory.json(status_path)
    except FileNotFoundError:
        # Strict reader completeness must not change MERGE-01's degraded intake.
        require(not for_reader, "MISSING_STATUS", "必需批次状态文件缺失：status.json")
        status = None
        warnings.append("status.json 缺失；没有独立状态快照可比对。")
    if status is not None:
        _version(status.get("schema_version"), 2)
        require(status.get("task_id") == task and status.get("status") == source_state and status.get("report_mode") == mode
                and status.get("updated_at") == m["updated_at"], "INCONSISTENT_STATUS", "status.json 与批次快照不一致")
        require(all(integer(status.get(k)) == v for k, v in counts.items()), "INCONSISTENT_COUNTS", "状态摘要计数不一致")
    state = {"completed": "COMPLETED_SOURCE_REPORTED", "completed_with_errors": "PARTIAL"}.get(source_state, "INCOMPLETE")
    if state == "COMPLETED_SOURCE_REPORTED" and (not documents or status is None or any(not a.exists for a in artifacts)):
        state = "INCOMPLETE_ARTIFACTS"
    directory.finish()
    return ResultSummary("Literature Evidence Assistant", LITERATURE_REVISION, "2", task, state, source_state, mode,
                         str(directory.manifest), directory.ledger[directory.manifest][1], tuple(artifacts), tuple(sources),
                         tuple(warnings), COMMON_LIMITATIONS + (
                             "verified=true 只保留上游原文匹配/定位声明；本程序没有重新核对 PDF，不代表科学结论真实。",
                             "规则提取、机器翻译和 LLM 生成内容均为上游研究材料，不能升级为已验证科学事实。",
                             "仅支持 Local Offline schema v2 批次；独立 Provider pipeline 的 status.json 没有此合同，不兼容。",
                         ), tuple(counts.items()), tuple(evidence), documents=tuple(document_views))
