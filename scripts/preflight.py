#!/usr/bin/env python3
"""Validate the files and local tools required by the current MVP."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

PYTHON_MODULES = ["argon2", "fastapi", "jsonschema", "pandas", "pydantic", "sklearn", "uvicorn"]
CURRENT_FILES = [
    "api/ontology_dashboard/app.py",
    "api/ontology_dashboard/main.py",
    "api/ontology_dashboard/dependencies.py",
    "api/ontology_dashboard/identity.py",
    "api/ontology_dashboard/projects/service.py",
    "api/ontology_dashboard/service.py",
    "api/ontology_dashboard/predictive_maintenance_runtime/models.py",
    "api/ontology_dashboard/predictive_maintenance_runtime/repository.py",
    "api/ontology_dashboard/predictive_maintenance_runtime/service.py",
    "api/ontology_dashboard/routers/auth.py",
    "api/ontology_dashboard/routers/projects.py",
    "api/ontology_dashboard/routers/manufacturing.py",
    "api/ontology_dashboard/routers/predictive_maintenance_runtime.py",
    "web/src/features/mvp/MvpApplication.tsx",
    "web/src/features/auth/LoginPage.tsx",
    "web/e2e/mvp-frontend-convergence.spec.ts",
    "schemas/input-event.schema.json",
    "schemas/evidence-package.schema.json",
    "schemas/report.schema.json",
    "schemas/ui-block.schema.json",
    "schemas/dataset-manifest.schema.json",
    "schemas/dataset-bundle-manifest.schema.json",
    "schemas/prediction-result.schema.json",
    "data/fixtures/GS-001-normal-stable.json",
    "docs/contracts/api-contract.md",
    "docs/contracts/data-contract.md",
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checks: list[dict[str, object]] = []
    for name in PYTHON_MODULES:
        checks.append({"name": f"python:{name}", "pass": importlib.util.find_spec(name) is not None})
    for command in ("node", "npm"):
        checks.append({"name": f"command:{command}", "pass": shutil.which(command) is not None})
    for relative in CURRENT_FILES:
        checks.append({"name": f"file:{relative}", "pass": (root / relative).is_file()})
    fixtures = sorted((root / "data" / "fixtures").glob("GS-*.json"))
    checks.append({"name": "gold-fixtures", "pass": len(fixtures) == 8, "value": len(fixtures)})
    failed = [item for item in checks if not item["pass"]]
    print(json.dumps({"root": str(root), "python": sys.version.split()[0], "checks": checks, "failed": failed, "pass": not failed}, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
