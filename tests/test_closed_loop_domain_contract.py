from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import app.maintenance as closed_loop_contract
from app.maintenance import (
    ActionInProgress,
    IdempotencyConflict,
    IdempotencyOutcome,
    IdempotencyRecord,
    IdempotencyState,
    InvalidTransition,
    MaintenanceActionStatus,
    OperationalDecisionKind,
    OperationalRecommendedAction,
    PriorActionFailed,
    ProducerRecommendation,
    RecommendationDecision,
    RecommendationDisposition,
    RecommendationStatus,
    RiskEventStatus,
    WorkOrder,
    WorkOrderAuthorization,
    WorkOrderStatus,
    WorkOrderType,
    apply_recommendation_decision,
    authorize_inspection_work_order,
    authorize_maintenance_work_order,
    create_inspection_work_order,
    create_operations_manual_recommendation,
    create_work_order_for_recommendation,
    materialize_recommended_action,
    plan_maintenance_action,
    record_maintenance_event,
    resolve_equipment_identity,
    resolve_idempotency,
    transition_maintenance_action,
    transition_recommendation,
    transition_risk_event,
    transition_work_order,
)
from app.operations.contracts import DecisionRequest


def equipment_identity():
    return resolve_equipment_identity(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        asset_id="CNC-001",
        asset_type="cnc_machine",
        candidates=[("CNC-001", "cnc_machine")],
    )


def producer_recommendation() -> ProducerRecommendation:
    return ProducerRecommendation(
        source_action_id="action-inspect-tool",
        source_product_result_id="result-cnc-001",
        source_evidence_id="evidence-cnc-001",
        source_schema_version="product-result-artifact-v1",
        source_policy_version="pdm-recommendation-policy-v1",
        label="Inspect the cutting tool",
        kind="inspect",
        requires_human_approval=True,
        basis=("tool_wear_high", "failure_probability_above_threshold"),
    )


def proposed_recommendation():
    return materialize_recommended_action(
        producer_recommendation(),
        recommendation_id="recommendation-001",
        identity=equipment_identity(),
        event_id="event-001",
    )


def proposed_manual_recommendation():
    return create_operations_manual_recommendation(
        identity=equipment_identity(),
        event_id="event-001",
        source_product_result_id="result-cnc-001",
        source_evidence_id="evidence-cnc-001",
        source_schema_version="product-result-artifact-v1",
        source_inspection_work_order_id="inspection-work-order-001",
        source_inspection_reference="inspection-result-001",
        authored_by="engineer-001",
        authored_at=datetime.now(timezone.utc),
        basis=("inspection-result-001:tool-replacement-required",),
        recommendation_id="recommendation-001",
    )


def inspection_source_lineage() -> dict[str, str]:
    return {
        "source_product_result_id": "result-cnc-001",
        "source_evidence_id": "evidence-cnc-001",
        "source_action_id": "action-inspect-tool",
        "source_schema_version": "product-result-artifact-v1",
        "source_policy_version": "pdm-recommendation-policy-v1",
    }


def recommendation_decision(
    disposition: RecommendationDisposition = RecommendationDisposition.ACCEPT,
    **updates,
) -> RecommendationDecision:
    payload = {
        "organization_id": "org-1",
        "project_id": "project-1",
        "workspace_id": "workspace-1",
        "decision_id": "decision-001",
        "event_id": "event-001",
        "recommendation_id": "recommendation-001",
        "disposition": disposition,
        "actor_id": "manager-001",
        "decided_at": datetime.now(timezone.utc),
    }
    payload.update(updates)
    return RecommendationDecision.model_validate(payload)


def test_existing_decision_request_and_closed_loop_share_one_enum() -> None:
    request = DecisionRequest(actor="manager-001", decision="review_shutdown")
    assert request.decision is OperationalDecisionKind.REVIEW_SHUTDOWN


