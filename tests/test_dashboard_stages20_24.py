from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient

from ontology_dashboard.identity import CSRF_COOKIE, AdminUserUpdateRequest, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService as FactorySignalService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "dashboard_stages20_24.db"


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


def login(client: TestClient, email: str, password: str) -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def resolved(client: TestClient) -> dict:
    response = client.get("/api/dashboards/resolved", params={"workspace_id": WORKSPACE})
    assert response.status_code == 200, response.text
    return response.json()


def save_dashboard(client: TestClient, payload: dict) -> dict:
    response = client.put(
        "/api/dashboards/preferences",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "base_revision": payload["preference_revision"],
            "active_tab_id": payload["active_tab_id"],
            "tabs": payload["tabs"],
            "parameter_state": payload["parameter_state"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_role_templates_versions_preview_and_dependency_graph(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    manager = resolved(client)
    schema = json.loads((ROOT / "schemas" / "dashboard-platform.schema.json").read_text(encoding="utf-8"))
    resolved_schema = schema["$defs"]["resolvedDashboard"]
    resolved_schema = {**resolved_schema, "$defs": schema["$defs"]}
    assert list(Draft202012Validator(resolved_schema).iter_errors(manager)) == []
    assert manager["template_version"] == 4
    assert [tab["title"] for tab in manager["tabs"]] == ["운영 판단", "근거와 후속"]
    manager_board_ids = {board["definition_id"] for tab in manager["tabs"] for board in tab["boards"]}
    assert {"manager-decision", "priority-list", "impact-summary"} <= manager_board_ids
    assert any(
        edge["source_board_id"].endswith("priority-list")
        and "selected_event_id" in edge["parameter_ids"]
        for edge in manager["dependency_graph"]
    )

    versions = client.get(
        "/api/dashboard-templates/process_manager/versions",
        params={"workspace_id": WORKSPACE},
    )
    assert versions.status_code == 200
    assert versions.json()["items"][0]["version"] == 4

    preview = client.get(
        "/api/dashboard-templates/process_manager/preview",
        params={"workspace_id": WORKSPACE},
    )
    assert preview.status_code == 200
    assert preview.json()["preference_revision"] == 0

    login(client, "engineer@ontology.local", "Engineer!2026")
    engineer = resolved(client)
    assert [tab["title"] for tab in engineer["tabs"]] == ["Evidence 분석", "점검 Workflow"]
    engineer_board_ids = {board["definition_id"] for tab in engineer["tabs"] for board in tab["boards"]}
    assert {"sensor-line-chart", "engineer-checklist", "evidence-table"} <= engineer_board_ids
    assert "manager-decision" not in engineer_board_ids


def test_personalization_persists_is_isolated_and_restores_defaults(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    original = resolved(client)
    draft = deepcopy(original)
    draft["tabs"].reverse()
    for index, tab in enumerate(draft["tabs"]):
        tab["order"] = index
    draft["active_tab_id"] = draft["tabs"][0]["id"]
    draft["parameter_state"]["status_filter"] = "warning"

    active_tab = draft["tabs"][0]
    active_tab["boards"].append(
        {
            "id": "custom:text:manager-note",
            "definition_id": "text-board",
            "title": "개인 교대 메모",
            "width": 4,
            "order": len(active_tab["boards"]),
            "hidden": False,
            "mandatory": False,
            "custom": True,
            "bindings": {},
            "settings": {"text": "다음 교대 전에 공구 상태를 확인합니다."},
        }
    )
    saved = save_dashboard(client, draft)
    assert saved["preference_revision"] == 1
    assert saved["active_tab_id"] == draft["active_tab_id"]
    assert saved["parameter_state"]["status_filter"] == "warning"
    assert any(
        board["id"] == "custom:text:manager-note"
        for tab in saved["tabs"]
        for board in tab["boards"]
    )

    client.post("/api/auth/logout", headers=csrf_headers(client))
    login(client, "manager@ontology.local", "Manager!2026")
    restored_session = resolved(client)
    assert restored_session["preference_revision"] == 1
    assert restored_session["tabs"][0]["id"] == draft["tabs"][0]["id"]

    login(client, "engineer@ontology.local", "Engineer!2026")
    engineer = resolved(client)
    assert engineer["preference_revision"] == 0
    assert not any(
        board["id"] == "custom:text:manager-note"
        for tab in engineer["tabs"]
        for board in tab["boards"]
    )

    login(client, "manager@ontology.local", "Manager!2026")
    reset = client.post(
        "/api/dashboards/preferences/restore",
        headers=csrf_headers(client),
        json={"workspace_id": WORKSPACE},
    )
    assert reset.status_code == 200
    assert reset.json()["preference_revision"] == 0
    assert [tab["title"] for tab in reset.json()["tabs"]] == ["운영 판단", "근거와 후속"]


def test_mandatory_board_cannot_be_removed_or_hidden(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    dashboard = resolved(client)
    mandatory = next(
        board
        for tab in dashboard["tabs"]
        for board in tab["boards"]
        if board["mandatory"]
    )
    for tab in dashboard["tabs"]:
        tab["boards"] = [board for board in tab["boards"] if board["id"] != mandatory["id"]]

    response = client.put(
        "/api/dashboards/preferences",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "base_revision": dashboard["preference_revision"],
            "active_tab_id": dashboard["active_tab_id"],
            "tabs": dashboard["tabs"],
            "parameter_state": dashboard["parameter_state"],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "mandatory_board_required"


def test_board_catalog_role_filter_binding_validation_and_plain_text_security(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    manager_catalog = client.get("/api/boards/catalog", params={"workspace_id": WORKSPACE})
    assert manager_catalog.status_code == 200
    manager_ids = {item["id"] for item in manager_catalog.json()["items"]}
    assert "manager-decision" in manager_ids
    assert "integration-health" not in manager_ids

    dashboard = resolved(client)
    tab = dashboard["tabs"][0]
    tab["boards"].append(
        {
            "id": "custom:text:unsafe",
            "definition_id": "text-board",
            "title": "Unsafe",
            "width": 6,
            "order": len(tab["boards"]),
            "hidden": False,
            "mandatory": False,
            "custom": True,
            "bindings": {},
            "settings": {"text": "<script>alert(1)</script>"},
        }
    )
    unsafe = client.put(
        "/api/dashboards/preferences",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "base_revision": dashboard["preference_revision"],
            "active_tab_id": dashboard["active_tab_id"],
            "tabs": dashboard["tabs"],
            "parameter_state": dashboard["parameter_state"],
        },
    )
    assert unsafe.status_code == 422
    assert "plain text" in unsafe.json()["error"]["message"]

    login(client, "fde@ontology.local", "FDE!2026")
    fde_catalog = client.get(
        "/api/boards/catalog",
        params={"workspace_id": WORKSPACE, "category": "build"},
    )
    assert fde_catalog.status_code == 200
    assert {item["id"] for item in fde_catalog.json()["items"]} >= {
        "integration-health",
        "text-board",
    }


def test_saved_view_and_share_restore_parameters_with_scope_enforcement(
    client: TestClient,
    identity: IdentityService,
) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    dashboard = resolved(client)
    dashboard["parameter_state"].update(
        {
            "selected_event_id": "EVT-GS-002",
            "selected_equipment_id": "M-014",
            "status_filter": "warning",
        }
    )
    view = client.post(
        "/api/dashboards/saved-views",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "name": "공구 마모 보고 View",
            "active_tab_id": dashboard["active_tab_id"],
            "tabs": dashboard["tabs"],
            "parameter_state": dashboard["parameter_state"],
        },
    )
    assert view.status_code == 201, view.text
    view_id = view.json()["id"]
    assert view.json()["parameter_state"]["selected_event_id"] == "EVT-GS-002"
    assert client.get(
        "/api/dashboards/saved-views",
        params={"workspace_id": WORKSPACE},
    ).json()["items"][0]["id"] == view_id

    share = client.post(
        "/api/dashboards/shares",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "active_tab_id": dashboard["active_tab_id"],
            "parameter_state": dashboard["parameter_state"],
            "expires_in_hours": 24,
        },
    )
    assert share.status_code == 201, share.text
    token = share.json()["token"]
    assert share.json()["path"].startswith("/app?share=")

    login(client, "quality@ontology.local", "Quality!2026")
    shared = client.get(f"/api/dashboards/shares/{token}")
    assert shared.status_code == 200
    assert shared.json()["parameter_state"]["selected_event_id"] == "EVT-GS-002"

    quality = next(
        user for user in identity.repository.list_users() if user["email"] == "quality@ontology.local"
    )
    admin = next(
        user for user in identity.repository.list_users() if user["email"] == "admin@ontology.local"
    )
    identity.repository.update_user(
        actor_user_id=admin["id"],
        target_user_id=quality["id"],
        request=AdminUserUpdateRequest(workspace_scopes=[]),
    )
    login(client, "quality@ontology.local", "Quality!2026")
    denied = client.get(f"/api/dashboards/shares/{token}")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "workspace_scope_denied"


def test_fde_template_publish_merges_existing_user_override(client: TestClient) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    dashboard = resolved(client)
    custom_title = "나의 운영 판단"
    dashboard["tabs"][0]["title"] = custom_title
    saved = save_dashboard(client, dashboard)
    assert saved["preference_revision"] == 1

    manager_publish_denied = client.post(
        "/api/dashboard-templates/process_manager/publish",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "display_name": "Denied",
            "tabs": dashboard["tabs"],
            "parameter_definitions": dashboard["parameter_definitions"],
        },
    )
    assert manager_publish_denied.status_code == 403

    login(client, "fde@ontology.local", "FDE!2026")
    preview = client.get(
        "/api/dashboard-templates/process_manager/preview",
        params={"workspace_id": WORKSPACE},
    )
    assert preview.status_code == 200
    template_tabs = preview.json()["tabs"]
    template_tabs[0]["boards"].append(
        {
            "id": "process_manager:operations:text-board:published",
            "definition_id": "text-board",
            "title": "Template Release Note",
            "width": 4,
            "order": len(template_tabs[0]["boards"]),
            "hidden": False,
            "mandatory": False,
            "custom": False,
            "bindings": {},
            "settings": {"text": "Template v2에서 추가된 board입니다."},
        }
    )
    requested = client.post(
        "/api/dashboard-templates/process_manager/publish-requests",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "target_role": "process_manager",
            "display_name": "Process Manager Dashboard v3",
            "tabs": template_tabs,
            "parameter_definitions": preview.json()["parameter_definitions"],
            "change_summary": "개인 override 병합 회귀 테스트",
        },
    )
    assert requested.status_code == 201, requested.text
    request_id = requested.json()["id"]

    login(client, "admin@ontology.local", "OntologyAdmin!2026")
    published = client.post(
        f"/api/admin/template-publish-requests/{request_id}/decision",
        headers=csrf_headers(client),
        json={"decision": "approve", "note": "병합 테스트 승인"},
    )
    assert published.status_code == 200, published.text
    assert published.json()["published_template"]["version"] == 5

    login(client, "manager@ontology.local", "Manager!2026")
    merged = resolved(client)
    assert merged["template_version"] == 5
    assert merged["preference_template_version"] == 4
    assert merged["tabs"][0]["title"] == custom_title
    assert merged["merge_notices"]
    assert any(
        board["id"] == "process_manager:operations:text-board:published"
        for tab in merged["tabs"]
        for board in tab["boards"]
    )
