from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.maintenance import (
    EquipmentIdentity,
    IdempotencyConflict,
    InvalidTransition,
    RecommendationDecision,
    RecommendationDisposition,
    WorkOrderStatus,
    apply_recommendation_decision,
    create_operations_manual_recommendation,
    create_work_order_for_recommendation,
    plan_maintenance_action,
    transition_work_order,
)
from app.maintenance.integration import (
    MaintenanceCause,
    MaintenanceCompletedEvent,
    MaintenanceReplayRequestedEvent,
    MaintenanceStartedEvent,
)
from app.infra.db.maintenance_repository import MaintenanceRepository
from app.infra.db.project_repository import (
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    ProjectContextError,
    SQLiteProjectContextResolver,
)


def test_retired_presentation_work_order_is_not_a_live_queue_item() -> None:
    retired_row = {
        "authorization_json": json.dumps(
            {"actor": "legacy-demo-user", "scope": "presentation-demo"}
        )
    }
    canonical_row = {
        "authorization_json": json.dumps(
            {"work_type": "inspection", "operational_decision": "request_inspection"}
        )
    }

    assert MaintenanceRepository._is_retired_presentation_work_order_row(retired_row)
    assert not MaintenanceRepository._is_retired_presentation_work_order_row(canonical_row)


def _recommendation_setup(repository: MaintenanceRepository):
    identity = EquipmentIdentity(
        organization_id=DEFAULT_ORGANIZATION_ID,
        project_id=DEFAULT_PROJECT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        asset_id="CNC-S02-L04-03",
        equipment_id="CNC-S02-L04-03",
        asset_type="cnc_machine",
    )
    recommendation = create_operations_manual_recommendation(
        identity=identity,
        event_id="RISK-EVENT-001",
        source_product_result_id="RESULT-001",
        source_evidence_id="EVIDENCE-001",
        source_schema_version="result-artifact-v1.0",
        source_inspection_work_order_id="INSPECTION-WORK-ORDER-001",
        source_inspection_reference="INSPECTION-RESULT-001",
        authored_by="engineer-001",
        authored_at=datetime(2026, 8, 18, 0, 58, tzinfo=timezone.utc),
        basis=("tool_wear_min threshold exceeded",),
        recommendation_id="RECOMMENDATION-001",
    )
    repository.save_recommendation(
        recommendation,
        recorded_at=datetime(2026, 8, 18, 0, 59, tzinfo=timezone.utc),
    )
    decision = RecommendationDecision(
        organization_id=DEFAULT_ORGANIZATION_ID,
        project_id=DEFAULT_PROJECT_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        decision_id="DECISION-001",
        event_id="RISK-EVENT-001",
        recommendation_id=recommendation.recommendation_id,
        disposition=RecommendationDisposition.ACCEPT,
        actor_id="manager-001",
        decided_at=datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc),
        note="시연 정비 승인",
    )
    accepted = apply_recommendation_decision(recommendation, decision)
    requested_work_order = create_work_order_for_recommendation(
        work_order_id="WORK-ORDER-001",
        recommendation=accepted,
        decision=decision,
        idempotency_key="http-recommendation-accept-001",
    )
    cause = MaintenanceCause(
        source_product_result_id=recommendation.source_product_result_id,
        source_evidence_id=recommendation.source_evidence_id,
        decision_id=decision.decision_id,
    )
    return recommendation, accepted, decision, requested_work_order, cause


def _foundation(repository: MaintenanceRepository):
    _, accepted, decision, requested_work_order, cause = _recommendation_setup(repository)
    decision_result = repository.decide_recommendation(
        recommendation=accepted,
        decision=decision,
        work_order=requested_work_order,
        request_idempotency_key="http-recommendation-accept-001",
        request_fingerprint="recommendation-001:accept",
    )
    assert decision_result["replayed"] is False
    approved_work_order = requested_work_order.model_copy(
        update={
            "status": transition_work_order(
                requested_work_order.status,
                WorkOrderStatus.APPROVED,
            )
        }
    )
    action = plan_maintenance_action(
        work_order=approved_work_order,
        maintenance_action_id="MAINTENANCE-ACTION-001",
        idempotency_key="http-work-order-approve-001",
    )
    approval_result = repository.approve_work_order(
        work_order=approved_work_order,
        action=action,
        simulation_session_id="DEMO-SESSION-001",
        actor_id="manager-001",
        approved_at=decision.decided_at + timedelta(minutes=5),
        request_idempotency_key="http-work-order-approve-001",
        request_fingerprint="work-order-001:approve",
    )
    assert approval_result["replayed"] is False
    return action, cause


