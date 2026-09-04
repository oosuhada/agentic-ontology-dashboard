#!/usr/bin/env python3
"""Smoke-test the local Backend outbox -> gen_data Runtime Overlay bridge.

This script uses a temporary SQLite database instead of production DB access.
It verifies the same local contract boundary used in operations:

SQLite transactional_outbox -> maintenance_replay_dispatcher --drain
-> shared maintenance-events.jsonl -> gen_data FastAPI Runtime Overlay
-> runtime_overlay/observations_available.jsonl -> Backend reader.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = ROOT / "systems" / "backend"
DEFAULT_WORK_ROOT = Path("/private/tmp/ontology-gen-data-full-local-bridge")

ORGANIZATION_ID = "org-local-bridge"
PROJECT_ID = "project-local-bridge"
WORKSPACE_ID = "workspace-local-bridge"
ACTION_ID = "ACTION-LOCAL-BRIDGE-001"
EQUIPMENT_ID = "CNC-S01-L01-01"
SESSION_ID = "DEMO-001"
RUN_ID = "SOURCE-RUN-FULL-BRIDGE-001"


def _backend_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND_PATH)
    if extra:
        env.update(extra)
    return env


def _run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        rendered = " ".join(args)
        raise RuntimeError(
            f"command failed ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )
    return result


def _insert_seed_outbox(database: Path) -> None:
    sys.path.insert(0, str(BACKEND_PATH))
    from app.infra.db.migrations import migrate
    from app.maintenance.integration import (
        MaintenanceCause,
        MaintenanceCompletedEvent,
        MaintenanceReplayRequestedEvent,
        MaintenanceStartedEvent,
        ToolReplacementStatePatch,
    )

    migrate(str(database))
    now = datetime.now(timezone.utc).isoformat()
    started_at = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=30)
    restart_at = started_at + timedelta(minutes=40)
    cause = MaintenanceCause(
        source_product_result_id="RESULT-LOCAL-BRIDGE-001",
        source_evidence_id="EVIDENCE-LOCAL-BRIDGE-001",
        decision_id="DECISION-LOCAL-BRIDGE-001",
    )
    events = [
        MaintenanceStartedEvent(
            event_id="00000000-0000-5000-8000-000000001001",
            idempotency_key=f"{ACTION_ID}:1",
            state_version=1,
            simulation_session_id=SESSION_ID,
            maintenance_action_id=ACTION_ID,
            work_order_id="WO-LOCAL-BRIDGE-001",
            equipment_id=EQUIPMENT_ID,
            maintenance_started_at=started_at,
            action_code="TOOL_REPLACEMENT",
            caused_by=cause,
        ).as_payload(),
        MaintenanceCompletedEvent(
            event_id="00000000-0000-5000-8000-000000001002",
            idempotency_key=f"{ACTION_ID}:2",
            state_version=2,
            simulation_session_id=SESSION_ID,
            maintenance_action_id=ACTION_ID,
            maintenance_event_id="MAINT-LOCAL-BRIDGE-001",
            equipment_id=EQUIPMENT_ID,
            maintenance_started_at=started_at,
            maintenance_completed_at=completed_at,
            action_code="TOOL_REPLACEMENT",
            state_patch=ToolReplacementStatePatch(),
            caused_by=cause,
        ).as_payload(),
        MaintenanceReplayRequestedEvent(
            event_id="00000000-0000-5000-8000-000000001003",
            idempotency_key=f"{ACTION_ID}:3",
            state_version=3,
            simulation_session_id=SESSION_ID,
            maintenance_action_id=ACTION_ID,
            maintenance_event_id="MAINT-LOCAL-BRIDGE-001",
            equipment_id=EQUIPMENT_ID,
            maintenance_started_at=started_at,
            maintenance_completed_at=completed_at,
            restart_at=restart_at,
            action_code="TOOL_REPLACEMENT",
            state_patch=ToolReplacementStatePatch(),
            caused_by=cause,
        ).as_payload(),
    ]

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO organizations(id,slug,name,created_at) VALUES (?,?,?,?)",
            (ORGANIZATION_ID, "local-bridge", "Local Bridge", now),
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
                "local-bridge",
                "Local Bridge",
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
                "local-bridge",
                "Local Bridge",
                "predictive-maintenance",
                now,
            ),
        )
        for event in reversed(events):
            connection.execute(
                """
                INSERT INTO transactional_outbox(
                    id,organization_id,project_id,workspace_id,aggregate_type,
                    aggregate_id,event_type,payload_json,status,attempt_count,
                    created_at,available_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event["event_id"],
                    ORGANIZATION_ID,
                    PROJECT_ID,
                    WORKSPACE_ID,
                    "maintenance_action",
                    ACTION_ID,
                    event["event_type"],
                    json.dumps(event, ensure_ascii=False, sort_keys=True),
                    "pending",
                    0,
                    now,
                    now,
                ),
            )


