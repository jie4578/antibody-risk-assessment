"""Local report projections from current verified snapshots and explicit user selections."""
from io import BytesIO
import json
import re

from .case_context import SOURCE_LABELS
from .case_record import LIMITATIONS, atomic_write, utc_now


def plain(value):
    """Inert text for both report formats, with Markdown metacharacters escaped."""
    text = str(value)
    # Suppress automatic external-resource links and raw HTML.
    text = re.sub(r"([\\\\\x60*{}\[\]()<>!#|])", r"\\\1", text).replace("\r", "")
    # CommonMark treats single intraword underscores as literal text.
    return re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", r"\\_", text)


def report_sections(context, version, quotes=()):
    sections = [("案例基本信息", [
        f"案例编号  {context.case_id}", f"研究主题  {context.topic}", f"材料类型  {context.material}",
        f"导出 UTC  {utc_now()}", f"应用版本  {version}",
        "本报告区分当前核验结果、历史记录及用户研究判断。",
    ])]
    for kind, title in SOURCE_LABELS.items():
        current = context.sources.get(kind)
        lines = [f"当前来源核验  {context.source_status(kind)}"]
        if current is None:
            lines.append("当前可信快照缺失；仅有历史记录时不据此补写科研结果。")
        else:
            lines.extend([f"来源身份  {current.identifier}", f"来源 SHA256  {current.sha256}",
                          f"当前摘要  {current.summary}"])
            data = json.loads(current.snapshot_json)
            if kind == "sequence":
                for key, label in (("rule_version", "规则版本"), ("score", "规则评分"),
                                   ("risk_level", "规则风险等级"), ("sequence_length", "序列长度")):
                    lines.append(f"{label}  {data.get(key, '未提供')}")
                for item in data.get("risks", []):
                    lines.append(f"风险位点  {item['position']} · {item['motif']} · {item['category']} · {item['region']}")
                lines.append("规则扫描属于计算预测，不能代替化学稳定性和可开发性实验验证。")
            else:
                for key, label in (("state", "接入状态"), ("source_state", "上游任务状态"), ("experiment", "分析类型")):
                    lines.append(label + "  " + str(data.get(key, "未提供")))
                if kind == "biolab":
                    metrics = data.get("elisa")
                    if metrics is None:
                        lines.append("ELISA 4PL 指标未提供；保留该报告类型实际已有的摘要。")
                    else:
                        lines.extend(key + "  " + json.dumps(value, ensure_ascii=False)
                                     for key, value in metrics.items())
                else:
                    lines.append("文献数量  " + str(data.get("counts", {}).get("document_count", "未提供")))
                    for key, label in (("records", "原始提取记录数"), ("groups", "引文位置组数"),
                                       ("unresolved", "未归组记录数")):
                        lines.append(label + "  " + str(data.get("citation_counts", {}).get(key, "未提供")))
                lines.extend(["QC", *data.get("warnings", []), "上游限制", *data.get("limitations", [])])
                for item in data.get("artifacts", []):
                    lines.append(f"产物  {item['role']} · {item['name']} · {item['hash_status']}")
                    lines.append("产物 SHA256  " + str(item["observed_sha256"] or "未取得"))
            if kind == "literature":
                lines.append("用户明确选择的引文及 PDF 物理页码")
                if not quotes:
                    lines.append("本次未选择引文。")
                for quote in quotes:
                    lines.extend([f"文献  {quote.document_id}；批次  {quote.batch_id}",
                                  f"来源摘要  {quote.source_content_sha256}",
                                  f"PDF 物理页码  {quote.page_start}–{quote.page_end}",
                                  f"定位状态  {quote.location_status}；上游 verified  {quote.upstream_verified}",
                                  quote.quote])
                lines.append("原始 PDF 未独立核验。引文组数不代表独立实验或证据强度。")
        previous = context.historical_sources.get(kind)
        if previous:
            lines.extend(["历史记录（用户可编辑，尚需当前核验）",
                          f"历史来源身份  {previous.identifier}", f"历史来源 SHA256  {previous.sha256}"])
            historical_limits = json.loads(previous.snapshot_json).get("limitations", [])
            if historical_limits:
                lines.extend(["历史来源限制（用户可编辑历史记录，未据此核验当前来源）", *historical_limits])
        sections.append((title, lines))
    current = context.association
    historical = context.historical_association
    lines = ["当前人工关联  " + (current.kind if current else "未关联")]
    if current:
        lines.extend(["当前依据  " + current.basis, "当前关系由用户声明，系统未验证同一分子或实验样品。"])
    lines.append("历史人工关联  " + (historical.kind if historical else "未保存历史关联"))
    if historical:
        lines.append("历史依据  " + historical.basis)
        lines.extend(f"历史关联成员  {kind} · {source.identifier} · {source.sha256}"
                     for kind, source in historical.sources)
    lines.extend(["用户研究发现", context.findings or "未填写", "研究备注", context.notes or "未填写",
                  "后续实验建议（用户研究判断）", context.recommendations or "未填写"])
    sections.append(("人工关联与研究判断", lines))
    sections.append(("局限性与来源记录", list(LIMITATIONS)))
    declared = [item for item in (context.scientific_limitations or ()) if item not in LIMITATIONS]
    if declared:
        sections.append(("案例文件科学限制记录", [
            "以下为用户可编辑的研究记录，未经系统独立核验。",
            *declared,
        ]))
    # Do not repeat incidental absolute paths carried in upstream messages or notes.
    def without_paths(value):
        return re.sub(r"(?<![A-Za-z0-9:/])(?:(?:[A-Za-z]:[\\/]|\\\\)[^\s<>\x22]+|/(?:[^/\s<>\x22]+/)+[^\s<>\x22]+)",
                      "[本地路径已省略]", str(value))
    return [(title, [without_paths(value) for value in values]) for title, values in sections]


def markdown_bytes(sections):
    lines = ["# 综合科研案例报告", ""]
    for title, paragraphs in sections:
        lines.extend(["## " + plain(title), ""])
        for paragraph in paragraphs:
            # Escaping also applies to user notes and selected upstream quotations.
            text = plain(paragraph).replace("://", "\\://")
            lines.extend([text, ""])
    return ("\n".join(lines)).encode("utf8")


def docx_bytes(sections):
    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.oxml.ns import qn
    except ImportError as exc:
        raise RuntimeError("DOCX_DEPENDENCY_UNAVAILABLE") from exc
    document = Document()
    document.sections[0].page_width = Inches(8.5)
    document.sections[0].page_height = Inches(11)
    style = document.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    for name in ("Title", "Heading 1"):
        heading = document.styles[name]
        heading.font.color.rgb = RGBColor(0, 0, 0)
        for border in heading.element.findall(".//" + qn("w:pBdr")):
            border.getparent().remove(border)
    document.add_paragraph("综合科研案例报告", style="Title")
    for title, paragraphs in sections:
        document.add_heading(title, level=1)
        for paragraph in paragraphs:
            document.add_paragraph(str(paragraph))
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def export_report(path, kind, context, version, quotes=(), *, overwrite=False):
    sections = report_sections(context, version, quotes)
    if kind == "md":
        content = markdown_bytes(sections)
    elif kind == "docx":
        content = docx_bytes(sections)
    else:
        raise ValueError("UNSUPPORTED_REPORT_FORMAT")
    atomic_write(path, content, overwrite=overwrite)
