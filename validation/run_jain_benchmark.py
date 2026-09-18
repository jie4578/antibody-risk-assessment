"""Run the Jain-only Phase 4C retrospective benchmark."""

from __future__ import annotations

from pathlib import Path

from validation.benchmark.jain_spearman import write_benchmark


ROOT = Path(__file__).resolve().parent


def run() -> None:
    write_benchmark(
        ROOT / "data/processed/jain_137.csv",
        ROOT / "data/features/jain_rule_features.csv",
        ROOT / "data/processed/jain_data_dictionary.csv",
        output_dir=ROOT / "data/benchmark",
        report_dir=ROOT / "reports/jain_benchmark",
    )


if __name__ == "__main__":
    run()
