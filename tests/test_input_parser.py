# tests/test_input_parser.py
# Stage A3：统一输入解析层（FASTA / Excel / CSV）
import os
from pathlib import Path

import pandas as pd
import pytest

from input_parser import (
    REQUIRED_COLUMNS,
    load_batch_input,
    parse_csv,
    parse_excel,
    parse_fasta,
)
from batch_analysis import batch_analysis

BASE_DIR = Path(__file__).resolve().parent.parent

VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK"


def _write_xlsx(tmp_path, rows, columns=REQUIRED_COLUMNS, name="data.xlsx"):
    p = tmp_path / name
    pd.DataFrame(rows, columns=columns).to_excel(p, index=False, sheet_name="Sheet1")
    return p


def _from_example_csv():
    return pd.read_csv(BASE_DIR / "example_antibodies.csv")


# ---------- FASTA ----------


class TestFasta:
    def test_single_vh(self, tmp_path):
        p = tmp_path / "a.fasta"
        p.write_text(f">AB001_VH\n{VH}\n", encoding="utf-8")
        df = parse_fasta(p)
        assert list(df.columns) == REQUIRED_COLUMNS
        assert len(df) == 1
        assert df.iloc[0]["antibody_id"] == "AB001"
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == ""

    def test_vh_vl_pair(self):
        df = parse_fasta(f">AB001_VH\n{VH}\n>AB001_VL\n{VL}\n")
        assert len(df) == 1
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_multiline_sequence_merged(self):
        content = (
            ">AB001_VH\n"
            "EVQLVESGGGLVQ\n"
            "PGGSLRLSCAAS\n"
            "GFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS\n"
        )
        df = parse_fasta(content)
        assert df.iloc[0]["VH"] == VH

    def test_lowercase_uppercased(self):
        df = parse_fasta(">AB001_VH\nevqlvesggglvq\n")
        assert df.iloc[0]["VH"] == "EVQLVESGGGLVQ"

    def test_pipe_header_pairing(self):
        df = parse_fasta(f">AB001|VH\n{VH}\n>AB001|VL\n{VL}\n")
        assert len(df) == 1
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_lowercase_chain_marker(self):
        df = parse_fasta(f">AB001|vh\n{VH}\n>AB001|vl\n{VL}\n")
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_unpaired_vh_keeps_empty_vl(self):
        df = parse_fasta(f">AB001_VH\n{VH}\n")
        assert len(df) == 1
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == ""

    def test_unpaired_vl_keeps_empty_vh(self):
        df = parse_fasta(f">AB001_VL\n{VL}\n")
        assert df.iloc[0]["VL"] == VL
        assert df.iloc[0]["VH"] == ""

    def test_duplicate_chain_raises(self):
        with pytest.raises(ValueError, match="重复"):
            parse_fasta(f">AB001_VH\n{VH}\n>AB001_VH\n{VH}\n")

    def test_empty_fasta_raises(self, tmp_path):
        p = tmp_path / "empty.fasta"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="未找到任何序列"):
            parse_fasta(p)

    def test_empty_sequence_raises(self):
        with pytest.raises(ValueError, match="序列为空"):
            parse_fasta(f">AB001_VH\n\n>AB001_VL\n{VL}\n")

    def test_malformed_header_raises(self):
        with pytest.raises(ValueError, match="非法 FASTA header"):
            parse_fasta(">no_chain_marker\nEVQL\n")

    def test_sequence_before_header_raises(self):
        with pytest.raises(ValueError, match="header"):
            parse_fasta("EVQL\n>AB001_VH\n")

    def test_missing_file_path_raises(self):
        with pytest.raises(ValueError, match="文件不存在"):
            parse_fasta("does_not_exist.fasta")

    def test_multiple_antibodies(self):
        src = _from_example_csv()
        lines = []
        for _, r in src.head(2).iterrows():
            lines.append(f">{r['antibody_id']}_VH\n{r['VH']}\n")
            lines.append(f">{r['antibody_id']}_VL\n{r['VL']}\n")
        df = parse_fasta("".join(lines))
        assert list(df["antibody_id"]) == ["AB001", "AB002"]
        assert df.iloc[0]["VH"] == src.iloc[0]["VH"]
        assert df.iloc[1]["VL"] == src.iloc[1]["VL"]

    def test_underscore_in_antibody_id_preserved(self):
        df = parse_fasta(f">AB006_RISK_VH\n{VH}\n>AB006_RISK_VL\n{VL}\n")
        assert df.iloc[0]["antibody_id"] == "AB006_RISK"


