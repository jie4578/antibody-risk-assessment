"""Adapters pinned to reviewed external schemas, not their Python environments."""
from .common import (Artifact, Evidence, IntegrationError, ResultDirectory, ResultSummary,
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
    for obj in (result, fact):
        for key, expected in (("document_id", doc["document_id"]), ("content_sha256", doc["content_sha256"]),
                              ("task_id", task), ("source_alias", doc["source_alias"])):
            require(key not in obj or obj[key] == expected, "CITATION_SOURCE_MISMATCH", "引文或结果身份与当前批次来源不一致")
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
                         tuple(sources), tuple(warnings), limitations, producer_versions=producer_versions)


def inspect_literature(selected):
    return _safe_call(_literature, selected)


def _literature(directory):
    require(directory.manifest.name == "batch_manifest.json", "UNSUPPORTED_FORMAT", "仅支持 batch_manifest.json schema v2")
    m = directory.json(directory.manifest)
    _version(m.get("schema_version"), 2)
    task = text(m.get("task_id")); source_state = text(m.get("status"))
    require(source_state in {"running", "paused", "completed", "completed_with_errors"}, "UNSUPPORTED_STATE", "不支持此批次状态")
    mode = text(m.get("report_mode")); text(m.get("created_at")); text(m.get("updated_at"))
    inputs = array(m.get("inputs")); documents = array(m.get("documents"))
    input_map = {}; doc_map = {}; warnings = []; sources = []; artifacts = []; evidence = []
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
        # Failed/in-progress results never become usable scientific evidence.
        if entry.exists and doc["status"] == "completed":
            result = directory.json(directory.path(result_file))
            require(result.get("document_id") == did and result.get("content_sha256") == doc.get("content_sha256"),
                    "INTEGRITY_MISMATCH", "文献结果与 manifest 文档身份不一致")
            require(not array(result.get("errors", [])), "INTEGRITY_MISMATCH", "完成文档仍含处理错误")
            warnings.extend(text(x) for x in array(result.get("warnings", [])))
            for key in ("facts", "evidence"):
                for fact in array(result.get(key, [])):
                    mapping(fact)
                    source = _citation_source(fact, result, doc, input_map, documents, task)
                    quote = fact.get("evidence_quote_raw") or fact.get("evidence_quote")
                    quote = text(quote)
                    start, end = fact.get("pdf_page_start"), fact.get("pdf_page_end")
                    require(start is None or (type(start) is int and start > 0))
                    require(end is None or (type(end) is int and end > 0 and (start is None or end >= start)))
                    flag = fact.get("verified", False)
                    require(type(flag) is bool)
                    require(not flag or (start is not None and end is not None), "INVALID_STRUCTURE", "定位声明缺少页码")
                    flags = tuple(text(x) for x in array(fact.get("quality_flags", [])))
                    evidence.append(Evidence(did, fingerprint, quote, start, end, flag, flags,
                                             source_file=source, source_alias=doc["source_alias"], batch_id=task))
                    require(len(evidence) <= 2000, "RESULT_LIMIT", "证据条数超过本轮展示范围")
        if doc.get("individual_report"):
            artifacts.append(_result_artifact(directory, doc["individual_report"], "individual_report"))
        doc_map[did] = doc
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
                         ), tuple(counts.items()), tuple(evidence))
