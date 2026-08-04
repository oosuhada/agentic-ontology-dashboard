from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.dashboard_models import SavedViewCreateRequest
from ontology_dashboard.dashboard_service import DashboardService
from ontology_dashboard.dependencies import get_project_service
from ontology_dashboard.export_repository import ExportRepository
from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.projects import ProjectRepository, ProjectService
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "project_layer.db"


@pytest.fixture()
def client(database_path: Path):
    identity = IdentityService(database_path, app_env="test", seed_demo=True)
    domain_service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)
    project_service = ProjectService(ProjectRepository(database_path))
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain_service
    app.dependency_overrides[get_project_service] = lambda: project_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def test_demo_project_is_seeded_and_exposed_with_project_scoped_workspace(
    client: TestClient,
) -> None:
    login(client, "manager@ontology.local", "Manager!2026")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    principal = me.json()["user"]
    assert principal["project_scopes"] == [
        "azure-fleet-maintenance-project",
        "manufacturing-demo-project",
        "metropt-compressor-project",
    ]
    assert principal["active_project_id"] == "manufacturing-demo-project"

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    assert [item["id"] for item in projects.json()["items"]] == [
        "azure-fleet-maintenance-project",
        "manufacturing-demo-project",
        "metropt-compressor-project",
    ]

    workspaces = client.get("/api/projects/manufacturing-demo-project/workspaces")
    assert workspaces.status_code == 200
    assert workspaces.json()["items"] == [
        {
            "id": "manufacturing-demo",
            "organization_id": "org-ontology-demo",
            "project_id": "manufacturing-demo-project",
            "slug": "manufacturing-demo",
            "display_name": "Manufacturing Demo",
            "domain_pack": "manufacturing-predictive-maintenance",
        }
    ]


def test_project_access_is_denied_outside_principal_and_tenant_scope(
    client: TestClient,
    database_path: Path,
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO organizations(id,slug,name,created_at) VALUES ('org-b','org-b','Org B','2026-08-01T00:00:00+00:00')"
        )
        connection.execute(
            """
            INSERT INTO projects(
                id,organization_id,slug,display_name,description,domain_pack_code,
                status,default_workspace_id,created_at,updated_at
            ) VALUES ('project-b','org-b','project-b','Project B','','generic','active',NULL,?,?)
            """,
            ("2026-08-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00"),
        )

    login(client, "manager@ontology.local", "Manager!2026")
    response = client.get("/api/projects/project-b")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "project_scope_denied"


def test_active_project_is_persisted_in_session_and_scopes_project_events(
    client: TestClient,
) -> None:
    csrf = login(client, "manager@ontology.local", "Manager!2026")
    activated = client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "azure-fleet-maintenance-project"},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["user"]["active_project_id"] == "azure-fleet-maintenance-project"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["active_project_id"] == "azure-fleet-maintenance-project"

    azure_events = client.get("/api/projects/azure-fleet-maintenance-project/events")
    assert azure_events.status_code == 200
    assert [item["event_id"] for item in azure_events.json()["items"]] == [
        "EVT-AZ-002",
        "EVT-AZ-001",
    ]
    azure_evidence = client.get("/api/events/EVT-AZ-002/evidence")
    assert azure_evidence.status_code == 200, azure_evidence.text
    assert azure_evidence.json()["lineage"]["project_id"] == "azure-fleet-maintenance-project"
    assert azure_evidence.json()["lineage"]["dataset_version"] == "azure-showcase-v1"

    inactive_events = client.get("/api/projects/manufacturing-demo-project/events")
    assert inactive_events.status_code == 409
    assert inactive_events.json()["error"]["code"] == "active_project_mismatch"

    refreshed = client.post("/api/auth/refresh", headers=csrf)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["user"]["active_project_id"] == "azure-fleet-maintenance-project"


def test_metropt_showcase_event_is_project_scoped_and_evidence_backed(
    client: TestClient,
) -> None:
    csrf = login(client, "manager@ontology.local", "Manager!2026")
    activated = client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "metropt-compressor-project"},
    )
    assert activated.status_code == 200, activated.text

    events = client.get("/api/projects/metropt-compressor-project/events")
    assert events.status_code == 200, events.text
    assert [item["event_id"] for item in events.json()["items"]] == ["EVT-MPT-001"]
    assert events.json()["items"][0]["status"] == "warning"

    evidence = client.get("/api/events/EVT-MPT-001/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["lineage"]["project_id"] == "metropt-compressor-project"
    assert evidence.json()["lineage"]["dataset_version"] == "metropt-showcase-v1"


def test_archived_project_is_removed_from_routes_and_cannot_be_activated(
    client: TestClient,
) -> None:
    csrf = login(client, "admin@ontology.local", "OntologyAdmin!2026")
    archived = client.patch(
        "/api/admin/projects/azure-fleet-maintenance-project",
        headers=csrf,
        json={"status": "archived"},
    )
    assert archived.status_code == 200

    listed = client.get("/api/projects")
    assert "azure-fleet-maintenance-project" not in {
        item["id"] for item in listed.json()["items"]
    }
    detail = client.get("/api/projects/azure-fleet-maintenance-project")
    assert detail.status_code == 404

    activate = client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "azure-fleet-maintenance-project"},
    )
    assert activate.status_code == 403
    assert activate.json()["error"]["code"] == "project_scope_denied"


