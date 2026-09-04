#!/usr/bin/env python3
"""Register the manufacturing Gold fixtures as versioned local Dataset resources.

This bootstrap is intentionally limited to the local demonstration database. It
does not pretend that the fixture Project is connected to an external production
source; it makes the already-used fixture records visible through the canonical
Dataset Catalog, immutable versions, mappings, materializations and projection
health contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from argon2 import PasswordHasher

from app.dependencies import build_manufacturing_service
from app.dataset.dataset_schema import (
    DatasetCreateRequest,
    DatasetFileCreate,
    DatasetVersionCreateRequest,
    MaterializationCreateRequest,
    OntologyMappingCreateRequest,
)
from app.infra.db.dataset_repository import DatasetRepository
from app.infra.db.identity_repository import IdentityRepository as SQLiteIdentityRepository
from app.identity import IdentityService
from app.infra.db.migrations import migrate
from app.infra.db.postgresql_repositories import PostgreSQLIdentityRepository
from app.infra.db.settings import database_location

ROOT = Path(__file__).resolve().parents[1]
ORGANIZATION_ID = "org-ontology-demo"
PROJECT_ID = "manufacturing-demo-project"
WORKSPACE_ID = "manufacturing-demo"
ACTOR_ID = "system:demo-dataset-bootstrap"


@dataclass(frozen=True)
class DemoDataset:
    dataset_id: str
    slug: str
    display_name: str
    description: str
    object_type: str
    identity_field: str
    rows: list[dict[str, Any]]
    property_mapping: dict[str, str]
    content_fields: list[str]


def _risk_rows(service: ManufacturingPredictiveMaintenanceService) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in service.list_events(PROJECT_ID):
        detail = service.event(event["event_id"])
        equipment = event["equipment"]
        observation = detail["observation"]
        rows.append(
            {
                "event_id": event["event_id"],
                "scenario_id": event["scenario_id"],
                "equipment_id": equipment["equipment_id"],
                "equipment_name": equipment["display_name"],
                "line": equipment["line"],
                "criticality": equipment["criticality"],
                "assigned_engineer": equipment.get("assigned_engineer"),
                "estimated_downtime_minutes": equipment.get("estimated_downtime_minutes"),
                "spare_part_available": equipment.get("spare_part_available"),
                "status": event["status"],
                "failure_probability": event["failure_probability"],
                "confidence": event["confidence"],
                "predicted_failure_type": event["predicted_failure_type"],
                "recommended_decision": event["recommended_decision"],
                "observation_timestamp": observation.get("timestamp"),
                "air_temperature_k": observation.get("air_temperature_k"),
                "process_temperature_k": observation.get("process_temperature_k"),
                "rotational_speed_rpm": observation.get("rotational_speed_rpm"),
                "torque_nm": observation.get("torque_nm"),
                "tool_wear_min": observation.get("tool_wear_min"),
                "source_reference": f"fixture:{event['scenario_id']}:{event['event_id']}",
            }
        )
    return sorted(rows, key=lambda item: item["event_id"])


def _equipment_rows(service: ManufacturingPredictiveMaintenanceService) -> list[dict[str, Any]]:
    events = service.list_events(PROJECT_ID)
    rows: list[dict[str, Any]] = []
    for equipment in service.list_equipment(PROJECT_ID):
        related = [
            event
            for event in events
            if event["equipment"]["equipment_id"] == equipment["equipment_id"]
        ]
        risks = [
            float(event["failure_probability"])
            for event in related
            if event["failure_probability"] is not None
        ]
        rows.append(
            {
                **equipment,
                "risk_event_count": len(related),
                "max_failure_probability": max(risks, default=None),
                "active_event_ids": [event["event_id"] for event in related],
                "source_reference": f"fixture-equipment:{equipment['equipment_id']}",
            }
        )
    return rows


def _datasets(service: ManufacturingPredictiveMaintenanceService) -> list[DemoDataset]:
    return [
        DemoDataset(
            dataset_id="ds-manufacturing-risk-events",
            slug="manufacturing-risk-events",
            display_name="Manufacturing Risk Events",
            description=(
                "Versioned local demonstration dataset assembled from the eight Gold risk-event "
                "fixtures used by the operational Dashboard and Ontology projection."
            ),
            object_type="risk_event",
            identity_field="event_id",
            rows=_risk_rows(service),
            property_mapping={
                "event_id": "event_id",
                "scenario_id": "scenario_id",
                "equipment_id": "equipment_id",
                "equipment_name": "equipment_name",
                "line": "line",
                "status": "status",
                "failure_probability": "failure_probability",
                "confidence": "confidence",
                "predicted_failure_type": "predicted_failure_type",
                "recommended_decision": "recommended_decision",
                "observation_timestamp": "observation_timestamp",
            },
            content_fields=[
                "event_id",
                "equipment_name",
                "line",
                "status",
                "predicted_failure_type",
                "recommended_decision",
            ],
        ),
        DemoDataset(
            dataset_id="ds-manufacturing-equipment",
            slug="manufacturing-equipment",
            display_name="Manufacturing Equipment Registry",
            description=(
                "Canonical equipment registry derived from the same local Gold fixture source, "
                "including current risk-event coverage and maintenance attributes."
            ),
            object_type="equipment",
            identity_field="equipment_id",
            rows=_equipment_rows(service),
            property_mapping={
                "equipment_id": "equipment_id",
                "display_name": "display_name",
                "line": "line",
                "criticality": "criticality",
                "assigned_engineer": "assigned_engineer",
                "last_maintenance_date": "last_maintenance_date",
                "estimated_downtime_minutes": "estimated_downtime_minutes",
                "spare_part_available": "spare_part_available",
                "risk_event_count": "risk_event_count",
                "max_failure_probability": "max_failure_probability",
            },
            content_fields=[
                "equipment_id",
                "display_name",
                "line",
                "criticality",
                "assigned_engineer",
            ],
        ),
    ]


def _write_jsonl(dataset: DemoDataset, artifact_root: Path) -> tuple[Path, str]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / f"{dataset.slug}.jsonl"
    rendered = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in dataset.rows
    )
    path.write_text(rendered, encoding="utf-8")
    return path, hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _schema(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sample = rows[0] if rows else {}

    def value_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "string"

    return {
        "format": "jsonl",
        "columns": [
            {"name": key, "value_type": value_type(value), "nullable": value is None}
            for key, value in sample.items()
        ],
    }


def _ensure_relational_projection(
    repository: DatasetRepository,
    *,
    dataset_id: str,
    version_id: str,
    record_count: int,
) -> None:
    projections = repository.list_projections(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        dataset_id=dataset_id,
        version_id=version_id,
    )
    projection = next(item for item in projections if item["store_kind"] == "relational")
    if projection["status"] == "ready":
        return
    if projection["status"] == "failed":
        repository.retry_projection(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            projection_id=projection["id"],
        )
    claimed = repository.claim_projection(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        projection_id=projection["id"],
    )
    repository.complete_projection(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        projection_id=claimed["id"],
        record_count=record_count,
    )


def seed(
    database: str,
    artifact_root: Path,
    *,
    allow_local_postgresql: bool = False,
) -> list[dict[str, Any]]:
    migrate(database)
    if database.startswith(("postgresql://", "postgresql+psycopg://")):
        endpoint = urlparse(database.replace("postgresql+psycopg://", "postgresql://", 1))
        if not allow_local_postgresql or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError(
                "fixture Dataset registration in PostgreSQL requires "
                "--allow-local-postgresql and a loopback database endpoint"
            )
    # Fresh Playwright/release databases need the canonical Organization,
    # Project and Workspace rows before Dataset foreign keys can be inserted.
    if database.startswith(("postgresql://", "postgresql+psycopg://")):
        password_hasher = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        IdentityService(
            PostgreSQLIdentityRepository(
                database,
                password_hasher=password_hasher,
                seed_reference_data=True,
            ),
            app_env="demo",
            seed_demo=True,
        )
    else:
        password_hasher = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        IdentityService(
            SQLiteIdentityRepository(database, password_hasher=password_hasher),
            app_env="demo",
            seed_demo=True,
            rate_limit_namespace=f"identity:{database}",
        )
    repository = DatasetRepository(database)
    service = build_manufacturing_service(database, root=ROOT)
    existing = {
        item["id"]: item
        for item in repository.list_datasets(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
        )
    }
    results: list[dict[str, Any]] = []

    for dataset in _datasets(service):
        artifact_path, checksum = _write_jsonl(dataset, artifact_root)
        if dataset.dataset_id not in existing:
            repository.create_dataset(
                organization_id=ORGANIZATION_ID,
                actor_user_id=ACTOR_ID,
                request=DatasetCreateRequest(
                    id=dataset.dataset_id,
                    project_id=PROJECT_ID,
                    workspace_id=WORKSPACE_ID,
                    slug=dataset.slug,
                    display_name=dataset.display_name,
                    description=dataset.description,
                    source_type="local_fixture",
                ),
            )

        versions = repository.list_versions(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            dataset_id=dataset.dataset_id,
        )
        version = next((item for item in versions if item["checksum_sha256"] == checksum), None)
        if version is None:
            version = repository.create_version(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
                dataset_id=dataset.dataset_id,
                actor_user_id=ACTOR_ID,
                request=DatasetVersionCreateRequest(
                    source_version="gold-fixtures-2026-08-01",
                    version_label="Gold fixture snapshot",
                    # These fixtures are local application resources, not an
                    # Adapter-ingested external manifest. Keep the foreign-key
                    # reference empty rather than inventing connector lineage.
                    manifest_id=None,
                    checksum_sha256=checksum,
                    schema=_schema(dataset.rows),
                    profile={
                        "row_count": len(dataset.rows),
                        "column_count": len(dataset.rows[0]) if dataset.rows else 0,
                        "source_mode": "local_fixture",
                        "usage": [
                            "legacy_comparison",
                            "offline_fallback",
                            "fixture_regression_test",
                            "team_share_history",
                        ],
                        "default_dashboard_source": False,
                    },
                    record_count=len(dataset.rows),
                    files=[
                        DatasetFileCreate(
                            uri=artifact_path.as_uri(),
                            media_type="application/x-ndjson",
                            checksum_sha256=checksum,
                            size_bytes=artifact_path.stat().st_size,
                        )
                    ],
                ),
            )

        repository.save_mapping(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            dataset_id=dataset.dataset_id,
            version_id=version["id"],
            actor_user_id=ACTOR_ID,
            request=OntologyMappingCreateRequest(
                object_type=dataset.object_type,
                identity_field=dataset.identity_field,
                property_mapping=dict(dataset.property_mapping),
                content_fields=list(dataset.content_fields),
                allowed_roles=[
                    "tenant_admin",
                    "executive_viewer",
                    "process_manager",
                    "process_engineer",
                    "quality_auditor",
                    "ml_validator",
                    "fde",
                ],
            ),
        )

        materializations = repository.list_materializations(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            dataset_id=dataset.dataset_id,
        )
        if not any(item["dataset_version_id"] == version["id"] for item in materializations):
            repository.create_materialization(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
                dataset_id=dataset.dataset_id,
                version_id=version["id"],
                actor_user_id=ACTOR_ID,
                request=MaterializationCreateRequest(
                    source_kind="query_result",
                    source_reference="fixture-set:GS-001..GS-008",
                    format="jsonl",
                    artifact_uri=artifact_path.as_uri(),
                    checksum_sha256=checksum,
                    record_count=len(dataset.rows),
                    metadata={
                        "source_mode": "local_fixture",
                        "external_connection": False,
                        "generated_by": "seed_demo_dataset_catalog.py",
                    },
                ),
            )

        _ensure_relational_projection(
            repository,
            dataset_id=dataset.dataset_id,
            version_id=version["id"],
            record_count=len(dataset.rows),
        )
        results.append(
            {
                "dataset_id": dataset.dataset_id,
                "version_id": version["id"],
                "records": len(dataset.rows),
                "artifact": artifact_path.as_uri(),
                "checksum_sha256": checksum,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Database URL/path; defaults to runtime settings")
    parser.add_argument(
        "--artifact-root",
        default=str(ROOT / "data" / "local" / "demo-datasets"),
        help="Directory for deterministic JSONL materialization artifacts",
    )
    parser.add_argument(
        "--allow-local-postgresql",
        action="store_true",
        help="Explicitly register legacy fixture Datasets in loopback PostgreSQL only",
    )
    args = parser.parse_args()
    database = args.database or database_location(ROOT)
    result = seed(
        database,
        Path(args.artifact_root).expanduser().resolve(),
        allow_local_postgresql=args.allow_local_postgresql,
    )
    print(
        json.dumps(
            {
                "project_id": PROJECT_ID,
                "workspace_id": WORKSPACE_ID,
                "source_mode": "local_fixture",
                "external_connection": False,
                "datasets": result,
                "pass": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
