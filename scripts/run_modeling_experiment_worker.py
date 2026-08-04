#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling import ModelingService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute one queued Adaptive Modeling Experiment Run."
    )
    parser.add_argument("experiment_id")
    parser.add_argument("--database", default=os.getenv("ONTOLOGY_DASHBOARD_DB", "data/ontology_dashboard.db"))
    parser.add_argument("--artifact-root", default=os.getenv("ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT"))
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--worker-id", default="modeling-worker-cli")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.artifact_root:
        raise SystemExit("--artifact-root or ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT is required")
    database = (
        args.database
        if args.database.startswith(("postgresql://", "postgresql+psycopg://"))
        else str(Path(args.database).expanduser())
    )
    migrate(database)
    service = ModelingService.configured(database, args.artifact_root)
    result = service.execute_experiment(
        args.experiment_id,
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        worker_id=args.worker_id,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
