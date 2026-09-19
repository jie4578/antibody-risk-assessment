"""Run the one-time authorized Phase 5D sealed TEST evaluation."""

from __future__ import annotations

from validation.ml_benchmark.phase5d import run_phase5d


if __name__ == "__main__":
    result = run_phase5d()
    print(result["report"])
