from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.application import create_app
from ontology_dashboard.deployment import (
    VERSIONED_ROUTES,
    deployment_readiness,
    process_probe,
    readiness_probe,
    verify_deployment_files,
)
from ontology_dashboard.settings import validate_runtime_environment
from ontology_dashboard.routers.platform import project_deployment_readiness


ROOT = Path(__file__).resolve().parents[1]


def test_static_production_topology_is_hardened_and_keeps_four_routes() -> None:
    evidence = verify_deployment_files(ROOT)
    assert evidence["pass"] is True
    assert all(evidence["checks"].values())
    nginx = (ROOT / "web/nginx.conf").read_text(encoding="utf-8")
    assert "try_files $uri $uri/ /index.html" in nginx
    manifest = (ROOT / "infra/production/platform.yaml").read_text(encoding="utf-8")
    for route in VERSIONED_ROUTES:
        assert route in manifest


def test_production_configuration_fails_fast_on_demo_defaults(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SEED_DEMO_ACCOUNTS", "1")
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_REDIS_URL", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError) as error:
        validate_runtime_environment(ROOT)
    message = str(error.value)
    assert "SEED_DEMO_ACCOUNTS" in message
    assert "PostgreSQL" in message or "SQLite" in message
    assert "Redis" in message or "REDIS" in message


def test_probe_purposes_are_separate_and_local_runtime_is_honest(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_REDIS_URL", raising=False)
    assert process_probe().state == "alive"
    readiness = readiness_probe(ROOT)
    assert readiness.state in {"ready", "degraded"}
    assert next(item for item in readiness.dependencies if item.name == "redis").required is False
    deployment = deployment_readiness(ROOT)
    assert deployment.state == "blocked"
    assert deployment.routes == VERSIONED_ROUTES


def test_health_routes_expose_liveness_startup_and_readiness(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_DB", str(tmp_path / "phase22.db"))
    app = create_app()
    from ontology_dashboard.routers.system import router

    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/health/live").json()["state"] == "alive"
        startup = client.get("/health/startup")
        assert startup.status_code in {200, 503}
        ready = client.get("/health/ready")
        assert ready.status_code in {200, 503}
        assert "dependencies" in ready.json()


def test_project_deployment_endpoint_returns_versioned_route_contract() -> None:
    class Projects:
        def get_for_principal(self, principal, project_id):
            assert project_id == "manufacturing-demo-project"
            return object()

    payload = project_deployment_readiness(
        "manufacturing-demo-project",
        principal=None,
        projects=Projects(),
    )
    assert payload["routes"] == list(VERSIONED_ROUTES)
    assert payload["probes"]["readiness"] == "/health/ready"
