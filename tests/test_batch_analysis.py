# tests/test_batch_analysis.py
import pandas as pd
import pytest

from batch_analysis import batch_analysis, OUTPUT_COLUMNS

VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK"


def _df(rows):
    return pd.DataFrame(rows)


def test_normal_batch_analysis():
    df = _df([
        {"antibody_id": "AB001", "VH": VH, "VL": VL},
        {"antibody_id": "AB002", "VH": VH, "VL": VL},
        {"antibody_id": "AB003", "VH": VH, "VL": VL},
    ])
    result = batch_analysis(df)
    assert len(result) == 3
    assert (result["analysis_status"] == "success").all()
    assert (result["VH_length"] > 0).all()
    assert (result["VL_length"] > 0).all()


def test_illegal_sequence_does_not_fail_batch():
    df = _df([
        {"antibody_id": "AB_OK", "VH": VH, "VL": VL},
        {"antibody_id": "AB_BAD", "VH": "EVQLVES1GGGLV", "VL": VL},
        {"antibody_id": "AB_OK2", "VH": VH, "VL": VL},
    ])
    result = batch_analysis(df)
    assert len(result) == 3

    bad = result[result["antibody_id"] == "AB_BAD"].iloc[0]
    assert bad["analysis_status"] in ("error", "partial_error")
    assert "非字母" in bad["warnings"]

    for ok_id in ("AB_OK", "AB_OK2"):
        assert result[result["antibody_id"] == ok_id].iloc[0]["analysis_status"] == "success"


def test_output_contains_required_fields():
    result = batch_analysis(_df([{"antibody_id": "A", "VH": VH, "VL": VL}]))
    for col in OUTPUT_COLUMNS:
        assert col in result.columns


def test_empty_input():
    # 空 DataFrame -> 返回带规定字段的空表，不报错
    result = batch_analysis(pd.DataFrame())
    assert result.empty
    for col in OUTPUT_COLUMNS:
        assert col in result.columns


def test_empty_rows_record_error():
    # VH/VL 均为空 -> 该条记录 error，不 crash
    result = batch_analysis(_df([{"antibody_id": "EMPTY", "VH": None, "VL": None}]))
    row = result.iloc[0]
    assert row["analysis_status"] == "error"
    assert row["VH_length"] == 0
    assert row["VL_length"] == 0
    assert "序列为空" in row["warnings"]


def test_missing_columns_raises():
    with pytest.raises(ValueError):
        batch_analysis(pd.DataFrame([{"foo": 1}]))
