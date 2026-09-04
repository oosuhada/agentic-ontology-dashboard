from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.infra.db.maintenance_repository import MaintenanceRepository
from app.maintenance.api_schema import (
    InspectionResultCreateRequest,
    InspectionWorkOrderCreateRequest,
    MaintenanceActionCompleteRequest,
    MaintenanceActionStartRequest,
    MaintenanceCostAnalysisCreateRequest,
    MaintenanceReplayRequest,
    MaintenanceWorkOrderApproveRequest,
    OperationsManualRecommendationCreateRequest,
    RecommendationInput,
    RecommendationDecisionCreateRequest,
    ToolReplacementCostAnalysisCreateRequest,
)
from app.maintenance.cost_analysis_schema import ExecutionTiming
from app.maintenance.cost_basis import (
    CoolingSystemRestoreCostBasis,
    CostBasisResolutionContext,
    ToolReplacementCostBasis,
)
from app.maintenance.maintenance_domain import IdempotencyConflict
from app.maintenance.maintenance_schema import RecommendationDisposition, WorkOrderStatus
from app.maintenance.service import MaintenanceLoopService


class Scope:
    organization_id = "org-1"
    project_id = "project-1"
    workspace_id = "workspace-1"


class Resolver:
    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection=None,
    ):
        del connection
        assert workspace_id == Scope.workspace_id
        assert expected_organization_id in {None, Scope.organization_id}
        assert expected_project_id in {None, Scope.project_id}
        return Scope()


class ProjectionQuery:
    def __init__(
        self,
        projection: dict | None = None,
        *,
        replay_binding: dict | None = None,
        replay_error: ValueError | None = None,
        source_binding: dict | None = None,
    ) -> None:
        self.projection = projection if projection is not None else canonical_projection()
        self.calls: list[dict] = []
        self.replay_binding = replay_binding
        self.replay_error = replay_error
        self.source_binding = source_binding
        self.replay_calls: list[dict] = []
        self.source_session_calls: list[dict] = []

    def event_evidence_projection(self, **scope):
        self.calls.append(scope)
        return self.projection

    def resolve_maintenance_replay_session(self, **values):
        self.replay_calls.append(values)
        if self.replay_error is not None:
            raise self.replay_error
        if self.replay_binding is not None:
            return self.replay_binding
        return {
            "simulation_session_id": values["session_id"],
            "organization_id": values["organization_id"],
            "project_id": values["project_id"],
            "workspace_id": values["workspace_id"],
            "equipment_id": values["equipment_id"],
        }

    def resolve_maintenance_source_session(self, **values):
        self.source_session_calls.append(values)
        if self.replay_error is not None:
            raise self.replay_error
        return self.source_binding


class SequencedProjectionQuery(ProjectionQuery):
    def __init__(self, projections: list[dict | None]) -> None:
        super().__init__(projections[0] if projections else None)
        self.projections = list(projections)

    def event_evidence_projection(self, **scope):
        self.calls.append(scope)
        if len(self.calls) <= len(self.projections):
            return self.projections[len(self.calls) - 1]
        return self.projections[-1] if self.projections else None


def canonical_projection(
    *,
    event_id: str = "EVT-RESULT-001",
    asset_id: str = "CNC-001",
    asset_type: str = "cnc",
    artifact_id: str = "RESULT-001",
    observed_at: str = "2026-08-01T00:00:00+09:00",
    model_version: str = "fixture-heuristic-v1",
    dataset_version: str = "fixture-compatibility",
    source_sha256: str | None = None,
    decision: str | None = "review_shutdown",
) -> dict:
    actions = [] if decision is None else [{"action_id": decision, "basis": ["factor.1"]}]
    return {
        "schema_version": "event-evidence-projection-v1",
        "contract_type": "event_evidence_projection",
        "event_id": event_id,
        "evidence_id": f"EVD-{event_id}",
        "subject": {
            "equipment_id": asset_id,
            "asset_type": asset_type,
        },
        "artifact_reference": {
            "event_id": event_id,
            "artifact_id": artifact_id,
            "artifact_schema_version": "result-artifact-v1.0",
            "asset_id": asset_id,
            "asset_type": asset_type,
            "observed_at": observed_at,
            "evidence_payload_reference": artifact_id,
            "source_sha256": source_sha256,
        },
        "assessment": {"operational_decision_kind": decision},
        "report_projection": {"recommended_actions": actions},
        "provenance": {
            "model_version": model_version,
            "dataset_version": dataset_version,
            "lineage": {"policy_version": "recommendation-policy-v1"},
        },
    }


def snapshot_basis(projection: dict) -> dict:
    artifact = projection["artifact_reference"]
    provenance = projection["provenance"]
    return {
        "artifact_id": artifact.get("artifact_id"),
        "evidence_payload_reference": artifact.get("evidence_payload_reference"),
        "asset_id": artifact.get("asset_id"),
        "event_id": projection.get("event_id"),
        "observed_at": artifact.get("observed_at"),
        "model_version": provenance.get("model_version"),
        "dataset_version": provenance.get("dataset_version"),
        "source_sha256": artifact.get("source_sha256"),
    }


class StaticCostBasisProvider:
    def __init__(self, basis: ToolReplacementCostBasis) -> None:
        self.basis = basis

    def tool_replacement_basis(
        self,
        *,
        calculated_at: datetime,
        context: CostBasisResolutionContext,
    ) -> ToolReplacementCostBasis:
        del calculated_at, context
        return self.basis

    def cooling_system_restore_basis(
        self,
        *,
        calculated_at: datetime,
        context: CostBasisResolutionContext,
    ) -> CoolingSystemRestoreCostBasis:
        del calculated_at, context
        return CoolingSystemRestoreCostBasis.model_validate(self.basis.model_dump())


