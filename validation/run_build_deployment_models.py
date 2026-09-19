"""Build local Phase 6A deployment artifacts from frozen inputs."""

from __future__ import annotations

import json

from validation.ml_benchmark.build_deployment_models import build_deployment_models


if __name__ == "__main__":
    print(json.dumps(build_deployment_models(), indent=2))
