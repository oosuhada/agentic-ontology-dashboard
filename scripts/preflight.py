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
    "api/ontology_dashboard/__init__.py",
    "api/ontology_dashboard/app.py",
    "api/ontology_dashboard/main.py",
    "api/ontology_dashboard/settings.py",
    "api/ontology_dashboard/context.py",
    "api/ontology_dashboard/contracts.py",
    "api/ontology_dashboard/security.py",
    "api/ontology_dashboard/identity.py",
    "api/ontology_dashboard/identity_models.py",
    "api/ontology_dashboard/identity_repository.py",
    "api/ontology_dashboard/repository.py",
    "api/ontology_dashboard/service.py",
    "api/ontology_dashboard/ontology.py",
    "api/ontology_dashboard/ontology_adapter.py",
    "api/ontology_dashboard/ontology_repository.py",
    "api/ontology_dashboard/ontology_service.py",
    "api/ontology_dashboard/conversation.py",
    "api/ontology_dashboard/llm.py",
    "api/ontology_dashboard/reports.py",
    "api/ontology_dashboard/dashboard_models.py",
    "api/ontology_dashboard/dashboard_catalog.py",
    "api/ontology_dashboard/dashboard_repository.py",
    "api/ontology_dashboard/dashboard_service.py",
    "api/ontology_dashboard/analysis_models.py",
    "api/ontology_dashboard/analysis_repository.py",
    "api/ontology_dashboard/analysis_service.py",
    "api/ontology_dashboard/role_workflow_models.py",
    "api/ontology_dashboard/role_workflow_repository.py",
    "api/ontology_dashboard/role_workflow_service.py",
    "api/ontology_dashboard/ontology_planner_models.py",
    "api/ontology_dashboard/ontology_planner_service.py",
    "api/ontology_dashboard/export_models.py",
    "api/ontology_dashboard/export_repository.py",
    "api/ontology_dashboard/export_service.py",
    "ml/src/ontology_dashboard_manufacturing_ml/__init__.py",
    "ml/src/factory_signal_ml/cli.py",
    "api/ontology_dashboard/application.py",
    "api/ontology_dashboard/migrations.py",
    "api/ontology_dashboard/ontology_instance_repository.py",
    "schemas/input-event.schema.json",
    "schemas/evidence-package.schema.json",
    "schemas/report.schema.json",
    "schemas/ui-block.schema.json",
    "schemas/ontology-core.schema.json",
    "schemas/dashboard-platform.schema.json",
    "schemas/role-workspaces.schema.json",
    "schemas/ontology-planner.schema.json",
    "schemas/export.schema.json",
    "schemas/dataset-manifest.schema.json",
    "schemas/prediction-result.schema.json",
    "evaluation/gold_scenarios.yml",
    "web/package.json",
    "web/src/features/dashboard/DashboardShell.tsx",
    "web/src/features/roles/RoleBoardRenderer.tsx",
    "web/src/features/planner/PlannerAssistantBoard.tsx",
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
