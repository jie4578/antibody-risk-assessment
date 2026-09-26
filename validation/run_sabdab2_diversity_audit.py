"""Run Phase 7B-A descriptive RULE48 and frozen ESM2 diversity audits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from validation.external_family_validation.acquisition.provenance import verify_manifest
from validation.external_family_validation.audit.embedding_audit import (
    EXTERNAL_DIR,
    compare_embedding_spaces,
    extract_external_embeddings,
    load_internal_embeddings,
)
from validation.external_family_validation.audit.report import (
    audit_germline_columns,
    render_report,
    write_report,
)
from validation.external_family_validation.audit.rule_audit import (
    load_external_pairs,
    load_internal_hashes,
    run_rule_audit,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "validation/external_family_validation/source_manifest.json"
PHASE7A_REPORT = ROOT / "validation/external_family_validation/reports/external_diversity_report.json"
RAW_SOURCE = ROOT / "validation/external_family_validation/data/raw/sabdab2_all_summary.csv"
OUTPUT_DIR = ROOT / "validation/external_family_validation/data/processed"
REPORT_PATH = ROOT / "validation/reports/sabdab2_diversity_report.md"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(stage: str = "all") -> None:
    errors = verify_manifest(SOURCE_MANIFEST)
    if errors:
        raise ValueError("SAbDab2 raw source integrity failed: " + "; ".join(errors))
    pairs = load_external_pairs()
    internal_hashes = load_internal_hashes()

    if stage in ("rule", "all"):
        summary, features, sites = run_rule_audit(pairs, internal_hashes)
        features.to_csv(OUTPUT_DIR / "sabdab2_rule48.csv", index=False)
        sites.to_csv(OUTPUT_DIR / "sabdab2_risk_sites.csv", index=False)
        _write_json(OUTPUT_DIR / "rule_distribution.json", summary)
        print(f"RULE48: {len(features)} external vs {len(internal_hashes)} internal unique paired hashes", flush=True)

    if stage in ("embeddings", "all"):
        manifest = extract_external_embeddings(pairs, progress=lambda message: print(message, flush=True))
        external_file = EXTERNAL_DIR / manifest["embedding_file"]
        with np.load(external_file, allow_pickle=False) as data:
            external_hashes = data["sequence_hashes"].astype(str)
            external_vectors = data["paired_embeddings"]
        internal_embedding_hashes, internal_vectors = load_internal_embeddings(internal_hashes)
        comparison = compare_embedding_spaces(
            external_hashes, external_vectors, internal_embedding_hashes, internal_vectors
        )
        _write_json(OUTPUT_DIR / "embedding_diversity.json", comparison)
        print(f"ESM2: {len(external_hashes)} external vs {len(internal_embedding_hashes)} internal embeddings", flush=True)

    if stage in ("report", "all"):
        source = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))["files"][0]
        phase7a = json.loads(PHASE7A_REPORT.read_text(encoding="utf-8"))
        rule = json.loads((OUTPUT_DIR / "rule_distribution.json").read_text(encoding="utf-8"))
        embedding = json.loads((OUTPUT_DIR / "embedding_diversity.json").read_text(encoding="utf-8"))
        embedding_manifest = json.loads((EXTERNAL_DIR / "external_embedding_manifest.json").read_text(encoding="utf-8"))
        columns = pd.read_csv(RAW_SOURCE, nrows=0).columns.tolist()
        content = render_report(
            source=source,
            phase7a=phase7a,
            rule=rule,
            embedding=embedding,
            embedding_manifest=embedding_manifest,
            germline=audit_germline_columns(columns, RAW_SOURCE),
        )
        write_report(REPORT_PATH, content)
        print(f"Report: {REPORT_PATH}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("rule", "embeddings", "report", "all"), default="all")
    args = parser.parse_args()
    run(args.stage)


if __name__ == "__main__":
    main()
