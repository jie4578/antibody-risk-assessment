"""Sequence-only compatibility check for the immutable rule-v1 checkpoint."""
from __future__ import annotations

import random
import subprocess
import types
from dataclasses import asdict
from pathlib import Path

from core import FROZEN_RULE_VERSION, analyze_sequence

BASELINE = "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d"
ROOT = Path(__file__).resolve().parents[1]


def assert_frozen_rule_compatibility():
    source = subprocess.check_output(["git", "show", f"{BASELINE}:core.py"], cwd=ROOT)
    frozen = types.ModuleType("frozen_baseline_core")
    exec(compile(source, "frozen_baseline_core.py", "exec"), frozen.__dict__)
    rng = random.Random(20261017)
    sequences = ["", "AX", "NNST", "NNNTT", "NPNST", "STSTSTS", "NGNSNNDGDSDAM"]
    sequences += ["".join(rng.choices("ACDEFGHIKLMNPQRSTVWY", k=n)) for n in range(1, 151)]
    for sequence in sequences:
        original = frozen.analyze_sequence(sequence, 31, 35, 50, 65, 99, 110)
        current = analyze_sequence(sequence, 31, 35, 50, 65, 99, 110, rule_version=FROZEN_RULE_VERSION)
        assert asdict(current) == asdict(original), f"Frozen v1 changed for {sequence!r}"
    original_score = subprocess.check_output(["git", "show", f"{BASELINE}:scoring.py"], cwd=ROOT)
    assert (ROOT / "scoring.py").read_bytes().replace(b"\r\n", b"\n") == original_score.replace(b"\r\n", b"\n")
