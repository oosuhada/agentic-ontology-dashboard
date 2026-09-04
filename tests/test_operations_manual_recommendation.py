from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.infra.db.maintenance_repository import MaintenanceRepository
from app.maintenance import (
    EquipmentIdentity,
    OperationalRecommendedAction,
    RecommendationDecision,
    RecommendationDisposition,
    RecommendationStatus,
    WorkOrderType,
    apply_recommendation_decision,
    create_operations_manual_recommendation,
    create_work_order_for_recommendation,
)


class _Scope:
    organization_id = "org-1"
    project_id = "project-1"
    workspace_id = "workspace-1"


class _Resolver:
    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection=None,
    ):
        del connection
        if workspace_id != _Scope.workspace_id:
            raise ValueError("workspace scope mismatch")
        if expected_organization_id not in {None, _Scope.organization_id}:
            raise ValueError("organization scope mismatch")
        if expected_project_id not in {None, _Scope.project_id}:
            raise ValueError("project scope mismatch")
        return _Scope()


def _identity() -> EquipmentIdentity:
    return EquipmentIdentity(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        asset_id="CNC-001",
        equipment_id="CNC-001",
        asset_type="cnc",
    )


def _manual_recommendation(**updates) -> OperationalRecommendedAction:
    arguments = {
        "identity": _identity(),
        "event_id": "event-001",
        "source_product_result_id": "result-001",
        "source_evidence_id": "evidence-001",
        "source_schema_version": "result-artifact-v1.0",
        "source_inspection_work_order_id": "inspection-work-order-001",
        "source_inspection_reference": "inspection-activity-001",
        "authored_by": "engineer-001",
        "authored_at": datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc),
        "basis": ("inspection-activity-001:tool-wear-exceeded",),
    }
    arguments.update(updates)
    return create_operations_manual_recommendation(**arguments)


def test_operations_manual_recommendation_has_separate_owned_lineage() -> None:
    recommendation = _manual_recommendation()

    assert recommendation.recommendation_origin == "operations_manual"
    assert recommendation.kind == recommendation.action_code == "TOOL_REPLACEMENT"
    assert recommendation.source_policy_version == "operations-manual-recommendation-v1"
    assert recommendation.source_product_result_id == "result-001"
    assert recommendation.source_evidence_id == "evidence-001"
    assert recommendation.source_inspection_work_order_id == "inspection-work-order-001"
    assert recommendation.source_inspection_reference == "inspection-activity-001"
    assert recommendation.authored_by == "engineer-001"
    assert recommendation.requires_human_approval is True
    assert recommendation.status is RecommendationStatus.PROPOSED
    assert recommendation.materialization_key == (
        "inspection-work-order-001:inspection-activity-001:TOOL_REPLACEMENT"
    )


def test_operations_manual_identity_is_stable_across_retries() -> None:
    first = _manual_recommendation()
    retried = _manual_recommendation()

    assert retried.recommendation_id == first.recommendation_id
    assert retried.source_action_id == first.source_action_id
    assert retried.materialization_key == first.materialization_key

    with pytest.raises(ValueError, match="already exists"):
        _manual_recommendation(
            existing_materialization_keys={first.materialization_key}
        )


def test_operations_manual_recommendation_round_trips_and_deduplicates(tmp_path) -> None:
    repository = MaintenanceRepository(
        tmp_path / "maintenance.db", project_context=_Resolver()
    )
    recommendation = _manual_recommendation()

    stored = repository.save_recommendation(
        recommendation,
        actor_user_id="engineer-001",
        actor_display_name="Engineer One",
    )
    replayed = repository.save_recommendation(
        recommendation,
        actor_user_id="engineer-001",
        actor_display_name="Engineer One",
    )

    assert stored == replayed == recommendation
    assert repository.get_recommendation(
        workspace_id="workspace-1",
        recommendation_id=recommendation.recommendation_id,
    ) == recommendation
    assert repository.operational_side_effect_counts()["recommendations"] == 1
    activities = repository.list_event_activity(
        workspace_id="workspace-1", event_id="event-001"
    )
    assert [activity["activity_type"] for activity in activities] == [
        "recommendation.materialized"
    ]