def _drain_dispatcher(database: Path, inbox_path: Path) -> dict[str, Any]:
    result = _run(
        [sys.executable, "-m", "app.maintenance_replay_dispatcher", "--drain"],
        cwd=ROOT,
        env=_backend_env(
            {
                "ONTOLOGY_DASHBOARD_DB": str(database),
                "ONTOLOGY_DASHBOARD_OUTBOX_ORGANIZATION_ID": ORGANIZATION_ID,
                "ONTOLOGY_DASHBOARD_OUTBOX_PROJECT_ID": PROJECT_ID,
                "ONTOLOGY_DASHBOARD_MAINTENANCE_REPLAY_EVENT_FILE": str(inbox_path),
            }
        ),
    )
    return json.loads(result.stdout)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_dispatch(database: Path, inbox_path: Path) -> None:
    rows = _read_jsonl(inbox_path)
    if [row["event_type"] for row in rows] != [
        "maintenance.started",
        "maintenance.completed",
        "maintenance.replay_requested",
    ]:
        raise AssertionError("maintenance replay inbox order is invalid")
    if [row["state_version"] for row in rows] != [1, 2, 3]:
        raise AssertionError("maintenance replay state_version order is invalid")
    if {row["simulation_session_id"] for row in rows} != {SESSION_ID}:
        raise AssertionError("maintenance replay session id does not match smoke run")
    if {row["equipment_id"] for row in rows} != {EQUIPMENT_ID}:
        raise AssertionError("maintenance replay equipment id does not match smoke target")

    with sqlite3.connect(database) as connection:
        states = connection.execute(
            """
            SELECT event_type,status,attempt_count FROM transactional_outbox
            WHERE event_type LIKE 'maintenance.%' ORDER BY payload_json
            """
        ).fetchall()
        deliveries = connection.execute(
            """
            SELECT event_type,handler_code FROM outbox_delivery_log
            ORDER BY delivered_at,outbox_id
            """
        ).fetchall()
    expected_states = [
        ("maintenance.started", "processed", 1),
        ("maintenance.completed", "processed", 1),
        ("maintenance.replay_requested", "processed", 1),
    ]
    if states != expected_states:
        raise AssertionError(f"unexpected outbox states: {states!r}")
    if {row[1] for row in deliveries} != {"maintenance-replay-jsonl-v1"}:
        raise AssertionError(f"unexpected delivery handlers: {deliveries!r}")