def recommendation_input_schema() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "schemas"
        / "recommendation-input.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def tool_replacement_cost_basis(
    *, missing_parts_cost: bool = False
) -> ToolReplacementCostBasis:
    scenarios = []
    for timing in ExecutionTiming:
        scenarios.append(
            {
                "execution_timing": timing,
                "parts_cost": (
                    None
                    if missing_parts_cost
                    else {"low_minor": 45000, "base_minor": 50000, "high_minor": 60000}
                ),
                "labor_duration": {"low_minutes": 20, "base_minutes": 30, "high_minutes": 40},
                "labor_rate_per_minute": {
                    "low_minor_per_minute": 800,
                    "base_minor_per_minute": 1000,
                    "high_minor_per_minute": 1200,
                },
                "external_service_cost": {"low_minor": 0, "base_minor": 0, "high_minor": 0},
                "expected_downtime": {"low_minutes": 30, "base_minutes": 45, "high_minutes": 60},
                "production_loss_rate_per_minute": {
                    "low_minor_per_minute": 900,
                    "base_minor_per_minute": 1100,
                    "high_minor_per_minute": 1300,
                },
                "expected_failure_loss": {"low_minor": 10000, "base_minor": 25000, "high_minor": 50000},
                "confidence": "medium",
            }
        )
    return ToolReplacementCostBasis(
        currency="KRW",
        currency_minor_unit=0,
        scenarios=tuple(scenarios),
        assumptions=("Failure loss is a sensitivity input.",),
        input_sources=(
            {
                "input_name": "tool_replacement_quote",
                "source_kind": "quoted",
                "source_reference": "quote/tool-replacement/2026-08",
                "confidence": "medium",
            },
        ),
        price_version="maintenance-price-2026-08",
        calculation_policy_version="maintenance-cost-policy-v1",
    )


def service(
    tmp_path,
    *,
    query: ProjectionQuery | None = None,
    cost_basis: ToolReplacementCostBasis | None = None,
) -> MaintenanceLoopService:
    provider = query or ProjectionQuery()
    return MaintenanceLoopService(
        MaintenanceRepository(tmp_path / "maintenance.db", project_context=Resolver()),
        event_evidence_query=provider,
        replay_session_query=provider,
        cost_basis_provider=StaticCostBasisProvider(
            cost_basis or tool_replacement_cost_basis()
        ),
    )


def inspection_request(
    projection: dict | None = None,
) -> InspectionWorkOrderCreateRequest:
    projection = projection or canonical_projection()
    return InspectionWorkOrderCreateRequest(
        event_id="EVT-RESULT-001",
        snapshot_basis=snapshot_basis(projection),
    )


def inspection_result(outcome: str = "maintenance_recommended") -> InspectionResultCreateRequest:
    return InspectionResultCreateRequest(
        outcome=outcome,
        checklist=(
            {"item_id": "tool-wear", "status": "fail", "note": "limit exceeded"},
            {"item_id": "cost-basis-in-house", "status": "pass", "note": ""},
            {
                "item_id": "cost-basis-spare-part-available",
                "status": "pass",
                "note": "",
            },
            {
                "item_id": "cost-basis-vendor-dispatch-required",
                "status": "fail",
                "note": "",
            },
        ),
        measurements=(
            {"name": "tool_wear_min", "value": 221, "unit": "min"},
        ),
        findings=("tool wear limit exceeded",),
        note="tool replacement should be reviewed",
    )


def cost_analysis_request() -> ToolReplacementCostAnalysisCreateRequest:
    return ToolReplacementCostAnalysisCreateRequest(
        sop_id="SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
        sop_version="demo-2026-08-28",
    )


def cooling_cost_analysis_request() -> MaintenanceCostAnalysisCreateRequest:
    return MaintenanceCostAnalysisCreateRequest(
        action_code="COOLING_SYSTEM_RESTORE",
        sop_id="SOP-DEMO-COOLING-SYSTEM-001",
        sop_version="demo-2026-08-31",
    )


def cooling_cost_applicability_checklist() -> tuple[dict[str, str], ...]:
    return (
        {"item_id": "cost-basis-in-house", "status": "pass", "note": ""},
        {
            "item_id": "cost-basis-vendor-dispatch-required",
            "status": "fail",
            "note": "",
        },
        {
            "item_id": "cost-basis-component-replacement-required",
            "status": "fail",
            "note": "",
        },
    )


def run_completed_inspection(
    loop: MaintenanceLoopService,
    *,
    outcome: str = "maintenance_recommended",
    result_payload: InspectionResultCreateRequest | None = None,
) -> tuple[str, str]:
    requested = loop.request_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        payload=inspection_request(),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="inspection-request-001",
    )
    work_order_id = requested["work_order_id"]
    loop.transition_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        target=WorkOrderStatus.APPROVED,
        actor_id="engineer-1",
        actor_display_name="Engineer One",
        idempotency_key="inspection-accept-001",
    )
    loop.transition_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        target=WorkOrderStatus.IN_PROGRESS,
        actor_id="engineer-1",
        actor_display_name="Engineer One",
        idempotency_key="inspection-start-001",
    )
    completed = loop.complete_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        payload=result_payload or inspection_result(outcome),
        actor_id="engineer-1",
        actor_display_name="Engineer One",
        idempotency_key="inspection-complete-001",
    )
    assert completed["maintenance_event_id"] is None
    return work_order_id, completed["inspection_result_id"]


def run_requested_maintenance(loop: MaintenanceLoopService) -> str:
    _inspection_work_order_id, inspection_result_id = run_completed_inspection(loop)
    created = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=OperationsManualRecommendationCreateRequest(
            basis=("field engineer confirmed tool wear",)
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-recommendation-001",
    )
    decided = loop.decide_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        recommendation_id=created["recommendation_id"],
        payload=RecommendationDecisionCreateRequest(
            disposition=RecommendationDisposition.ACCEPT,
            note="approve tool replacement",
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-decision-accept-001",
    )
    assert decided["work_order_id"] is not None
    return decided["work_order_id"]


