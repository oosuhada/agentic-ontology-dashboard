from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from factory_signal_board.identity import CSRF_COOKIE, DEMO_ACCOUNTS, AuthError, IdentityService
from factory_signal_board.main import app, get_identity_service, get_service
from factory_signal_board.service import FactorySignalService

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "auth_rbac_test.db"


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    return IdentityService(database_path, app_env="test", seed_demo=True)


@pytest.fixture()
def service(database_path: Path) -> FactorySignalService:
    return FactorySignalService(ROOT, database_path=database_path)


@pytest.fixture()
def client(identity: IdentityService, service: FactorySignalService):
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def admin_user(client: TestClient, email: str) -> dict:
    response = client.get("/api/admin/users")
    assert response.status_code == 200
    return next(item for item in response.json()["items"] if item["email"] == email)


def test_eight_demo_accounts_login_with_argon2id_hashes(client: TestClient, identity: IdentityService) -> None:
    expected_roles = {
        "admin@ontology.local": "tenant_admin",
        "executive@ontology.local": "executive_viewer",
        "manager@ontology.local": "process_manager",
        "engineer@ontology.local": "process_engineer",
        "technician@ontology.local": "maintenance_technician",
        "quality@ontology.local": "quality_auditor",
        "datascientist@ontology.local": "ml_validator",
        "fde@ontology.local": "fde",
    }
    assert len(DEMO_ACCOUNTS) == 8
    for account in DEMO_ACCOUNTS:
        response = login(client, account["email"], account["password"])
        assert response.status_code == 200, response.text
        user = response.json()["user"]
        assert user["roles"] == [expected_roles[account["email"]]]
        assert user["workspace_scopes"] == ["manufacturing-demo"]
        password_hash = identity.repository.password_hash_for_email(account["email"])
        assert password_hash is not None
        assert password_hash.startswith("$argon2id$")
        assert account["password"] not in password_hash

    fde = login(client, "fde@ontology.local", "FDE!2026").json()["user"]
    assert fde["is_admin"] is False
    assert not any(permission.startswith("admin.") for permission in fde["permissions"])


def test_signup_stays_pending_until_admin_approves_role_and_scope(client: TestClient) -> None:
    registration = client.post(
        "/api/auth/register",
        json={
            "display_name": "신규 엔지니어",
            "email": "new.engineer@example.com",
            "password": "NewEngineer!2026",
            "organization_name": "New Factory",
            "terms_accepted": True,
        },
    )
    assert registration.status_code == 201
    assert registration.json()["status"] == "pending_approval"

    pending_login = login(client, "new.engineer@example.com", "NewEngineer!2026")
    assert pending_login.status_code == 403
    assert pending_login.json()["error"]["code"] == "pending_approval"

    assert login(client, "admin@ontology.local", "OntologyAdmin!2026").status_code == 200
    pending_user = admin_user(client, "new.engineer@example.com")
    approval = client.patch(
        f"/api/admin/users/{pending_user['id']}",
        headers=csrf_headers(client),
        json={
            "status": "active",
            "roles": ["process_engineer"],
            "workspace_scopes": ["manufacturing-demo"],
        },
    )
    assert approval.status_code == 200, approval.text
    assert approval.json()["roles"] == ["process_engineer"]
    assert approval.json()["workspace_scopes"] == ["manufacturing-demo"]

    audit = client.get("/api/admin/audit")
    assert audit.status_code == 200
    assert any(item["target_email"] == "new.engineer@example.com" for item in audit.json()["items"])

    active_login = login(client, "new.engineer@example.com", "NewEngineer!2026")
    assert active_login.status_code == 200
    assert active_login.json()["user"]["default_path"] == "/app"


def test_pending_disabled_and_logout_block_protected_access(client: TestClient) -> None:
    assert login(client, "admin@ontology.local", "OntologyAdmin!2026").status_code == 200
    manager = admin_user(client, "manager@ontology.local")
    disabled = client.patch(
        f"/api/admin/users/{manager['id']}",
        headers=csrf_headers(client),
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200

    blocked = login(client, "manager@ontology.local", "Manager!2026")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "account_disabled"

    assert login(client, "engineer@ontology.local", "Engineer!2026").status_code == 200
    assert client.get("/api/events").status_code == 200
    logged_out = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert logged_out.status_code == 204
    assert client.get("/api/events").status_code == 401


def test_admin_route_is_server_protected_and_fde_is_not_admin(client: TestClient) -> None:
    assert login(client, "fde@ontology.local", "FDE!2026").status_code == 200
    denied = client.get("/api/admin/overview")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"

    assert login(client, "admin@ontology.local", "OntologyAdmin!2026").status_code == 200
    overview = client.get("/api/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["active_users"] == 8


def test_workspace_scope_is_enforced_for_existing_manufacturing_api(client: TestClient) -> None:
    assert login(client, "admin@ontology.local", "OntologyAdmin!2026").status_code == 200
    engineer = admin_user(client, "engineer@ontology.local")
    updated = client.patch(
        f"/api/admin/users/{engineer['id']}",
        headers=csrf_headers(client),
        json={"workspace_scopes": []},
    )
    assert updated.status_code == 200

    assert login(client, "engineer@ontology.local", "Engineer!2026").status_code == 200
    denied = client.get("/api/events")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "workspace_scope_denied"
    assert client.get("/api/workspaces").json()["items"] == []


def test_csrf_is_required_for_cookie_authenticated_mutations(client: TestClient) -> None:
    assert login(client, "manager@ontology.local", "Manager!2026").status_code == 200
    without_csrf = client.post(
        "/api/events/EVT-GS-002/decision",
        json={"actor": "spoof", "decision": "request_inspection", "note": "test"},
    )
    assert without_csrf.status_code == 403
    assert without_csrf.json()["error"]["code"] == "csrf_validation_failed"

    with_csrf = client.post(
        "/api/events/EVT-GS-002/decision",
        headers=csrf_headers(client),
        json={"actor": "spoof", "decision": "request_inspection", "note": "test"},
    )
    assert with_csrf.status_code == 200
    assert with_csrf.json()["actor"] == "김현우"


def test_ontology_registry_is_domain_neutral_foundation(client: TestClient) -> None:
    assert login(client, "quality@ontology.local", "Quality!2026").status_code == 200
    registry = client.get("/api/ontology/registry")
    assert registry.status_code == 200
    payload = registry.json()
    assert payload["domain_packs"][0]["display_name"] == "Manufacturing Predictive Maintenance Pack"
    assert {item["id"] for item in payload["object_types"]} >= {"equipment", "risk_event", "inspection"}
    assert {item["id"] for item in payload["link_types"]} >= {"equipment_has_risk_event"}
    assert {item["id"] for item in payload["action_types"]} >= {"record_operational_decision"}


def test_production_forbids_demo_seed(database_path: Path) -> None:
    production = IdentityService(database_path, app_env="production", seed_demo=False)
    assert production.repository.list_users() == []
    with pytest.raises(AuthError):
        production.repository.authenticate("admin@ontology.local", "OntologyAdmin!2026")

    with pytest.raises(RuntimeError, match="forbidden"):
        IdentityService(database_path.with_name("forbidden.db"), app_env="production", seed_demo=True)