def _run_gen_data(gen_data_root: Path, inbox_path: Path, output_root: Path) -> dict[str, Any]:
    python = gen_data_root / ".venv" / "bin" / "python"
    if not python.exists():
        raise FileNotFoundError(
            f"gen_data virtualenv not found: {python}. "
            "Run `python3 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt` "
            "inside the gen_data checkout first."
        )

    program = f"""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app

root = Path({str(output_root)!r})
client = TestClient(create_app())
for path in ('/health/live', '/health/ready'):
    response = client.get(path)
    response.raise_for_status()
start = client.post('/api/runs', json={{
    'run_id': {RUN_ID!r},
    'simulation_session_id': {SESSION_ID!r},
    'start_at': '2026-08-18T01:00:00+00:00',
    'duration_hours': 2,
    'continuous': False,
    'publish_opcua': False,
}})
start.raise_for_status()
ticks = []
for index in range(5):
    tick = client.post('/api/runs/' + {RUN_ID!r} + '/tick')
    tick.raise_for_status()
    ticks.append(tick.json())
outputs = client.get('/api/runs/' + {RUN_ID!r} + '/outputs')
outputs.raise_for_status()
source_path = root / 'runs' / {RUN_ID!r} / 'source' / 'sensor_records.jsonl'
source_rows = [
    json.loads(line)
    for line in source_path.read_text(encoding='utf-8').splitlines()
    if line.strip()
]
available_path = root / 'runtime_overlay' / 'observations_available.jsonl'
available_rows = [
    json.loads(line)
    for line in available_path.read_text(encoding='utf-8').splitlines()
    if line.strip()
]
client.post('/api/runs/' + {RUN_ID!r} + '/stop')
print(json.dumps({{
    'tick_count': len(ticks),
    'last_sequence': ticks[-1]['last_sequence'],
    'source_record_count': ticks[-1]['source_record_count'],
    'output_counts': outputs.json()['counts'],
    'target_in_source': any(row.get('asset_id') == {EQUIPMENT_ID!r} for row in source_rows),
    'available_count': len(available_rows),
    'available_event_ids': [row['event_id'] for row in available_rows],
    'available_storage': [row['storage_reference'] for row in available_rows],
}}, sort_keys=True))
"""
    result = _run(
        [str(python), "-c", program],
        cwd=gen_data_root,
        env={
            **os.environ,
            "GEN_DATA_OUTPUT_DIR": str(output_root),
            "GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE": str(inbox_path),
        },
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _assert_gen_data(result: dict[str, Any]) -> None:
    if result["tick_count"] != 5:
        raise AssertionError(f"unexpected tick count: {result['tick_count']}")
    if result["source_record_count"] != 495:
        raise AssertionError(f"unexpected source record count: {result['source_record_count']}")
    if result["output_counts"]["canonical_observations"] != 495:
        raise AssertionError(f"unexpected canonical count: {result['output_counts']}")
    if result["target_in_source"]:
        raise AssertionError(f"{EQUIPMENT_ID} was not excluded from canonical source rows")
    if result["available_count"] != 1:
        raise AssertionError(f"unexpected availability count: {result['available_count']}")
    if result["available_event_ids"] != ["OVERLAY-AVAILABLE:MAINT-LOCAL-BRIDGE-001:post:1"]:
        raise AssertionError(f"unexpected availability ids: {result['available_event_ids']}")


def _read_backend_overlay(output_root: Path) -> list[dict[str, Any]]:
    sys.path.insert(0, str(BACKEND_PATH))
    from app.infra.live_predictive_maintenance_runtime import read_overlay_available_events

    return read_overlay_available_events(output_root)


def smoke(gen_data_root: Path, work_root: Path) -> dict[str, Any]:
    if work_root.exists():
        shutil.rmtree(work_root)
    inbox_path = work_root / "inbox" / "maintenance-events.jsonl"
    output_root = work_root / "output"
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    database = work_root / "ontology-dashboard-local.db"
    _insert_seed_outbox(database)

    first_drain = _drain_dispatcher(database, inbox_path)
    if first_drain != {"mode": "drain", "processed": 3}:
        raise AssertionError(f"unexpected dispatcher result: {first_drain!r}")
    _assert_dispatch(database, inbox_path)

    gen_data_result = _run_gen_data(gen_data_root, inbox_path, output_root)
    _assert_gen_data(gen_data_result)

    backend_events = _read_backend_overlay(output_root)
    if len(backend_events) != 1:
        raise AssertionError(f"unexpected backend overlay event count: {len(backend_events)}")
    event = backend_events[0]
    if event["equipment_id"] != EQUIPMENT_ID or event["batch_rows"] != 1:
        raise AssertionError(f"unexpected backend overlay event: {event!r}")

    second_drain = _drain_dispatcher(database, inbox_path)
    if second_drain != {"mode": "drain", "processed": 0}:
        raise AssertionError(f"unexpected idempotency drain result: {second_drain!r}")
    if len(_read_jsonl(inbox_path)) != 3:
        raise AssertionError("dispatcher re-drain appended duplicate maintenance events")

    return {
        "work_root": str(work_root),
        "database": str(database),
        "inbox": str(inbox_path),
        "output_root": str(output_root),
        "dispatcher_first_drain": first_drain,
        "dispatcher_second_drain": second_drain,
        "inbox_line_count": 3,
        "gen_data": gen_data_result,
        "backend_reader": {
            "event_count": len(backend_events),
            "event_id": event["event_id"],
            "equipment_id": event["equipment_id"],
            "batch_rows": event["batch_rows"],
            "storage_reference": event["storage_reference"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gen-data-root",
        type=Path,
        default=ROOT.parent / "gen-data",
        help="Path to the Biz-CollabCraft/gen_data checkout.",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=DEFAULT_WORK_ROOT,
        help="Temporary root for local SQLite, shared inbox, and gen_data output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = smoke(args.gen_data_root.expanduser().resolve(), args.work_root.expanduser())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