def _started(action, cause, started_at):
    return MaintenanceStartedEvent(
        event_id="OUTBOX-MAINTENANCE-001",
        idempotency_key="maintenance-action-001:1",
        state_version=1,
        simulation_session_id="DEMO-SESSION-001",
        maintenance_action_id=action.maintenance_action_id,
        work_order_id=action.work_order_id,
        equipment_id=action.equipment_id,
        maintenance_started_at=started_at,
        caused_by=cause,
    )


def _completed(action, cause, started_at, completed_at):
    return MaintenanceCompletedEvent(
        event_id="OUTBOX-MAINTENANCE-002",
        idempotency_key="maintenance-action-001:2",
        state_version=2,
        simulation_session_id="DEMO-SESSION-001",
        maintenance_event_id="MAINTENANCE-EVENT-001",
        maintenance_action_id=action.maintenance_action_id,
        equipment_id=action.equipment_id,
        maintenance_started_at=started_at,
        maintenance_completed_at=completed_at,
        caused_by=cause,
    )


def test_accept_decision_and_requested_work_order_are_one_idempotent_transaction(
    tmp_path: Path,
) -> None:
    class FailingWorkOrderRepository(MaintenanceRepository):
        fail_work_order = True

        def _insert_work_order(self, connection, *, work_order, now):
            if self.fail_work_order:
                raise RuntimeError("simulated work order insert failure")
            return super()._insert_work_order(connection, work_order=work_order, now=now)

    database = tmp_path / "accept-atomic.db"
    repository = FailingWorkOrderRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    _, accepted, decision, requested_work_order, _ = _recommendation_setup(repository)
    command = {
        "recommendation": accepted,
        "decision": decision,
        "work_order": requested_work_order,
        "request_idempotency_key": "http-recommendation-accept-001",
        "request_fingerprint": "recommendation-001:accept",
    }

    with pytest.raises(RuntimeError, match="simulated work order insert failure"):
        repository.decide_recommendation(**command)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT status FROM closed_loop_recommendations WHERE recommendation_id='RECOMMENDATION-001'"
        ).fetchone()[0] == "proposed"
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_recommendation_decisions"
        ).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM closed_loop_work_orders").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_idempotency_records WHERE idempotency_key='http-recommendation-accept-001'"
        ).fetchone()[0] == 0

    repository.fail_work_order = False
    first = repository.decide_recommendation(**command)
    replay = repository.decide_recommendation(**command)
    assert first["replayed"] is False
    assert replay == {**first, "replayed": True}
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_recommendation_decisions"
        ).fetchone()[0] == 1
        assert connection.execute("SELECT status FROM closed_loop_work_orders").fetchone()[0] == "requested"


