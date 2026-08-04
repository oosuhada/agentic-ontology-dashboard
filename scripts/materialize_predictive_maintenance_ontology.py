#!/usr/bin/env python3
"""Approve and materialize one PostgreSQL predictive-maintenance Dataset Version."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ontology_dashboard.domain_packs.predictive_maintenance import (
    PredictiveMaintenanceOntologyMaterializer,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version-id", required=True)
    parser.add_argument("--approve-default-mapping", action="store_true")
    parser.add_argument("--approved-by", default="phase3-cli")
    parser.add_argument("--output")
    args = parser.parse_args()

    materializer = PredictiveMaintenanceOntologyMaterializer(args.database_url)
    mapping = materializer.ensure_default_mapping(
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        dataset_id=args.dataset_id,
        dataset_version_id=args.dataset_version_id,
        approve=args.approve_default_mapping,
        approved_by=args.approved_by,
    )
    if mapping["status"] != "approved":
        raise RuntimeError(
            "default mapping is draft; approve it explicitly with --approve-default-mapping"
        )
    result = materializer.materialize(
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        dataset_id=args.dataset_id,
        dataset_version_id=args.dataset_version_id,
    )
    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
