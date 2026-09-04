"""State transitions and authorization gates for the closed loop."""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel

from app.diagnosis.recommendation_schema import ProducerRecommendation

from .cost_analysis_schema import MaintenanceActionCode
from .cost_basis import CostBasisResolutionContext
from .maintenance_schema import (
    EquipmentIdentity,
    IdempotencyOutcome,
    IdempotencyRecord,
    IdempotencyState,
    InspectionOutcome,
    InspectionResult,
    MaintenanceAction,
    MaintenanceActionCandidate,
    MaintenanceActionStatus,
    MaintenanceEvent,
    MaterializationStrategy,
    OperationalDecisionKind,
    OperationalRecommendedAction,
    RecommendationDecision,
    RecommendationDisposition,
    RecommendationStatus,
    RiskEventStatus,
    WorkOrderAuthorization,
    WorkOrder,
    WorkOrderStatus,
    WorkOrderType,
)


class InvalidTransition(ValueError):
    """Raised when a requested domain state transition is not allowed."""


class IdempotencyConflict(ValueError):
    """Raised when a key is reused for a different command."""


class ActionInProgress(ValueError):
    """Raised when an identical command is already running."""


class PriorActionFailed(ValueError):
    """Raised when the previous command with the same identity failed."""


class SourceSimulationSessionUnavailable(ValueError):
    """Raised when a historical Product Result has no source simulation lineage."""


RISK_EVENT_TRANSITIONS = {
    RiskEventStatus.OPEN: {RiskEventStatus.ACKNOWLEDGED},
    RiskEventStatus.ACKNOWLEDGED: {RiskEventStatus.IN_PROGRESS},
    RiskEventStatus.IN_PROGRESS: {RiskEventStatus.RESOLVED},
    RiskEventStatus.RESOLVED: {RiskEventStatus.CLOSED},
    RiskEventStatus.CLOSED: set(),
}
RECOMMENDATION_TRANSITIONS = {
    RecommendationStatus.PROPOSED: {
        RecommendationStatus.ACCEPTED,
        RecommendationStatus.REJECTED,
        RecommendationStatus.DEFERRED,
        RecommendationStatus.SUPERSEDED,
    },
    RecommendationStatus.DEFERRED: {
        RecommendationStatus.ACCEPTED,
        RecommendationStatus.REJECTED,
        RecommendationStatus.SUPERSEDED,
    },
    RecommendationStatus.ACCEPTED: set(),
    RecommendationStatus.REJECTED: set(),
    RecommendationStatus.SUPERSEDED: set(),
}
WORK_ORDER_TRANSITIONS = {
    WorkOrderStatus.REQUESTED: {WorkOrderStatus.APPROVED},
    WorkOrderStatus.APPROVED: {WorkOrderStatus.IN_PROGRESS},
    WorkOrderStatus.IN_PROGRESS: {
        WorkOrderStatus.COMPLETED,
        WorkOrderStatus.BLOCKED,
        WorkOrderStatus.FAILED,
        WorkOrderStatus.CANCELLED,
    },
    WorkOrderStatus.COMPLETED: set(),
    WorkOrderStatus.BLOCKED: set(),
    WorkOrderStatus.FAILED: set(),
    WorkOrderStatus.CANCELLED: set(),
}
MAINTENANCE_ACTION_TRANSITIONS = {
    MaintenanceActionStatus.PLANNED: {MaintenanceActionStatus.IN_PROGRESS},
    MaintenanceActionStatus.IN_PROGRESS: {
        MaintenanceActionStatus.COMPLETED,
        MaintenanceActionStatus.FAILED,
        MaintenanceActionStatus.CANCELLED,
    },
    MaintenanceActionStatus.COMPLETED: set(),
    MaintenanceActionStatus.FAILED: set(),
    MaintenanceActionStatus.CANCELLED: set(),
}

