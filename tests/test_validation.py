# tests/test_validation.py
# B1：统一氨基酸序列校验
import pandas as pd
import pytest

from core import normalize_sequence, validate_sequence, scan_sequence
from batch_analysis import batch_analysis


def _cdr_defaults():
    return (31, 35, 50, 65, 99, 110)


class TestNormalizeSequence:
    def test_none_to_empty(self):
        assert normalize_sequence(None) == ""

    def test_strips_and_uppercases(self):
        assert normalize_sequence("  evql  ") == "EVQL"


class TestValidateSequence:
    def test_all_standard_aa_accepted(self):
        ok, err = validate_sequence("ACDEFGHIKLMNPQRSTVWY")
        assert ok is True
        assert err == ""

    def test_lowercase_normalized_and_accepted(self):
        assert validate_sequence("evql")[0] is True

    def test_whitespace_padding_accepted(self):
        assert validate_sequence("  EVQL  ")[0] is True

    def test_none_rejected(self):
        assert validate_sequence(None)[0] is False

    def test_empty_rejected(self):
        assert validate_sequence("")[0] is False

    def test_blank_rejected(self):
        assert validate_sequence("   ")[0] is False

    @pytest.mark.parametrize("bad", ["ACDéEF", "ACD汉"])
    def test_unicode_letter_rejected(self, bad):
        assert validate_sequence(bad)[0] is False

    def test_digit_rejected(self):
        assert validate_sequence("ACD1EF")[0] is False

    def test_punctuation_rejected(self):
        assert validate_sequence("ACD.EF")[0] is False

    @pytest.mark.parametrize("bad", ["B", "Z", "X", "J", "U", "ACDX"])
    def test_non_standard_aa_rejected(self, bad):
        assert validate_sequence(bad)[0] is False

    def test_internal_space_rejected(self):
        assert validate_sequence("EV Q")[0] is False

    def test_allow_empty(self):
        assert validate_sequence("", allow_empty=True)[0] is True


class TestScanSequenceValidation:
    def test_invalid_returns_error_tuple(self):
        report, risks, summary = scan_sequence("ACDéEF", *_cdr_defaults())
        assert "错误" in report
        assert risks == []
        assert summary == ""

    def test_empty_returns_error_tuple(self):
        report, _, _ = scan_sequence("", *_cdr_defaults())
        assert "错误" in report

    def test_whitespace_padding_is_normalized(self):
        report, _, _ = scan_sequence("  EVQL  ", *_cdr_defaults())
        assert "序列长度: 4 aa" in report


class TestBatchUsesSameValidation:
    def test_non_standard_aa_recorded_as_warning(self):
        df = pd.DataFrame([{"antibody_id": "X1", "VH": "ACDX", "VL": "ACD"}])
        result = batch_analysis(df)
        row = result.iloc[0]
        assert row["analysis_status"] == "partial_error"
        assert "非标准氨基酸" in row["warnings"]

    def test_unicode_recorded_as_warning(self):
        df = pd.DataFrame([{"antibody_id": "X2", "VH": "ACDé", "VL": "ACD"}])
        result = batch_analysis(df)
        assert "非 ASCII" in result.iloc[0]["warnings"]
