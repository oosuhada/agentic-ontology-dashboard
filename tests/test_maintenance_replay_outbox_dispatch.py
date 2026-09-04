from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.infra.db.migrations import migrate
from app.infra.messaging.maintenance_replay_jsonl import (
    MAINTENANCE_REPLAY_EVENT_TYPES,
    MaintenanceReplayDeliveryConflict,
    MaintenanceReplayJsonlHandler,
)
from app.infra.messaging.outbox import (
    OutboxMessage,
    ProjectOutboxRepository,
    ProjectOutboxWorker,
)
from app.maintenance.integration import (
    CoolingSystemRestoreStatePatch,
    MaintenanceCause,
    MaintenanceCompletedEvent,
    MaintenanceReplayRequestedEvent,
    MaintenanceStartedEvent,
    ToolReplacementStatePatch,
)


ORGANIZATION_ID = "org-ontology-demo"
PROJECT_ID = "manufacturing-demo-project"
WORKSPACE_ID = "manufacturing-demo"
ACTION_ID = "MAINTENANCE-ACTION-001"
EQUIPMENT_ID = "CNC-S02-L04-03"
SESSION_ID = "SIMULATION-SESSION-001"


def setup_database(tmp_path: Path) -> Path:
    database = tmp_path / "maintenance-outbox.db"
    migrate(str(database))
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO organizations(id,slug,name,created_at) VALUES (?,?,?,?)",
            (ORGANIZATION_ID, "ontology-demo", "Ontology Demo", now),
        )
        connection.execute(
            """
            INSERT INTO projects(
                id,organization_id,slug,display_name,description,domain_pack_code,
                status,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                PROJECT_ID,
                ORGANIZATION_ID,
                "manufacturing-demo",
                "Manufacturing Demo",
                "",
                "predictive-maintenance",
                "active",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO workspaces(
                id,organization_id,project_id,slug,display_name,domain_pack,created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                WORKSPACE_ID,
                ORGANIZATION_ID,
                PROJECT_ID,
                "manufacturing-demo",
                "Manufacturing Demo",
                "predictive-maintenance",
                now,
            ),
        )
    return database


def cause() -> MaintenanceCause:
    return MaintenanceCause(
        source_product_result_id="RESULT-001",
        source_evidence_id="EVIDENCE-001",
        decision_id="DECISION-001",
    )


def replay_events() -> list[dict[str, object]]:
    started_at = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=30)
    restart_at = completed_at + timedelta(minutes=10)
    return [
        MaintenanceStartedEvent(
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "maintenance-started")),
            idempotency_key=f"{ACTION_ID}:1",
            state_version=1,
            simulation_session_id=SESSION_ID,
            maintenance_action_id=ACTION_ID,
            work_order_id="WORK-ORDER-001",
            equipment_id=EQUIPMENT_ID,
            maintenance_started_at=started_at,
            action_code="TOOL_REPLACEMENT",
            caused_by=cause(),
        ).as_payload(),
        MaintenanceCompletedEvent(
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "maintenance-completed")),
            idempotency_key=f"{ACTION_ID}:2",
            state_version=2,
            simulation_session_id=SESSION_ID,
            maintenance_action_id=ACTION_ID,
            maintenance_event_id="MAINTENANCE-EVENT-001",
            equipment_id=EQUIPMENT_ID,
            maintenance_started_at=started_at,
            maintenance_completed_at=completed_at,
            action_code="TOOL_REPLACEMENT",
            state_patch=ToolReplacementStatePatch(),
            caused_by=cause(),
        ).as_payload(),
        MaintenanceReplayRequestedEvent(
            event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "maintenance-replay")),
            idempotency_key=f"{ACTION_ID}:3",
            state_version=3,
            simulation_session_id=SESSION_ID,
            maintenance_action_id=ACTION_ID,
            maintenance_event_id="MAINTENANCE-EVENT-001",
            equipment_id=EQUIPMENT_ID,
            maintenance_started_at=started_at,
            maintenance_completed_at=completed_at,
            restart_at=restart_at,
            action_code="TOOL_REPLACEMENT",
            state_patch=ToolReplacementStatePatch(),
            caused_by=cause(),
        ).as_payload(),
    ]


def cooling_replay_event() -> dict[str, object]:
    completed_at = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    return MaintenanceReplayRequestedEvent(
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "cooling-maintenance-replay")),
        idempotency_key="COOLING-ACTION-001:3",
        state_version=3,
        simulation_session_id=SESSION_ID,
        maintenance_event_id="COOLING-MAINTENANCE-EVENT-001",
        maintenance_action_id="COOLING-ACTION-001",
        equipment_id=EQUIPMENT_ID,
        maintenance_completed_at=completed_at,
        restart_at=completed_at + timedelta(minutes=5),
        action_code="COOLING_SYSTEM_RESTORE",
        state_patch=CoolingSystemRestoreStatePatch(),
        caused_by=cause(),
    ).as_payload()


def insert_outbox(
    database: Path,
    payload: dict[str, object],
    *,
    organization_id: str = ORGANIZATION_ID,
    project_id: str = PROJECT_ID,
    created_at: str | None = None,
) -> None:
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO transactional_outbox(
                id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                event_type,payload_json,status,attempt_count,created_at,available_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload["event_id"],
                organization_id,
                project_id,
                WORKSPACE_ID,
                "maintenance_action",
                ACTION_ID,
                payload["event_type"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "pending",
                0,
                timestamp,
                timestamp,
            ),
        )


def worker(database: Path, event_file: Path, *, max_attempts: int = 3):
    handler = MaintenanceReplayJsonlHandler(event_file)
    return ProjectOutboxWorker(
        ProjectOutboxRepository(database),
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        handlers={
            event_type: (handler.handler_code, handler)
            for event_type in MAINTENANCE_REPLAY_EVENT_TYPES
        },
        max_attempts=max_attempts,
        retry_delay_seconds=1,
        worker_id="maintenance-dispatch-test",
        lease_seconds=5,
    )


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_worker_delivers_validated_maintenance_events_in_state_order(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    timestamp = datetime.now(timezone.utc).isoformat()
    for event in reversed(replay_events()):
        insert_outbox(database, event, created_at=timestamp)
    event_file = tmp_path / "gen-data-inbox" / "maintenance-events.jsonl"

    assert worker(database, event_file).drain() == 3

    delivered = read_jsonl(event_file)
    assert [item["event_type"] for item in delivered] == [
        "maintenance.started",
        "maintenance.completed",
        "maintenance.replay_requested",
    ]
    assert [item["state_version"] for item in delivered] == [1, 2, 3]
    with sqlite3.connect(database) as connection:
        states = connection.execute(
            """
            SELECT status,attempt_count FROM transactional_outbox
            WHERE event_type LIKE 'maintenance.%' ORDER BY payload_json
            """
        ).fetchall()
        deliveries = connection.execute(
            "SELECT event_type,handler_code FROM outbox_delivery_log ORDER BY delivered_at,outbox_id"
        ).fetchall()
    assert states == [("processed", 1), ("processed", 1), ("processed", 1)]
    assert {row[0] for row in deliveries} == set(MAINTENANCE_REPLAY_EVENT_TYPES)
    assert {row[1] for row in deliveries} == {"maintenance-replay-jsonl-v1"}


def test_jsonl_dispatch_preserves_cooling_action_and_typed_patch(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    event = cooling_replay_event()
    insert_outbox(database, event)
    event_file = tmp_path / "gen-data-inbox" / "maintenance-events.jsonl"

    assert worker(database, event_file).drain() == 1

    assert read_jsonl(event_file) == [event]


def test_jsonl_handler_tolerates_same_event_redelivery_and_rejects_conflict(
    tmp_path: Path,
) -> None:
    payload = replay_events()[0]
    event_file = tmp_path / "maintenance-events.jsonl"
    handler = MaintenanceReplayJsonlHandler(event_file)
    message = OutboxMessage(
        id=str(payload["event_id"]),
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        aggregate_type="maintenance_action",
        aggregate_id=ACTION_ID,
        event_type=str(payload["event_type"]),
        payload=payload,
        attempt_count=1,
        lease_token="lease-token",
    )

    handler(message)
    handler(message)
    assert len(read_jsonl(event_file)) == 1

    conflicting = dict(payload)
    conflicting["equipment_id"] = "CNC-CONFLICT"
    conflict_message = OutboxMessage(
        **{**message.__dict__, "payload": conflicting}
    )
    try:
        handler(conflict_message)
    except MaintenanceReplayDeliveryConflict as exc:
        assert exc.retryable is False
    else:
        raise AssertionError("conflicting event redelivery must fail")


def test_invalid_known_event_retries_then_dead_letters(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    invalid = replay_events()[1]
    invalid["state_patch"] = {
        "tool_wear_min": {"operation": "reset", "value": 10, "unit": "min"}
    }
    insert_outbox(database, invalid)
    dispatcher = worker(database, tmp_path / "maintenance-events.jsonl", max_attempts=2)

    assert dispatcher.process_once() is True
    with sqlite3.connect(database) as connection:
        first = connection.execute(
            "SELECT status,attempt_count,last_error FROM transactional_outbox"
        ).fetchone()
        connection.execute(
            "UPDATE transactional_outbox SET available_at=?",
            (datetime.now(timezone.utc).isoformat(),),
        )
    assert first[0:2] == ("retry", 1)
    assert "maintenance integration event schema validation failed" in first[2]

    assert dispatcher.process_once() is True
    with sqlite3.connect(database) as connection:
        second = connection.execute(
            "SELECT status,attempt_count FROM transactional_outbox"
        ).fetchone()
    assert second == ("dead_letter", 2)
    assert not (tmp_path / "maintenance-events.jsonl").exists()

    dispatcher.repository.replay_dead_letter(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        event_id=str(invalid["event_id"]),
    )
    with sqlite3.connect(database) as connection:
        replayed = connection.execute(
            "SELECT status,attempt_count,last_error FROM transactional_outbox"
        ).fetchone()
    assert replayed == ("pending", 0, None)


def test_expired_lease_is_recovered_without_duplicate_delivery(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    payload = replay_events()[0]
    insert_outbox(database, payload)
    repository = ProjectOutboxRepository(database)
    claimed = repository.claim_one(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        event_types=MAINTENANCE_REPLAY_EVENT_TYPES,
        max_attempts=3,
        worker_id="crashed-worker",
        lease_seconds=5,
    )
    assert claimed is not None
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE transactional_outbox SET lease_expires_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                payload["event_id"],
            ),
        )

    event_file = tmp_path / "maintenance-events.jsonl"
    assert worker(database, event_file).process_once() is True
    assert len(read_jsonl(event_file)) == 1
    with sqlite3.connect(database) as connection:
        state = connection.execute(
            "SELECT status,attempt_count FROM transactional_outbox"
        ).fetchone()
    assert state == ("processed", 2)


def test_append_before_delivery_commit_is_redelivered_without_duplicate(
    tmp_path: Path,
) -> None:
    database = setup_database(tmp_path)
    payload = replay_events()[0]
    insert_outbox(database, payload)
    repository = ProjectOutboxRepository(database)
    claimed = repository.claim_one(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        event_types=MAINTENANCE_REPLAY_EVENT_TYPES,
        max_attempts=3,
        worker_id="crashed-after-append",
        lease_seconds=5,
    )
    assert claimed is not None

    event_file = tmp_path / "maintenance-events.jsonl"
    MaintenanceReplayJsonlHandler(event_file)(claimed)
    assert len(read_jsonl(event_file)) == 1

    with sqlite3.connect(database) as connection:
        before_recovery = connection.execute(
            "SELECT status,attempt_count FROM transactional_outbox"
        ).fetchone()
        delivery_count = connection.execute(
            "SELECT COUNT(*) FROM outbox_delivery_log"
        ).fetchone()[0]
        connection.execute(
            "UPDATE transactional_outbox SET lease_expires_at=? WHERE id=?",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                payload["event_id"],
            ),
        )
    assert before_recovery == ("processing", 1)
    assert delivery_count == 0

    assert worker(database, event_file).process_once() is True

    assert len(read_jsonl(event_file)) == 1
    with sqlite3.connect(database) as connection:
        recovered = connection.execute(
            "SELECT status,attempt_count FROM transactional_outbox"
        ).fetchone()
        deliveries = connection.execute(
            "SELECT outbox_id,handler_code FROM outbox_delivery_log"
        ).fetchall()
    assert recovered == ("processed", 2)
    assert deliveries == [
        (str(payload["event_id"]), "maintenance-replay-jsonl-v1")
    ]


def test_worker_leaves_unregistered_outbox_events_untouched(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO transactional_outbox(
                id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                event_type,payload_json,status,attempt_count,created_at,available_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(uuid.uuid4()),
                ORGANIZATION_ID,
                PROJECT_ID,
                WORKSPACE_ID,
                "dataset_version",
                "DATASET-001",
                "dataset.version.relational_ready",
                "{}",
                "pending",
                0,
                now,
                now,
            ),
        )

    assert worker(database, tmp_path / "maintenance-events.jsonl").process_once() is False
    with sqlite3.connect(database) as connection:
        state = connection.execute(
            "SELECT status,attempt_count FROM transactional_outbox"
        ).fetchone()
    assert state == ("pending", 0)


def test_retrying_equipment_does_not_block_another_equipment(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    first = replay_events()[1]
    first["state_patch"] = {
        "tool_wear_min": {"operation": "reset", "value": 10, "unit": "min"}
    }
    second = replay_events()[0]
    second["event_id"] = str(uuid.uuid4())
    second["idempotency_key"] = "MAINTENANCE-ACTION-002:1"
    second["maintenance_action_id"] = "MAINTENANCE-ACTION-002"
    second["equipment_id"] = "CNC-S02-L04-04"
    timestamp = datetime.now(timezone.utc).isoformat()
    insert_outbox(database, first, created_at=timestamp)
    insert_outbox(database, second, created_at=timestamp)
    event_file = tmp_path / "maintenance-events.jsonl"
    dispatcher = worker(database, event_file)

    assert dispatcher.process_once() is True
    assert dispatcher.process_once() is True

    assert read_jsonl(event_file) == [second]
    with sqlite3.connect(database) as connection:
        states = dict(
            connection.execute(
                "SELECT equipment_id,status FROM ("
                "SELECT json_extract(payload_json,'$.equipment_id') AS equipment_id,status "
                "FROM transactional_outbox)"
            ).fetchall()
        )
    assert states == {
        EQUIPMENT_ID: "retry",
        "CNC-S02-L04-04": "processed",
    }
