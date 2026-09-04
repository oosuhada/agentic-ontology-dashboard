from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.identity import AuthError, Principal
from app.maintenance.maintenance_router import create_maintenance_router


class Identity:
    @staticmethod
    def require_project(principal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise AuthError("project_scope_denied", "project denied")

    @staticmethod
    def require_workspace(principal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise AuthError("workspace_scope_denied", "workspace denied")


class Service:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def request_inspection(self, **values):
        self.calls.append(("request", values))
        return {"work_order_id": "INSPECTION-WO-1", "work_type": "inspection"}

    def transition_inspection(self, **values):
        self.calls.append(("transition", values))
        return {
            "work_order_id": values["work_order_id"],
            "work_order_status": values["target"].value,
        }

    def complete_inspection(self, **values):
        self.calls.append(("complete", values))
        return {
            "work_order_id": values["work_order_id"],
            "inspection_result_id": "INSPECTION-RESULT-1",
            "maintenance_event_id": None,
        }

    def create_manual_recommendation(self, **values):
        self.calls.append(("manual", values))
        return {"recommendation_id": "REC-1"}

    def list_action_candidates(self, **values):
        self.calls.append(("action_candidates", values))
        return {
            "inspection_result_id": values["inspection_result_id"],
            "items": [],
        }

    def calculate_maintenance_cost(self, **values):
        self.calls.append(("cost_calculate", values))
        return {
            "analysis_id": "COST-ANALYSIS-1",
            "calculation_status": "calculated",
        }

    def get_cost_analysis(self, **values):
        self.calls.append(("cost_get", values))
        return {"analysis_id": values["analysis_id"]}

    def list_cost_analyses(self, **values):
        self.calls.append(("cost_list", values))
        return {
            "inspection_result_id": values["inspection_result_id"],
            "items": [],
        }

    def decide_manual_recommendation(self, **values):
        self.calls.append(("decision", values))
        return {"decision_id": "DECISION-1", "work_order_id": "MAINTENANCE-WO-1"}

    def approve_maintenance_work_order(self, **values):
        self.calls.append(("maintenance_approve", values))
        return {"maintenance_action_id": "MAINTENANCE-ACTION-1"}

    def start_maintenance(self, **values):
        self.calls.append(("maintenance_start", values))
        return {"status": "in_progress"}

    def complete_maintenance(self, **values):
        self.calls.append(("maintenance_complete", values))
        return {"maintenance_event_id": "MAINTENANCE-EVENT-1"}

    def request_maintenance_replay(self, **values):
        self.calls.append(("maintenance_replay", values))
        return {"status": "replay_requested"}

    def event_lineage(self, **values):
        self.calls.append(("lineage", values))
        return {
            "event_id": values["event_id"],
            "cost_analyses": [],
            "activities": [],
        }


def principal(role: str) -> Principal:
    permissions = {
        "process_manager": ["events.read", "events.decision"],
        "process_engineer": ["events.read", "field.tasks.update"],
        "maintenance_technician": ["events.read", "field.tasks.update"],
    }[role]
    return Principal(
        user_id=f"user-{role}",
        organization_id="org-1",
        email=f"{role}@example.test",
        display_name=role,
        status="active",
        roles=[role],
        permissions=permissions,
        workspace_scopes=["workspace-1"],
        project_scopes=["project-1"],
        project_roles={"project-1": [role]},
        active_project_id="project-1",
        active_project_roles=[role],
        is_admin=False,
        default_path="/",
        landing_key=role,
    )


def client_for(role: str) -> tuple[TestClient, Service]:
    actor = principal(role)
    service = Service()
    identity = Identity()

    def require_permission(permission: str):
        def dependency():
            if permission not in actor.permissions:
                raise AuthError("permission_denied", "permission denied")
            return actor

        return dependency

    app = FastAPI()

    @app.exception_handler(AuthError)
    async def auth_error_handler(_: Request, exc: AuthError):
        return JSONResponse(
            status_code=403,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(
        create_maintenance_router(
            require_permission=require_permission,
            get_identity_service=lambda: identity,
            get_maintenance_service=lambda: service,
            require_csrf=lambda: None,
        )
    )
    return TestClient(app), service


BASE = "/api/projects/project-1/workspaces/workspace-1/maintenance"
INSPECTION = {
    "event_id": "EVT-1",
    "snapshot_basis": {
        "artifact_id": "RESULT-1",
        "evidence_payload_reference": "RESULT-1",
        "asset_id": "CNC-1",
        "event_id": "EVT-1",
    },
}
RESULT = {
    "outcome": "maintenance_recommended",
    "checklist": [{"item_id": "tool", "status": "fail", "note": "worn"}],
    "measurements": [{"name": "tool_wear_min", "value": 220, "unit": "min"}],
    "findings": ["tool worn"],
    "note": "replacement candidate",
}


def cost_request(action_code: str = "TOOL_REPLACEMENT") -> dict:
    return {
        "action_code": action_code,
        "sop_id": "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
        "sop_version": "demo-2026-08-28",
    }


def test_manager_can_request_and_decide_but_idempotency_header_is_required() -> None:
    client, service = client_for("process_manager")

    missing = client.post(f"{BASE}/inspection-work-orders", json=INSPECTION)
    requested = client.post(
        f"{BASE}/inspection-work-orders",
        json=INSPECTION,
        headers={"Idempotency-Key": "inspection-request-001"},
    )
    decided = client.post(
        f"{BASE}/recommendations/REC-1/decisions",
        json={"disposition": "accept", "note": "approved"},
        headers={"Idempotency-Key": "recommendation-decision-001"},
    )

    assert missing.status_code == 422
    assert requested.status_code == 200
    assert decided.status_code == 200
    assert [name for name, _ in service.calls] == ["request", "decision"]


def test_inspection_request_rejects_caller_supplied_authorization_lineage() -> None:
    client, service = client_for("process_manager")
    forged = {
        **INSPECTION,
        "operational_decision_kind": "review_shutdown",
        "source_product_result_id": "FORGED-RESULT",
    }

    response = client.post(
        f"{BASE}/inspection-work-orders",
        json=forged,
        headers={"Idempotency-Key": "inspection-request-001"},
    )

    assert response.status_code == 422
    assert service.calls == []


def test_process_engineer_can_record_inspection_result() -> None:
    client, service = client_for("process_engineer")

    started = client.post(
        f"{BASE}/inspection-work-orders/INSPECTION-WO-1/start",
        headers={"Idempotency-Key": "inspection-start-001"},
    )
    completed = client.post(
        f"{BASE}/inspection-work-orders/INSPECTION-WO-1/complete",
        json=RESULT,
        headers={"Idempotency-Key": "inspection-complete-001"},
    )

    assert started.status_code == 200
    assert completed.status_code == 200
    assert completed.json()["maintenance_event_id"] is None
    assert [name for name, _ in service.calls] == ["transition", "complete"]


def test_maintenance_technician_cannot_take_process_engineer_inspection_action() -> None:
    client, service = client_for("maintenance_technician")

    response = client.post(
        f"{BASE}/inspection-work-orders/INSPECTION-WO-1/complete",
        json=RESULT,
        headers={"Idempotency-Key": "inspection-complete-001"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_context_denied"
    assert service.calls == []


def test_manager_approves_maintenance_but_cannot_execute_it() -> None:
    client, service = client_for("process_manager")

    missing_idempotency = client.post(
        f"{BASE}/maintenance-work-orders/MAINTENANCE-WO-1/approve",
        json={"simulation_session_id": "SIMULATION-SESSION-001"},
    )
    approved = client.post(
        f"{BASE}/maintenance-work-orders/MAINTENANCE-WO-1/approve",
        json={"simulation_session_id": "SIMULATION-SESSION-001"},
        headers={"Idempotency-Key": "maintenance-approve-001"},
    )
    denied = client.post(
        f"{BASE}/maintenance-actions/MAINTENANCE-ACTION-1/start",
        json={},
        headers={"Idempotency-Key": "maintenance-start-001"},
    )

    assert missing_idempotency.status_code == 422
    assert approved.status_code == 200
    assert denied.status_code == 403
    assert [name for name, _ in service.calls] == ["maintenance_approve"]


def test_technician_executes_and_requests_replay_without_caller_lineage() -> None:
    client, service = client_for("maintenance_technician")

    denied_approval = client.post(
        f"{BASE}/maintenance-work-orders/MAINTENANCE-WO-1/approve",
        json={"simulation_session_id": "SIMULATION-SESSION-001"},
        headers={"Idempotency-Key": "maintenance-approve-001"},
    )
    started = client.post(
        f"{BASE}/maintenance-actions/MAINTENANCE-ACTION-1/start",
        json={},
        headers={"Idempotency-Key": "maintenance-start-001"},
    )
    completed = client.post(
        f"{BASE}/maintenance-actions/MAINTENANCE-ACTION-1/complete",
        json={"outcome": "tool replaced"},
        headers={"Idempotency-Key": "maintenance-complete-001"},
    )
    replay = client.post(
        f"{BASE}/maintenance-events/MAINTENANCE-EVENT-1/replay",
        json={"restart_at": "2026-08-24T09:35:00Z"},
        headers={"Idempotency-Key": "maintenance-replay-001"},
    )

    assert denied_approval.status_code == 403
    assert started.status_code == 200
    assert completed.status_code == 200
    assert replay.status_code == 200
    assert [name for name, _ in service.calls] == [
        "maintenance_start",
        "maintenance_complete",
        "maintenance_replay",
    ]


def test_maintenance_commands_reject_caller_supplied_canonical_lineage() -> None:
    client, service = client_for("maintenance_technician")

    forged = client.post(
        f"{BASE}/maintenance-actions/MAINTENANCE-ACTION-1/complete",
        json={
            "outcome": "tool replaced",
            "source_product_result_id": "FORGED-RESULT",
            "equipment_id": "FORGED-EQUIPMENT",
            "state_patch": {"tool_wear_min": 999},
        },
        headers={"Idempotency-Key": "maintenance-complete-001"},
    )

    assert forged.status_code == 422
    assert service.calls == []


def test_manager_requests_cost_analysis_and_readers_can_query_results() -> None:
    manager_client, manager_service = client_for("process_manager")
    created = manager_client.post(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses",
        json=cost_request(),
        headers={"Idempotency-Key": "cost-analysis-request-001"},
    )
    loaded = manager_client.get(f"{BASE}/cost-analyses/COST-ANALYSIS-1")
    listed = manager_client.get(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses"
    )

    assert created.status_code == 200
    assert loaded.status_code == 200
    assert listed.status_code == 200
    assert [name for name, _ in manager_service.calls] == [
        "cost_calculate",
        "cost_get",
        "cost_list",
    ]
    assert manager_service.calls[0][1]["actor_id"] == "user-process_manager"
    assert "asset_id" not in created.request.content.decode("utf-8")


def test_reader_lists_candidates_and_manager_can_request_cooling_cost() -> None:
    manager_client, manager_service = client_for("process_manager")
    candidates = manager_client.get(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/action-candidates"
    )
    payload = cost_request("COOLING_SYSTEM_RESTORE")
    created = manager_client.post(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses",
        json=payload,
        headers={"Idempotency-Key": "cooling-cost-analysis-request-001"},
    )

    assert candidates.status_code == 200
    assert created.status_code == 200
    assert [name for name, _ in manager_service.calls] == [
        "action_candidates",
        "cost_calculate",
    ]
    assert manager_service.calls[1][1]["payload"].action_code == (
        "COOLING_SYSTEM_RESTORE"
    )


def test_cost_analysis_request_rejects_forged_lineage_and_wrong_role() -> None:
    manager_client, manager_service = client_for("process_manager")
    forged = manager_client.post(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses",
        json={
            **cost_request(),
            "asset_id": "FORGED-ASSET",
            "equipment_id": "FORGED-EQUIPMENT",
            "action_candidate_id": "FORGED-CANDIDATE",
        },
        headers={"Idempotency-Key": "cost-analysis-request-001"},
    )
    missing_key = manager_client.post(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses",
        json=cost_request(),
    )
    engineer_client, engineer_service = client_for("process_engineer")
    denied = engineer_client.post(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses",
        json=cost_request(),
        headers={"Idempotency-Key": "cost-analysis-request-001"},
    )

    assert forged.status_code == 422
    assert missing_key.status_code == 422
    assert denied.status_code == 403
    assert manager_service.calls == []
    assert engineer_service.calls == []


def test_cooling_cost_request_rejects_client_owned_economic_inputs() -> None:
    manager_client, manager_service = client_for("process_manager")
    response = manager_client.post(
        f"{BASE}/inspection-results/INSPECTION-RESULT-1/cost-analyses",
        json={
            **cost_request("COOLING_SYSTEM_RESTORE"),
            "currency": "KRW",
            "price_version": "forged-client-price",
        },
        headers={"Idempotency-Key": "cooling-forged-economic-input-001"},
    )

    assert response.status_code == 422
    assert manager_service.calls == []


def test_cost_analysis_is_read_only_and_exposes_no_recommendation_command() -> None:
    manager_client, manager_service = client_for("process_manager")
    response = manager_client.post(
        f"{BASE}/cost-analyses/COST-ANALYSIS-1/options/COST-OPTION-1/recommendations",
        json={"basis": ["must not create a recommendation"]},
        headers={"Idempotency-Key": "cost-option-recommendation-001"},
    )

    assert response.status_code == 404
    assert manager_service.calls == []
