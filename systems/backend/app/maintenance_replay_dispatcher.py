"""Deliver Maintenance outbox events to the gen_data Runtime Overlay inbox."""

from __future__ import annotations

import argparse
import json
import os

from app.common.runtime_settings import project_root
from app.infra.db.migrations import migrate
from app.infra.db.settings import database_location
from app.infra.messaging import (
    MaintenanceReplayJsonlHandler,
    ProjectOutboxRepository,
    ProjectOutboxWorker,
)
from app.infra.messaging.maintenance_replay_jsonl import MAINTENANCE_REPLAY_EVENT_TYPES


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def build_worker() -> ProjectOutboxWorker:
    database = database_location(project_root())
    migrate(database)
    organization_id = _required_environment(
        "ONTOLOGY_DASHBOARD_OUTBOX_ORGANIZATION_ID"
    )
    project_id = _required_environment("ONTOLOGY_DASHBOARD_OUTBOX_PROJECT_ID")
    event_file = _required_environment(
        "ONTOLOGY_DASHBOARD_MAINTENANCE_REPLAY_EVENT_FILE"
    )
    handler = MaintenanceReplayJsonlHandler(event_file)
    handlers = {
        event_type: (handler.handler_code, handler)
        for event_type in MAINTENANCE_REPLAY_EVENT_TYPES
    }
    return ProjectOutboxWorker(
        ProjectOutboxRepository(database),
        organization_id=organization_id,
        project_id=project_id,
        handlers=handlers,
        max_attempts=int(os.getenv("ONTOLOGY_DASHBOARD_OUTBOX_MAX_ATTEMPTS", "5")),
        retry_delay_seconds=int(
            os.getenv("ONTOLOGY_DASHBOARD_OUTBOX_RETRY_SECONDS", "5")
        ),
        lease_seconds=int(os.getenv("ONTOLOGY_DASHBOARD_OUTBOX_LEASE_SECONDS", "60")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--drain", action="store_true")
    parser.add_argument("--max-messages", type=int, default=1000)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    worker = build_worker()
    if args.once:
        processed = 1 if worker.process_once() else 0
        print(json.dumps({"mode": "once", "processed": processed}))
        return 0
    if args.drain:
        processed = worker.drain(max_messages=args.max_messages)
        print(json.dumps({"mode": "drain", "processed": processed}))
        return 0
    worker.run_forever(poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