# ---------- Excel ----------


class TestExcel:
    def test_normal(self, tmp_path):
        p = _write_xlsx(tmp_path, [{"antibody_id": "AB001", "VH": VH, "VL": VL}])
        df = parse_excel(p)
        assert list(df.columns) == REQUIRED_COLUMNS
        assert df.iloc[0]["antibody_id"] == "AB001"
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_column_order_varied(self, tmp_path):
        rows = [{"VL": VL, "antibody_id": "AB001", "VH": VH}]
        p = _write_xlsx(tmp_path, rows, columns=["VL", "antibody_id", "VH"])
        df = parse_excel(p)
        assert df.iloc[0]["antibody_id"] == "AB001"
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_lowercase_sequence_uppercased(self, tmp_path):
        p = _write_xlsx(tmp_path, [{"antibody_id": "AB001", "VH": "evql", "VL": VL}])
        assert parse_excel(p).iloc[0]["VH"] == "EVQL"

    def test_missing_vh_raises(self, tmp_path):
        p = _write_xlsx(tmp_path, [{"antibody_id": "AB001", "VL": VL}], columns=["antibody_id", "VL"])
        with pytest.raises(ValueError, match="VH"):
            parse_excel(p)

    def test_missing_vl_raises(self, tmp_path):
        p = _write_xlsx(tmp_path, [{"antibody_id": "AB001", "VH": VH}], columns=["antibody_id", "VH"])
        with pytest.raises(ValueError, match="VL"):
            parse_excel(p)

    def test_missing_antibody_id_raises(self, tmp_path):
        p = _write_xlsx(tmp_path, [{"VH": VH, "VL": VL}], columns=["VH", "VL"])
        with pytest.raises(ValueError, match="antibody_id"):
            parse_excel(p)

    def test_empty_excel_raises(self, tmp_path):
        p = tmp_path / "empty.xlsx"
        pd.DataFrame().to_excel(p, index=False)
        with pytest.raises(ValueError, match="为空"):
            parse_excel(p)

    def test_not_xlsx_extension_raises(self, tmp_path):
        p = tmp_path / "data.xls"
        pd.DataFrame([{"antibody_id": "A", "VH": "ACD", "VL": "ACD"}]).to_excel(p, index=False)
        with pytest.raises(ValueError, match=".xlsx"):
            parse_excel(p)

    def test_duplicate_antibody_id_raises(self, tmp_path):
        rows = [
            {"antibody_id": "AB001", "VH": VH, "VL": VL},
            {"antibody_id": "AB001", "VH": VH, "VL": VL},
        ]
        p = _write_xlsx(tmp_path, rows)
        with pytest.raises(ValueError, match="重复"):
            parse_excel(p)


# ---------- CSV ----------


class TestCsv:
    def test_normal(self, tmp_path):
        p = tmp_path / "data.csv"
        pd.DataFrame([{"antibody_id": "AB001", "VH": VH, "VL": VL}]).to_csv(p, index=False)
        df = parse_csv(p)
        assert list(df.columns) == REQUIRED_COLUMNS
        assert df.iloc[0]["antibody_id"] == "AB001"
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_missing_columns_raises(self, tmp_path):
        p = tmp_path / "bad.csv"
        pd.DataFrame([{"foo": "1"}]).to_csv(p, index=False)
        with pytest.raises(ValueError, match="必需列"):
            parse_csv(p)

    def test_empty_raises(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="为空"):
            parse_csv(p)


# ---------- 统一 loader ----------


