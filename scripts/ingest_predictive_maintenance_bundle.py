#!/usr/bin/env python3
"""Validate and optionally COPY a Predictive Maintenance Canonical v2/v3.1 bundle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.dataset.ingestion import (
    BundleFileAdapter,
    PredictiveMaintenanceCanonicalV2Adapter,
)
from app.infra.db.postgresql_bundle_ingestion import PostgreSQLPredictiveMaintenanceBundleIngestor
from app.infra.db.migrations import migrate


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
    parser.add_argument(
        "package_root",
        help="Path to predictive_maintenance_canonical_v2 or predictive_maintenance_canonical_v3.1",
    )
    parser.add_argument("--organization-id", default="org-ontology-demo")
    parser.add_argument("--project-id", default="predictive-maintenance-v2")
    parser.add_argument("--workspace-id", default="predictive-maintenance-main")
    parser.add_argument("--manifest-id", default="predictive-maintenance-canonical-v2")
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Optional display name. Defaults to the package Dataset Version.",
    )
    parser.add_argument(
        "--allow-root",
        action="append",
        dest="allow_roots",
        help="Allowed local bundle root. Repeat for multiple roots.",
    )
    parser.add_argument("--manifest-output", help="Optional generated Bundle Manifest v2 JSON")
    parser.add_argument("--output", help="Optional validation artifact JSON")
    parser.add_argument("--ingestion-output", help="Optional PostgreSQL ingestion artifact JSON")
    parser.add_argument("--issue-sample-limit", type=int, default=100)
    parser.add_argument(
        "--execute-postgresql",
        action="store_true",
        help="Apply migrations and atomically COPY the validated bundle into PostgreSQL.",
    )
    parser.add_argument(
        "--postgresql-dsn",
        default=os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL"),
        help="PostgreSQL URL. Defaults to ONTOLOGY_DASHBOARD_DATABASE_URL.",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Skip migration application when the destination is already migrated.",
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
    if validation.status != "completed":
        print(json.dumps(validation_payload, ensure_ascii=False, indent=2))
        return 1
    if args.execute_postgresql:
        if not args.postgresql_dsn:
            parser.error(
                "--execute-postgresql requires --postgresql-dsn or "
                "ONTOLOGY_DASHBOARD_DATABASE_URL"
            )
        if not args.skip_migrations:
            migrate(args.postgresql_dsn)
        ingestion = PostgreSQLPredictiveMaintenanceBundleIngestor(
            args.postgresql_dsn
        ).ingest_validated_bundle(
            manifest=manifest,
            validation=validation,
        )
        ingestion_payload = ingestion.model_dump(mode="json")
        if args.ingestion_output:
            _write_json(args.ingestion_output, ingestion_payload)
        print(
            json.dumps(
                {"validation": validation_payload, "postgresql_ingestion": ingestion_payload},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(json.dumps(validation_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
