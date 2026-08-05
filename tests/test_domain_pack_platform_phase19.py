from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.dependencies import get_project_service
from ontology_dashboard.domain_packs import resolve_domain_pack
from ontology_dashboard.identity import IdentityService
from ontology_dashboard.main import app
from ontology_dashboard.main import get_identity_service, get_service
from ontology_dashboard.projects import ProjectRepository, ProjectService
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path: Path):
    database = tmp_path / "phase19.db"
    identity = IdentityService(database, app_env="test", seed_demo=True)
    domain_service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database)
    project_service = ProjectService(ProjectRepository(database))
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain_service
    app.dependency_overrides[get_project_service] = lambda: project_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_domain_pack_registry_is_domain_neutral_and_alias_safe() -> None:
    generic, generic_source = resolve_domain_pack("unknown-domain")
    manufacturing, manufacturing_source = resolve_domain_pack("predictive-maintenance")

    assert generic.code == "generic-operations"
    assert generic_source == "default_platform"
    assert manufacturing.code == "manufacturing-predictive-maintenance"
    assert manufacturing_source == "project_metadata"
    assert {item.id for item in manufacturing.bounded_contexts} == {
        "asset-reliability",
        "maintenance-execution",
        "model-operations",
        "source-integration",
    }
    assert generic.namespace.startswith("ontology_dashboard.")
    assert manufacturing.namespace.startswith("ontology_dashboard.")


def test_v4_application_definition_uses_project_domain_pack(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "manager@ontology.local", "password": "Manager!2026"},
    )
    assert login.status_code == 200
    response = client.get(
        "/api/platform/projects/manufacturing-demo-project/applications/v4"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["application_id"] == "ontology-commercial-v4"
    assert payload["application_version"] == "v4"
    assert payload["domain_pack"]["code"] == "manufacturing-predictive-maintenance"
    assert payload["platform_namespace"] == "ontology_dashboard"
    assert payload["compatibility_namespaces"] == []