def test_work_order_approval_and_planned_action_are_one_idempotent_transaction(
    tmp_path: Path,
) -> None:
    class FailingActionRepository(MaintenanceRepository):
        fail_action = True

        def _insert_maintenance_action(
            self,
            connection,
            *,
            action,
            simulation_session_id,
            action_code,
            now,
        ):
            if self.fail_action:
                raise RuntimeError("simulated maintenance action insert failure")
            return super()._insert_maintenance_action(
                connection,
                action=action,
                simulation_session_id=simulation_session_id,
                action_code=action_code,
                now=now,
            )

    database = tmp_path / "approval-atomic.db"
    repository = FailingActionRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    _, accepted, decision, requested_work_order, _ = _recommendation_setup(repository)
    repository.decide_recommendation(
        recommendation=accepted,
        decision=decision,
        work_order=requested_work_order,
        request_idempotency_key="http-recommendation-accept-001",
        request_fingerprint="recommendation-001:accept",
    )
    approved_work_order = requested_work_order.model_copy(
        update={
            "status": transition_work_order(
                requested_work_order.status,
                WorkOrderStatus.APPROVED,
            )
        }
    )
    action = plan_maintenance_action(
        work_order=approved_work_order,
        maintenance_action_id="MAINTENANCE-ACTION-001",
        idempotency_key="http-work-order-approve-001",
    )
    command = {
        "work_order": approved_work_order,
        "action": action,
        "simulation_session_id": "DEMO-SESSION-001",
        "actor_id": "manager-001",
        "approved_at": decision.decided_at + timedelta(minutes=5),
        "request_idempotency_key": "http-work-order-approve-001",
        "request_fingerprint": "work-order-001:approve",
    }

    with pytest.raises(RuntimeError, match="simulated maintenance action insert failure"):
        repository.approve_work_order(**command)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM closed_loop_work_orders").fetchone()[0] == "requested"
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_maintenance_actions"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_idempotency_records WHERE idempotency_key='http-work-order-approve-001'"
        ).fetchone()[0] == 0

    repository.fail_action = False
    first = repository.approve_work_order(**command)
    replay = repository.approve_work_order(**command)
    assert first["replayed"] is False
    assert replay == {**first, "replayed": True}
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM closed_loop_work_orders").fetchone()[0] == "approved"
        assert connection.execute(
            "SELECT status FROM closed_loop_maintenance_actions"
        ).fetchone()[0] == "planned"


def test_closed_loop_completion_is_atomic_and_does_not_auto_request_replay(tmp_path: Path) -> None:
    database = tmp_path / "closed-loop.db"
    repository = MaintenanceRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=20)

    assert repository.start_maintenance(
        _started(action, cause, started_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    ) == {
        "status": "in_progress",
        "maintenance_action_id": action.maintenance_action_id,
        "replayed": False,
    }
    result = repository.complete_maintenance(
        _completed(action, cause, started_at, completed_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        outcome="tool replaced",
        request_idempotency_key="http-maintenance-complete-001",
        request_fingerprint="maintenance-action-001:complete",
    )
    assert result == {
        "status": "completed",
        "maintenance_event_id": "MAINTENANCE-EVENT-001",
        "replayed": False,
    }

    state = repository.equipment_state(
        workspace_id=DEFAULT_WORKSPACE_ID,
        equipment_id=action.equipment_id,
    )
    assert state is not None
    assert state["state_version"] == 1
    assert state["state"] == {
        "tool_wear_min": {"unit": "min", "value": 0}
    }
    activities = repository.list_event_activity(
        workspace_id=DEFAULT_WORKSPACE_ID,
        event_id="RISK-EVENT-001",
    )
    assert [item["activity_type"] for item in activities] == [
        "recommendation.materialized",
        "recommendation.accepted",
        "work_order.requested",
        "work_order.approved",
        "maintenance_action.planned",
        "work_order.in_progress",
        "maintenance.started",
        "work_order.completed",
        "maintenance_action.completed",
        "maintenance.completed",
        "equipment.state_updated",
    ]
    assert all(item["equipment_id"] == action.equipment_id for item in activities)
    accepted_activity = next(
        item for item in activities if item["activity_type"] == "recommendation.accepted"
    )
    assert accepted_activity["actor_user_id"] == "manager-001"
    assert accepted_activity["before_status"] == "proposed"
    assert accepted_activity["after_status"] == "accepted"
    completion_activity = next(
        item for item in activities if item["activity_type"] == "maintenance.completed"
    )
    assert completion_activity["maintenance_event_id"] == "MAINTENANCE-EVENT-001"
    with sqlite3.connect(database) as connection:
        statuses = connection.execute(
            """
            SELECT w.status,a.status
            FROM closed_loop_work_orders w
            JOIN closed_loop_maintenance_actions a ON a.work_order_id=w.work_order_id
            WHERE a.maintenance_action_id=?
            """,
            (action.maintenance_action_id,),
        ).fetchone()
        event_types = [
            row[0]
            for row in connection.execute(
                "SELECT event_type FROM transactional_outbox WHERE event_type LIKE 'maintenance.%' ORDER BY created_at,id"
            ).fetchall()
        ]
        persisted_patch = json.loads(
            connection.execute(
                "SELECT state_patch_json FROM closed_loop_maintenance_events"
            ).fetchone()[0]
        )
    assert statuses == ("completed", "completed")
    assert event_types == ["maintenance.started", "maintenance.completed"]
    assert persisted_patch == {
        "tool_wear_min": {"operation": "reset", "unit": "min", "value": 0}
    }


def test_closed_loop_commands_replay_same_result_and_conflict_on_changed_payload(tmp_path: Path) -> None:
    database = tmp_path / "idempotency.db"
    repository = MaintenanceRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    event = _started(action, cause, started_at)

    first = repository.start_maintenance(
        event,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )
    replay = repository.start_maintenance(
        event,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )
    assert first["replayed"] is False
    assert replay == {**first, "replayed": True}

    changed = event.model_copy(update={"event_id": "OUTBOX-MAINTENANCE-CHANGED"})
    with pytest.raises(IdempotencyConflict, match="idempotency_key_conflict"):
        repository.start_maintenance(
            changed,
            workspace_id=DEFAULT_WORKSPACE_ID,
            actor_id="technician-001",
            request_idempotency_key="http-maintenance-start-001",
            request_fingerprint="maintenance-action-001:start-changed",
        )

    with sqlite3.connect(repository.database) as connection:
        stored_http_key = connection.execute(
            "SELECT idempotency_key FROM closed_loop_idempotency_records WHERE command_type='maintenance.started'"
        ).fetchone()[0]
        delivery_payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM transactional_outbox WHERE event_type='maintenance.started'"
            ).fetchone()[0]
        )
    assert stored_http_key == "http-maintenance-start-001"
    assert delivery_payload["idempotency_key"] == "maintenance-action-001:1"
    assert stored_http_key != delivery_payload["idempotency_key"]