TOOL_WEAR_CHECKLIST_ITEM_ID = "tool-wear"
TOOL_WEAR_MEASUREMENT_NAME = "tool_wear_min"
COOLING_PATH_CHECKLIST_ITEM_ID = "cooling-path"
COOLANT_TEMPERATURE_MEASUREMENT_NAME = "coolant_temperature_c"
COST_BASIS_IN_HOUSE_CHECKLIST_ITEM_ID = "cost-basis-in-house"
COST_BASIS_SPARE_PART_CHECKLIST_ITEM_ID = "cost-basis-spare-part-available"
COST_BASIS_VENDOR_DISPATCH_CHECKLIST_ITEM_ID = "cost-basis-vendor-dispatch-required"
COST_BASIS_COMPONENT_REPLACEMENT_CHECKLIST_ITEM_ID = (
    "cost-basis-component-replacement-required"
)


def derive_cost_basis_resolution_context(
    inspection_result: InspectionResult,
) -> CostBasisResolutionContext:
    """Project explicit cost-basis applicability facts from inspection data.

    A missing or ``not_checked`` item remains unknown.  The cost path therefore
    fails closed instead of silently assuming an in-house job, spare-part
    availability, or the absence of vendor/component work.
    """

    statuses = {
        item.item_id: item.status
        for item in inspection_result.checklist
        if item.status != "not_checked"
    }

    def condition(item_id: str) -> bool | None:
        status = statuses.get(item_id)
        if status is None:
            return None
        return status == "pass"

    in_house = condition(COST_BASIS_IN_HOUSE_CHECKLIST_ITEM_ID)
    return CostBasisResolutionContext(
        execution_mode=(
            "in_house" if in_house is True else "external" if in_house is False else None
        ),
        spare_part_available=condition(COST_BASIS_SPARE_PART_CHECKLIST_ITEM_ID),
        vendor_dispatch_required=condition(COST_BASIS_VENDOR_DISPATCH_CHECKLIST_ITEM_ID),
        component_replacement_required=condition(
            COST_BASIS_COMPONENT_REPLACEMENT_CHECKLIST_ITEM_ID
        ),
    )


def derive_tool_replacement_action_candidate(
    inspection_result: InspectionResult,
) -> MaintenanceActionCandidate:
    """Project the authoritative tool-replacement candidate or fail closed.

    Cost analysis must not infer an action from a generic
    ``maintenance_recommended`` outcome.  Maintenance owns this deterministic
    projection and requires structured tool-wear evidence from the immutable
    inspection result.
    """

    if inspection_result.outcome is not InspectionOutcome.MAINTENANCE_RECOMMENDED:
        raise ValueError(
            "TOOL_REPLACEMENT candidate requires maintenance_recommended inspection outcome"
        )
    has_failed_tool_wear_check = any(
        item.item_id == TOOL_WEAR_CHECKLIST_ITEM_ID and item.status == "fail"
        for item in inspection_result.checklist
    )
    has_tool_wear_measurement = any(
        measurement.name == TOOL_WEAR_MEASUREMENT_NAME
        and isinstance(measurement.value, (int, float))
        and not isinstance(measurement.value, bool)
        for measurement in inspection_result.measurements
    )
    if not has_failed_tool_wear_check or not has_tool_wear_measurement:
        raise ValueError(
            "TOOL_REPLACEMENT candidate requires failed tool-wear checklist "
            "and numeric tool_wear_min measurement"
        )

    action_code = "TOOL_REPLACEMENT"
    source = ":".join(
        (
            inspection_result.organization_id,
            inspection_result.project_id,
            inspection_result.workspace_id,
            inspection_result.inspection_result_id,
            action_code,
        )
    )
    return MaintenanceActionCandidate(
        organization_id=inspection_result.organization_id,
        project_id=inspection_result.project_id,
        workspace_id=inspection_result.workspace_id,
        action_candidate_id=f"ACTION-CANDIDATE-{uuid.uuid5(uuid.NAMESPACE_URL, source)}",
        inspection_result_id=inspection_result.inspection_result_id,
        event_id=inspection_result.event_id,
        asset_id=inspection_result.asset_id,
        equipment_id=inspection_result.equipment_id,
        action_code=action_code,
        basis_codes=(
            "inspection.checklist:tool-wear:fail",
            "inspection.measurement:tool_wear_min",
        ),
    )


