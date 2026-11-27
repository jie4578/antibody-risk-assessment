"""Offline DOCX dependency/resource probe; no files, network or scientific computation."""
from hashlib import sha256
from importlib import metadata, resources
from io import BytesIO
import json
from zipfile import ZipFile

SYNTHETIC_TEXT = "合成案例 DOCX 检查：来源、人工声明与科学限制。"


def check_docx_support():
    from docx import Document
    from lxml import etree

    template = resources.files("docx").joinpath("templates", "default.docx")
    if not template.is_file():
        raise RuntimeError("DOCX_DEFAULT_TEMPLATE_MISSING")
    raw = template.read_bytes()
    with ZipFile(BytesIO(raw)) as package:
        if "word/document.xml" not in package.namelist():
            raise RuntimeError("DOCX_DEFAULT_TEMPLATE_INVALID")
    document = Document()
    document.add_paragraph(SYNTHETIC_TEXT)
    stream = BytesIO()
    document.save(stream)
    data = stream.getvalue()
    restored = Document(BytesIO(data))
    if SYNTHETIC_TEXT not in "\n".join(p.text for p in restored.paragraphs):
        raise RuntimeError("DOCX_UNICODE_ROUNDTRIP_FAILED")
    with ZipFile(BytesIO(data)) as package:
        for name in package.namelist():
            if name.endswith(".rels"):
                root = etree.fromstring(package.read(name))
                if any(item.get("TargetMode") == "External" for item in root):
                    raise RuntimeError("DOCX_UNEXPECTED_EXTERNAL_RELATIONSHIP")
    return dict(status="PASS",python_docx=metadata.version("python-docx"),
                lxml=metadata.version("lxml"),template_sha256=sha256(raw).hexdigest(),
                chinese_roundtrip=True,external_relationships=0,
                libxml_compiled=list(etree.LIBXML_COMPILED_VERSION),
                libxslt_compiled=list(etree.LIBXSLT_COMPILED_VERSION))


def main():
    try:
        result = check_docx_support()
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        print(json.dumps(dict(status="FAIL",error=type(exc).__name__,code="DOCX_SUPPORT_UNAVAILABLE")))
        return 1
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