def test_two_stage_inspection_to_maintenance_work_order_lineage(tmp_path) -> None:
    loop = service(tmp_path)
    inspection_work_order_id, inspection_result_id = run_completed_inspection(loop)
    inspection_work_order = loop.repository.get_work_order(
        workspace_id="workspace-1",
        work_order_id=inspection_work_order_id,
    )
    assert inspection_work_order is not None
    assert inspection_work_order.authorization.model_dump(mode="json") == {
        "work_type": "inspection",
        "recommendation_id": None,
        "recommendation_decision_id": None,
        "recommendation_status": None,
        "recommendation_disposition": None,
        "operational_decision": "review_shutdown",
        "source_product_result_id": "RESULT-001",
        "source_evidence_id": "EVD-EVT-RESULT-001",
        "source_action_id": "review_shutdown",
        "source_schema_version": "result-artifact-v1.0",
        "source_policy_version": "recommendation-policy-v1",
    }

    created = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=OperationsManualRecommendationCreateRequest(
            basis=("field engineer confirmed tool wear",)
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-recommendation-001",
    )
    recommendation_id = created["recommendation_id"]
    assert created["recommendation"]["recommendation_origin"] == "operations_manual"
    assert created["recommendation"]["source_product_result_id"] == "RESULT-001"
    assert created["recommendation"]["source_inspection_reference"] == inspection_result_id
    assert created["recommendation"]["asset_type"] == "cnc"

    decided = loop.decide_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        recommendation_id=recommendation_id,
        payload=RecommendationDecisionCreateRequest(
            disposition=RecommendationDisposition.ACCEPT,
            note="approve tool replacement",
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-decision-accept-001",
    )
    assert decided["work_order_id"] is not None

    lineage = loop.event_lineage(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )
    assert [item["work_type"] for item in lineage["work_orders"]] == [
        "inspection",
        "maintenance",
    ]
    assert lineage["inspection_results"][0]["work_order_id"] == inspection_work_order_id
    assert lineage["recommendations"][0]["source_product_result_id"] == "RESULT-001"
    assert lineage["decisions"][0]["recommendation_id"] == recommendation_id
    work_order_activities = [
        item for item in lineage["activities"] if item["work_order_id"] is not None
    ]
    assert {item["work_type"] for item in work_order_activities} == {
        "inspection",
        "maintenance",
    }
    assert lineage["maintenance_actions"] == []
    assert lineage["maintenance_events"] == []


