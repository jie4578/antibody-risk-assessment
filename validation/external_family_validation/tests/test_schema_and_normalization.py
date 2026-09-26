from __future__ import annotations

import pandas as pd

from validation.external_family_validation.preprocessing.normalize_sequences import (
    normalize_sabdab2_summary,
)
from validation.external_family_validation.preprocessing.schema import (
    validate_normalized_frame,
)


def test_normalization_preserves_rows_duplicates_and_missing_chains(tmp_path):
    source = tmp_path / "summary.csv"
    frame = pd.DataFrame(
        [
            {"INSTANCE": "1abc_1", "SABDAB_ID": "1abc", "VH": " aaA ", "VL": "BBB", "organism": "human", "type": "FAB"},
            {"INSTANCE": "1abc_2", "SABDAB_ID": "1abc", "VH": "AAA", "VL": "BBB", "organism": "human", "type": "FAB"},
            {"INSTANCE": "2def_1", "SABDAB_ID": "2def", "VH": "CCC", "VL": "", "organism": "mouse", "type": "FV"},
        ]
    )
    frame.to_csv(source, index=False)

    normalized = normalize_sabdab2_summary(source)

    assert len(normalized) == 3
    assert normalized["record_id"].tolist() == ["1abc_1", "1abc_2", "2def_1"]
    assert normalized.loc[0, "raw_VH"] == "aaA"
    assert normalized.loc[0, "VH"] == "AAA"
    assert normalized.loc[0, "sequence_hash"] == normalized.loc[1, "sequence_hash"]
    assert normalized.loc[2, "sequence_status"] == "PARTIAL"
    assert set(normalized["label_status"]) == {"MISSING"}
    validate_normalized_frame(normalized)
