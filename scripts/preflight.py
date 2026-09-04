#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import sys
from pathlib import Path

REQUIRED_PYTHON_MODULES = [
    "argon2",
    "fastapi",
    "httpx",
    "jsonschema",
    "joblib",
    "numpy",
    "pandas",
    "pydantic",
    "reportlab",
    "sklearn",
    "uvicorn",
    "yaml",
]
REQUIRED_FILES = [
    "systems/backend/app/main.py",
    "systems/backend/app/application.py",
    "systems/backend/app/dependencies.py",
    "systems/backend/app/health.py",
    "systems/backend/app/migrate.py",
    "systems/backend/app/common/runtime_settings.py",
    "systems/backend/app/common/rate_limit.py",
    "systems/backend/app/identity/identity_service.py",
    "systems/backend/app/identity/identity_router.py",
    "systems/backend/app/project/project_service.py",
    "systems/backend/app/project/project_router.py",
    "systems/backend/app/ontology/ontology_service.py",
    "systems/backend/app/ontology/ontology_router.py",
    "systems/backend/app/equipment/equipment_service.py",
    "systems/backend/app/equipment/equipment_router.py",
    "systems/backend/app/dataset/dataset_service.py",
    "systems/backend/app/dataset/dataset_router.py",
    "systems/backend/app/dataset/ingestion/api_service.py",
    "systems/backend/app/dataset/ingestion/router.py",
    "systems/backend/app/diagnosis/runtime_service.py",
    "systems/backend/app/diagnosis/runtime_router.py",
    "systems/backend/app/maintenance/maintenance_domain.py",
    "systems/backend/app/maintenance/service.py",
    "systems/backend/app/maintenance/maintenance_router.py",
    "systems/backend/app/dashboard/dashboard_service.py",
    "systems/backend/app/dashboard/dashboard_router.py",
    "systems/backend/app/report/report_service.py",
    "systems/backend/app/report/report_router.py",
    "systems/backend/app/planner/planner_service.py",
    "systems/backend/app/planner/planner_router.py",
    "systems/backend/app/governance/governance_service.py",
    "systems/backend/app/governance/governance_router.py",
    "systems/backend/app/operations/service.py",
    "systems/backend/app/operations/router.py",
    "systems/backend/app/infra/db/settings.py",
    "systems/backend/app/infra/db/connection.py",
    "systems/backend/app/infra/db/pool.py",
    "systems/backend/app/infra/db/migrations.py",
    "systems/backend/app/infra/db/project_repository.py",
    "systems/backend/app/infra/db/dataset_repository.py",
    "systems/backend/app/infra/db/prediction_result_repository.py",
    "systems/backend/app/infra/rate_limit.py",
    "systems/backend/app/infra/llm/provider.py",
    "systems/backend/app/infra/observability/runtime.py",
    "systems/backend/app/infra/storage/object_storage.py",
    "ml/src/ontology_dashboard_manufacturing_ml/__init__.py",
    "systems/generator/model/contracts.py",
    "contracts/schemas/input-event.schema.json",
    "contracts/schemas/evidence-package.schema.json",
    "contracts/schemas/report.schema.json",
    "contracts/schemas/ontology-core.schema.json",
    "contracts/schemas/dataset-manifest.schema.json",
    "contracts/schemas/dataset-bundle-manifest.schema.json",
    "contracts/schemas/prediction-result.schema.json",
    "contracts/schemas/product-result-artifact.schema.json",
    "contracts/schemas/event-evidence-projection.schema.json",
    "scripts/ingest_predictive_maintenance_bundle.py",
    "scripts/materialize_predictive_maintenance_ontology.py",
    "scripts/preflight.py",
    "systems/verify_architecture.py",
    "systems/frontend/package.json",
    "systems/frontend/src/features/operations/OperationsApplication.tsx",
]


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    checks: list[dict[str, object]] = []

    for name in REQUIRED_PYTHON_MODULES:
        present = importlib.util.find_spec(name) is not None
        checks.append({"name": f"python:{name}", "pass": present})

    for command in ["node", "npm"]:
        path = shutil.which(command)
        checks.append({"name": f"command:{command}", "pass": path is not None, "path": path})

    for relative in REQUIRED_FILES:
        present = (root / relative).is_file()
        checks.append({"name": f"file:{relative}", "pass": present})

    fixture_count = len(list((root / "data" / "fixtures").glob("GS-*.json")))
    checks.append({"name": "gold_fixture_count", "pass": fixture_count == 8, "value": fixture_count})
    api_port = int(os.getenv("API_PORT", "8100"))
    web_port = int(os.getenv("WEB_PORT", "3100"))
    checks.append({"name": f"port:{api_port}", "pass": port_available(api_port)})
    checks.append({"name": f"port:{web_port}", "pass": port_available(web_port)})

    failed = [check for check in checks if not check["pass"]]
    report = {
        "python": sys.version,
        "root": str(root),
        "checks": checks,
        "failed": failed,
        "pass": not failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
