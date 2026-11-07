"""Reproduce native notices from hash-pinned, official upstream source files.

Acquisition (--download) and local parsing are separate. No archive is extracted
onto the filesystem; only text notices are read from regular tar members.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging/windows/licenses/native/source_manifest.json"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_notices(path):
    """Include all upstream attributions, license texts and cited license files.

    Some Qt attribution JSON contains comments. Preserve it verbatim rather
    than silently dropping records that strict JSON parsers reject.
    This intentionally includes notices for unshipped platforms/build tools.
    """
    result = []
    with tarfile.open(path) as archive:
        members = {m.name: m for m in archive if m.isfile()}
        for name, member in sorted(members.items()):
            p = PurePosixPath(name)
            lower = p.name.lower()
            selected = (lower == "qt_attribution.json" or "LICENSES" in p.parts
                        or any(word in lower for word in ("license", "licence", "copying", "copyright"))
                        or lower in {"ftl.txt", "notice", "notice.txt", "legal"})
            if not selected or member.size > 2_000_000:
                continue
            data = archive.extractfile(member).read()
            if b"\0" in data:
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
            result.append((name, text))
    return result


def collect(cache, manifest_path=MANIFEST):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    sections = ["Native upstream copyright, attribution and license materials.\n"
                "Verbatim source texts; platform/build-only notices may also appear.\n"
                "Not every upstream component below is included in the executable.\n"]
    for item in manifest["sources"]:
        path = Path(cache) / item["filename"]
        if sha256(path) != item["sha256"]:
            raise ValueError("Source SHA256 mismatch: " + item["filename"])
        if item["kind"] == "tar":
            texts = archive_notices(path)
            if not texts:
                raise ValueError("No upstream notices: " + item["filename"])
        elif item["kind"] == "text":
            texts = [(item["filename"], path.read_text(encoding="utf-8"))]
        else:
            continue  # Binary reference is hash-checked, never executed.
        for name, text in texts:
            sections.append("\n" + "=" * 72 + "\n" + item["url"] + "\n" + name + "\n" + "=" * 72 + "\n" + text + "\n")
    return "".join(sections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    args.cache.mkdir(parents=True, exist_ok=True)
    if args.download:
        for item in manifest["sources"]:
            target = args.cache / item["filename"]
            if not target.exists():
                partial = target.with_name(target.name + ".part")
                subprocess.run(["curl.exe", "--fail", "--location", "--retry", "2", "--max-time", "180",
                                item["url"], "--output", str(partial)], check=True)
                if sha256(partial) != item["sha256"]:
                    raise ValueError("Downloaded SHA256 mismatch: " + item["filename"])
                partial.rename(target)
    text = collect(args.cache)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "NOTICES.txt").write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"notice_bytes": len(text.encode("utf-8")), "sources": len(manifest["sources"])}, indent=2))


if __name__ == "__main__":
    main()
