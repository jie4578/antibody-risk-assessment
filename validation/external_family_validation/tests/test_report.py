from __future__ import annotations

import pandas as pd

from validation.external_family_validation.diversity.diversity_report import (
    build_diversity_report,
)
from validation.external_family_validation.diversity.family_clustering import (
    cluster_unique_paired_sequences,
)
from validation.schemas.dataset_schema import sequence_hash


def test_report_preserves_missing_labels_and_population_counts():
    normalized = pd.DataFrame(
        [
            {"dataset": "SAbDab2", "record_id": "a", "antibody_id": "a", "VH": "A" * 10, "VL": "B" * 10, "sequence_status": "VALID", "sequence_hash": sequence_hash("A" * 10, "B" * 10)},
            {"dataset": "SAbDab2", "record_id": "b", "antibody_id": "b", "VH": "", "VL": "B" * 10, "sequence_status": "PARTIAL", "sequence_hash": sequence_hash("", "B" * 10)},
        ]
    )
    assignments, clusters = cluster_unique_paired_sequences(normalized, 0.9)
    report = build_diversity_report(
        normalized,
        {0.9: (assignments, clusters)},
        source_manifest={"files": []},
        max_identity_pairs=10,
    )
    assert report["population"]["source_records"] == 2
    assert report["population"]["valid_paired_unique_sequences"] == 1
    assert report["experimental_labels"]["status"] == "MISSING"
    assert report["split_readiness"]["decision"] == "HUMAN_REVIEW_REQUIRED"
