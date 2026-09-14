"""Machine-readable provenance and raw-file integrity helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Iterable


REQUIRED_FIELDS = {
    "dataset", "article_title", "doi", "publisher_or_repository",
    "source_filename", "supplementary_dataset_number", "retrieval_date",
    "sha256", "file_size_bytes", "file_format", "data_availability_note",
    "local_raw_path", "source_url",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_entry(*, dataset: str, article_title: str, doi: str,
                publisher_or_repository: str, source_filename: str,
                supplementary_dataset_number: str, local_raw_path: str,
                source_url: str, data_availability_note: str) -> dict:
    path = Path(local_raw_path)
    return {
        "dataset": dataset,
        "article_title": article_title,
        "doi": doi,
        "publisher_or_repository": publisher_or_repository,
        "source_filename": source_filename,
        "supplementary_dataset_number": supplementary_dataset_number,
        "retrieval_date": date.today().isoformat(),
        "sha256": sha256_file(path),
        "file_size_bytes": path.stat().st_size,
        "file_format": path.suffix.lstrip(".").lower(),
        "data_availability_note": data_availability_note,
        "local_raw_path": str(path).replace("\\", "/"),
        "source_url": source_url,
    }


def write_manifest(entries: Iterable[dict], path: str | Path) -> None:
    entries = list(entries)
    for entry in entries:
        missing = REQUIRED_FIELDS - set(entry)
        if missing:
            raise ValueError(f"manifest entry missing fields: {sorted(missing)}")
    Path(path).write_text(json.dumps({"files": entries}, indent=2), encoding="utf-8")


def verify_manifest(path: str | Path) -> list[str]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    for entry in manifest.get("files", []):
        file_path = Path(entry["local_raw_path"])
        if not file_path.is_absolute():
            # The checked-in manifest can use a repository-relative path.
            # source_manifest.json lives at validation/data/raw/.
            file_path = manifest_path.resolve().parents[3] / file_path
        if not file_path.exists():
            errors.append(f"missing raw file: {file_path}")
        elif sha256_file(file_path) != entry["sha256"]:
            errors.append(f"sha256 mismatch: {file_path}")
    return errors