def test_maintenance_execution_uses_persisted_lineage_and_emits_replay_events(tmp_path) -> None:
    diagnosis = ProjectionQuery()
    loop = service(tmp_path, query=diagnosis)
    work_order_id = run_requested_maintenance(loop)
    started_at = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=30)
    restart_at = completed_at + timedelta(minutes=5)

    approved = loop.approve_maintenance_work_order(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        payload=MaintenanceWorkOrderApproveRequest(
            simulation_session_id="SIMULATION-SESSION-001"
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="maintenance-approve-001",
        approved_at=started_at - timedelta(minutes=5),
    )
    action_id = approved["maintenance_action_id"]
    assert approved["maintenance_action_status"] == "planned"
    assert diagnosis.replay_calls == [
        {
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "session_id": "SIMULATION-SESSION-001",
            "equipment_id": "CNC-001",
        }
    ]

    started = loop.start_maintenance(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        maintenance_action_id=action_id,
        payload=MaintenanceActionStartRequest(),
        actor_id="technician-1",
        actor_display_name="Technician One",
        idempotency_key="maintenance-start-001",
        started_at=started_at,
    )
    completed = loop.complete_maintenance(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        maintenance_action_id=action_id,
        payload=MaintenanceActionCompleteRequest(outcome="tool replaced"),
        actor_id="technician-1",
        actor_display_name="Technician One",
        idempotency_key="maintenance-complete-001",
        completed_at=completed_at,
    )
    replay = loop.request_maintenance_replay(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        maintenance_event_id=completed["maintenance_event_id"],
        payload=MaintenanceReplayRequest(restart_at=restart_at),
        actor_id="technician-1",
        actor_display_name="Technician One",
        idempotency_key="maintenance-replay-001",
    )

    assert started["status"] == "in_progress"
    assert completed["status"] == "completed"
    assert replay["status"] == "replay_requested"

    lineage = loop.event_lineage(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )
    assert len(lineage["maintenance_actions"]) == 1
    assert lineage["maintenance_actions"][0]["simulation_session_id"] == (
        "SIMULATION-SESSION-001"
    )
    assert lineage["maintenance_actions"][0]["lifecycle_state_version"] == 3
    assert len(lineage["maintenance_events"]) == 1
    assert lineage["maintenance_events"][0]["state_patch"] == {
        "tool_wear_min": {"operation": "reset", "unit": "min", "value": 0}
    }
    equipment_state = loop.repository.equipment_state(
        workspace_id="workspace-1",
        equipment_id="CNC-001",
    )
    assert equipment_state is not None
    assert equipment_state["state"] == {
        "tool_wear_min": {"unit": "min", "value": 0}
    }

    with loop.repository._connect() as connection:
        outbox = connection.execute(
            "SELECT id,event_type,payload_json FROM transactional_outbox "
            "WHERE event_type LIKE 'maintenance.%' ORDER BY id"
        ).fetchall()
    assert all(str(uuid.UUID(row["id"])) == row["id"] for row in outbox)
    assert {
        row["event_type"]: json.loads(row["payload_json"])["state_version"]
        for row in outbox
    } == {
        "maintenance.started": 1,
        "maintenance.completed": 2,
        "maintenance.replay_requested": 3,
    }
    assert all("SIMULATION-SESSION-001" in row["payload_json"] for row in outbox)


def test_live_maintenance_approval_uses_authorized_product_result_source_session(
    tmp_path,
) -> None:
    diagnosis = ProjectionQuery(
        source_binding={
            "simulation_session_id": "SOURCE-SIMULATION-SESSION-001",
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "equipment_id": "CNC-001",
        }
    )
    loop = service(tmp_path, query=diagnosis)
    work_order_id = run_requested_maintenance(loop)

    approved = loop.approve_maintenance_work_order(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        payload=MaintenanceWorkOrderApproveRequest(),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="maintenance-source-session-approve-001",
    )

    assert approved["maintenance_action_status"] == "planned"
    assert diagnosis.replay_calls == []
    assert diagnosis.source_session_calls == [
        {
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "source_product_result_id": "RESULT-001",
            "equipment_id": "CNC-001",
        }
    ]
    lineage = loop.event_lineage(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )
    assert lineage["maintenance_actions"][0]["simulation_session_id"] == (
        "SOURCE-SIMULATION-SESSION-001"
    )


def test_live_maintenance_approval_rejects_caller_session_override(tmp_path) -> None:
    diagnosis = ProjectionQuery(
        source_binding={
            "simulation_session_id": "SOURCE-SIMULATION-SESSION-001",
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "equipment_id": "CNC-001",
        }
    )
    loop = service(tmp_path, query=diagnosis)
    work_order_id = run_requested_maintenance(loop)

    with pytest.raises(ValueError, match="canonical identity mismatch"):
        loop.approve_maintenance_work_order(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            work_order_id=work_order_id,
            payload=MaintenanceWorkOrderApproveRequest(
                simulation_session_id="CALLER-OVERRIDE-SESSION"
            ),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="maintenance-source-session-conflict-001",
        )


def test_maintenance_approval_fails_closed_when_diagnosis_rejects_replay(tmp_path) -> None:
    diagnosis = ProjectionQuery(
        replay_error=ValueError("replay session is not available in the requested scope")
    )
    loop = service(tmp_path, query=diagnosis)
    work_order_id = run_requested_maintenance(loop)

    with pytest.raises(ValueError, match="not available in the requested scope"):
        loop.approve_maintenance_work_order(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            work_order_id=work_order_id,
            payload=MaintenanceWorkOrderApproveRequest(
                simulation_session_id="FORGED-SESSION"
            ),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="maintenance-approve-rejected-001",
        )

    lineage = loop.event_lineage(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )
    assert lineage["maintenance_actions"] == []


def test_maintenance_approval_fails_closed_until_diagnosis_provider_is_wired(
    tmp_path,
) -> None:
    loop = MaintenanceLoopService(
        MaintenanceRepository(tmp_path / "maintenance.db", project_context=Resolver()),
        event_evidence_query=ProjectionQuery(),
    )
    work_order_id = run_requested_maintenance(loop)

    with pytest.raises(ValueError, match="validation is unavailable"):
        loop.approve_maintenance_work_order(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            work_order_id=work_order_id,
            payload=MaintenanceWorkOrderApproveRequest(
                simulation_session_id="SIMULATION-SESSION-001"
            ),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="maintenance-approve-provider-missing-001",
        )

    assert loop.repository.operational_side_effect_counts()["maintenance_actions"] == 0


@pytest.mark.parametrize(
    ("field", "invalid_value", "message"),
    (
        ("project_id", "another-project", "project_id scope mismatch"),
        ("equipment_id", "CNC-999", "equipment identity mismatch"),
        (
            "simulation_session_id",
            "ANOTHER-SESSION",
            "canonical identity mismatch",
        ),
    ),
)
def test_maintenance_approval_rejects_noncanonical_replay_binding(
    tmp_path, field: str, invalid_value: str, message: str
) -> None:
    binding = {
        "simulation_session_id": "SIMULATION-SESSION-001",
        "organization_id": "org-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "equipment_id": "CNC-001",
    }
    binding[field] = invalid_value
    loop = service(tmp_path, query=ProjectionQuery(replay_binding=binding))
    work_order_id = run_requested_maintenance(loop)

    with pytest.raises(ValueError, match=message):
        loop.approve_maintenance_work_order(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            work_order_id=work_order_id,
            payload=MaintenanceWorkOrderApproveRequest(
                simulation_session_id="SIMULATION-SESSION-001"
            ),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key=f"maintenance-approve-{field}-001",
        )


def test_maintenance_execution_commands_are_idempotent(tmp_path) -> None:
    loop = service(tmp_path)
    work_order_id = run_requested_maintenance(loop)
    approve_payload = MaintenanceWorkOrderApproveRequest(
        simulation_session_id="SIMULATION-SESSION-001"
    )
    command = {
        "organization_id": "org-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "work_order_id": work_order_id,
        "payload": approve_payload,
        "actor_id": "manager-1",
        "actor_display_name": "Manager One",
        "idempotency_key": "maintenance-approve-001",
    }
    first = loop.approve_maintenance_work_order(**command)
    second = loop.approve_maintenance_work_order(**command)

    assert second["maintenance_action_id"] == first["maintenance_action_id"]
    assert second["replayed"] is True
    assert loop.repository.operational_side_effect_counts()["maintenance_actions"] == 1

    with pytest.raises(IdempotencyConflict):
        loop.approve_maintenance_work_order(
            **{
                **command,
                "payload": MaintenanceWorkOrderApproveRequest(
                    simulation_session_id="ANOTHER-SIMULATION-SESSION"
                ),
            }
        )


def test_manual_recommendation_replay_dedupe_and_conflict(tmp_path) -> None:
    loop = service(tmp_path)
    _work_order_id, inspection_result_id = run_completed_inspection(loop)
    payload = OperationsManualRecommendationCreateRequest(basis=("replace worn tool",))

    first = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=payload,
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-recommendation-001",
    )
    replay = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=payload,
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-recommendation-001",
    )
    duplicate = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=payload,
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-recommendation-002",
    )

    assert replay["recommendation_id"] == first["recommendation_id"]
    assert replay["replayed"] is True
    assert duplicate["recommendation_id"] == first["recommendation_id"]
    assert duplicate["deduplicated"] is True
    assert loop.repository.operational_side_effect_counts()["recommendations"] == 1

    try:
        loop.create_manual_recommendation(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            inspection_result_id=inspection_result_id,
            payload=OperationsManualRecommendationCreateRequest(
                basis=("different command body",)
            ),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="manual-recommendation-001",
        )
    except IdempotencyConflict:
        pass
    else:
        raise AssertionError("reusing an idempotency key with another body must conflict")


