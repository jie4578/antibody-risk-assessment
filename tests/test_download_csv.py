# tests/test_download_csv.py
# B5：下载用临时 CSV 生命周期
import os

import pandas as pd

from batch_analysis import write_result_csv, cleanup_result_csv, _DOWNLOAD_TMP_DIR


def _sample_df():
    return pd.DataFrame({"antibody_id": ["A"], "total_risk_count": [1]})


class TestWriteResultCsv:
    def test_creates_csv_in_managed_dir(self):
        path = write_result_csv(_sample_df())
        try:
            assert os.path.isfile(path)
            assert path.endswith(".csv")
            assert os.path.dirname(path) == _DOWNLOAD_TMP_DIR.name
        finally:
            cleanup_result_csv(path)

    def test_content_roundtrips(self):
        path = write_result_csv(_sample_df())
        try:
            df = pd.read_csv(path)
            assert list(df.columns) == ["antibody_id", "total_risk_count"]
            assert df.iloc[0]["antibody_id"] == "A"
            assert df.iloc[0]["total_risk_count"] == 1
        finally:
            cleanup_result_csv(path)

    def test_cleanup_removes_file(self):
        path = write_result_csv(_sample_df())
        cleanup_result_csv(path)
        assert not os.path.exists(path)

    def test_cleanup_nonexistent_is_noop(self):
        cleanup_result_csv(None)
        cleanup_result_csv("")
        cleanup_result_csv(os.path.join(_DOWNLOAD_TMP_DIR.name, "does_not_exist.csv"))