def derive_cooling_system_restore_action_candidate(
    inspection_result: InspectionResult,
) -> MaintenanceActionCandidate:
    """Project a cooling-system restoration candidate from typed inspection evidence."""

    if inspection_result.outcome is not InspectionOutcome.MAINTENANCE_RECOMMENDED:
        raise ValueError(
            "COOLING_SYSTEM_RESTORE candidate requires maintenance_recommended "
            "inspection outcome"
        )
    has_failed_cooling_path_check = any(
        item.item_id == COOLING_PATH_CHECKLIST_ITEM_ID and item.status == "fail"
        for item in inspection_result.checklist
    )
    has_coolant_temperature_measurement = any(
        measurement.name == COOLANT_TEMPERATURE_MEASUREMENT_NAME
        and isinstance(measurement.value, (int, float))
        and not isinstance(measurement.value, bool)
        for measurement in inspection_result.measurements
    )
    if not has_failed_cooling_path_check or not has_coolant_temperature_measurement:
        raise ValueError(
            "COOLING_SYSTEM_RESTORE candidate requires failed cooling-path checklist "
            "and numeric coolant_temperature_c measurement"
        )

    action_code = MaintenanceActionCode.COOLING_SYSTEM_RESTORE.value
    source = ":".join(
        (
            inspection_result.organization_id,
            inspection_result.project_id,
            inspection_result.workspace_id,
            inspection_result.inspection_result_id,
            action_code,
        )
    )
    return MaintenanceActionCandidate(
        organization_id=inspection_result.organization_id,
        project_id=inspection_result.project_id,
        workspace_id=inspection_result.workspace_id,
        action_candidate_id=f"ACTION-CANDIDATE-{uuid.uuid5(uuid.NAMESPACE_URL, source)}",
        inspection_result_id=inspection_result.inspection_result_id,
        event_id=inspection_result.event_id,
        asset_id=inspection_result.asset_id,
        equipment_id=inspection_result.equipment_id,
        action_code=action_code,
        basis_codes=(
            "inspection.checklist:cooling-path:fail",
            "inspection.measurement:coolant_temperature_c",
        ),
    )

OPERATIONS_MANUAL_POLICY_VERSION = "operations-manual-recommendation-v1"

StatusT = TypeVar("StatusT")


def _transition(current: StatusT, target: StatusT, transitions: dict[StatusT, set[StatusT]], kind: str) -> StatusT:
    if target not in transitions[current]:
        raise InvalidTransition(f"invalid {kind} status transition: {current} -> {target}")
    return target


def transition_risk_event(current: RiskEventStatus, target: RiskEventStatus) -> RiskEventStatus:
    return _transition(current, target, RISK_EVENT_TRANSITIONS, "risk event")


def transition_recommendation(
    current: RecommendationStatus, target: RecommendationStatus
) -> RecommendationStatus:
    return _transition(current, target, RECOMMENDATION_TRANSITIONS, "recommendation")


def transition_work_order(current: WorkOrderStatus, target: WorkOrderStatus) -> WorkOrderStatus:
    return _transition(current, target, WORK_ORDER_TRANSITIONS, "work order")


def transition_maintenance_action(
    current: MaintenanceActionStatus, target: MaintenanceActionStatus
) -> MaintenanceActionStatus:
    return _transition(current, target, MAINTENANCE_ACTION_TRANSITIONS, "maintenance action")


class _EquipmentCandidate(BaseModel):
    equipment_id: str
    asset_type: str


