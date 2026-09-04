from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from app.maintenance.integration import (
    MaintenanceCause,
    MaintenanceCompletedEvent,
    MaintenanceReplayRequestedEvent,
    MaintenanceStartedEvent,
)

ROOT = Path(__file__).resolve().parents[1]


def cause() -> MaintenanceCause:
    return MaintenanceCause(
        source_product_result_id="RESULT-001",
        source_evidence_id="EVIDENCE-001",
        decision_id="DECISION-001",
    )


def test_maintenance_event_schema_is_valid_draft_2020_12() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "maintenance-replay-event.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)


def test_owned_maintenance_events_pass_the_machine_contract() -> None:
    started_at = datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc)
    completed_at = started_at + timedelta(minutes=20)
    common = {
        "simulation_session_id": "DEMO-001",
        "maintenance_action_id": "ACTION-001",
        "equipment_id": "CNC-S02-L04-03",
        "caused_by": cause(),
    }

    events = [
        MaintenanceStartedEvent(
            event_id="INTEGRATION-001",
            idempotency_key="ACTION-001:1",
            state_version=1,
            work_order_id="WO-001",
            maintenance_started_at=started_at,
            **common,
        ),
        MaintenanceCompletedEvent(
            event_id="INTEGRATION-002",
            idempotency_key="ACTION-001:2",
            state_version=2,
            maintenance_event_id="MAINT-001",
            maintenance_started_at=started_at,
            maintenance_completed_at=completed_at,
            **common,
        ),
        MaintenanceReplayRequestedEvent(
            event_id="INTEGRATION-003",
            idempotency_key="ACTION-001:3",
            state_version=3,
            maintenance_event_id="MAINT-001",
            maintenance_started_at=started_at,
            maintenance_completed_at=completed_at,
            restart_at=completed_at,
            action_code="TOOL_REPLACEMENT",
            state_patch={"tool_wear_min": {"operation": "reset", "value": 0, "unit": "min"}},
            **common,
        ),
    ]

    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "maintenance-replay-event.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for event in events:
        payload = event.as_payload()
        assert list(validator.iter_errors(payload)) == []


def test_cooling_completion_uses_its_own_typed_state_patch() -> None:
    event = MaintenanceCompletedEvent(
        event_id="INTEGRATION-COOLING-002",
        idempotency_key="ACTION-COOLING-001:2",
        state_version=2,
        simulation_session_id="DEMO-001",
        maintenance_event_id="MAINT-COOLING-001",
        maintenance_action_id="ACTION-COOLING-001",
        equipment_id="CNC-S02-L04-03",
        maintenance_completed_at=datetime(
            2026, 8, 18, 1, 20, tzinfo=timezone.utc
        ),
        action_code="COOLING_SYSTEM_RESTORE",
        state_patch={
            "cooling_system_state": {
                "operation": "restore",
                "value": "nominal",
                "unit": "state",
            }
        },
        caused_by=cause(),
    )

    event.as_payload()

    with pytest.raises(ValidationError, match="requires cooling_system_state"):
        MaintenanceCompletedEvent(
            **{
                **event.model_dump(mode="json"),
                "state_patch": {
                    "tool_wear_min": {
                        "operation": "reset",
                        "value": 0,
                        "unit": "min",
                    }
                },
            }
        )


def test_started_event_cannot_claim_a_completed_maintenance_event() -> None:
    payload = MaintenanceStartedEvent(
        event_id="INTEGRATION-001",
        idempotency_key="ACTION-001:1",
        state_version=1,
        simulation_session_id="DEMO-001",
        maintenance_action_id="ACTION-001",
        work_order_id="WO-001",
        equipment_id="CNC-S02-L04-03",
        maintenance_started_at=datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc),
        caused_by=cause(),
    ).as_payload()
    payload["maintenance_event_id"] = "MAINT-NOT-CREATED"

    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "maintenance-replay-event.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_replay_request_rejects_restart_before_completion() -> None:
    completed_at = datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="restart cannot precede maintenance completion"):
        MaintenanceReplayRequestedEvent(
            event_id="INTEGRATION-003",
            idempotency_key="ACTION-001:3",
            state_version=3,
            simulation_session_id="DEMO-001",
            maintenance_event_id="MAINT-001",
            maintenance_action_id="ACTION-001",
            equipment_id="CNC-S02-L04-03",
            maintenance_completed_at=completed_at,
            restart_at=completed_at - timedelta(seconds=1),
            caused_by=cause(),
        )
