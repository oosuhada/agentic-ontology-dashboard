from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    build_manufacturing_service,
    get_identity_service,
    get_project_service,
    get_service,
)
from app.infra.db.project_repository import ProjectRepository
from app.main import app
from app.infra.observability.runtime import observability_readiness
from app.project import ProjectService
from identity_test_support import build_identity_service


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path: Path):
    database = tmp_path / "canonical-runtime-smoke.db"
    identity = build_identity_service(database, app_env="test", seed_demo=True)
    service = build_manufacturing_service(database, root=ROOT)
    projects = ProjectService(ProjectRepository(database))
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_project_service] = lambda: projects
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_health_and_main_operations_flow(client: TestClient) -> None:
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    assert live.json()["status"] == "ok"
    assert ready.json()["status"] == "ready"
    assert "build_sha" in live.json()
    assert "build_sha" in ready.json()

    observability = client.get("/health/observability")
    assert observability.status_code == 200
    assert observability.json()["metrics"]["endpoint"] == "/metrics"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "ontology_build_info" in metrics.text
    assert "ontology_http_requests_total" in metrics.text

    login = client.post(
        "/api/auth/login",
        json={"email": "manager@ontology.local", "password": "Manager!2026"},
    )
    assert login.status_code == 200, login.text

    projects = client.get("/api/projects")
    assert projects.status_code == 200, projects.text
    assert projects.json()["items"]

    events = client.get("/api/events")
    assert events.status_code == 200, events.text
    assert events.json()["items"]

    workspaces = client.get("/api/workspaces")
    assert workspaces.status_code == 200, workspaces.text
    assert workspaces.json()["items"]


def test_openapi_keeps_current_product_routes() -> None:
    paths = app.openapi()["paths"]
    required = {
        "/api/auth/login",
        "/api/projects",
        "/api/events",
        "/api/workspaces",
        "/api/projects/{project_id}/dataset-catalog",
        "/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance/dashboard",
        "/api/dashboards/resolved",
        "/api/reports/draft",
        "/api/planner/object-query",
        "/metrics",
    }
    assert required <= set(paths)


def test_production_observability_degrades_without_optional_trace_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_METRICS_TOKEN", "test-metrics-token")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALERT_DESTINATION_REF", "structured-log")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    readiness = observability_readiness()
    assert readiness.state == "degraded"
    assert readiness.tracing["state"] == "not_configured"

    monkeypatch.delenv("ONTOLOGY_DASHBOARD_METRICS_TOKEN")
    assert observability_readiness().state == "blocked"
