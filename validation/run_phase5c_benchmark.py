"""Run the frozen Phase 5C TRAIN/VALIDATION benchmark only."""

from __future__ import annotations

from validation.ml_benchmark.phase5c import run_phase5c


if __name__ == "__main__":
    result = run_phase5c()
    print(result["report"])
