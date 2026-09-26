from __future__ import annotations

import pandas as pd
from pandas.testing import assert_frame_equal

from validation.external_family_validation.diversity.family_clustering import (
    cluster_unique_paired_sequences,
)
from validation.schemas.dataset_schema import sequence_hash


def _records() -> pd.DataFrame:
    rows = [
        ("a", "A" * 10, "B" * 10),
        ("b", "A" * 9 + "C", "B" * 9 + "C"),
        ("c", "D" * 10, "E" * 10),
    ]
    return pd.DataFrame(
        [
            {
                "sequence_hash": sequence_hash(vh, vl),
                "VH": vh,
                "VL": vl,
                "sequence_status": "VALID",
                "record_id": record_id,
            }
            for record_id, vh, vl in rows
        ]
    )


def test_clustering_is_reproducible_and_thresholded():
    records = _records()
    first = cluster_unique_paired_sequences(records, 0.9)
    second = cluster_unique_paired_sequences(records, 0.9)
    assert_frame_equal(first[0], second[0])
    assert_frame_equal(first[1], second[1])
    assert sorted(first[1]["cluster_size"].tolist()) == [1, 2]


def test_identity_threshold_can_separate_near_pair():
    records = _records()
    assignments, clusters = cluster_unique_paired_sequences(records, 1.0)
    assert len(clusters) == 3
    assert assignments["cluster_id"].nunique() == 3