def test_operational_records_are_isolated_between_projects(database_path: Path) -> None:
    identity = IdentityService(database_path, app_env="test", seed_demo=True)
    manager_user = identity.repository.authenticate(
        "manager@ontology.local",
        "Manager!2026",
    )
    manager = identity.repository.principal(
        manager_user["id"],
        active_project_id="azure-fleet-maintenance-project",
    )
    dashboards = DashboardService(database_path)
    template = dashboards.current_template(
        workspace_id="azure-fleet-maintenance",
        role_code="process_manager",
    )
    dashboards.create_saved_view(
        principal=manager,
        request=SavedViewCreateRequest(
            workspace_id="azure-fleet-maintenance",
            name="Azure only",
            active_tab_id=template.tabs[0].id,
            tabs=template.tabs,
            parameter_state={},
        ),
    )
    assert len(
        dashboards.repository.list_saved_views(
            user_id=manager.user_id,
            workspace_id="azure-fleet-maintenance",
        )
    ) == 1
    assert dashboards.repository.list_saved_views(
        user_id=manager.user_id,
        workspace_id="manufacturing-demo",
    ) == []

    exports = ExportRepository(database_path)
    exports.create_checkpoint(
        workspace_id="azure-fleet-maintenance",
        scope="dashboard",
        export_format="json",
        event_id=None,
        filename="azure.json",
        media_type="application/json",
        content_bytes=2,
        snapshot_hash="a" * 64,
        content_hash="b" * 64,
        requested_by=manager.user_id,
        requested_by_name=manager.display_name,
        snapshot={},
    )
    assert len(exports.list_checkpoints(workspace_id="azure-fleet-maintenance")) == 1
    assert exports.list_checkpoints(workspace_id="manufacturing-demo") == []


def test_project_membership_roles_drive_active_principal_permissions(client: TestClient) -> None:
    csrf = login(client, "admin@ontology.local", "OntologyAdmin!2026")
    users = client.get("/api/admin/users").json()["items"]
    manager = next(item for item in users if item["email"] == "manager@ontology.local")

    updated = client.put(
        f"/api/admin/projects/azure-fleet-maintenance-project/members/{manager['id']}",
        headers=csrf,
        json={"status": "active", "roles": ["executive_viewer"]},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["roles"] == ["executive_viewer"]

    members = client.get(
        "/api/admin/projects/azure-fleet-maintenance-project/members"
    )
    assert members.status_code == 200
    member = next(item for item in members.json()["items"] if item["user_id"] == manager["id"])
    assert member["roles"] == ["executive_viewer"]

    csrf = login(client, "manager@ontology.local", "Manager!2026")
    activated = client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "azure-fleet-maintenance-project"},
    )
    assert activated.status_code == 200, activated.text
    principal = activated.json()["user"]
    assert principal["roles"] == ["executive_viewer"]
    assert principal["active_project_roles"] == ["executive_viewer"]
    assert principal["project_roles"]["azure-fleet-maintenance-project"] == [
        "executive_viewer"
    ]
    assert "executive.overview.read" in principal["permissions"]
    assert "events.decision" not in principal["permissions"]

    restored = client.patch(
        "/api/auth/active-project",
        headers=csrf,
        json={"project_id": "manufacturing-demo-project"},
    )
    assert restored.status_code == 200
    assert "process_manager" in restored.json()["user"]["roles"]
    assert "events.decision" in restored.json()["user"]["permissions"]


def test_suspended_project_membership_revokes_scope_and_active_session(client: TestClient) -> None:
    admin_csrf = login(client, "admin@ontology.local", "OntologyAdmin!2026")
    users = client.get("/api/admin/users").json()["items"]
    engineer = next(item for item in users if item["email"] == "engineer@ontology.local")

    suspended = client.put(
        f"/api/admin/projects/metropt-compressor-project/members/{engineer['id']}",
        headers=admin_csrf,
        json={"status": "suspended", "roles": ["process_engineer"]},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"

    engineer_csrf = login(client, "engineer@ontology.local", "Engineer!2026")
    me = client.get("/api/auth/me").json()["user"]
    assert "metropt-compressor-project" not in me["project_scopes"]
    denied = client.patch(
        "/api/auth/active-project",
        headers=engineer_csrf,
        json={"project_id": "metropt-compressor-project"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "project_scope_denied"


def test_admin_cannot_remove_own_project_admin_membership(client: TestClient) -> None:
    csrf = login(client, "admin@ontology.local", "OntologyAdmin!2026")
    me = client.get("/api/auth/me").json()["user"]
    response = client.put(
        f"/api/admin/projects/manufacturing-demo-project/members/{me['user_id']}",
        headers=csrf,
        json={"status": "active", "roles": ["executive_viewer"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "self_lockout_blocked"


def test_admin_project_create_and_default_workspace_validation(client: TestClient) -> None:
    csrf = login(client, "admin@ontology.local", "OntologyAdmin!2026")
    created = client.post(
        "/api/admin/projects",
        headers=csrf,
        json={
            "slug": "customer-fleet-maintenance",
            "display_name": "Customer Fleet Maintenance",
            "description": "Fleet risk and maintenance decision support.",
            "domain_pack_code": "azure-pdm",
            "status": "draft",
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    invalid = client.patch(
        f"/api/admin/projects/{project_id}",
        headers=csrf,
        json={"default_workspace_id": "manufacturing-demo"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_default_workspace"
