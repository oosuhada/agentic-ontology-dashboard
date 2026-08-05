#!/usr/bin/env python3
"""Verify migration-backed RLS coverage and report live runtime status separately."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ontology_dashboard.persistence_readiness import (
    persistence_readiness,
    verify_rls_migration_evidence,
)
from ontology_dashboard.settings import database_location


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    source = verify_rls_migration_evidence(ROOT)
    runtime = persistence_readiness(database_location(ROOT))
    payload = {
        "check": "tenant-isolation",
        "source_evidence": source,
        "runtime": runtime.model_dump(mode="json"),
        "live_postgresql_required": bool(os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL")),
        "pass": bool(source["pass"]),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if source["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
