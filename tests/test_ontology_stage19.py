from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.identity import AdminUserUpdateRequest, CSRF_COOKIE, IdentityService
from identity_test_support import build_identity_service
from app.main import app
from app.dependencies import get_identity_service, get_service
from app.operations.service import ManufacturingPredictiveMaintenanceService as FactorySignalService
from app.dependencies import build_manufacturing_service

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "ontology_stage19_test.db"


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    return build_identity_service(database_path, app_env="test", seed_demo=True)


@pytest.fixture()
def service(database_path: Path) -> FactorySignalService:
    return build_manufacturing_service(database_path, root=ROOT)


@pytest.fixture()
def client(identity: IdentityService, service: FactorySignalService):
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def test_object_query_and_two_hop_relation_traversal(client: TestClient) -> None:
    login(client, "quality@ontology.local", "Quality!2026")

    equipment = client.get(
        "/api/ontology/objects",
        params={"workspace_id": WORKSPACE, "object_type": "equipment", "q": "CNC-S04-L04-01"},
    )
    assert equipment.status_code == 200, equipment.text
    assert equipment.json()["total"] == 1
    assert equipment.json()["items"][0]["id"] == "equipment:CNC-S04-L04-01"

    event = client.get(
        "/api/ontology/objects/risk_event:EVT-GS-002",
        params={"workspace_id": WORKSPACE},
    )
    assert event.status_code == 200
    assert event.json()["properties"]["recommended_decision"] == "request_inspection"

    traversal = client.get(
        "/api/ontology/objects/equipment:CNC-S04-L04-01/links",
        params={"workspace_id": WORKSPACE, "direction": "outgoing", "depth": 2},
    )
    assert traversal.status_code == 200, traversal.text
    payload = traversal.json()
    assert payload["root"]["id"] == "equipment:CNC-S04-L04-01"
    node_ids = {item["id"] for item in payload["nodes"]}
    edge_types = {item["link_type"] for item in payload["edges"]}
    assert "risk_event:EVT-GS-002" in node_ids
    assert "evidence_package:EVD-EVT-GS-002" in node_ids
    assert "work_order:EVT-GS-002" in node_ids
    assert "inspection:EVT-GS-002" in node_ids
    assert edge_types >= {
        "equipment_has_risk_event",
        "risk_event_has_evidence",
        "equipment_has_work_order",
        "risk_event_requires_work_order",
        "risk_event_requires_inspection",
    }


def test_action_is_idempotent_and_persists_explicit_audit(
    client: TestClient,
    service: FactorySignalService,
) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    request = {
        "action_type": "record_operational_decision",
        "object_id": "risk_event:EVT-GS-002",
        "workspace_id": WORKSPACE,
        "parameters": {"decision": "request_inspection", "note": "베어링과 공구 상태 확인"},
        "idempotency_key": "stage19-manager-decision-001",
    }

    first = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json=request,
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["state"] == "succeeded"
    assert first_payload["replayed"] is False
    assert first_payload["result"]["actor"] == "김현우"

    replay = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json=request,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["invocation_id"] == first_payload["invocation_id"]
    assert replay.json()["result"]["id"] == first_payload["result"]["id"]

    conflict_request = {**request, "parameters": {"decision": "review_shutdown", "note": "different"}}
    conflict = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json=conflict_request,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_conflict"

    invocations = client.get(
        "/api/ontology/objects/risk_event:EVT-GS-002/action-invocations",
        params={"workspace_id": WORKSPACE},
    )
    assert invocations.status_code == 200
    assert len(invocations.json()["items"]) == 1
    assert invocations.json()["items"][0]["audit_id"] == first_payload["audit_id"]

    with sqlite3.connect(service.repository.path) as connection:
        rows = connection.execute(
            "SELECT action,payload_json FROM audit_log WHERE action=?",
            ("ontology.action.record_operational_decision",),
        ).fetchall()
    assert len(rows) == 1
    audit_payload = json.loads(rows[0][1])
    assert audit_payload["actor_display_name"] == "김현우"
    assert audit_payload["invocation_id"] == first_payload["invocation_id"]