def resolve_equipment_identity(
    *,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    asset_id: str,
    asset_type: str,
    candidates: Sequence[tuple[str, str]],
) -> EquipmentIdentity:
    """Resolve direct Operations identity and fail instead of guessing a mapping."""

    matches = [
        _EquipmentCandidate(equipment_id=equipment_id, asset_type=candidate_type)
        for equipment_id, candidate_type in candidates
        if equipment_id == asset_id
    ]
    if not matches:
        raise ValueError(f"equipment mapping not found for asset_id={asset_id}")
    if len(matches) != 1:
        raise ValueError(f"ambiguous equipment mapping for asset_id={asset_id}")
    match = matches[0]
    if match.asset_type != asset_type:
        raise ValueError(
            f"asset_type mismatch for asset_id={asset_id}: {asset_type} != {match.asset_type}"
        )
    return EquipmentIdentity(
        organization_id=organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        equipment_id=match.equipment_id,
        asset_type=asset_type,
    )


def materialize_recommended_action(
    producer: ProducerRecommendation,
    *,
    recommendation_id: str | None = None,
    identity: EquipmentIdentity,
    event_id: str,
    materialization_strategy: MaterializationStrategy = MaterializationStrategy.RUNTIME_GENERATED,
    existing_materialization_keys: Collection[str] = (),
) -> OperationalRecommendedAction:
    """Add workflow identity/state while preserving producer-owned meaning exactly."""

    if materialization_strategy is not MaterializationStrategy.RUNTIME_GENERATED:
        raise ValueError("only runtime_generated producer recommendations can be operationalized")
    if producer.kind == "unavailable":
        raise ValueError("unavailable is not a recommendation kind to materialize")
    if producer.materialization_key in existing_materialization_keys:
        raise ValueError(
            f"recommendation already materialized: {producer.materialization_key}"
        )
    return OperationalRecommendedAction(
        organization_id=identity.organization_id,
        project_id=identity.project_id,
        workspace_id=identity.workspace_id,
        recommendation_id=recommendation_id or deterministic_recommendation_id(producer),
        materialization_strategy=MaterializationStrategy.RUNTIME_GENERATED,
        asset_id=identity.asset_id,
        equipment_id=identity.equipment_id,
        asset_type=identity.asset_type,
        event_id=event_id,
        source_action_id=producer.source_action_id,
        source_product_result_id=producer.source_product_result_id,
        source_evidence_id=producer.source_evidence_id,
        source_schema_version=producer.source_schema_version,
        source_policy_version=producer.source_policy_version,
        label=producer.label,
        kind=producer.kind,
        requires_human_approval=producer.requires_human_approval,
        basis=producer.basis,
    )


def deterministic_recommendation_id(producer: ProducerRecommendation) -> str:
    return f"REC-{uuid.uuid5(uuid.NAMESPACE_URL, producer.materialization_key)}"


