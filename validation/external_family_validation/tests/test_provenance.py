from __future__ import annotations

import json

from validation.external_family_validation.acquisition.provenance import (
    build_manifest_entry,
    sha256_file,
    verify_manifest,
    write_manifest,
)


def test_manifest_round_trip_and_hash_integrity(tmp_path):
    raw = tmp_path / "raw.csv"
    raw.write_bytes(b"record,VH,VL\nA,AAA,BBB\n")
    manifest = tmp_path / "source_manifest.json"
    entry = build_manifest_entry(
        raw,
        dataset="test",
        source_url="https://example.invalid/source.csv",
        publication="test source",
        accessibility_note="test only",
        sequence_availability="VH/VL",
        vh_vl_availability="one row",
        experimental_label_availability="MISSING",
        local_raw_path="raw.csv",
        acquisition_date="2026-09-25",
    )
    write_manifest(entry, manifest)
    assert entry["sha256"] == sha256_file(raw)
    assert verify_manifest(manifest) == []

    raw.write_bytes(b"changed")
    errors = verify_manifest(manifest)
    assert any("sha256 mismatch" in error for error in errors)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["files"][0]["dataset"] == "test"
