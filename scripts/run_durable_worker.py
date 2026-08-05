#!/usr/bin/env python3
"""Run the tenant-scoped durable execution worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import time
from pathlib import Path

from ontology_dashboard.distributed_handlers import configured_handlers
from ontology_dashboard.distributed_runtime import DurableJobRepository, DurableWorker
from ontology_dashboard.migrations import migrate
from ontology_dashboard.settings import database_location


ROOT = Path(__file__).resolve().parents[1]


def runtime_checksum() -> str:
    digest = hashlib.sha256()
    for path in (
        ROOT / "api/ontology_dashboard/distributed_runtime.py",
        ROOT / "api/ontology_dashboard/distributed_handlers.py",
    ):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--worker-type", default="application")
    parser.add_argument("--job-types", default="analysis")
    args = parser.parse_args()

    database = args.database or database_location(ROOT)
    migrate(database)
    repository = DurableJobRepository(database)
    supported = tuple(
        item.strip()
        for item in args.job_types.split(",")
        if item.strip()
    )
    handlers = configured_handlers(database, ROOT)
    unknown = sorted(set(supported) - set(handlers))
    if unknown:
        raise SystemExit(f"No configured handler for: {', '.join(unknown)}")
    worker_id = os.getenv(
        "ONTOLOGY_DASHBOARD_WORKER_ID",
        f"{socket.gethostname()}-{os.getpid()}-{args.worker_type}",
    )
    checksum = runtime_checksum()
    worker = DurableWorker(
        repository,
        worker_id=worker_id,
        worker_version=os.getenv("ONTOLOGY_DASHBOARD_RELEASE_SHA", "development"),
        runtime_checksum=checksum,
        job_types=supported,
        handlers={name: handlers[name] for name in supported},
        lease_seconds=max(5, int(os.getenv("ONTOLOGY_DASHBOARD_JOB_LEASE_SECONDS", "60"))),
    )
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    repository.record_worker_heartbeat(
        worker_id=worker_id,
        worker_type=args.worker_type,
        worker_version=worker.worker_version,
        runtime_checksum=checksum,
        state="starting",
        queue_names=supported,
    )
    processed = 0
    while not stopping:
        found = False
        for organization_id, project_id in repository.project_scopes():
            repository.record_worker_heartbeat(
                worker_id=worker_id,
                worker_type=args.worker_type,
                worker_version=worker.worker_version,
                runtime_checksum=checksum,
                state="ready",
                queue_names=supported,
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
        if args.once:
            print(json.dumps({"processed": processed, "worker_id": worker_id}))
            break
        if not found:
            time.sleep(max(0.1, args.poll_seconds))
    repository.record_worker_heartbeat(
        worker_id=worker_id,
        worker_type=args.worker_type,
        worker_version=worker.worker_version,
        runtime_checksum=checksum,
        state="stopped",
        queue_names=supported,
        metrics={"processed": processed},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