def create_operations_manual_recommendation(
    *,
    identity: EquipmentIdentity,
    event_id: str,
    source_product_result_id: str,
    source_evidence_id: str,
    source_schema_version: str,
    source_inspection_work_order_id: str,
    source_inspection_reference: str,
    authored_by: str,
    authored_at: datetime,
    basis: tuple[str, ...],
    action_code: MaintenanceActionCode = MaintenanceActionCode.TOOL_REPLACEMENT,
    source_cost_analysis_id: str | None = None,
    source_cost_option_id: str | None = None,
    source_action_candidate_id: str | None = None,
    recommendation_id: str | None = None,
    existing_materialization_keys: Collection[str] = (),
) -> OperationalRecommendedAction:
    """Create the separate Operations-owned recommendation after inspection.

    ``source_inspection_reference`` is an opaque stable reference supplied by
    the Inspection owner. The recommendation preserves the completed inspection
    result as its source and remains distinct from a Diagnosis-produced
    recommendation.
    """

    action_value = action_code.value
    materialization_key = (
        f"{source_inspection_work_order_id}:"
        f"{source_inspection_reference}:{action_value}"
    )
    if materialization_key in existing_materialization_keys:
        raise ValueError(
            f"operations manual recommendation already exists: {materialization_key}"
        )
    scoped_key = ":".join(
        (
            identity.organization_id,
            identity.project_id,
            identity.workspace_id,
            event_id,
            identity.equipment_id,
            materialization_key,
        )
    )
    source_action_id = (
        "OPERATIONS-MANUAL-ACTION-"
        f"{uuid.uuid5(uuid.NAMESPACE_URL, scoped_key)}"
    )
    return OperationalRecommendedAction(
        organization_id=identity.organization_id,
        project_id=identity.project_id,
        workspace_id=identity.workspace_id,
        recommendation_id=(
            recommendation_id
            or f"REC-{uuid.uuid5(uuid.NAMESPACE_URL, scoped_key)}"
        ),
        recommendation_origin="operations_manual",
        materialization_strategy=MaterializationStrategy.RUNTIME_GENERATED,
        asset_id=identity.asset_id,
        equipment_id=identity.equipment_id,
        asset_type=identity.asset_type,
        event_id=event_id,
        source_action_id=source_action_id,
        source_product_result_id=source_product_result_id,
        source_evidence_id=source_evidence_id,
        source_schema_version=source_schema_version,
        source_policy_version=OPERATIONS_MANUAL_POLICY_VERSION,
        label={
            MaintenanceActionCode.TOOL_REPLACEMENT: "공구 교체",
            MaintenanceActionCode.COOLING_SYSTEM_RESTORE: "냉각 시스템 복구",
        }[action_code],
        kind=action_value,
        action_code=action_value,
        requires_human_approval=True,
        basis=basis,
        source_inspection_work_order_id=source_inspection_work_order_id,
        source_inspection_reference=source_inspection_reference,
        source_cost_analysis_id=source_cost_analysis_id,
        source_cost_option_id=source_cost_option_id,
        source_action_candidate_id=source_action_candidate_id,
        authored_by=authored_by,
        authored_at=authored_at,
    )


def validate_single_dataset_writer(
    dataset_version_id: str, writers: Collection[str]
) -> str:
    del dataset_version_id
    normalized = {str(writer) for writer in writers if str(writer)}
    if len(normalized) != 1:
        raise ValueError("one Dataset Version must have exactly one materialization writer")
    writer = next(iter(normalized))
    if writer not in {item.value for item in MaterializationStrategy}:
        raise ValueError(f"unsupported materialization_strategy: {writer}")
    return writer


def imported_result_detail_view(
    result_artifact: dict, *, evidence_detail: dict | None
) -> dict:
    """Preserve imported Result while marking only missing Evidence detail unavailable."""

    return {
        "materialization_strategy": MaterializationStrategy.IMPORTED_PRECOMPUTED.value,
        "result_artifact": result_artifact,
        "recommendations": list(
            (result_artifact.get("evidence_payload") or {}).get("recommended_actions") or []
        ),
        "schema_version": result_artifact.get("schema_version"),
        "provenance": result_artifact.get("provenance") or {},
        "evidence_detail": (
            evidence_detail
            if evidence_detail is not None
            else {
                "status": "unavailable",
                "reason": "imported_result_artifact_missing_evidence_detail",
            }
        ),
    }


def resolve_idempotency(
    *,
    idempotency_key: str,
    request_fingerprint: str,
    existing: IdempotencyRecord | None,
) -> IdempotencyOutcome:
    """Match the existing Ontology Action replay/conflict contract."""

    candidate = IdempotencyRecord(
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        state=IdempotencyState.RUNNING,
    )
    if existing is None:
        return IdempotencyOutcome.NEW
    if existing.idempotency_key != candidate.idempotency_key:
        raise ValueError("existing idempotency record belongs to a different key")
    if existing.request_fingerprint != candidate.request_fingerprint:
        raise IdempotencyConflict("idempotency_key_conflict")
    if existing.state is IdempotencyState.SUCCEEDED:
        return IdempotencyOutcome.REPLAY
    if existing.state is IdempotencyState.RUNNING:
        raise ActionInProgress("action_in_progress")
    raise PriorActionFailed("prior_action_failed")


