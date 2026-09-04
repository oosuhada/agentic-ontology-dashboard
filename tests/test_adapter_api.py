from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    build_adapter_service,
    build_manufacturing_service,
    get_adapter_service,
    get_project_service,
    get_identity_service,
    get_service,
)
from app.identity import CSRF_COOKIE, IdentityService
from app.main import app
from app.project import ProjectService
from app.infra.db.project_repository import ProjectRepository
from identity_test_support import build_identity_service

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def adapter_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    database = tmp_path / "adapter-api.db"
    data_root = tmp_path / "datasets"
    data_root.mkdir()
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_DATA_ROOTS", str(data_root))
    identity = build_identity_service(database, app_env="test", seed_demo=True)
    domain_service = build_manufacturing_service(database, root=ROOT)
    project_service = ProjectService(ProjectRepository(database))
    adapter_service = build_adapter_service(database, root=ROOT)
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain_service
    app.dependency_overrides[get_project_service] = lambda: project_service
    app.dependency_overrides[get_adapter_service] = lambda: adapter_service
    with TestClient(app) as client:
        yield client, data_root
    app.dependency_overrides.clear()


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "datascientist@ontology.local",
            "password": "DataScience!2026",
        },
    )
    assert response.status_code == 200, response.text
    csrf = client.cookies.get(CSRF_COOKIE)
    assert csrf
    return {"X-CSRF-Token": csrf}


def prediction_payload() -> dict:
    return {
        "contract_version": "1.0",
        "prediction_id": "api-prediction-1",
        "organization_id": "org-ontology-demo",
        "project_id": "azure-fleet-maintenance-project",
        "workspace_id": "azure-fleet-maintenance",
        "subject": {
            "object_type": "equipment",
            "object_id": "machine-1",
            "observed_at": "2026-08-01T00:00:00Z",
        },
        "prediction": {
            "task": "classification",
            "status": "warning",
            "label": "failure-risk",
            "score": 0.75,
            "confidence": 0.9,
        },
        "evidence": [
            {
                "evidence_id": "api-evidence-1",
                "kind": "feature",
                "label": "pressure",
                "value": 4.2,
                "unit": "bar",
                "source": {
                    "system": "adapter-api-test",
                    "reference": "row:1",
                    "checksum": "a" * 64,
                },
            }
        ],
        "recommended_actions": [],
        "model": {
            "provider": "fixture",
            "model_name": "azure-risk",
            "model_version": "v1",
            "dataset_version": "api-v1",
        },
        "data_quality": {"status": "pass", "issues": []},
        "created_at": "2026-08-01T00:00:00Z",
    }


def test_dataset_and_prediction_api_are_project_scoped(adapter_api) -> None:
    client, data_root = adapter_api
    csrf = login(client)
    active = client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "azure-fleet-maintenance-project"},
    )
    assert active.status_code == 200

    source = data_root / "azure-api.csv"
    source.write_text(
        "datetime,machineID,errorID,failure\n"
        "2026-01-01T00:00:00Z,1,error1,\n"
        "2026-01-01T08:00:00Z,1,,comp1\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {
        "manifest_version": "1.0",
        "manifest_id": "api-manifest-1",
        "organization_id": "org-ontology-demo",
        "project_id": "azure-fleet-maintenance-project",
        "workspace_id": "azure-fleet-maintenance",
        "adapter_code": "azure-fleet-maintenance",
        "dataset_name": "Azure API Fixture",
        "dataset_version": "api-v1",
        "source": {
            "uri": str(source),
            "media_type": "text/csv",
            "checksum_sha256": digest,
            "size_bytes": source.stat().st_size,
            "encoding": "utf-8",
        },
        "schema": {
            "format": "csv",
            "required_fields": ["datetime", "machineID"],
            "field_aliases": {},
            "primary_key": [],
            "timezone": "UTC",
        },
        "quality_rules": [],
        "created_at": "2026-08-01T00:00:00Z",
    }
    ingested = client.post(
        "/api/projects/azure-fleet-maintenance-project/datasets/ingest",
        headers=csrf,
        json=manifest,
    )
    assert ingested.status_code == 201, ingested.text
    assert ingested.json()["metrics"]["error_to_failure_24h"]["error1"]["conversion_rate"] == 1.0

    datasets = client.get("/api/projects/azure-fleet-maintenance-project/datasets")
    assert datasets.status_code == 200
    assert [item["id"] for item in datasets.json()["items"]] == ["api-manifest-1"]

    prediction = client.post(
        "/api/projects/azure-fleet-maintenance-project/predictions",
        headers=csrf,
        json=prediction_payload(),
    )
    assert prediction.status_code == 201, prediction.text
    assert prediction.json()["project_id"] == "azure-fleet-maintenance-project"

    predictions = client.get("/api/projects/azure-fleet-maintenance-project/predictions")
    assert predictions.status_code == 200
    assert [item["prediction_id"] for item in predictions.json()["items"]] == ["api-prediction-1"]

    inactive = client.get("/api/projects/manufacturing-demo-project/predictions")
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "active_project_mismatch"


def test_manifest_project_mismatch_is_rejected_before_file_access(adapter_api) -> None:
    client, _ = adapter_api
    csrf = login(client)
    client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "azure-fleet-maintenance-project"},
    )
    payload = {
        "manifest_version": "1.0",
        "manifest_id": "mismatch",
        "organization_id": "org-ontology-demo",
        "project_id": "manufacturing-demo-project",
        "workspace_id": "azure-fleet-maintenance",
        "adapter_code": "azure-fleet-maintenance",
        "dataset_name": "Mismatch",
        "dataset_version": "v1",
        "source": {
            "uri": "/not/read/before/scope/check.csv",
            "media_type": "text/csv",
            "checksum_sha256": "a" * 64,
        },
        "schema": {
            "format": "csv",
            "required_fields": ["datetime", "machineID"],
        },
        "created_at": "2026-08-01T00:00:00Z",
    }
    response = client.post(
        "/api/projects/azure-fleet-maintenance-project/datasets/ingest",
        headers=csrf,
        json=payload,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "project_context_mismatch"