def test_manual_recommendation_request_rejects_incomplete_cost_reference() -> None:
    with pytest.raises(ValidationError, match="cost_analysis_id and action_candidate_id"):
        OperationsManualRecommendationCreateRequest(
            basis=("replace worn tool",),
            cost_analysis_id="cost-analysis-001",
        )


def test_no_action_inspection_cannot_create_maintenance_recommendation(tmp_path) -> None:
    loop = service(tmp_path)
    requested = loop.request_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        payload=inspection_request(),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="inspection-request-001",
    )
    work_order_id = requested["work_order_id"]
    for target, actor, key in (
            (WorkOrderStatus.APPROVED, "engineer-1", "inspection-accept-001"),
        (WorkOrderStatus.IN_PROGRESS, "engineer-1", "inspection-start-001"),
    ):
        loop.transition_inspection(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            work_order_id=work_order_id,
            target=target,
            actor_id=actor,
            actor_display_name=actor,
            idempotency_key=key,
        )
    completed = loop.complete_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        payload=inspection_result("no_action_required"),
        actor_id="engineer-1",
        actor_display_name="Engineer One",
        idempotency_key="inspection-complete-001",
    )

    try:
        loop.create_manual_recommendation(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            inspection_result_id=completed["inspection_result_id"],
            payload=OperationsManualRecommendationCreateRequest(basis=("replace",)),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="manual-recommendation-001",
        )
    except ValueError as exc:
        assert "maintenance_recommended" in str(exc)
    else:
        raise AssertionError("no_action_required must not create maintenance work")


def test_inspection_request_fails_closed_for_unknown_or_mismatched_projection(tmp_path) -> None:
    missing = service(tmp_path / "missing", query=ProjectionQuery(None))
    missing.event_evidence_query.projection = None
    with pytest.raises(KeyError, match="EVT-RESULT-001"):
        missing.request_inspection(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            payload=inspection_request(),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="inspection-request-001",
        )

    mismatched = service(
        tmp_path / "mismatch",
        query=ProjectionQuery(canonical_projection(event_id="EVT-OTHER")),
    )
    with pytest.raises(ValueError, match="event_id mismatch"):
        mismatched.request_inspection(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            payload=inspection_request(),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="inspection-request-001",
        )


def test_recommendation_input_is_projected_from_event_evidence_only(tmp_path) -> None:
    projection = canonical_projection(
        event_id="EVT-RESULT-001",
        asset_id="CNC-RECOMMENDATION-001",
        asset_type="cnc",
        artifact_id="RESULT-RECOMMENDATION-001",
        source_sha256="a" * 64,
        decision="request_inspection",
    )
    query = ProjectionQuery(projection)
    loop = service(tmp_path, query=query)

    recommendation_input = loop.recommendation_input(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )

    assert RecommendationInput.model_validate(recommendation_input)
    assert (
        list(
            Draft202012Validator(recommendation_input_schema()).iter_errors(
                recommendation_input
            )
        )
        == []
    )
    assert recommendation_input["snapshot_basis"] == snapshot_basis(projection)
    assert recommendation_input["equipment"] == {
        "organization_id": "org-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "asset_id": "CNC-RECOMMENDATION-001",
        "equipment_id": "CNC-RECOMMENDATION-001",
        "asset_type": "cnc",
    }
    assert recommendation_input["operational_decision_kind"] == "request_inspection"
    assert recommendation_input["source_context"] == {
        "source_product_result_id": "RESULT-RECOMMENDATION-001",
        "source_evidence_id": "EVD-EVT-RESULT-001",
        "source_action_id": "request_inspection",
        "source_schema_version": "result-artifact-v1.0",
        "source_policy_version": "recommendation-policy-v1",
    }
    assert "risk" not in recommendation_input
    assert "review_draft" not in recommendation_input
    assert "maintenance_history_summary" not in recommendation_input


def test_inspection_request_rejects_stale_client_snapshot_basis(tmp_path) -> None:
    query = ProjectionQuery(
        canonical_projection(artifact_id="RESULT-OLD")
    )
    loop = service(tmp_path, query=query)
    user_seen_basis = snapshot_basis(query.projection)

    query.projection = canonical_projection(artifact_id="RESULT-NEW")
    with pytest.raises(ValueError, match="snapshot_basis mismatch: artifact_id"):
        loop.request_inspection(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            payload=InspectionWorkOrderCreateRequest(
                event_id="EVT-RESULT-001",
                snapshot_basis=user_seen_basis,
            ),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="inspection-request-001",
        )

    assert loop.repository.operational_side_effect_counts()["work_orders"] == 0
    assert query.calls == [
        {
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "event_id": "EVT-RESULT-001",
        },
        {
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "event_id": "EVT-RESULT-001",
        }
    ]


def test_inspection_request_requires_snapshot_basis_precondition() -> None:
    with pytest.raises(ValidationError, match="snapshot_basis"):
        InspectionWorkOrderCreateRequest(event_id="EVT-RESULT-001")


def test_inspection_request_rejects_empty_snapshot_basis_identity() -> None:
    with pytest.raises(ValidationError, match="snapshot_basis requires identity fields"):
        InspectionWorkOrderCreateRequest(
            event_id="EVT-RESULT-001",
            snapshot_basis={},
        )


