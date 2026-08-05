from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ontology_dashboard.identity import IdentityService
from ontology_dashboard.migrations import migrate
from ontology_dashboard.outbox import OutboxRepository, OutboxWorker, default_outbox_worker
from ontology_dashboard.role_workflow_repository import RoleWorkflowRepository


def setup_database(tmp_path: Path) -> Path:
    database = tmp_path / "outbox.db"
    migrate(str(database))
    IdentityService(database, app_env="test", seed_demo=True)
    return database


def test_outbox_worker_processes_project_scoped_field_event_once(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    identity = IdentityService(database, app_env="test", seed_demo=True)
    user = identity.repository.authenticate("engineer@ontology.local", "Engineer!2026")
    principal = identity.repository.principal(user["id"])
    workflows = RoleWorkflowRepository(database)
    action = workflows.record_field_action(
        workspace_id="manufacturing-demo",
        event_id="EVT-OUTBOX-1",
        action="complete",
        actor_user_id=principal.user_id,
        actor_display_name=principal.display_name,
        payload={"checklist": "complete"},
    )
    assert action["project_id"] == "manufacturing-demo-project"

    worker = default_outbox_worker(database)
    assert worker.process_once() is True
    assert worker.process_once() is False

    with sqlite3.connect(database) as connection:
        status = connection.execute(
            "SELECT status,attempt_count FROM transactional_outbox"
        ).fetchone()
        delivery = connection.execute(
            "SELECT project_id,event_type,handler_code FROM outbox_delivery_log"
        ).fetchone()
    assert status == ("processed", 1)
    assert delivery == (
        "manufacturing-demo-project",
        "field_task.complete",
        "delivery-log-v1",
    )


def test_outbox_worker_retries_then_dead_letters_unknown_event(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    outbox_id = str(uuid.uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO transactional_outbox(
                id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                event_type,payload_json,status,attempt_count,created_at,available_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                outbox_id,
                "org-ontology-demo",
                "manufacturing-demo-project",
                "manufacturing-demo",
                "fixture",
                "fixture-1",
                "unknown.event",
                json.dumps({"value": 1}),
                "pending",
                0,
                now,
                now,
            ),
        )

    worker = OutboxWorker(database, max_attempts=2, retry_delay_seconds=1)
    assert worker.process_once() is True
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE transactional_outbox SET available_at=? WHERE id=?",
            (now, outbox_id),
        )
    assert worker.process_once() is True

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status,attempt_count,last_error FROM transactional_outbox WHERE id=?",
            (outbox_id,),
        ).fetchone()
        deliveries = connection.execute(
            "SELECT COUNT(*) FROM outbox_delivery_log WHERE outbox_id=?",
            (outbox_id,),
        ).fetchone()[0]
    assert row[0] == "dead_letter"
    assert row[1] == 2
    assert "UnknownOutboxEvent" in row[2]
    assert deliveries == 0

    repository = OutboxRepository(database)
    replayed = repository.replay_dead_letter(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        event_id=outbox_id,
    )
    assert replayed.attempt_count == 0
    assert repository.metrics(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
    )["pending"] == 1


def test_outbox_processing_lease_recovers_after_worker_crash(tmp_path: Path) -> None:
    database = setup_database(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    outbox_id = str(uuid.uuid4())
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO transactional_outbox(
                id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                event_type,payload_json,status,attempt_count,created_at,available_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                outbox_id,
                "org-ontology-demo",
                "manufacturing-demo-project",
                "manufacturing-demo",
                "fixture",
                "fixture-lease",
                "unknown.event",
                json.dumps({"value": 2}),
                "pending",
                0,
                now,
                now,
            ),
        )
    repository = OutboxRepository(database)
    first = repository.claim_one(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        max_attempts=3,
        worker_id="crashed-worker",
        lease_seconds=5,
    )
    assert first is not None
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE transactional_outbox SET lease_expires_at=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), outbox_id),
        )
    recovered = repository.claim_one(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        max_attempts=3,
        worker_id="replacement-worker",
        lease_seconds=5,
    )
    assert recovered is not None
    assert recovered.id == outbox_id
    assert recovered.attempt_count == 2
    assert recovered.lease_owner == "replacement-worker"