def test_canonical_work_order_action_and_links_are_persisted(client: TestClient) -> None:
    login(client, "technician@ontology.local", "Technician!2026")
    work_order = client.get(
        "/api/ontology/objects/work_order:EVT-GS-002",
        params={"workspace_id": WORKSPACE},
    )
    assert work_order.status_code == 200, work_order.text
    assert work_order.json()["object_type"] == "work_order"
    assert work_order.json()["properties"]["event_id"] == "EVT-GS-002"

    action = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json={
            "action_type": "complete_work_order",
            "object_id": "work_order:EVT-GS-002",
            "workspace_id": WORKSPACE,
            "parameters": {
                "checklist": ["bearing", "pressure"],
                "measurements": {"pressure_bar": 5.7},
                "photo_metadata": [{"name": "pressure-gauge.jpg"}],
                "note": "canonical work order completed",
                "location": "Line A",
            },
            "idempotency_key": "stage53-work-order-complete-001",
        },
    )
    assert action.status_code == 200, action.text
    assert action.json()["state"] == "succeeded"

    traversal = client.get(
        "/api/ontology/objects/work_order:EVT-GS-002/links",
        params={"workspace_id": WORKSPACE, "direction": "outgoing", "depth": 1},
    )
    assert traversal.status_code == 200, traversal.text
    edge_types = {item["link_type"] for item in traversal.json()["edges"]}
    node_ids = {item["id"] for item in traversal.json()["nodes"]}
    assert "work_order_records_action" in edge_types
    assert any(item.startswith("maintenance_action:") for item in node_ids)


def test_inspection_note_action_materializes_virtual_inspection(client: TestClient) -> None:
    login(client, "engineer@ontology.local", "Engineer!2026")

    before = client.get(
        "/api/ontology/objects/inspection:EVT-GS-001",
        params={"workspace_id": WORKSPACE},
    )
    assert before.status_code == 404

    action = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json={
            "action_type": "record_inspection_note",
            "object_id": "inspection:EVT-GS-001",
            "workspace_id": WORKSPACE,
            "parameters": {"body": "정상 설비 예방 점검 메모"},
            "idempotency_key": "stage19-inspection-note-001",
        },
    )
    assert action.status_code == 200, action.text
    assert action.json()["result"]["actor"] == "박지민"

    after = client.get(
        "/api/ontology/objects/inspection:EVT-GS-001",
        params={"workspace_id": WORKSPACE},
    )
    assert after.status_code == 200
    assert after.json()["properties"]["status"] == "in_progress"

    traversal = client.get(
        "/api/ontology/objects/risk_event:EVT-GS-001/links",
        params={"workspace_id": WORKSPACE, "depth": 2},
    )
    node_ids = {item["id"] for item in traversal.json()["nodes"]}
    edge_types = {item["link_type"] for item in traversal.json()["edges"]}
    assert "inspection:EVT-GS-001" in node_ids
    assert any(item.startswith("maintenance_action:") for item in node_ids)
    assert "inspection_records_action" in edge_types


def test_action_permission_and_workspace_scope_are_server_enforced(
    client: TestClient,
    identity: IdentityService,
) -> None:
    login(client, "quality@ontology.local", "Quality!2026")
    denied_action = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json={
            "action_type": "record_operational_decision",
            "object_id": "risk_event:EVT-GS-002",
            "workspace_id": WORKSPACE,
            "parameters": {"decision": "request_inspection"},
            "idempotency_key": "stage19-quality-denied-001",
        },
    )
    assert denied_action.status_code == 403
    assert denied_action.json()["error"]["code"] == "permission_denied"

    quality = next(
        item for item in identity.repository.list_users() if item["email"] == "quality@ontology.local"
    )
    identity.repository.update_user(
        actor_user_id=quality["id"],
        target_user_id=quality["id"],
        request=AdminUserUpdateRequest(workspace_scopes=[]),
    )
    login(client, "quality@ontology.local", "Quality!2026")
    denied_query = client.get(
        "/api/ontology/objects",
        params={"workspace_id": WORKSPACE},
    )
    assert denied_query.status_code == 403
    assert denied_query.json()["error"]["code"] == "workspace_scope_denied"


def test_legacy_decision_and_note_endpoints_are_backed_by_ontology_actions(
    client: TestClient,
    service: FactorySignalService,
) -> None:
    login(client, "manager@ontology.local", "Manager!2026")
    decision = client.post(
        "/api/events/EVT-GS-002/decision",
        headers=csrf_headers(client),
        json={"actor": "spoof", "decision": "request_inspection", "note": "legacy route"},
    )
    assert decision.status_code == 200
    assert decision.json()["actor"] == "김현우"

    login(client, "engineer@ontology.local", "Engineer!2026")
    note = client.post(
        "/api/events/EVT-GS-002/notes",
        headers=csrf_headers(client),
        json={"actor": "spoof", "body": "legacy note route"},
    )
    assert note.status_code == 200
    assert note.json()["actor"] == "박지민"

    with sqlite3.connect(service.repository.path) as connection:
        action_types = {
            row[0]
            for row in connection.execute(
                "SELECT action_type FROM ontology_action_invocations WHERE state='succeeded'"
            ).fetchall()
        }
    assert action_types >= {"record_operational_decision", "record_inspection_note"}

    service.reset()
    with sqlite3.connect(service.repository.path) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM ontology_action_invocations"
        ).fetchone()[0]
    assert remaining == 0