def test_inspection_request_retries_once_for_transient_stale_projection(tmp_path) -> None:
    current = canonical_projection(artifact_id="RESULT-CURRENT")
    stale = canonical_projection(artifact_id="RESULT-STALE")
    query = SequencedProjectionQuery([stale, current])
    loop = service(tmp_path, query=query)

    requested = loop.request_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        payload=InspectionWorkOrderCreateRequest(
            event_id="EVT-RESULT-001",
            snapshot_basis=snapshot_basis(current),
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="inspection-request-001",
    )

    work_order = loop.repository.get_work_order(
        workspace_id="workspace-1",
        work_order_id=requested["work_order_id"],
    )
    assert work_order is not None
    assert work_order.authorization.source_product_result_id == "RESULT-CURRENT"
    assert loop.repository.operational_side_effect_counts()["work_orders"] == 1
    assert len(query.calls) == 2


def test_inspection_request_accepts_matching_client_snapshot_basis(tmp_path) -> None:
    projection = canonical_projection()
    query = ProjectionQuery(projection)
    loop = service(tmp_path, query=query)

    requested = loop.request_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        payload=InspectionWorkOrderCreateRequest(
            event_id="EVT-RESULT-001",
            snapshot_basis=snapshot_basis(projection),
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="inspection-request-001",
    )

    work_order = loop.repository.get_work_order(
        workspace_id="workspace-1",
        work_order_id=requested["work_order_id"],
    )
    assert work_order is not None
    assert work_order.authorization.source_product_result_id == "RESULT-001"


def test_inspection_request_rejects_non_authorizing_canonical_decision(tmp_path) -> None:
    loop = service(
        tmp_path,
        query=ProjectionQuery(canonical_projection(decision="continue_monitoring")),
    )
    with pytest.raises(ValueError, match="does not authorize an inspection"):
        loop.request_inspection(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            payload=inspection_request(),
            actor_id="manager-1",
            actor_display_name="Manager One",
            idempotency_key="inspection-request-001",
        )


def test_asset_type_is_preserved_from_projection_through_inspection(tmp_path) -> None:
    projection = canonical_projection(asset_id="CMP-001", asset_type="compressor")
    query = ProjectionQuery(projection)
    loop = service(
        tmp_path,
        query=query,
    )
    requested = loop.request_inspection(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        payload=inspection_request(projection),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="inspection-request-001",
    )
    stored = loop.repository.get_work_order(
        workspace_id="workspace-1",
        work_order_id=requested["work_order_id"],
    )
    assert stored is not None
    assert stored.asset_type == "compressor"
    assert query.calls == [
        {
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "event_id": "EVT-RESULT-001",
        }
    ]