def test_distinct_request_key_cannot_repeat_an_already_started_transition(tmp_path: Path) -> None:
    database = tmp_path / "transition-race.db"
    repository = MaintenanceRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    first_event = _started(action, cause, started_at)
    repository.start_maintenance(
        first_event,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )
    competing_event = first_event.model_copy(
        update={
            "event_id": "OUTBOX-MAINTENANCE-COMPETING",
            "idempotency_key": "maintenance-action-001:competing",
            "state_version": 2,
        }
    )

    with pytest.raises(InvalidTransition, match="maintenance start requires"):
        repository.start_maintenance(
            competing_event,
            workspace_id=DEFAULT_WORKSPACE_ID,
            actor_id="technician-002",
            request_idempotency_key="http-maintenance-start-competing",
            request_fingerprint="maintenance-action-001:start-competing",
        )

    with sqlite3.connect(repository.database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM transactional_outbox WHERE event_type='maintenance.started'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_idempotency_records WHERE idempotency_key='http-maintenance-start-competing'"
        ).fetchone()[0] == 0


def test_closed_loop_mutation_requires_authenticated_workspace_scope_and_exact_lineage(
    tmp_path: Path,
) -> None:
    database = tmp_path / "scope-and-lineage.db"
    repository = MaintenanceRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    event = _started(action, cause, started_at)

    with pytest.raises(ProjectContextError, match="not assigned"):
        repository.start_maintenance(
            event,
            workspace_id="other-tenant-workspace",
            actor_id="technician-001",
            request_idempotency_key="http-maintenance-start-001",
            request_fingerprint="maintenance-action-001:start",
        )

    wrong_lineage = event.model_copy(
        update={
            "caused_by": cause.model_copy(update={"source_evidence_id": "EVIDENCE-OTHER"})
        }
    )
    with pytest.raises(ValueError, match="Evidence lineage"):
        repository.start_maintenance(
            wrong_lineage,
            workspace_id=DEFAULT_WORKSPACE_ID,
            actor_id="technician-001",
            request_idempotency_key="http-maintenance-start-wrong",
            request_fingerprint="maintenance-action-001:start-wrong-lineage",
        )

    assert repository.start_maintenance(
        event,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )["status"] == "in_progress"