def apply_recommendation_decision(
    recommendation: OperationalRecommendedAction,
    decision: RecommendationDecision,
) -> OperationalRecommendedAction:
    if decision.recommendation_id != recommendation.recommendation_id:
        raise ValueError("decision does not belong to the recommendation")
    _require_same_scope(recommendation, decision)
    if decision.event_id != recommendation.event_id:
        raise ValueError("decision event does not match the recommendation")
    target = {
        RecommendationDisposition.ACCEPT: RecommendationStatus.ACCEPTED,
        RecommendationDisposition.REJECT: RecommendationStatus.REJECTED,
        RecommendationDisposition.DEFER: RecommendationStatus.DEFERRED,
    }[decision.disposition]
    transition_recommendation(recommendation.status, target)
    return recommendation.model_copy(update={"status": target})


def authorize_inspection_work_order(
    *,
    operational_decision: OperationalDecisionKind,
    source_product_result_id: str,
    source_evidence_id: str,
    source_action_id: str,
    source_schema_version: str,
    source_policy_version: str,
) -> WorkOrderAuthorization:
    if operational_decision not in {
        OperationalDecisionKind.REQUEST_INSPECTION,
        OperationalDecisionKind.REVIEW_SHUTDOWN,
    }:
        raise ValueError("inspection requires request_inspection or review_shutdown")
    return WorkOrderAuthorization(
        work_type=WorkOrderType.INSPECTION,
        operational_decision=operational_decision,
        source_product_result_id=source_product_result_id,
        source_evidence_id=source_evidence_id,
        source_action_id=source_action_id,
        source_schema_version=source_schema_version,
        source_policy_version=source_policy_version,
    )


def authorize_maintenance_work_order(
    *,
    recommendation: OperationalRecommendedAction,
    decision: RecommendationDecision,
) -> WorkOrderAuthorization:
    if recommendation.recommendation_origin != "operations_manual":
        raise ValueError(
            "maintenance work order requires an operations_manual recommendation"
        )
    if recommendation.action_code not in {
        MaintenanceActionCode.TOOL_REPLACEMENT.value,
        MaintenanceActionCode.COOLING_SYSTEM_RESTORE.value,
    }:
        raise ValueError(
            "maintenance work order requires an approved Maintenance action"
        )
    if decision.recommendation_id != recommendation.recommendation_id:
        raise ValueError("decision does not belong to the recommendation")
    _require_same_scope(recommendation, decision)
    if decision.event_id != recommendation.event_id:
        raise ValueError("decision event does not match the recommendation")
    if decision.disposition is not RecommendationDisposition.ACCEPT:
        raise ValueError("maintenance work order requires explicit recommendation acceptance")
    if recommendation.status is not RecommendationStatus.ACCEPTED:
        raise ValueError("maintenance work order requires an accepted recommendation")
    return WorkOrderAuthorization(
        work_type=WorkOrderType.MAINTENANCE,
        recommendation_id=recommendation.recommendation_id,
        recommendation_decision_id=decision.decision_id,
        recommendation_status=RecommendationStatus.ACCEPTED,
        recommendation_disposition=RecommendationDisposition.ACCEPT,
    )


def create_inspection_work_order(
    *,
    work_order_id: str,
    identity: EquipmentIdentity,
    event_id: str,
    operational_decision: OperationalDecisionKind,
    source_product_result_id: str,
    source_evidence_id: str,
    source_action_id: str,
    source_schema_version: str,
    source_policy_version: str,
    idempotency_key: str,
) -> WorkOrder:
    """Create inspection work with explicit canonical projection lineage."""

    authorization = authorize_inspection_work_order(
        operational_decision=operational_decision,
        source_product_result_id=source_product_result_id,
        source_evidence_id=source_evidence_id,
        source_action_id=source_action_id,
        source_schema_version=source_schema_version,
        source_policy_version=source_policy_version,
    )
    return WorkOrder(
        organization_id=identity.organization_id,
        project_id=identity.project_id,
        workspace_id=identity.workspace_id,
        work_order_id=work_order_id,
        event_id=event_id,
        asset_id=identity.asset_id,
        equipment_id=identity.equipment_id,
        asset_type=identity.asset_type,
        work_type=WorkOrderType.INSPECTION,
        idempotency_key=idempotency_key,
        authorization=authorization,
    )


