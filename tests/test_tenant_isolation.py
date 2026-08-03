from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.identity import IdentityService, RegisterRequest
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "tenant_isolation.db"


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    service = IdentityService(database_path, app_env="test", seed_demo=True)
    second = service.repository.create_pending_user(
        RegisterRequest(
            display_name="Tenant B Admin",
            email="admin@tenant-b.example",
            password="TenantBAdmin!2026",
            organization_name="Tenant B",
            terms_accepted=True,
        )
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO organizations (id,slug,name,created_at) VALUES (?,?,?,datetime('now'))",
            ("org-tenant-b", "tenant-b", "Tenant B"),
        )
        connection.execute(
            """
            INSERT INTO workspaces (id,organization_id,slug,display_name,domain_pack,created_at)
            VALUES (?,?,?,?,?,datetime('now'))
            """,
            ("tenant-b-workspace", "org-tenant-b", "tenant-b-workspace", "Tenant B Workspace", "generic"),
        )
        connection.execute(
            "UPDATE users SET organization_id=?,status='active' WHERE id=?",
            ("org-tenant-b", second["id"]),
        )
        connection.execute(
            "INSERT INTO user_roles (user_id,role_code) VALUES (?,?)",
            (second["id"], "tenant_admin"),
        )
        connection.execute(
            "INSERT INTO user_scopes (user_id,workspace_id) VALUES (?,?)",
            (second["id"], "tenant-b-workspace"),
        )
    return service


@pytest.fixture()
def client(identity: IdentityService, database_path: Path):
    domain_service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_tenant_admin_is_scoped_to_organization(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@tenant-b.example", "password": "TenantBAdmin!2026"},
    )
    assert login.status_code == 200
    principal = login.json()["user"]
    assert principal["organization_id"] == "org-tenant-b"
    assert principal["workspace_scopes"] == ["tenant-b-workspace"]

    users = client.get("/api/admin/users")
    assert users.status_code == 200
    emails = {item["email"] for item in users.json()["items"]}
    assert "admin@tenant-b.example" in emails
    assert "admin@ontology.local" not in emails
    assert "manager@ontology.local" not in emails

    workspaces = client.get("/api/admin/workspaces")
    assert workspaces.status_code == 200
    assert [item["id"] for item in workspaces.json()["items"]] == ["tenant-b-workspace"]

    audit = client.get("/api/admin/audit")
    assert audit.status_code == 200
    assert all(item["actor_email"] == "admin@tenant-b.example" for item in audit.json()["items"])