def test_completion_rolls_back_state_activity_outbox_and_idempotency_together(tmp_path: Path) -> None:
    class FailingOutboxRepository(MaintenanceRepository):
        fail_enqueue = False

        def _enqueue(self, connection, *, scope, event, payload, now):
            if self.fail_enqueue:
                raise RuntimeError("simulated outbox failure")
            return super()._enqueue(
                connection,
                scope=scope,
                event=event,
                payload=payload,
                now=now,
            )

    database = tmp_path / "rollback.db"
    repository = FailingOutboxRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    repository.start_maintenance(
        _started(action, cause, started_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )
    repository.fail_enqueue = True

    with pytest.raises(RuntimeError, match="simulated outbox failure"):
        repository.complete_maintenance(
            _completed(action, cause, started_at, started_at + timedelta(minutes=20)),
            workspace_id=DEFAULT_WORKSPACE_ID,
            actor_id="technician-001",
            outcome="tool replaced",
            request_idempotency_key="http-maintenance-complete-001",
            request_fingerprint="maintenance-action-001:complete",
        )

    with sqlite3.connect(database) as connection:
        statuses = connection.execute(
            """
            SELECT w.status,a.status
            FROM closed_loop_work_orders w
            JOIN closed_loop_maintenance_actions a ON a.work_order_id=w.work_order_id
            WHERE a.maintenance_action_id=?
            """,
            (action.maintenance_action_id,),
        ).fetchone()
        assert connection.execute("SELECT COUNT(*) FROM closed_loop_maintenance_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM closed_loop_equipment_state").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_activities WHERE activity_type='maintenance.completed'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_idempotency_records WHERE idempotency_key='http-maintenance-complete-001'"
        ).fetchone()[0] == 0
    assert statuses == ("in_progress", "in_progress")


