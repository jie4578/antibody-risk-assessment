"""Run Phase 4B frozen rule-feature extraction from Phase 4A tables."""

from __future__ import annotations

from pathlib import Path

from validation.features.extract_rule_features import write_feature_outputs


ROOT = Path(__file__).resolve().parent


def run() -> None:
    write_feature_outputs(
        {
            "jain_2017": ROOT / "data/processed/jain_137.csv",
            "aintibody_2026": ROOT / "data/processed/aintibody_2026.csv",
        },
        output_dir=ROOT / "data/features",
        report_dir=ROOT / "reports/data_audit",
    )


if __name__ == "__main__":
    run()
