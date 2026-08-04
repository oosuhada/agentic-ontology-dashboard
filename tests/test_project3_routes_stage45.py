from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.dependencies import get_project3_client
from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.integrations.project3 import (
    Project3GraphSchema,
    Project3Health,
    Project3Readiness,
    Project3Subgraph,
)
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]


class ReadyProject3Client:
    def health(self, *, project_id: str | None = None) -> Project3Health:
        return Project3Health(
            status="ready",
            available=True,
            mapped_project_id="cip-dmd",
            latency_ms=8,
            checks=[
                {
                    "check": "neo4j",
                    "status": "ready",
                    "detail": "connected",
                    "required": True,
                }
            ],
        )

    def readiness(self, project_id: str) -> Project3Readiness:
        assert project_id == "manufacturing-demo-project"
        return Project3Readiness(
            project_id="cip-dmd",
            lifecycle_status="ready",
            source_type="neo4j",
            schema_available=True,
            node_count=9,
            relationship_count=5,
            can_query=True,
            next_action="query",
        )

    def graph_schema(self, project_id: str) -> Project3GraphSchema:
        assert project_id == "manufacturing-demo-project"
        return Project3GraphSchema(
            project_id="cip-dmd",
            schema_version="1.1",
            title="Manufacturing graph",
            schema_context="Equipment and risk events",
            node_identities=[
                {"label": "Equipment", "identity_property": "equipment_id"}
            ],
            relationship_types=["HAS_RISK_EVENT"],
        )

    def subgraph(
        self,
        project_id: str,
        *,
        label: str,
        identity: str,
        depth: int,
        limit: int,
    ) -> Project3Subgraph:
        assert project_id == "manufacturing-demo-project"
        assert label == "Equipment"
        assert identity == "M-014"
        assert depth == 2
        assert limit == 50
        return Project3Subgraph(
            root={"id": "M-014", "label": "Equipment"},
            nodes=[{"id": "M-014", "label": "Equipment"}],
            relationships=[],
            node_count=1,
            relationship_count=0,
            depth=2,
            truncated=False,
        )


class DegradedProject3Client:
    def health(self, *, project_id: str | None = None) -> Project3Health:
        return Project3Health(
            status="unavailable",
            available=False,
            mapped_project_id="cip-dmd",
            error="connection refused",
        )


@pytest.fixture()
def client(tmp_path: Path):
    database_path = tmp_path / "project3-routes.db"
    identity = IdentityService(database_path, app_env="test", seed_demo=True)
    service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_project3_client] = lambda: ReadyProject3Client()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "engineer@ontology.local", "password": "Engineer!2026"},
    )
    assert response.status_code == 200, response.text
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def test_project3_status_and_subgraph_are_typed_and_project_scoped(client: TestClient) -> None:
    login(client)

    status = client.get(
        "/api/integrations/project3/status",
        params={"project_id": "manufacturing-demo-project"},
    )
    assert status.status_code == 200, status.text
    payload = status.json()
    assert payload["health"]["status"] == "ready"
    assert payload["readiness"]["can_query"] is True
    assert payload["schema"]["node_identities"] == [
        {"label": "Equipment", "identity_property": "equipment_id"}
    ]

    graph = client.get(
        "/api/integrations/project3/subgraph",
        params={
            "project_id": "manufacturing-demo-project",
            "label": "Equipment",
            "identity": "M-014",
            "depth": 2,
            "limit": 50,
        },
    )
    assert graph.status_code == 200, graph.text
    assert graph.json()["node_count"] == 1


def test_project3_proxy_denies_inactive_or_unknown_project(client: TestClient) -> None:
    login(client)

    inactive = client.get(
        "/api/integrations/project3/status",
        params={"project_id": "azure-fleet-maintenance-project"},
    )
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "active_project_mismatch"

    unknown = client.get(
        "/api/integrations/project3/status",
        params={"project_id": "other-tenant-project"},
    )
    assert unknown.status_code == 403
    assert unknown.json()["error"]["code"] == "project_scope_denied"


def test_project3_status_exposes_degraded_state_without_breaking_request(client: TestClient) -> None:
    login(client)
    app.dependency_overrides[get_project3_client] = lambda: DegradedProject3Client()

    response = client.get(
        "/api/integrations/project3/status",
        params={"project_id": "manufacturing-demo-project"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["health"]["available"] is False
    assert payload["health"]["status"] == "unavailable"
    assert payload["degraded_reason"] == "connection refused"
    assert payload["readiness"] is None
    assert payload["schema"] is None