def test_cost_analysis_resolves_lineage_and_persists_read_only_snapshot(tmp_path) -> None:
    loop = service(tmp_path)
    inspection_work_order_id, inspection_result_id = run_completed_inspection(loop)
    calculated_at = datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)

    created = loop.calculate_tool_replacement_cost(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=cost_analysis_request(),
        actor_id="manager-1",
        idempotency_key="cost-analysis-request-001",
        calculated_at=calculated_at,
    )

    result = created["cost_analysis"]
    assert created["calculation_status"] == "calculated"
    assert created["replayed"] is False
    assert result["asset_id"] == result["equipment_id"] == "CNC-001"
    assert result["based_on"] == {
        "product_result_id": "RESULT-001",
        "evidence_id": "EVD-EVT-RESULT-001",
        "inspection_work_order_id": inspection_work_order_id,
        "inspection_result_id": inspection_result_id,
        "sop_id": "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
        "sop_version": "demo-2026-08-28",
    }
    assert {
        option["action_candidate_id"] for option in result["options"]
    } == {
        loop._stable_id(
            "ACTION-CANDIDATE",
            "org-1",
            "project-1",
            "workspace-1",
            inspection_result_id,
            "TOOL_REPLACEMENT",
        )
    }

    loaded = loop.get_cost_analysis(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        analysis_id=created["analysis_id"],
    )
    listed = loop.list_cost_analyses(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
    )
    assert loaded == result
    assert listed == {
        "inspection_result_id": inspection_result_id,
        "items": [result],
    }
    lineage = loop.event_lineage(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )
    assert lineage["cost_analyses"] == [result]
    side_effects = loop.repository.operational_side_effect_counts()
    assert side_effects["recommendations"] == 0
    assert side_effects["decisions"] == 0
    assert side_effects["maintenance_actions"] == 0
    assert side_effects["maintenance_events"] == 0

    with sqlite3.connect(loop.repository.database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE closed_loop_maintenance_cost_analyses "
                "SET result_json='{}' WHERE analysis_id=?",
                (created["analysis_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM closed_loop_maintenance_cost_analyses WHERE analysis_id=?",
                (created["analysis_id"],),
            )

    assert loop.get_cost_analysis(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        analysis_id=created["analysis_id"],
    ) == result


def test_manual_recommendation_preserves_consulted_analysis_without_selecting_option(
    tmp_path,
) -> None:
    loop = service(tmp_path)
    _work_order_id, inspection_result_id = run_completed_inspection(loop)
    created = loop.calculate_tool_replacement_cost(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=cost_analysis_request(),
        actor_id="manager-1",
        idempotency_key="cost-analysis-reference-001",
    )
    result = created["cost_analysis"]
    action_candidate_id = result["options"][0]["action_candidate_id"]

    recommendation = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=OperationsManualRecommendationCreateRequest(
            basis=("manager reviewed cost analysis",),
            cost_analysis_id=created["analysis_id"],
            action_candidate_id=action_candidate_id,
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="manual-recommendation-with-cost-reference-001",
    )["recommendation"]

    assert recommendation["source_cost_analysis_id"] == created["analysis_id"]
    assert recommendation["source_action_candidate_id"] == action_candidate_id
    assert recommendation["source_cost_option_id"] is None
    assert recommendation["status"] == "proposed"


def test_cost_analysis_is_idempotent_but_new_request_appends_snapshot(tmp_path) -> None:
    loop = service(tmp_path)
    _work_order_id, inspection_result_id = run_completed_inspection(loop)
    payload = cost_analysis_request()
    command = {
        "organization_id": "org-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "inspection_result_id": inspection_result_id,
        "payload": payload,
        "actor_id": "manager-1",
        "idempotency_key": "cost-analysis-request-001",
        "calculated_at": datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc),
    }

    first = loop.calculate_tool_replacement_cost(**command)
    replay = loop.calculate_tool_replacement_cost(**command)
    second_snapshot = loop.calculate_tool_replacement_cost(
        **{
            **command,
            "idempotency_key": "cost-analysis-request-002",
            "calculated_at": datetime(2026, 8, 31, 1, 5, tzinfo=timezone.utc),
        }
    )

    assert replay == {**first, "replayed": True}
    assert second_snapshot["analysis_id"] != first["analysis_id"]
    assert len(
        loop.repository.list_cost_analyses(
            workspace_id="workspace-1",
            inspection_result_id=inspection_result_id,
        )
    ) == 2

    with pytest.raises(IdempotencyConflict, match="idempotency_key_conflict"):
        loop.calculate_tool_replacement_cost(
            **{
                **command,
                "payload": payload.model_copy(
                    update={"sop_version": "demo-2026-09-01"}
                ),
            }
        )


def test_insufficient_cost_analysis_is_preserved_without_operational_effects(
    tmp_path,
) -> None:
    loop = service(
        tmp_path,
        cost_basis=tool_replacement_cost_basis(missing_parts_cost=True),
    )
    _work_order_id, inspection_result_id = run_completed_inspection(loop)

    created = loop.calculate_tool_replacement_cost(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=cost_analysis_request(),
        actor_id="manager-1",
        idempotency_key="cost-analysis-insufficient-001",
    )

    assert created["calculation_status"] == "insufficient"
    assert created["cost_analysis"]["lowest_calculated_cost_option_id"] is None
    assert created["cost_analysis"]["missing_inputs"] == ["parts_cost"]
    assert loop.repository.operational_side_effect_counts()["recommendations"] == 0


def test_cost_analysis_rejects_no_action_inspection_without_persisting(tmp_path) -> None:
    loop = service(tmp_path)
    _work_order_id, inspection_result_id = run_completed_inspection(
        loop,
        outcome="no_action_required",
    )

    with pytest.raises(ValueError, match="maintenance_recommended"):
        loop.calculate_tool_replacement_cost(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            inspection_result_id=inspection_result_id,
            payload=cost_analysis_request(),
            actor_id="manager-1",
            idempotency_key="cost-analysis-request-001",
        )

    assert loop.repository.list_cost_analyses(
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
    ) == ()


def test_cost_analysis_fails_closed_when_applicability_facts_are_missing(
    tmp_path,
) -> None:
    loop = service(tmp_path)
    _work_order_id, inspection_result_id = run_completed_inspection(
        loop,
        result_payload=InspectionResultCreateRequest(
            outcome="maintenance_recommended",
            checklist=(
                {
                    "item_id": "tool-wear",
                    "status": "fail",
                    "note": "limit exceeded",
                },
            ),
            measurements=(
                {"name": "tool_wear_min", "value": 221, "unit": "min"},
            ),
            findings=("tool wear limit exceeded",),
            note="cost-basis applicability was not established",
        ),
    )

    with pytest.raises(ValueError, match="explicit applicability facts"):
        loop.calculate_tool_replacement_cost(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            inspection_result_id=inspection_result_id,
            payload=cost_analysis_request(),
            actor_id="manager-1",
            idempotency_key="cost-analysis-missing-applicability-001",
        )

    assert loop.repository.list_cost_analyses(
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
    ) == ()


def test_cost_analysis_rejects_unrelated_maintenance_candidate_without_persisting(
    tmp_path,
) -> None:
    loop = service(tmp_path)
    _work_order_id, inspection_result_id = run_completed_inspection(
        loop,
        result_payload=InspectionResultCreateRequest(
            outcome="maintenance_recommended",
            checklist=(
                {
                    "item_id": "cooling-path",
                    "status": "fail",
                    "note": "coolant flow is restricted",
                },
                *cooling_cost_applicability_checklist(),
            ),
            measurements=(
                {"name": "coolant_temperature_c", "value": 92, "unit": "C"},
            ),
            findings=("cooling path requires maintenance",),
            note="tool wear was not confirmed",
        ),
    )

    with pytest.raises(ValueError, match="TOOL_REPLACEMENT candidate requires"):
        loop.calculate_tool_replacement_cost(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            inspection_result_id=inspection_result_id,
            payload=cost_analysis_request(),
            actor_id="manager-1",
            idempotency_key="cost-analysis-request-001",
        )

    assert loop.repository.list_cost_analyses(
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
    ) == ()


def test_cooling_action_candidate_and_cost_analysis_are_canonical_and_append_only(
    tmp_path,
) -> None:
    loop = service(tmp_path)
    work_order_id, inspection_result_id = run_completed_inspection(
        loop,
        result_payload=InspectionResultCreateRequest(
            outcome="maintenance_recommended",
            checklist=(
                {
                    "item_id": "cooling-path",
                    "status": "fail",
                    "note": "coolant flow is restricted",
                },
                *cooling_cost_applicability_checklist(),
            ),
            measurements=(
                {"name": "coolant_temperature_c", "value": 92, "unit": "C"},
            ),
            findings=("cooling path requires maintenance",),
            note="cooling system restoration should be reviewed",
        ),
    )

    candidates = loop.list_action_candidates(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
    )
    assert candidates == {
        "inspection_result_id": inspection_result_id,
        "items": [
            {
                "organization_id": "org-1",
                "project_id": "project-1",
                "workspace_id": "workspace-1",
                "action_candidate_id": loop._stable_id(
                    "ACTION-CANDIDATE",
                    "org-1",
                    "project-1",
                    "workspace-1",
                    inspection_result_id,
                    "COOLING_SYSTEM_RESTORE",
                ),
                "inspection_result_id": inspection_result_id,
                "event_id": "EVT-RESULT-001",
                "asset_id": "CNC-001",
                "equipment_id": "CNC-001",
                "action_code": "COOLING_SYSTEM_RESTORE",
                "basis_codes": [
                    "inspection.checklist:cooling-path:fail",
                    "inspection.measurement:coolant_temperature_c",
                ],
            }
        ],
    }

    created = loop.calculate_maintenance_cost(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=cooling_cost_analysis_request(),
        actor_id="manager-1",
        idempotency_key="cooling-cost-analysis-001",
        calculated_at=datetime(2026, 8, 31, 2, 0, tzinfo=timezone.utc),
    )
    result = created["cost_analysis"]
    assert created["calculation_status"] == "calculated"
    assert result["based_on"]["inspection_work_order_id"] == work_order_id
    assert result["based_on"]["inspection_result_id"] == inspection_result_id
    assert {option["action_code"] for option in result["options"]} == {
        "COOLING_SYSTEM_RESTORE"
    }
    assert loop.list_cost_analyses(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
    )["items"] == [result]

    with sqlite3.connect(loop.repository.database) as connection:
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(closed_loop_recommendations)"
        ).fetchall()
        assert any(
            row[2] == "closed_loop_maintenance_cost_analyses" for row in foreign_keys
        )