class TestLoadBatchInput:
    def test_csv(self, tmp_path):
        p = tmp_path / "data.csv"
        pd.DataFrame([{"antibody_id": "AB001", "VH": VH, "VL": VL}]).to_csv(p, index=False)
        df = load_batch_input(p)
        assert list(df.columns) == REQUIRED_COLUMNS
        assert df.iloc[0]["VH"] == VH

    def test_xlsx(self, tmp_path):
        p = _write_xlsx(tmp_path, [{"antibody_id": "AB001", "VH": VH, "VL": VL}])
        df = load_batch_input(p)
        assert df.iloc[0]["antibody_id"] == "AB001"
        assert df.iloc[0]["VL"] == VL

    def test_fasta(self, tmp_path):
        p = tmp_path / "ab.fasta"
        p.write_text(f">AB001_VH\n{VH}\n>AB001_VL\n{VL}\n", encoding="utf-8")
        df = load_batch_input(p)
        assert df.iloc[0]["VH"] == VH
        assert df.iloc[0]["VL"] == VL

    def test_fasta_uppercase_extension(self, tmp_path):
        p = tmp_path / "ab.FASTA"
        p.write_text(f">AB001_VH\n{VH}\n>AB001_VL\n{VL}\n", encoding="utf-8")
        assert load_batch_input(p).iloc[0]["antibody_id"] == "AB001"

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "data.txt"
        p.write_text("hi", encoding="utf-8")
        with pytest.raises(ValueError, match="不支持"):
            load_batch_input(p)


# ---------- 一致性：不同输入格式 → 相同分析结果 ----------


class TestFormatConsistency:
    def test_all_formats_identical_batch_result(self, tmp_path):
        src = _from_example_csv()

        csv_p = tmp_path / "data.csv"
        src.to_csv(csv_p, index=False)

        xlsx_p = tmp_path / "data.xlsx"
        src.to_excel(xlsx_p, index=False)

        lines = []
        for _, r in src.iterrows():
            lines.append(f">{r['antibody_id']}_VH\n{r['VH']}\n")
            lines.append(f">{r['antibody_id']}_VL\n{r['VL']}\n")
        fasta_p = tmp_path / "data.fasta"
        fasta_p.write_text("".join(lines), encoding="utf-8")

        cols = [
            "antibody_id",
            "risk_score",
            "risk_level",
            "analysis_status",
            "PTM_risk_count",
            "liability_risk_count",
            "total_risk_count",
        ]
        ref = batch_analysis(load_batch_input(csv_p)).sort_values("antibody_id").reset_index(drop=True)[cols]
        for p in (xlsx_p, fasta_p):
            got = batch_analysis(load_batch_input(p)).sort_values("antibody_id").reset_index(drop=True)[cols]
            pd.testing.assert_frame_equal(ref, got)

    def test_ab001_score_via_fasta(self):
        df = parse_fasta(f">AB001_VH\n{VH}\n>AB001_VL\n{VL}\n")
        row = batch_analysis(df).iloc[0]
        assert row["risk_score"] == pytest.approx(64.30, abs=0.02)
        assert row["risk_level"] == "Medium Risk"

    def test_ab002_score_via_excel(self, tmp_path):
        src = _from_example_csv()
        ab2 = src[src["antibody_id"] == "AB002"].iloc[0]
        p = _write_xlsx(tmp_path, [{"antibody_id": "AB002", "VH": ab2["VH"], "VL": ab2["VL"]}])
        row = batch_analysis(parse_excel(p)).iloc[0]
        assert row["risk_score"] == pytest.approx(74.00, abs=0.02)
        assert row["risk_level"] == "Medium Risk"

    def test_ab006_risk_score_via_fasta(self):
        src = _from_example_csv()
        ab6 = src[src["antibody_id"] == "AB006_RISK"].iloc[0]
        df = parse_fasta(f">AB006_RISK_VH\n{ab6['VH']}\n>AB006_RISK_VL\n{ab6['VL']}\n")
        row = batch_analysis(df).iloc[0]
        assert row["risk_score"] == pytest.approx(48.95, abs=0.05)
        assert row["risk_level"] == "High Risk"
