from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from fastapi.testclient import TestClient

from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService as FactorySignalService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "role_workspaces.db"


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


def validate_role_contract(payload: dict) -> None:
    schema = json.loads((ROOT / "schemas" / "role-workspaces.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors == [], "\n".join(error.message for error in errors)


def test_executive_workspace_aggregates_without_sensor_detail_and_supports_drilldown(client: TestClient) -> None:
    user = login(client, "executive@ontology.local", "Executive!2026")
    assert "executive.overview.read" in user["permissions"]
    response = client.get("/api/role-workspaces/executive", params={"workspace_id": WORKSPACE})
    assert response.status_code == 200, response.text
    payload = response.json()
    validate_role_contract(payload)
    assert payload["aggregate"]["equipment_count"] == 7
    assert payload["aggregate"]["event_count"] == 8
    assert payload["business_impact"]["currency_impact"] is None
    assert payload["assumptions"]
    assert payload["unresolved_critical_events"]
    assert "history" not in payload
    event_id = payload["unresolved_critical_events"][0]["event_id"]
    assert client.get(f"/api/events/{event_id}/evidence").status_code == 200

    login(client, "engineer@ontology.local", "Engineer!2026")
    denied = client.get("/api/role-workspaces/executive", params={"workspace_id": WORKSPACE})
    assert denied.status_code == 403


def test_auditor_reconstructs_evidence_and_records_export_checkpoint(client: TestClient, database_path: Path) -> None:
    login(client, "quality@ontology.local", "Quality!2026")
    reconstruction = client.get(
        "/api/role-workspaces/audit",
        params={"workspace_id": WORKSPACE, "event_id": "EVT-GS-002"},
    )
    assert reconstruction.status_code == 200, reconstruction.text
    payload = reconstruction.json()
    validate_role_contract(payload)
    assert payload["input_snapshot"]["scenario_id"] == "GS-002"
    assert payload["version_snapshot"]["model_version"] == "fixture-heuristic-v1"
    assert payload["version_snapshot"]["policy_version"] == "operational-policy-v1"
    assert payload["evidence_to_report_trace"]
    assert all(item["evidence_field_ids"] for item in payload["evidence_to_report_trace"])

    checkpoint = client.post(
        "/api/role-workspaces/audit/export-checkpoints",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "event_id": "EVT-GS-002",
            "export_format": "json",
            "reason": "분기 품질 검토 증적",
        },
    )
    assert checkpoint.status_code == 201, checkpoint.text
    assert len(checkpoint.json()["content_hash"]) == 64
    assert checkpoint.json()["audit_id"]

    rebuilt = client.get(
        "/api/role-workspaces/audit",
        params={"workspace_id": WORKSPACE, "event_id": "EVT-GS-002"},
    ).json()
    assert rebuilt["export_checkpoints"][0]["id"] == checkpoint.json()["id"]
    with sqlite3.connect(database_path) as connection:
        action = connection.execute(
            "SELECT action FROM audit_log WHERE id=?",
            (checkpoint.json()["audit_id"],),
        ).fetchone()[0]
    assert action == "audit.export.checkpoint"


def test_field_worker_completes_mobile_task_with_measurement_and_photo_metadata(client: TestClient) -> None:
    login(client, "technician@ontology.local", "Technician!2026")
    workspace = client.get("/api/role-workspaces/field", params={"workspace_id": WORKSPACE})
    assert workspace.status_code == 200, workspace.text
    validate_role_contract(workspace.json())
    task = next(item for item in workspace.json()["tasks"] if item["event_id"] == "EVT-GS-002")
    assert task["task_status"] == "assigned"
    assert task["safety"]
    assert task["location"] == "가공 2라인"
    assert workspace.json()["offline_queue_design"]["implemented"] is False

    action = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json={
            "action_type": "complete_inspection",
            "object_id": "inspection:EVT-GS-002",
            "workspace_id": WORKSPACE,
            "parameters": {
                "checklist": ["공구 마모 상태 확인", "베어링 소음 확인"],
                "measurements": {"tool_wear_min": 235, "torque_nm": 56.2},
                "photo_metadata": [
                    {
                        "filename": "tool-edge.jpg",
                        "captured_at": "2026-08-01T09:40:00+09:00",
                        "mime_type": "image/jpeg",
                        "size_bytes": 245120,
                        "caption": "공구 날 상태",
                        "sha256": "a" * 64,
                    }
                ],
                "note": "마모 확인 후 엔지니어에게 교체 판단 요청",
                "location": "가공 2라인",
            },
            "idempotency_key": "field-complete-stage27-001",
        },
    )
    assert action.status_code == 200, action.text
    assert action.json()["action_type"] == "complete_inspection"
    assert action.json()["result"]["status"] == "completed"

    replay = client.post(
        "/api/ontology/actions/invoke",
        headers=csrf_headers(client),
        json={
            "action_type": "complete_inspection",
            "object_id": "inspection:EVT-GS-002",
            "workspace_id": WORKSPACE,
            "parameters": {
                "checklist": ["공구 마모 상태 확인", "베어링 소음 확인"],
                "measurements": {"tool_wear_min": 235, "torque_nm": 56.2},
                "photo_metadata": [
                    {
                        "filename": "tool-edge.jpg",
                        "captured_at": "2026-08-01T09:40:00+09:00",
                        "mime_type": "image/jpeg",
                        "size_bytes": 245120,
                        "caption": "공구 날 상태",
                        "sha256": "a" * 64,
                    }
                ],
                "note": "마모 확인 후 엔지니어에게 교체 판단 요청",
                "location": "가공 2라인",
            },
            "idempotency_key": "field-complete-stage27-001",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    refreshed = client.get("/api/role-workspaces/field", params={"workspace_id": WORKSPACE}).json()
    completed = next(item for item in refreshed["tasks"] if item["event_id"] == "EVT-GS-002")
    assert completed["task_status"] == "completed"
    assert completed["latest_action"]["payload"]["photo_metadata"][0]["filename"] == "tool-edge.jpg"


def test_fde_template_publish_requires_admin_approval_and_hides_secrets(client: TestClient) -> None:
    login(client, "fde@ontology.local", "FDE!2026")
    workbench = client.get("/api/role-workspaces/fde", params={"workspace_id": WORKSPACE})
    assert workbench.status_code == 200, workbench.text
    validate_role_contract(workbench.json())
    body = workbench.text.lower()
    assert "password_hash" not in body
    assert "session_token" not in body
    assert "provider_secret" not in body
    assert workbench.json()["deployment_checklist"]
    assert workbench.json()["diagnostic_events"]

    preview = client.get(
        "/api/dashboard-templates/process_manager/preview",
        params={"workspace_id": WORKSPACE},
    ).json()
    direct = client.post(
        "/api/dashboard-templates/process_manager/publish",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "display_name": "FDE direct publish must fail",
            "tabs": preview["tabs"],
            "parameter_definitions": preview["parameter_definitions"],
        },
    )
    assert direct.status_code == 403

    requested = client.post(
        "/api/dashboard-templates/process_manager/publish-requests",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "target_role": "process_manager",
            "display_name": "Process Manager Approved Template",
            "tabs": preview["tabs"],
            "parameter_definitions": preview["parameter_definitions"],
            "change_summary": "고객 운영 판단 workflow 검토 결과 반영",
        },
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["status"] == "pending_approval"
    request_id = requested.json()["id"]

    login(client, "admin@ontology.local", "OntologyAdmin!2026")
    approvals = client.get("/api/admin/workflow-approvals")
    assert approvals.status_code == 200
    assert any(item["id"] == request_id for item in approvals.json()["template_publish_requests"])
    approved = client.post(
        f"/api/admin/template-publish-requests/{request_id}/decision",
        headers=csrf_headers(client),
        json={"decision": "approve", "note": "고객 workflow와 권한 경계 확인"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["published_template"]["version"] == 5


def test_model_console_separates_metrics_and_thresholds_and_release_is_approved(client: TestClient) -> None:
    login(client, "datascientist@ontology.local", "DataScience!2026")
    console = client.get("/api/role-workspaces/ml", params={"workspace_id": WORKSPACE})
    assert console.status_code == 200, console.text
    payload = console.json()
    validate_role_contract(payload)
    assert payload["training_metrics"]["scope"] == "training_or_offline_evaluation"
    assert payload["operational_thresholds"]["scope"] == "production_decision_policy"
    assert payload["gold_regression"]["scenario_count"] == 8
    assert payload["gold_regression"]["passed"] == 8
    assert payload["threshold_cost"]
    assert payload["drift_and_schema"]

    release = client.post(
        "/api/role-workspaces/ml/release-requests",
        headers=csrf_headers(client),
        json={
            "workspace_id": WORKSPACE,
            "model_version": "fixture-heuristic-v2-rc1",
            "dataset_version": "fixture-schema-1.0",
            "policy_version": "operational-policy-v2-rc1",
            "metrics": {"gold_pass_rate": 1.0, "scenario_count": 8},
            "threshold_evaluation": {"candidate_threshold": 0.55, "relative_cost": 4},
            "notes": "Gold 8건 통과 후 운영 승인 요청",
        },
    )
    assert release.status_code == 201, release.text
    assert release.json()["status"] == "pending_approval"
    release_id = release.json()["id"]

    login(client, "admin@ontology.local", "OntologyAdmin!2026")
    approved = client.post(
        f"/api/admin/model-release-requests/{release_id}/decision",
        headers=csrf_headers(client),
        json={"decision": "approve", "note": "운영 threshold와 학습 지표 분리 확인"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["audit_id"]
