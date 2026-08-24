# input_parser.py
# 统一批量输入解析：CSV / Excel / FASTA → 统一 pandas.DataFrame（antibody_id, VH, VL）。
# 只负责格式解析；不包含序列分析、风险扫描、评分或 UI。
# 氨基酸合法性校验交给 core.py（validate_sequence），本模块不复制校验逻辑。

import os
from typing import Union

import pandas as pd

from core import normalize_sequence

# 与 batch_analysis.REQUIRED_COLUMNS 一致；本模块作为统一输入层的规范列
REQUIRED_COLUMNS = ["antibody_id", "VH", "VL"]

FASTA_EXTENSIONS = {".fasta", ".fa", ".faa"}

# FASTA header 支持的链标记
_CHAIN_MARKERS = ("VH", "VL")


def parse_fasta(source: Union[str, os.PathLike]) -> pd.DataFrame:
    """
    解析 FASTA 文件（或 FASTA 内容字符串），返回 (antibody_id, VH, VL) 的 DataFrame。

    source 可以是文件路径（str / PathLike）或 FASTA 内容字符串。

    支持的 header：
        >抗体ID_VH   /   >抗体ID_VL
        >抗体ID|VH   /   >抗体ID|VL
    链标记大小写不敏感。多条序列、多行序列均支持，多行序列自动合并。

    行为约定：
        - 序列自动转大写并去除行首尾空白
        - 空序列、非法 header、同一 (抗体ID, 链) 重复出现 → 抛清晰 ValueError
        - VH/VL 无法配对时保留该抗体行，缺失链使用空值
    """
    content = _read_fasta_source(source)
    records = {}
    order = []

    current = None
    seq_lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if current is not None:
                _flush(current, seq_lines, records, order)
            current = _parse_fasta_header(line[1:])
            seq_lines = []
        else:
            if current is None:
                raise ValueError("FASTA 文件格式错误：序列行出现在第一个 header 之前")
            seq_lines.append(line)
    if current is not None:
        _flush(current, seq_lines, records, order)

    if not records:
        raise ValueError("FASTA 文件为空或未找到任何序列")

    rows = [
        {"antibody_id": aid, "VH": chains.get("VH", ""), "VL": chains.get("VL", "")}
        for aid, chains in ((aid, records[aid]) for aid in order)
    ]
    return pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def parse_csv(file_or_path: Union[str, os.PathLike]) -> pd.DataFrame:
    """
    解析 CSV 文件，返回 (antibody_id, VH, VL) 的 DataFrame。
    必须包含 antibody_id、VH、VL 三列；列顺序不限。
    """
    path = _resolve_path(file_or_path)
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise ValueError("CSV 文件为空")
    except FileNotFoundError:
        raise ValueError(f"文件不存在: {path}")
    except Exception as e:
        raise ValueError(f"读取 CSV 文件失败: {e}")
    if df.empty:
        raise ValueError("CSV 文件为空")
    _validate_columns(df, "CSV")
    return _normalize_frame(df)


def parse_excel(file_or_path: Union[str, os.PathLike]) -> pd.DataFrame:
    """
    解析 .xlsx Excel 文件（默认第一个 sheet），返回 (antibody_id, VH, VL) 的 DataFrame。
    必须包含 antibody_id、VH、VL 三列；列顺序不限。
    """
    path = _resolve_path(file_or_path)
    if not str(path).lower().endswith(".xlsx"):
        raise ValueError("仅支持 .xlsx 格式的 Excel 文件")
    try:
        xl = pd.ExcelFile(path)
    except FileNotFoundError:
        raise ValueError(f"文件不存在: {path}")
    except Exception as e:
        raise ValueError(f"无法读取 Excel 文件（确认是有效的 .xlsx）: {e}")
    sheets = xl.sheet_names
    if not sheets:
        raise ValueError("Excel 文件中没有 sheet")
    try:
        df = xl.parse(sheets[0])
    except Exception as e:
        raise ValueError(f"无法读取 Excel 第一个 sheet（{sheets[0]}）: {e}")
    if df.empty:
        raise ValueError("Excel 文件为空")
    _validate_columns(df, "Excel")
    df = _normalize_frame(df)
    _check_duplicate_ids(df)
    return df


