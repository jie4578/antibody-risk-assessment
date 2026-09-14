"""Build Phase 4A inspection, provenance and processed audit outputs."""

from __future__ import annotations

import json
from pathlib import Path

from validation.acquisition.inspect_aintibody import inspect_aintibody
from validation.acquisition.inspect_jain import inspect_jain
from validation.acquisition.provenance import build_entry, sha256_file, verify_manifest, write_manifest
from validation.preprocessing.normalize_aintibody import write_outputs as write_aintibody_outputs
from validation.preprocessing.normalize_jain import JAIN_FILES, write_outputs as write_jain_outputs

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports" / "data_audit"


def run() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    aintibody = RAW / "aintibody_2026"
    jain = RAW / "jain_2017"
    entries = []
    for filename, number in [("41587_2026_3238_MOESM3_ESM.xlsx", "Supplementary Tables 1–5"), ("41587_2026_3238_MOESM4_ESM.xlsx", "Supplementary Data 1–3")]:
        path = aintibody / filename
        if path.exists():
            entries.append(build_entry(
                dataset="aintibody_2026",
                article_title="A blinded, prospective benchmark of in silico antibody discovery anchored to experimental affinity and developability",
                doi="10.1038/s41587-026-03238-6",
                publisher_or_repository="Nature Biotechnology / Springer Nature",
                source_filename=filename,
                supplementary_dataset_number=number,
                local_raw_path=path,
                source_url="https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2Fs41587-026-03238-6/MediaObjects/41587_2026_3238_" + ("MOESM3_ESM.xlsx" if "MOESM3" in filename else "MOESM4_ESM.xlsx"),
                data_availability_note="Publisher-hosted supplementary workbook; license terms were not explicitly stated on the article download page.",
            ))
            entries[-1]["local_raw_path"] = str(path.relative_to(ROOT.parent)).replace("\\", "/")
    for filename, number in [("pnas.1616408114.sd01.xlsx", "S1"), ("pnas.1616408114.sd02.xlsx", "S2"), ("pnas.1616408114.sd03.xlsx", "S3")]:
        path = jain / filename
        if path.exists():
            entries.append(build_entry(
                dataset="jain_2017",
                article_title="Biophysical properties of the clinical-stage antibody landscape",
                doi="10.1073/pnas.1616408114",
                publisher_or_repository="PNAS / PMC",
                source_filename=filename,
                supplementary_dataset_number=number,
                local_raw_path=path,
                source_url="https://doi.org/10.1073/pnas.1616408114",
                data_availability_note="Manually supplied from the official PNAS Supporting Information; exact resolved download URL was not recorded.",
            ))
            entries[-1]["local_raw_path"] = str(path.relative_to(ROOT.parent)).replace("\\", "/")
    manifest = RAW / "source_manifest.json"
    before_hashes = {entry["source_filename"]: entry["sha256"] for entry in entries}
    write_manifest(entries, manifest)
    (REPORTS / "source_inspection.json").write_text(json.dumps({
        "jain_2017": inspect_jain(RAW / "jain_2017"),
        "aintibody_2026": inspect_aintibody(aintibody / "41587_2026_3238_MOESM4_ESM.xlsx"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    write_aintibody_outputs(
        aintibody / "41587_2026_3238_MOESM4_ESM.xlsx",
        PROCESSED / "aintibody_2026.csv",
        REPORTS / "aintibody_audit.json",
        REPORTS / "aintibody_audit.md",
    )
    jain_paths = [RAW / "jain_2017" / filename for filename in JAIN_FILES.values()]
    if all(path.exists() for path in jain_paths):
        write_jain_outputs(RAW / "jain_2017", PROCESSED / "jain_137.csv", PROCESSED / "jain_data_dictionary.csv", REPORTS / "jain_audit.json", REPORTS / "jain_audit.md")
    else:
        status = {
            "dataset": "jain_2017",
            "status": "acquisition_blocked",
            "reason": "Official PMC/PNAS XLSX links returned a download verification page during this run; no HTML response was accepted as raw data.",
            "expected_files": [str(path).replace("\\", "/") for path in jain_paths],
            "official_source_urls": [f"https://pmc.ncbi.nlm.nih.gov/articles/instance/5293111/bin/{filename}" for filename in JAIN_FILES.values()],
        }
        (REPORTS / "jain_audit.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
        (REPORTS / "jain_audit.md").write_text("# Jain 2017 data audit\n\n**Status: acquisition blocked.** The official PMC/PNAS download endpoint returned a verification page. No non-primary mirror was used and no normalized Jain table was generated.\n", encoding="utf-8")
    integrity = verify_manifest(manifest)
    after_hashes = {entry["source_filename"]: sha256_file(ROOT.parent / entry["local_raw_path"]) for entry in entries}
    (REPORTS / "raw_integrity.json").write_text(json.dumps({"before_sha256": before_hashes, "after_sha256": after_hashes, "errors": integrity, "status": "PASS" if not integrity and before_hashes == after_hashes else "FAIL"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run()
