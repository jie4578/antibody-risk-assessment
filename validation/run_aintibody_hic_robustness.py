"""Run the Phase 4D2 post-hoc oxidation/HIC robustness analysis."""

from __future__ import annotations

from pathlib import Path

from validation.external_validation.analyze_hic_robustness import run_hic_robustness


ROOT = Path(__file__).resolve().parent


def run() -> dict:
    return run_hic_robustness(
        ROOT / "data/external_validation/aintibody_primary_population.csv",
        ROOT / "data/features/aintibody_rule_features.csv",
        ROOT / "data/external_validation",
        ROOT / "reports/aintibody_external/hic_robustness_report.md",
    )


if __name__ == "__main__":
    run()
