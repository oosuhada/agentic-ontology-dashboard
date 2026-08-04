#!/usr/bin/env python3
"""Validate a Predictive Maintenance Canonical v2 bundle before PostgreSQL COPY."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ontology_dashboard.adapters import (
    BundleFileAdapter,
    PredictiveMaintenanceCanonicalV2Adapter,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: str | Path, payload: dict[str, object]) -> None:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root", help="Path to predictive_maintenance_canonical_v2")
    parser.add_argument("--organization-id", default="org-ontology-demo")
    parser.add_argument("--project-id", default="predictive-maintenance-v2")
    parser.add_argument("--workspace-id", default="predictive-maintenance-main")
    parser.add_argument("--manifest-id", default="predictive-maintenance-canonical-v2")
    parser.add_argument("--dataset-name", default="Predictive Maintenance Canonical v2")
    parser.add_argument(
        "--allow-root",
        action="append",
        dest="allow_roots",
        help="Allowed local bundle root. Repeat for multiple roots.",
    )
    parser.add_argument("--manifest-output", help="Optional generated Bundle Manifest v2 JSON")
    parser.add_argument("--output", help="Optional validation artifact JSON")
    parser.add_argument("--issue-sample-limit", type=int, default=100)
    parser.add_argument(
        "--execute-postgresql",
        action="store_true",
        help=(
            "Reserved Phase 2 switch. Validation runs now, but PostgreSQL fact-table "
            "COPY is intentionally not implemented in Phase 1."
        ),
    )
    parser.add_argument(
        "--postgresql-dsn",
        help="Reserved Phase 2 PostgreSQL destination; no connection is opened in Phase 1.",
    )
    args = parser.parse_args()

    package_root = Path(args.package_root).expanduser().resolve(strict=True)
    manifest = PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        package_root,
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        manifest_id=args.manifest_id,
        dataset_name=args.dataset_name,
    )

    configured_roots = [
        Path(value)
        for value in os.getenv("ONTOLOGY_DASHBOARD_DATA_ROOTS", "").split(os.pathsep)
        if value.strip()
    ]
    allowed_roots = [Path(value) for value in (args.allow_roots or [])]
    if not allowed_roots:
        allowed_roots = configured_roots or [package_root]

    validation = BundleFileAdapter(
        allowed_roots=allowed_roots,
        issue_sample_limit=args.issue_sample_limit,
    ).validate(manifest)

    manifest_payload = manifest.model_dump(mode="json", by_alias=True)
    validation_payload = validation.model_dump(mode="json")
    if args.manifest_output:
        _write_json(args.manifest_output, manifest_payload)
    if args.output:
        _write_json(args.output, validation_payload)
    print(json.dumps(validation_payload, ensure_ascii=False, indent=2))

    if validation.status != "completed":
        return 1
    if args.execute_postgresql:
        destination = args.postgresql_dsn or "<not provided>"
        raise RuntimeError(
            "PostgreSQL bundle ingestion is a Phase 2 capability. "
            f"Validated artifact is ready for destination {destination}, but no COPY was executed."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