def load_batch_input(file_or_path: Union[str, os.PathLike]) -> pd.DataFrame:
    """按文件扩展名自动分派到对应 parser，统一返回 (antibody_id, VH, VL) 的 DataFrame。"""
    ext = os.path.splitext(str(file_or_path))[1].lower()
    if ext in FASTA_EXTENSIONS:
        return parse_fasta(file_or_path)
    if ext == ".csv":
        return parse_csv(file_or_path)
    if ext == ".xlsx":
        return parse_excel(file_or_path)
    raise ValueError(
        f"不支持的文件格式: {ext or '(无扩展名)'}（支持 .csv / .xlsx / .fasta / .fa / .faa）"
    )


# ---------- 内部 helper ----------


def _read_fasta_source(source):
    if isinstance(source, os.PathLike):
        return _read_text(os.fspath(source))
    if isinstance(source, str):
        if os.path.isfile(source):
            return _read_text(source)
        if os.path.splitext(source)[1].lower() in FASTA_EXTENSIONS:
            raise ValueError(f"文件不存在: {source}")
        return source
    raise TypeError(f"不支持的输入类型: {type(source).__name__}（应为路径或 FASTA 字符串）")


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"文件不存在: {path}")
    except UnicodeDecodeError:
        raise ValueError(f"无法读取文件（编码不是 UTF-8）: {path}")


def _parse_fasta_header(header: str):
    """解析 FASTA header（去掉 '>' 后的文本），返回 (antibody_id, chain)。"""
    stripped = header.strip()
    if not stripped:
        raise ValueError("非法 FASTA header: 缺少序列标识")
    token = stripped.split()[0]
    if "|" in token:
        parts = token.split("|")
        if len(parts) != 2:
            raise ValueError(f"非法 FASTA header: {token}")
        chain = parts[1].upper()
        if chain not in _CHAIN_MARKERS:
            raise ValueError(f"非法 FASTA header: 无法识别的链类型 {parts[1]}（仅支持 VH / VL）")
        if not parts[0]:
            raise ValueError("非法 FASTA header: 缺少抗体 ID")
        return parts[0], chain
    upper = token.upper()
    if upper.endswith("_VH") or upper.endswith("_VL"):
        chain = upper[-2:]
        antibody_id = upper[:-3]
        if not antibody_id:
            raise ValueError("非法 FASTA header: 缺少抗体 ID")
        return antibody_id, chain
    raise ValueError(
        f"非法 FASTA header: {token}（期望 >抗体ID_VH / >抗体ID_VL 或 >抗体ID|VH / >抗体ID|VL）"
    )


def _flush(current, seq_lines, records, order):
    antibody_id, chain = current
    seq = normalize_sequence("".join(seq_lines))
    if not seq:
        raise ValueError(f"FASTA 序列为空: {antibody_id}_{chain}")
    if antibody_id not in records:
        records[antibody_id] = {}
        order.append(antibody_id)
    if chain in records[antibody_id]:
        raise ValueError(f"FASTA 抗体 {antibody_id} 的 {chain} 链重复出现")
    records[antibody_id][chain] = seq


def _resolve_path(file_or_path):
    if isinstance(file_or_path, os.PathLike):
        return os.fspath(file_or_path)
    if isinstance(file_or_path, str):
        return file_or_path
    raise TypeError(
        f"不支持的输入类型: {type(file_or_path).__name__}（应为路径或字符串）"
    )


def _validate_columns(df, fmt):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{fmt} 文件缺少必需列: {', '.join(missing)}")


def _check_duplicate_ids(df):
    ids = df["antibody_id"]
    dup = ids[ids.duplicated(keep=False)]
    if not dup.empty:
        seen = sorted(dict.fromkeys(str(x) for x in dup.unique()))
        raise ValueError(f"Excel 文件存在重复的 antibody_id: {', '.join(seen)}")


def _normalize_frame(df):
    out = df.copy()
    out["antibody_id"] = out["antibody_id"].map(_normalize_id)
    out["VH"] = out["VH"].map(_normalize_seq)
    out["VL"] = out["VL"].map(_normalize_seq)
    return out[REQUIRED_COLUMNS]


def _normalize_seq(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return normalize_sequence(value)


def _normalize_id(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
