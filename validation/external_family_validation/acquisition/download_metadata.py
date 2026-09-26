"""Download metadata for the official SAbDab2 summary source.

Network access is explicit: importing this module never downloads anything.
Tests use local fixtures and do not depend on the live OPIG service.
"""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path


OFFICIAL_SABDAB2_SUMMARY_URL = "https://sabdab.opig.stats.ox.ac.uk/api/download/all-summary"


def download_sabdab2_summary(destination: str | Path, *, timeout: int = 120) -> Path:
    """Download the official all-summary CSV to an explicit local path."""

    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        OFFICIAL_SABDAB2_SUMMARY_URL,
        headers={"User-Agent": "antibody-risk-assessment/phase-7a"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return target