def test_materialization_preserves_meaning_scope_lineage_and_dedupe_key() -> None:
    source = producer_recommendation()
    before = source.model_dump()
    identity = equipment_identity()

    action = materialize_recommended_action(
        source,
        recommendation_id="recommendation-001",
        identity=identity,
        event_id="event-001",
    )

    assert source.model_dump() == before
    assert action.recommendation_origin == "product_result_projection"
    assert action.status is RecommendationStatus.PROPOSED
    assert action.materialization_key == "result-cnc-001:action-inspect-tool"
    assert action.organization_id == identity.organization_id
    assert action.project_id == identity.project_id
    assert action.workspace_id == identity.workspace_id
    assert action.asset_id == action.equipment_id == "CNC-001"
    assert action.event_id == "event-001"
    for field in (
        "source_action_id",
        "source_product_result_id",
        "source_evidence_id",
        "source_schema_version",
        "source_policy_version",
        "label",
        "kind",
        "requires_human_approval",
        "basis",
    ):
        assert getattr(action, field) == getattr(source, field)

    with pytest.raises(ValueError, match="already materialized"):
        materialize_recommended_action(
            source,
            recommendation_id="recommendation-duplicate",
            identity=identity,
            event_id="event-001",
            existing_materialization_keys={source.materialization_key},
        )


def test_operational_recommendation_rejects_mismatched_operations_identity() -> None:
    payload = proposed_recommendation().model_dump()
    payload["equipment_id"] = "CNC-OTHER"
    with pytest.raises(ValidationError, match="equipment_id = asset_id"):
        OperationalRecommendedAction.model_validate(payload)


def test_materialization_refuses_missing_policy_version() -> None:
    payload = producer_recommendation().model_dump()
    payload["source_policy_version"] = ""
    with pytest.raises(ValidationError, match="source_policy_version"):
        ProducerRecommendation.model_validate(payload)


@pytest.mark.parametrize("kind", ["inspect", "monitor", "stop_review", "data_quality"])
def test_materialization_preserves_producer_owned_action_kind(kind: str) -> None:
    payload = producer_recommendation().model_dump()
    payload["kind"] = kind
    source = ProducerRecommendation.model_validate(payload)

    action = materialize_recommended_action(
        source,
        recommendation_id=f"recommendation-{kind}",
        identity=equipment_identity(),
        event_id="event-001",
    )

    assert action.kind == kind


def test_equipment_identity_is_direct_stable_and_dataset_independent() -> None:
    identity = equipment_identity()
    assert identity.equipment_id == identity.asset_id
    assert identity.stable_key == "org-1:project-1:CNC-001"
    assert "dataset" not in type(identity).model_fields