def test_cooling_vertical_slice_preserves_action_and_typed_overlay_patch(tmp_path) -> None:
    diagnosis = ProjectionQuery()
    loop = service(tmp_path, query=diagnosis)
    _inspection_work_order_id, inspection_result_id = run_completed_inspection(
        loop,
        result_payload=InspectionResultCreateRequest(
            outcome="maintenance_recommended",
            checklist=(
                {
                    "item_id": "cooling-path",
                    "status": "fail",
                    "note": "coolant flow is restricted",
                },
                *cooling_cost_applicability_checklist(),
            ),
            measurements=(
                {"name": "coolant_temperature_c", "value": 92, "unit": "C"},
            ),
            findings=("cooling path requires maintenance",),
            note="cooling system restoration should be reviewed",
        ),
    )
    analysis = loop.calculate_maintenance_cost(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=cooling_cost_analysis_request(),
        actor_id="manager-1",
        idempotency_key="cooling-vertical-cost-001",
    )["cost_analysis"]
    assert analysis["options"]
    assert loop.repository.operational_side_effect_counts()["recommendations"] == 0
    recommendation = loop.create_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id=inspection_result_id,
        payload=OperationsManualRecommendationCreateRequest(
            action_code="COOLING_SYSTEM_RESTORE",
            basis=("inspection result requires cooling restoration",),
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="cooling-vertical-recommendation-001",
    )["recommendation"]
    assert recommendation["action_code"] == "COOLING_SYSTEM_RESTORE"
    assert recommendation["status"] == "proposed"

    decision = loop.decide_manual_recommendation(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        recommendation_id=recommendation["recommendation_id"],
        payload=RecommendationDecisionCreateRequest(
            disposition=RecommendationDisposition.ACCEPT,
            note="approve cooling system restoration",
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="cooling-vertical-decision-001",
    )
    work_order_id = decision["work_order_id"]
    assert work_order_id is not None

    started_at = datetime(2026, 8, 31, 3, 0, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=25)
    restart_at = completed_at + timedelta(minutes=5)
    approved = loop.approve_maintenance_work_order(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        work_order_id=work_order_id,
        payload=MaintenanceWorkOrderApproveRequest(
            simulation_session_id="SIMULATION-SESSION-COOLING-001"
        ),
        actor_id="manager-1",
        actor_display_name="Manager One",
        idempotency_key="cooling-vertical-approve-001",
        approved_at=started_at - timedelta(minutes=5),
    )
    action_id = approved["maintenance_action_id"]
    loop.start_maintenance(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        maintenance_action_id=action_id,
        payload=MaintenanceActionStartRequest(),
        actor_id="technician-1",
        actor_display_name="Technician One",
        idempotency_key="cooling-vertical-start-001",
        started_at=started_at,
    )
    completed = loop.complete_maintenance(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        maintenance_action_id=action_id,
        payload=MaintenanceActionCompleteRequest(outcome="cooling path restored"),
        actor_id="technician-1",
        actor_display_name="Technician One",
        idempotency_key="cooling-vertical-complete-001",
        completed_at=completed_at,
    )
    loop.request_maintenance_replay(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        maintenance_event_id=completed["maintenance_event_id"],
        payload=MaintenanceReplayRequest(restart_at=restart_at),
        actor_id="technician-1",
        actor_display_name="Technician One",
        idempotency_key="cooling-vertical-replay-001",
    )

    lineage = loop.event_lineage(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        event_id="EVT-RESULT-001",
    )
    assert lineage["maintenance_actions"][0]["action_code"] == (
        "COOLING_SYSTEM_RESTORE"
    )
    assert lineage["maintenance_events"][0]["state_patch"] == {
        "cooling_system_state": {
            "operation": "restore",
            "unit": "state",
            "value": "nominal",
        }
    }
    equipment_state = loop.repository.equipment_state(
        workspace_id="workspace-1", equipment_id="CNC-001"
    )
    assert equipment_state is not None
    assert equipment_state["state"] == {
        "cooling_system_state": {"unit": "state", "value": "nominal"}
    }
    with loop.repository._connect() as connection:
        outbox = connection.execute(
            "SELECT event_type,payload_json FROM transactional_outbox "
            "WHERE event_type LIKE 'maintenance.%' ORDER BY created_at"
        ).fetchall()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    payloads = {row["event_type"]: json.loads(row["payload_json"]) for row in outbox}
    assert payloads["maintenance.started"]["action_code"] == (
        "COOLING_SYSTEM_RESTORE"
    )
    assert payloads["maintenance.completed"]["state_patch"] == {
        "cooling_system_state": {
            "operation": "restore",
            "unit": "state",
            "value": "nominal",
        }
    }
    assert payloads["maintenance.replay_requested"]["state_patch"] == (
        payloads["maintenance.completed"]["state_patch"]
    )