def test_equipment_state_compare_and_swap_rejects_stale_update_and_insert(tmp_path: Path) -> None:
    database = tmp_path / "equipment-state-cas.db"
    repository = MaintenanceRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=20)
    repository.start_maintenance(
        _started(action, cause, started_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )
    repository.complete_maintenance(
        _completed(action, cause, started_at, completed_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        outcome="tool replaced",
        request_idempotency_key="http-maintenance-complete-001",
        request_fingerprint="maintenance-action-001:complete",
    )

    with repository._connect() as connection:
        scope = repository.project_context.resolve(
            DEFAULT_WORKSPACE_ID,
            connection=connection,
        )
        with pytest.raises(InvalidTransition, match="changed concurrently"):
            repository._persist_equipment_state(
                connection,
                scope=scope,
                equipment_id=action.equipment_id,
                expected_version=0,
                new_version=1,
                state={"tool_wear_min": {"value": 0, "unit": "min"}},
                maintenance_event_id="MAINTENANCE-EVENT-001",
                updated_at=completed_at.isoformat(),
            )
        with pytest.raises(InvalidTransition, match="created concurrently"):
            repository._persist_equipment_state(
                connection,
                scope=scope,
                equipment_id=action.equipment_id,
                expected_version=None,
                new_version=1,
                state={"tool_wear_min": {"value": 0, "unit": "min"}},
                maintenance_event_id="MAINTENANCE-EVENT-001",
                updated_at=completed_at.isoformat(),
            )

    state = repository.equipment_state(
        workspace_id=DEFAULT_WORKSPACE_ID,
        equipment_id=action.equipment_id,
    )
    assert state is not None
    assert state["state_version"] == 1
    assert state["last_maintenance_event_id"] == "MAINTENANCE-EVENT-001"


def test_equipment_state_concurrency_conflict_rolls_back_completion(tmp_path: Path) -> None:
    class ConflictingEquipmentStateRepository(MaintenanceRepository):
        def _persist_equipment_state(self, *args, **kwargs):
            raise InvalidTransition("equipment state was changed concurrently")

    database = tmp_path / "equipment-state-conflict.db"
    repository = ConflictingEquipmentStateRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    repository.start_maintenance(
        _started(action, cause, started_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )

    with pytest.raises(InvalidTransition, match="changed concurrently"):
        repository.complete_maintenance(
            _completed(action, cause, started_at, started_at + timedelta(minutes=20)),
            workspace_id=DEFAULT_WORKSPACE_ID,
            actor_id="technician-001",
            outcome="tool replaced",
            request_idempotency_key="http-maintenance-complete-001",
            request_fingerprint="maintenance-action-001:complete",
        )

    with sqlite3.connect(database) as connection:
        statuses = connection.execute(
            """
            SELECT w.status,a.status
            FROM closed_loop_work_orders w
            JOIN closed_loop_maintenance_actions a ON a.work_order_id=w.work_order_id
            WHERE a.maintenance_action_id=?
            """,
            (action.maintenance_action_id,),
        ).fetchone()
        assert connection.execute("SELECT COUNT(*) FROM closed_loop_maintenance_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM closed_loop_equipment_state").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_activities WHERE activity_type='maintenance.completed'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM transactional_outbox WHERE event_type='maintenance.completed'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM closed_loop_idempotency_records WHERE idempotency_key='http-maintenance-complete-001'"
        ).fetchone()[0] == 0
    assert statuses == ("in_progress", "in_progress")


def test_replay_request_requires_completion_and_advances_lifecycle_version(tmp_path: Path) -> None:
    database = tmp_path / "replay.db"
    repository = MaintenanceRepository(
        database,
        project_context=SQLiteProjectContextResolver(database),
    )
    action, cause = _foundation(repository)
    started_at = datetime(2026, 8, 18, 1, 10, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=20)
    repository.start_maintenance(
        _started(action, cause, started_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        request_idempotency_key="http-maintenance-start-001",
        request_fingerprint="maintenance-action-001:start",
    )
    repository.complete_maintenance(
        _completed(action, cause, started_at, completed_at),
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="technician-001",
        outcome="tool replaced",
        request_idempotency_key="http-maintenance-complete-001",
        request_fingerprint="maintenance-action-001:complete",
    )
    replay = MaintenanceReplayRequestedEvent(
        event_id="OUTBOX-MAINTENANCE-003",
        idempotency_key="maintenance-action-001:3",
        state_version=3,
        simulation_session_id="DEMO-SESSION-001",
        maintenance_event_id="MAINTENANCE-EVENT-001",
        maintenance_action_id=action.maintenance_action_id,
        equipment_id=action.equipment_id,
        maintenance_started_at=started_at,
        maintenance_completed_at=completed_at,
        restart_at=completed_at,
        action_code="TOOL_REPLACEMENT",
        state_patch={"tool_wear_min": {"operation": "reset", "value": 0, "unit": "min"}},
        caused_by=cause,
    )

    assert repository.request_replay(
        replay,
        workspace_id=DEFAULT_WORKSPACE_ID,
        actor_id="system",
        request_idempotency_key="http-maintenance-replay-001",
        request_fingerprint="maintenance-action-001:replay",
    ) == {
        "status": "replay_requested",
        "maintenance_event_id": "MAINTENANCE-EVENT-001",
        "replayed": False,
    }
    state = repository.equipment_state(
        workspace_id=DEFAULT_WORKSPACE_ID,
        equipment_id=action.equipment_id,
    )
    assert state is not None and state["state_version"] == 1
    with sqlite3.connect(repository.database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM transactional_outbox WHERE event_type='maintenance.replay_requested'"
        ).fetchone()
        persisted_restart_at = connection.execute(
            "SELECT restart_at FROM closed_loop_maintenance_actions WHERE maintenance_action_id=?",
            (action.maintenance_action_id,),
        ).fetchone()[0]
        maintenance_event_columns = {
            column[1]
            for column in connection.execute("PRAGMA table_info(closed_loop_maintenance_events)")
        }
    assert row is not None
    assert json.loads(row[0])["maintenance_event_id"] == "MAINTENANCE-EVENT-001"
    assert persisted_restart_at == completed_at.isoformat()
    assert "restart_at" not in maintenance_event_columns
