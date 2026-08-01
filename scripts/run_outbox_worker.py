#!/usr/bin/env python3
"""Run or drain the Project-scoped transactional outbox worker."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ontology_dashboard.migrations import migrate
from ontology_dashboard.outbox import default_outbox_worker
from ontology_dashboard.settings import database_location

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Database URL/path; defaults to runtime settings")
    parser.add_argument("--once", action="store_true", help="Process at most one message")
    parser.add_argument("--drain", action="store_true", help="Drain all currently available messages")
    parser.add_argument("--max-messages", type=int, default=1000)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()

    database = args.database or database_location(ROOT)
    migrate(database)
    worker = default_outbox_worker(database)
    if args.once:
        processed = 1 if worker.process_once() else 0
        print(json.dumps({"processed": processed, "mode": "once"}))
        return 0
    if args.drain:
        processed = worker.drain(max_messages=max(1, args.max_messages))
        print(json.dumps({"processed": processed, "mode": "drain"}))
        return 0
    worker.run_forever(poll_seconds=max(0.1, args.poll_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
