"""Run Phase 4D1B AIntibody external validation after the frozen audit."""

from __future__ import annotations

from pathlib import Path

from validation.external_validation.analyze_aintibody import run_external_validation


ROOT = Path(__file__).resolve().parent


def run() -> dict:
    return run_external_validation(
        ROOT / "data/external_validation/aintibody_primary_population.csv",
        ROOT / "data/features/aintibody_rule_features.csv",
        ROOT / "data/processed/aintibody_2026.csv",
        ROOT / "data/external_validation/aintibody_population_audit.csv",
        ROOT / "data/external_validation",
        ROOT / "reports/aintibody_external/report.md",
    )


if __name__ == "__main__":
    run()
