# batch_analysis.py
# 批量分析独立模块：逐条复用 core.analyze_sequence 分析多条抗体序列。
# 不复制核心分析逻辑，只负责批量调度、异常隔离与结果汇总。
# 内部单条使用 AnalysisResult，再转换为 DataFrame 输出 schema。

import atexit
import os
import tempfile

import pandas as pd

from core import normalize_sequence, validate_sequence, analyze_sequence
from scoring import compute_risk_score

# 输入必需列
REQUIRED_COLUMNS = ["antibody_id", "VH", "VL"]

# 输出字段（固定顺序，保证下游稳定）
OUTPUT_COLUMNS = [
    "antibody_id",
    "VH_length",
    "VL_length",
    "CDR1_risk_count",
    "CDR2_risk_count",
    "CDR3_risk_count",
    "FW_risk_count",
    "PTM_risk_count",
    "liability_risk_count",
    "total_risk_count",
    "warnings",
    "analysis_status",
    "risk_score",
    "risk_level",
]

# 归为 PTM（翻译后修饰）的类别；其余基序归为化学 liability
PTM_CATEGORIES = {"N-糖基化"}

CDR_REGIONS = ("CDR1", "CDR2", "CDR3", "FW")


def _raw_cell(value):
    """把 DataFrame 单元格转成可处理值；None/NaN → None。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


# 下载文件的临时目录：进程生命周期内有效，退出时自动清理。
# Gradio 6 的 File.postprocess 对本地路径直接返回原路径（不复制），
# 因此下载文件必须存活到用户下载完成；进程退出前统一清理，避免遗留。
_DOWNLOAD_TMP_DIR = tempfile.TemporaryDirectory(prefix="antibody_risk_download_")
atexit.register(_DOWNLOAD_TMP_DIR.cleanup)


def write_result_csv(result_df):
    """把结果 DataFrame 写入临时 CSV 文件，返回文件路径。"""
    fd, path = tempfile.mkstemp(dir=_DOWNLOAD_TMP_DIR.name, suffix=".csv")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        result_df.to_csv(f, index=False)
    return path


def cleanup_result_csv(path):
    """删除下载用临时 CSV（不再需要下载时调用；文件不存在时静默忽略）。"""
    try:
        if path:
            os.remove(path)
    except OSError:
        pass


def _new_record(antibody_id):
    """构造一条初始记录。"""
    return {
        "antibody_id": antibody_id,
        "VH_length": 0,
        "VL_length": 0,
        "CDR1_risk_count": 0,
        "CDR2_risk_count": 0,
        "CDR3_risk_count": 0,
        "FW_risk_count": 0,
        "PTM_risk_count": 0,
        "liability_risk_count": 0,
        "total_risk_count": 0,
        "warnings": "",
        "analysis_status": "success",
        "risk_score": float("nan"),
        "risk_level": "N/A",
    }


def _accumulate_risks(risk_items, record):
    """把 AnalysisResult.risks（RiskItem 列表）累加进 record。"""
    for r in risk_items:
        key = f"{r.region}_risk_count"
        if key in record:
            record[key] += 1

        if r.category in PTM_CATEGORIES:
            record["PTM_risk_count"] += 1
        else:
            record["liability_risk_count"] += 1


def _analyze_chain(seq, chain_name, cdr_args, record, warnings):
    """
    分析单条链并累加计数。
    返回 (是否成功, AnalysisResult | None)；失败不抛出，记录到 warnings。
    """
    ok, err = validate_sequence(seq)
    if not ok:
        warnings.append(f"{chain_name} {err}")
        return False, None

    try:
        result = analyze_sequence(seq, *cdr_args)
        _accumulate_risks(result.risks, record)
        return True, result
    except Exception as e:  # 单条失败不中断整批
        warnings.append(f"{chain_name} 分析异常: {e}")
        return False, None


def batch_analysis(df, cdr1_s=31, cdr1_e=35, cdr2_s=50, cdr2_e=65, cdr3_s=99, cdr3_e=110):
    """
    批量分析抗体序列。

    参数:
        df: pandas.DataFrame，必须包含 antibody_id, VH, VL 列
        cdr*: CDR 边界（Kabat 编号）
    返回:
        result_df: pandas.DataFrame，包含规定输出字段
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"输入 CSV 缺少必需列: {', '.join(missing)}")

    cdr_args = (cdr1_s, cdr1_e, cdr2_s, cdr2_e, cdr3_s, cdr3_e)

    records = []
    for _, row in df.iterrows():
        antibody_id = row.get("antibody_id")
        if antibody_id is None or (isinstance(antibody_id, float) and pd.isna(antibody_id)):
            antibody_id = ""
        else:
            antibody_id = str(antibody_id)

        record = _new_record(antibody_id)
        warnings = []

        vh = normalize_sequence(_raw_cell(row.get("VH")))
        vl = normalize_sequence(_raw_cell(row.get("VL")))

        record["VH_length"] = len(vh)
        record["VL_length"] = len(vl)

        vh_ok, vh_result = _analyze_chain(vh, "VH", cdr_args, record, warnings)
        vl_ok, vl_result = _analyze_chain(vl, "VL", cdr_args, record, warnings)

        record["total_risk_count"] = record["PTM_risk_count"] + record["liability_risk_count"]
        record["warnings"] = "; ".join(warnings)

        if vh_ok and vl_ok:
            record["analysis_status"] = "success"
        elif vh_ok or vl_ok:
            record["analysis_status"] = "partial_error"
        else:
            record["analysis_status"] = "error"

        risk = compute_risk_score([("VH", vh_result), ("VL", vl_result)])
        record["risk_score"] = risk.overall_score
        record["risk_level"] = risk.risk_level

        records.append(record)

    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)
