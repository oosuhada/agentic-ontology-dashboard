"""Production durable worker entrypoint.

Run with `python -m ontology_dashboard.worker`. The process drains on SIGTERM,
records heartbeats and never executes durable work inside the API process.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import time
from pathlib import Path

from .distributed_handlers import configured_handlers
from .distributed_runtime import DurableJobRepository, DurableWorker
from .migrations import migrate
from .settings import database_location


ROOT = Path(os.getenv("ONTOLOGY_DASHBOARD_ROOT", "/app"))


def _runtime_checksum() -> str:
    release = os.getenv("ONTOLOGY_DASHBOARD_RELEASE_SHA", "development")
    return hashlib.sha256(release.encode()).hexdigest()


def main() -> int:
    database = database_location(ROOT)
    migrate(database)
    repository = DurableJobRepository(
        database,
        max_queued_per_project=max(
            1,
            int(os.getenv("ONTOLOGY_DASHBOARD_MAX_QUEUED_JOBS_PER_PROJECT", "5000")),
        ),
    )
    configured = configured_handlers(database, ROOT)
    requested = tuple(
        item.strip()
        for item in os.getenv("ONTOLOGY_DASHBOARD_WORKER_JOB_TYPES", "analysis").split(",")
        if item.strip()
    )
    missing = sorted(set(requested) - set(configured))
    if missing:
        raise RuntimeError(f"No worker handler configured for: {', '.join(missing)}")
    worker_id = os.getenv(
        "ONTOLOGY_DASHBOARD_WORKER_ID",
        f"{socket.gethostname()}-{os.getpid()}-durable",
    )
    release = os.getenv("ONTOLOGY_DASHBOARD_RELEASE_SHA", "development")
    checksum = _runtime_checksum()
    worker = DurableWorker(
        repository,
        worker_id=worker_id,
        worker_version=release,
        runtime_checksum=checksum,
        job_types=requested,
        handlers={name: configured[name] for name in requested},
        lease_seconds=max(5, int(os.getenv("ONTOLOGY_DASHBOARD_JOB_LEASE_SECONDS", "60"))),
    )
    stopping = False

    def stop(*_args) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    processed = 0
    while not stopping:
        found = False
        for organization_id, project_id in repository.project_scopes():
            repository.record_worker_heartbeat(
                worker_id=worker_id,
                worker_type="durable",
                worker_version=release,
                runtime_checksum=checksum,
                state="ready",
                queue_names=requested,
                organization_id=organization_id,
                project_id=project_id,
                metrics={"processed": processed},
            )
            result = worker.process_once(
                organization_id=organization_id,
                project_id=project_id,
            )
            if result is not None:
                processed += 1
                found = True
                break
        if not found:
            time.sleep(max(0.1, float(os.getenv("ONTOLOGY_DASHBOARD_WORKER_POLL_SECONDS", "1"))))
    repository.record_worker_heartbeat(
        worker_id=worker_id,
        worker_type="durable",
        worker_version=release,
        runtime_checksum=checksum,
        state="stopped",
        queue_names=requested,
        metrics={"processed": processed},
    )
    print(json.dumps({"worker_id": worker_id, "processed": processed, "state": "stopped"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