@pytest.mark.parametrize(
    ("candidates", "message"),
    [
        ([], "not found"),
        ([("CNC-001", "cnc_machine"), ("CNC-001", "cnc_machine")], "ambiguous"),
        ([("CNC-001", "robot")], "asset_type mismatch"),
    ],
)
def test_equipment_identity_mapping_fails_fast(
    candidates: list[tuple[str, str]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_equipment_identity(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            asset_id="CNC-001",
            asset_type="cnc_machine",
            candidates=candidates,
        )


def test_state_machines_cover_rejected_deferred_blocked_and_terminal_rollback() -> None:
    assert transition_risk_event(RiskEventStatus.OPEN, RiskEventStatus.ACKNOWLEDGED) == "acknowledged"
    assert transition_recommendation(RecommendationStatus.PROPOSED, RecommendationStatus.REJECTED) == "rejected"
    assert transition_recommendation(RecommendationStatus.PROPOSED, RecommendationStatus.DEFERRED) == "deferred"
    assert transition_recommendation(RecommendationStatus.DEFERRED, RecommendationStatus.ACCEPTED) == "accepted"
    assert transition_work_order(WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.BLOCKED) == "blocked"
    assert transition_maintenance_action(
        MaintenanceActionStatus.IN_PROGRESS, MaintenanceActionStatus.COMPLETED
    ) == "completed"

    with pytest.raises(InvalidTransition, match="work order"):
        transition_work_order(WorkOrderStatus.COMPLETED, WorkOrderStatus.IN_PROGRESS)
    with pytest.raises(InvalidTransition, match="recommendation"):
        transition_recommendation(RecommendationStatus.REJECTED, RecommendationStatus.ACCEPTED)
    with pytest.raises(InvalidTransition, match="recommendation"):
        transition_recommendation(RecommendationStatus.ACCEPTED, RecommendationStatus.SUPERSEDED)
    with pytest.raises(InvalidTransition, match="recommendation"):
        transition_recommendation(RecommendationStatus.REJECTED, RecommendationStatus.SUPERSEDED)


def test_inspection_mapping_preserves_existing_decision_behavior() -> None:
    for decision in (
        OperationalDecisionKind.REQUEST_INSPECTION,
        OperationalDecisionKind.REVIEW_SHUTDOWN,
    ):
        authorization = authorize_inspection_work_order(
            operational_decision=decision,
            **inspection_source_lineage(),
        )
        assert authorization.work_type is WorkOrderType.INSPECTION
        assert authorization.operational_decision is decision

    for decision in (
        OperationalDecisionKind.CONTINUE_MONITORING,
        OperationalDecisionKind.HOLD_FOR_DATA_CHECK,
    ):
        with pytest.raises(ValueError, match="request_inspection or review_shutdown"):
            authorize_inspection_work_order(
                operational_decision=decision,
                **inspection_source_lineage(),
            )


def test_authorization_model_rejects_mixed_or_incomplete_authority() -> None:
    with pytest.raises(ValidationError, match="maintenance authorization cannot use"):
        WorkOrderAuthorization(
            work_type=WorkOrderType.MAINTENANCE,
            operational_decision=OperationalDecisionKind.REQUEST_INSPECTION,
        )
    with pytest.raises(ValidationError, match="cannot contain maintenance approval"):
        WorkOrderAuthorization(
            work_type=WorkOrderType.INSPECTION,
            operational_decision=OperationalDecisionKind.REQUEST_INSPECTION,
            recommendation_id="recommendation-001",
        )


def test_maintenance_work_requires_matching_scoped_explicit_acceptance() -> None:
    producer_projection = proposed_recommendation()
    producer_decision = recommendation_decision()
    accepted_projection = apply_recommendation_decision(
        producer_projection, producer_decision
    )
    with pytest.raises(ValueError, match="operations_manual recommendation"):
        authorize_maintenance_work_order(
            recommendation=accepted_projection,
            decision=producer_decision,
        )

    proposed = proposed_manual_recommendation()
    decision = recommendation_decision()
    accepted = apply_recommendation_decision(proposed, decision)

    authorization = authorize_maintenance_work_order(
        recommendation=accepted,
        decision=decision,
    )
    assert authorization.work_type is WorkOrderType.MAINTENANCE
    assert authorization.recommendation_decision_id == "decision-001"

    with pytest.raises(ValueError, match="accepted recommendation"):
        authorize_maintenance_work_order(recommendation=proposed, decision=decision)

    deferred = recommendation_decision(RecommendationDisposition.DEFER)
    deferred_recommendation = apply_recommendation_decision(proposed, deferred)
    with pytest.raises(ValueError, match="explicit recommendation acceptance"):
        authorize_maintenance_work_order(
            recommendation=deferred_recommendation,
            decision=deferred,
        )

    wrong_scope = recommendation_decision(workspace_id="other-workspace")
    with pytest.raises(ValueError, match="workspace_id scope mismatch"):
        apply_recommendation_decision(proposed, wrong_scope)


def test_action_and_event_require_approved_completed_matching_lineage() -> None:
    identity = equipment_identity()
    recommendation = proposed_manual_recommendation()
    decision = recommendation_decision()
    accepted = apply_recommendation_decision(recommendation, decision)
    recommendation_order = create_work_order_for_recommendation(
        work_order_id="work-order-from-recommendation",
        recommendation=accepted,
        decision=decision,
        idempotency_key="work-order-from-recommendation-001",
    )
    assert recommendation_order.asset_id == recommendation_order.equipment_id == "CNC-001"
    assert recommendation_order.event_id == accepted.event_id
    assert recommendation_order.authorization.recommendation_decision_id == decision.decision_id

    wrong_event_decision = recommendation_decision(event_id="event-other")
    with pytest.raises(ValueError, match="decision event does not match"):
        create_work_order_for_recommendation(
            work_order_id="work-order-wrong-event",
            recommendation=accepted,
            decision=wrong_event_decision,
            idempotency_key="work-order-wrong-event-001",
        )

    requested = recommendation_order
    with pytest.raises(ValueError, match="approved work order"):
        plan_maintenance_action(
            work_order=requested,
            maintenance_action_id="maintenance-action-001",
            idempotency_key="maintenance-plan-001",
        )

    approved = WorkOrder.model_validate(
        {**requested.model_dump(), "status": WorkOrderStatus.APPROVED}
    )
    action = plan_maintenance_action(
        work_order=approved,
        maintenance_action_id="maintenance-action-001",
        idempotency_key="maintenance-plan-001",
    )
    assert action.workspace_id == approved.workspace_id
    assert action.event_id == approved.event_id
    assert action.recommendation_decision_id == "decision-001"

    with pytest.raises(ValueError, match="completed work order"):
        record_maintenance_event(
            work_order=approved,
            action=action,
            maintenance_event_id="maintenance-event-001",
            completed_at=datetime.now(timezone.utc),
            outcome="tool replaced",
        )

    completed_order = WorkOrder.model_validate(
        {**approved.model_dump(), "status": WorkOrderStatus.COMPLETED}
    )
    completed_action = type(action).model_validate(
        {**action.model_dump(), "status": MaintenanceActionStatus.COMPLETED}
    )
    wrong_approval_action = completed_action.model_copy(
        update={"recommendation_decision_id": "decision-other"}
    )
    with pytest.raises(ValueError, match="approval lineage"):
        record_maintenance_event(
            work_order=completed_order,
            action=wrong_approval_action,
            maintenance_event_id="maintenance-event-wrong-approval",
            completed_at=datetime.now(timezone.utc),
            outcome="tool replaced",
        )

    event = record_maintenance_event(
        work_order=completed_order,
        action=completed_action,
        maintenance_event_id="maintenance-event-001",
        completed_at=datetime.now(timezone.utc),
        outcome="tool replaced",
    )
    assert event.work_order_id == completed_order.work_order_id
    assert event.maintenance_action_id == completed_action.maintenance_action_id
    assert event.recommendation_id == "recommendation-001"

    inspection = create_inspection_work_order(
        work_order_id="inspection-001",
        identity=identity,
        event_id="event-001",
        operational_decision=OperationalDecisionKind.REQUEST_INSPECTION,
        **inspection_source_lineage(),
        idempotency_key="inspection-create-001",
    )
    inspection_approved = WorkOrder.model_validate(
        {
            **inspection.model_dump(),
            "status": WorkOrderStatus.APPROVED,
            "assigned_to": "engineer-1",
            "assigned_at": datetime.now(timezone.utc),
        }
    )
    with pytest.raises(ValueError, match="maintenance work order"):
        plan_maintenance_action(
            work_order=inspection_approved,
            maintenance_action_id="invalid-action",
            idempotency_key="invalid-action-001",
        )


def test_public_work_order_factories_do_not_expose_unbound_authorization_path() -> None:
    assert not hasattr(closed_loop_contract, "create_work_order")
    assert hasattr(closed_loop_contract, "create_inspection_work_order")
    assert hasattr(closed_loop_contract, "create_work_order_for_recommendation")


def test_idempotency_allows_replay_and_rejects_conflict_or_unfinished_state() -> None:
    assert (
        resolve_idempotency(
            idempotency_key="decision-001",
            request_fingerprint="sha256:same",
            existing=None,
        )
        is IdempotencyOutcome.NEW
    )
    succeeded = IdempotencyRecord(
        idempotency_key="decision-001",
        request_fingerprint="sha256:same",
        state=IdempotencyState.SUCCEEDED,
    )
    assert (
        resolve_idempotency(
            idempotency_key="decision-001",
            request_fingerprint="sha256:same",
            existing=succeeded,
        )
        is IdempotencyOutcome.REPLAY
    )
    with pytest.raises(IdempotencyConflict, match="idempotency_key_conflict"):
        resolve_idempotency(
            idempotency_key="decision-001",
            request_fingerprint="sha256:different",
            existing=succeeded,
        )
    for state, error, message in (
        (IdempotencyState.RUNNING, ActionInProgress, "action_in_progress"),
        (IdempotencyState.FAILED, PriorActionFailed, "prior_action_failed"),
    ):
        existing = succeeded.model_copy(update={"state": state})
        with pytest.raises(error, match=message):
            resolve_idempotency(
                idempotency_key="decision-001",
                request_fingerprint="sha256:same",
                existing=existing,
            )
