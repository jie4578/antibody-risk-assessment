"""Run the Phase 4D1A AIntibody population/schema audit."""

from __future__ import annotations

from pathlib import Path

from validation.external_validation.population_audit import run_population_audit


ROOT = Path(__file__).resolve().parent


def run() -> dict:
    return run_population_audit(
        ROOT / "data/processed/aintibody_2026.csv",
        ROOT / "data/features/aintibody_rule_features.csv",
        ROOT / "data/external_validation",
        ROOT / "reports/aintibody_external",
    )


if __name__ == "__main__":
    run()
