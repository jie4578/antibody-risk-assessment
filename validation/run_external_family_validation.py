"""Run the Phase 7A external family-diversity audit without model fitting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validation.external_family_validation.acquisition.provenance import verify_manifest
from validation.external_family_validation.diversity.diversity_report import (
    build_diversity_report,
    write_diversity_report,
)
from validation.external_family_validation.diversity.family_clustering import (
    cluster_unique_paired_sequences,
)
from validation.external_family_validation.preprocessing.normalize_sequences import (
    normalize_sabdab2_summary,
)


PACKAGE_ROOT = Path(__file__).resolve().parent / "external_family_validation"
DEFAULT_RAW = PACKAGE_ROOT / "data" / "raw" / "sabdab2_all_summary.csv"
DEFAULT_MANIFEST = PACKAGE_ROOT / "source_manifest.json"
DEFAULT_OUTPUT = PACKAGE_ROOT / "data" / "processed"
DEFAULT_REPORT = PACKAGE_ROOT / "reports" / "external_diversity_report.json"
DEFAULT_THRESHOLDS = (0.7, 0.8, 0.9)


def run_audit(
    *,
    raw_path: str | Path = DEFAULT_RAW,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    output_dir: str | Path = DEFAULT_OUTPUT,
    report_path: str | Path = DEFAULT_REPORT,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
    max_identity_pairs: int = 10_000,
) -> dict:
    """Normalize and audit the selected source; never trains or tunes a model."""

    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    errors = verify_manifest(manifest_file)
    if errors:
        raise ValueError("raw source failed manifest integrity check: " + "; ".join(errors))

    normalized_path = Path(output_dir) / "sabdab2_normalized.csv"
    normalized = normalize_sabdab2_summary(raw_path, normalized_path)
    cluster_outputs = {}
    for threshold in thresholds:
        assignments, clusters = cluster_unique_paired_sequences(normalized, threshold)
        assignments.to_csv(Path(output_dir) / f"sabdab2_assignments_{threshold:.2f}.csv", index=False)
        clusters.to_csv(Path(output_dir) / f"sabdab2_clusters_{threshold:.2f}.csv", index=False)
        cluster_outputs[threshold] = (assignments, clusters)

    report = build_diversity_report(
        normalized,
        cluster_outputs,
        source_manifest=manifest,
        max_identity_pairs=max_identity_pairs,
    )
    write_diversity_report(report, report_path)
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--max-identity-pairs", type=int, default=10_000)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_audit(
        raw_path=args.raw,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        report_path=args.report,
        max_identity_pairs=args.max_identity_pairs,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
