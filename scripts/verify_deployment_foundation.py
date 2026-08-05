#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from ontology_dashboard.deployment import deployment_readiness, verify_deployment_files


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = verify_deployment_files(ROOT)
    readiness = deployment_readiness(ROOT)
    payload = {
        "check": "production-deployment-foundation",
        "static": files,
        "runtime": readiness.model_dump(mode="json"),
        "pass": bool(files["pass"]),
        "production_evidence": "blocked" if readiness.state != "ready" else "ready",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if files["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
