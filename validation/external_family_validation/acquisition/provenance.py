"""Provenance and raw-file integrity for the Phase 7A source bundle."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "dataset",
    "source_url",
    "publication",
    "accessibility_note",
    "license_or_accessibility",
    "acquisition_date",
    "sha256",
    "file_size_bytes",
    "file_format",
    "local_raw_path",
    "sequence_availability",
    "vh_vl_availability",
    "experimental_label_availability",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest_entry(
    source_path: str | Path,
    *,
    dataset: str,
    source_url: str,
    publication: str,
    accessibility_note: str,
    sequence_availability: str,
    vh_vl_availability: str,
    experimental_label_availability: str,
    acquisition_date: str | None = None,
    local_raw_path: str | None = None,
    supplementary_dataset: str | None = None,
) -> dict[str, Any]:
    path = Path(source_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "dataset": dataset,
        "source_url": source_url,
        "publication": publication,
        "accessibility_note": accessibility_note,
        "license_or_accessibility": accessibility_note,
        "acquisition_date": acquisition_date or date.today().isoformat(),
        "sha256": sha256_file(path),
        "file_size_bytes": path.stat().st_size,
        "file_format": path.suffix.lstrip(".").lower(),
        "local_raw_path": local_raw_path or path.as_posix(),
        "source_filename": path.name,
        "supplementary_dataset": supplementary_dataset,
        "sequence_availability": sequence_availability,
        "vh_vl_availability": vh_vl_availability,
        "experimental_label_availability": experimental_label_availability,
    }


def write_manifest(entry: dict[str, Any], path: str | Path) -> None:
    missing = REQUIRED_FIELDS - set(entry)
    if missing:
        raise ValueError(f"manifest entry missing fields: {sorted(missing)}")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "purpose": "Phase 7A external family-diverse validation foundation",
                "files": [entry],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def verify_manifest(path: str | Path, repository_root: str | Path | None = None) -> list[str]:
    """Return integrity errors without changing raw data."""

    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = Path(repository_root) if repository_root else manifest_path.parent
    errors: list[str] = []
    for entry in payload.get("files", []):
        raw_path = Path(str(entry["local_raw_path"]))
        if not raw_path.is_absolute():
            raw_path = root / raw_path
        if not raw_path.exists():
            errors.append(f"missing raw file: {raw_path}")
            continue
        if sha256_file(raw_path) != entry["sha256"]:
            errors.append(f"sha256 mismatch: {raw_path}")
        if raw_path.stat().st_size != int(entry["file_size_bytes"]):
            errors.append(f"file size mismatch: {raw_path}")
    return errors
