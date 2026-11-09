"""Bounded, offline CSV/XLSX inspection. Preview is separate from persistence."""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
import csv
import hashlib
import io
import zipfile

from .schema import Issue, SPECS, columns, normalize_fields

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 256


class ImportFormatError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRow:
    source_row: int
    original: dict
    fields: dict


@dataclass(frozen=True)
class ImportPreview:
    kind: str
    filename: str
    sheet: str
    sha256: str
    raw_bytes: bytes = field(repr=False)
    headers: tuple[str, ...]
    rows: tuple[SourceRow, ...]
    issues: tuple[Issue, ...]
    blank_rows: int = 0
    source_path: Path | None = field(default=None, repr=False)
    source_kind: str = "FILE"

    @property
    def valid(self):
        return not any(issue.severity == "ERROR" for issue in self.issues)


def read_source(path):
    path = Path(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ImportFormatError("文件超过 25 MiB，请拆分后导入；不会静默截断")
    return data


def _workbook(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED_BYTES:
                raise ImportFormatError("XLSX 展开后超过 64 MiB")
        from openpyxl import load_workbook
        return load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
    except ImportError as exc:
        raise ImportFormatError("XLSX 导入需要可选的 openpyxl 依赖") from exc
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ImportFormatError("无法解析 XLSX 原件：" + str(exc)) from exc


def sheet_names(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return ("CSV",)
    if path.suffix.lower() != ".xlsx":
        raise ImportFormatError("仅支持 UTF-8 CSV 与 .xlsx，不猜测文件格式")
    book = _workbook(read_source(path))
    try:
        return tuple(book.sheetnames)
    finally:
        book.close()


def _scalar(value):
    return value.isoformat() if isinstance(value, (datetime, date, time)) else value


def preview_bytes(kind, data, filename, sheet=None):
    if kind not in SPECS:
        raise ImportFormatError("未知记录类型")
    if len(data) > MAX_FILE_BYTES:
        raise ImportFormatError("文件超过 25 MiB")
    suffix = Path(filename).suffix.lower()
    book = None
    if suffix == ".csv":
        try:
            lines = iter(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True))
        except UnicodeDecodeError as exc:
            raise ImportFormatError("CSV 需要 UTF-8 编码；不自动猜测或改写原文件") from exc
        sheet = "CSV"
    elif suffix == ".xlsx":
        book = _workbook(data)
        if sheet is None:
            if len(book.sheetnames) != 1:
                book.close()
                raise ImportFormatError("多工作表文件请显式选择工作表")
            sheet = book.sheetnames[0]
        if sheet not in book.sheetnames:
            book.close()
            raise ImportFormatError("指定工作表不存在")
        ws = book[sheet]
        ws.reset_dimensions()  # Do not trust incorrect writer-provided dimensions.
        lines = ws.iter_rows()  # Inspect actual width; never hide populated far-right columns.
    else:
        raise ImportFormatError("仅支持 UTF-8 CSV 与 .xlsx")
    issues, rows, ids, hashes, blanks = [], [], set(), set(), 0
    try:
        first = next(lines, None)
        if first is None:
            raise ImportFormatError("缺少表头")
        if book:
            if any(cell.data_type in {"f", "e"} for cell in first):
                issues.append(Issue(1, "header", "FORMULA_OR_CELL_ERROR", "表头包含公式或 Excel 错误"))
            headers = [cell.value for cell in first]
            while headers and headers[-1] is None:
                headers.pop()
        else:
            headers = list(first)
        if not headers or len(headers) > MAX_COLUMNS or any(not isinstance(h, str) or not h.strip() for h in headers):
            raise ImportFormatError("表头必须是非空文本，最多 256 列")
        canonical = [h.strip() for h in headers]
        if len(set(canonical)) != len(canonical):
            raise ImportFormatError("存在重复表头；不能无损映射字段")
        missing = set(SPECS[kind].required) - set(canonical)
        if missing:
            raise ImportFormatError("缺少必需列：" + ", ".join(sorted(missing)))
        for extra in sorted(set(canonical) - set(columns(kind))):
            issues.append(Issue(1, extra, "EXTRA_COLUMN", "额外原始列将完整保留，不自动映射科学含义", "WARNING"))
        for number, source in enumerate(lines, 2):
            if number > MAX_ROWS + 1:
                raise ImportFormatError("超过 10,000 个数据行，请拆分；不静默截断")
            if book:
                for cell in source:
                    if cell.data_type in {"f", "e"}:
                        issues.append(Issue(number, str(cell.column), "FORMULA_OR_CELL_ERROR", "不执行公式或使用可能过期的缓存值；请提供经核实的原始实测导出"))
                values = [_scalar(cell.value) for cell in source]
            else:
                values = list(source)
            if not any(v is not None and v != "" for v in values):
                blanks += 1
                continue
            if any(v is not None and v != "" for v in values[len(headers):]):
                issues.append(Issue(number, "", "ROW_WIDTH", "数据超出表头列数，不能无损导入"))
            values += [None] * max(0, len(headers) - len(values))
            original = dict(zip(headers, values))
            raw_fields = {h: values[i] for i, h in enumerate(canonical)}
            fields, found = normalize_fields(kind, raw_fields, number)
            issues.extend(found)
            identifier = fields.get(SPECS[kind].id_field)
            if isinstance(identifier, str):
                if identifier in ids:
                    issues.append(Issue(number, SPECS[kind].id_field, "DUPLICATE_ID", "重复 ID；不会覆盖、合并或丢弃任何记录"))
                ids.add(identifier)
            sequence_hash = fields.get("sequence_sha256") if kind == "protein_variants" else None
            if sequence_hash:
                if sequence_hash in hashes:
                    issues.append(Issue(number, "sequence", "DUPLICATE_SEQUENCE", "相同序列、不同记录均保留", "WARNING"))
                hashes.add(sequence_hash)
            rows.append(SourceRow(number, original, fields))
        return ImportPreview(kind, Path(filename).name, str(sheet), hashlib.sha256(data).hexdigest(), data,
                             tuple(headers), tuple(rows), tuple(issues), blanks)
    except csv.Error as exc:
        raise ImportFormatError("CSV 结构错误：" + str(exc)) from exc
    finally:
        if book:
            book.close()


def preview_file(kind, path, sheet=None):
    from dataclasses import replace
    path = Path(path).resolve()
    preview = preview_bytes(kind, read_source(path), path.name, sheet)
    return replace(preview, source_path=path)