def test_operations_manual_requires_complete_inspection_and_author_lineage() -> None:
    payload = _manual_recommendation().model_dump()
    payload["source_inspection_reference"] = None
    with pytest.raises(ValidationError, match="inspection, action, and author lineage"):
        OperationalRecommendedAction.model_validate(payload)

    payload = _manual_recommendation().model_dump()
    payload["requires_human_approval"] = False
    with pytest.raises(ValidationError, match="requires human approval"):
        OperationalRecommendedAction.model_validate(payload)


def test_cost_referenced_recommendation_allows_analysis_without_option_selection() -> None:
    referenced = _manual_recommendation(
        source_cost_analysis_id="cost-analysis-001",
        source_action_candidate_id="action-candidate-001",
    )
    assert referenced.source_cost_analysis_id == "cost-analysis-001"
    assert referenced.source_cost_option_id is None
    assert referenced.source_action_candidate_id == "action-candidate-001"

    payload = referenced.model_dump()
    payload["source_action_candidate_id"] = None
    with pytest.raises(ValidationError, match="analysis and action candidate lineage"):
        OperationalRecommendedAction.model_validate(payload)


def test_cost_selected_recommendation_preserves_complete_option_lineage() -> None:
    selected = _manual_recommendation(
        source_cost_analysis_id="cost-analysis-001",
        source_cost_option_id="cost-option-001",
        source_action_candidate_id="action-candidate-001",
    )
    assert selected.source_cost_analysis_id == "cost-analysis-001"
    assert selected.source_cost_option_id == "cost-option-001"
    assert selected.source_action_candidate_id == "action-candidate-001"


def test_cost_selected_recommendation_must_use_validating_command_path(tmp_path) -> None:
    repository = MaintenanceRepository(
        tmp_path / "maintenance.db", project_context=_Resolver()
    )
    selected = _manual_recommendation(
        source_cost_analysis_id="cost-analysis-001",
        source_cost_option_id="cost-option-001",
        source_action_candidate_id="action-candidate-001",
    )

    with pytest.raises(ValueError, match="create_manual_recommendation"):
        repository.save_recommendation(selected)


def test_sqlite_rejects_partial_cost_selection_lineage(tmp_path) -> None:
    repository = MaintenanceRepository(
        tmp_path / "maintenance.db", project_context=_Resolver()
    )
    recommendation = _manual_recommendation()
    repository.save_recommendation(recommendation)

    with sqlite3.connect(repository.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="invalid recommendation"):
            connection.execute(
                """
                UPDATE closed_loop_recommendations
                SET source_cost_option_id='cost-option-only'
                WHERE recommendation_id=?
                """,
                (recommendation.recommendation_id,),
            )


def test_product_projection_cannot_smuggle_operations_manual_fields() -> None:
    payload = _manual_recommendation().model_dump()
    payload["recommendation_origin"] = "product_result_projection"
    with pytest.raises(ValidationError, match="cannot contain operations_manual lineage"):
        OperationalRecommendedAction.model_validate(payload)


def test_manual_recommendation_still_requires_second_acceptance_for_maintenance() -> None:
    proposed = _manual_recommendation()
    decision = RecommendationDecision(
        organization_id=proposed.organization_id,
        project_id=proposed.project_id,
        workspace_id=proposed.workspace_id,
        decision_id="decision-001",
        event_id=proposed.event_id,
        recommendation_id=proposed.recommendation_id,
        disposition=RecommendationDisposition.ACCEPT,
        actor_id="manager-001",
        decided_at=datetime(2026, 8, 21, 9, 10, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="accepted recommendation"):
        create_work_order_for_recommendation(
            work_order_id="maintenance-work-order-001",
            recommendation=proposed,
            decision=decision,
            idempotency_key="maintenance-work-order-001",
        )

    accepted = apply_recommendation_decision(proposed, decision)
    work_order = create_work_order_for_recommendation(
        work_order_id="maintenance-work-order-001",
        recommendation=accepted,
        decision=decision,
        idempotency_key="maintenance-work-order-001",
    )

    assert work_order.work_type is WorkOrderType.MAINTENANCE
    assert work_order.authorization.recommendation_id == proposed.recommendation_id
    assert work_order.authorization.recommendation_decision_id == decision.decision_id