def create_work_order_for_recommendation(
    *,
    work_order_id: str,
    recommendation: OperationalRecommendedAction,
    decision: RecommendationDecision,
    idempotency_key: str,
) -> WorkOrder:
    """Create maintenance work while deriving all lineage from its recommendation."""

    authorization = authorize_maintenance_work_order(
        recommendation=recommendation,
        decision=decision,
    )
    return WorkOrder(
        organization_id=recommendation.organization_id,
        project_id=recommendation.project_id,
        workspace_id=recommendation.workspace_id,
        work_order_id=work_order_id,
        event_id=recommendation.event_id,
        asset_id=recommendation.asset_id,
        equipment_id=recommendation.equipment_id,
        asset_type=recommendation.asset_type,
        work_type=WorkOrderType.MAINTENANCE,
        idempotency_key=idempotency_key,
        authorization=authorization,
    )


def plan_maintenance_action(
    *,
    work_order: WorkOrder,
    maintenance_action_id: str,
    idempotency_key: str,
) -> MaintenanceAction:
    if work_order.work_type is not WorkOrderType.MAINTENANCE:
        raise ValueError("maintenance action requires a maintenance work order")
    if work_order.status is not WorkOrderStatus.APPROVED:
        raise ValueError("maintenance action requires an approved work order")
    authorization = work_order.authorization
    if authorization.recommendation_id is None or authorization.recommendation_decision_id is None:
        raise ValueError("maintenance action requires recommendation approval lineage")
    return MaintenanceAction(
        organization_id=work_order.organization_id,
        project_id=work_order.project_id,
        workspace_id=work_order.workspace_id,
        maintenance_action_id=maintenance_action_id,
        work_order_id=work_order.work_order_id,
        event_id=work_order.event_id,
        asset_id=work_order.asset_id,
        equipment_id=work_order.equipment_id,
        recommendation_id=authorization.recommendation_id,
        recommendation_decision_id=authorization.recommendation_decision_id,
        idempotency_key=idempotency_key,
    )


def record_maintenance_event(
    *,
    work_order: WorkOrder,
    action: MaintenanceAction,
    maintenance_event_id: str,
    completed_at: datetime,
    outcome: str,
) -> MaintenanceEvent:
    if work_order.work_type is not WorkOrderType.MAINTENANCE:
        raise ValueError("maintenance event requires a maintenance work order")
    if work_order.status is not WorkOrderStatus.COMPLETED:
        raise ValueError("maintenance event requires a completed work order")
    if action.status is not MaintenanceActionStatus.COMPLETED:
        raise ValueError("maintenance event requires a completed maintenance action")
    if action.work_order_id != work_order.work_order_id:
        raise ValueError("maintenance action does not belong to the work order")
    _require_same_scope(work_order, action)
    if action.event_id != work_order.event_id or action.equipment_id != work_order.equipment_id:
        raise ValueError("maintenance action lineage does not match the work order")
    authorization = work_order.authorization
    if (
        action.recommendation_id != authorization.recommendation_id
        or action.recommendation_decision_id != authorization.recommendation_decision_id
    ):
        raise ValueError("maintenance action approval lineage does not match the work order")
    return MaintenanceEvent(
        organization_id=work_order.organization_id,
        project_id=work_order.project_id,
        workspace_id=work_order.workspace_id,
        maintenance_event_id=maintenance_event_id,
        maintenance_action_id=action.maintenance_action_id,
        work_order_id=work_order.work_order_id,
        event_id=work_order.event_id,
        asset_id=work_order.asset_id,
        equipment_id=work_order.equipment_id,
        recommendation_id=action.recommendation_id,
        recommendation_decision_id=action.recommendation_decision_id,
        completed_at=completed_at,
        outcome=outcome,
    )


def _require_same_scope(left: object, right: object) -> None:
    for field in ("organization_id", "project_id", "workspace_id"):
        if getattr(left, field) != getattr(right, field):
            raise ValueError(f"{field} scope mismatch")
