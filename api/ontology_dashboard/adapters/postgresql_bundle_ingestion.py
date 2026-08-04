"""Atomic PostgreSQL COPY ingestion for validated predictive-maintenance bundles."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .bundle_file_adapter import bundle_source_path
from .bundle_models import (
    BundleValidationResult,
    DatasetBundleManifestV2,
    PostgreSQLBundleIngestionResult,
)
from .predictive_maintenance_v2 import ROLE_CONTRACTS


ROLE_TARGET_TABLES = {
    "asset_master": "pm_assets",
    "asset_relation": "pm_asset_relations",
    "compressor_sensor_observation": "pm_compressor_observations",
    "cnc_sensor_observation": "pm_cnc_observations",
    "cnc_production_cycle": "pm_production_cycles",
    "maintenance_event": "pm_maintenance_events",
    "prediction_snapshot": "pm_prediction_snapshots",
    "prediction_factor": "pm_prediction_factors",
    "prediction_timeline": "pm_prediction_timeline",
    "result_artifact": "pm_result_artifacts",
}

STAGING_TABLES = {
    "asset_master": "stg_pm_assets",
    "asset_relation": "stg_pm_asset_relations",
    "compressor_sensor_observation": "stg_pm_compressor_observations",
    "cnc_sensor_observation": "stg_pm_cnc_observations",
    "cnc_production_cycle": "stg_pm_production_cycles",
    "maintenance_event": "stg_pm_maintenance_events",
    "prediction_snapshot": "stg_pm_prediction_snapshots",
    "prediction_factor": "stg_pm_prediction_factors",
    "prediction_timeline": "stg_pm_prediction_timeline",
    "result_artifact": "stg_pm_result_artifacts",
}

STAGING_DDL = {
    role: (
        f"CREATE TEMP TABLE {STAGING_TABLES[role]} ("
        + ",".join(f'"{field}" text' for field in contract.required_fields)
        + ") ON COMMIT DROP"
    )
    for role, contract in ROLE_CONTRACTS.items()
}


def _require_psycopg():
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL bundle ingestion requires api[postgres] with psycopg installed"
        ) from exc
    return psycopg, sql, dict_row, Jsonb


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = normalized[:120].rstrip("-")
    return normalized if len(normalized) >= 3 else f"dataset-{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list, bool, int, float)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


class PostgreSQLPredictiveMaintenanceBundleIngestor:
    """COPY one validated bundle into catalog, facts, and outbox atomically.

    The control ingestion run is committed before the data transaction so a
    rollback can preserve the failure reason without leaving a partial Dataset
    Version or partial fact rows.
    """

    def __init__(self, database_url: str) -> None:
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not normalized.startswith("postgresql://"):
            raise ValueError("PostgreSQL bundle ingestion requires a PostgreSQL URL")
        self.database_url = normalized

    def ingest_validated_bundle(
        self,
        *,
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
        fail_after_role: str | None = None,
    ) -> PostgreSQLBundleIngestionResult:
        self._validate_artifact_binding(manifest, validation)
        manifest_record_id, run_id = self._start_control_run(manifest, validation)
        try:
            committed = self._ingest_transaction(
                manifest=manifest,
                validation=validation,
                manifest_record_id=manifest_record_id,
                run_id=run_id,
                fail_after_role=fail_after_role,
            )
        except Exception as exc:
            self._fail_control_run(
                manifest=manifest,
                run_id=run_id,
                error_message=str(exc),
            )
            raise
        return committed

    @staticmethod
    def _validate_artifact_binding(
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
    ) -> None:
        if validation.status != "completed":
            raise ValueError("only a completed BundleValidationResult can be ingested")
        expected = {
            "manifest_id": manifest.manifest_id,
            "organization_id": manifest.organization_id,
            "project_id": manifest.project_id,
            "workspace_id": manifest.workspace_id,
            "adapter_code": manifest.adapter_code,
            "dataset_version": manifest.dataset_version,
            "bundle_checksum_sha256": manifest.bundle_checksum_sha256,
        }
        for field, value in expected.items():
            if getattr(validation, field) != value:
                raise ValueError(f"validation artifact {field} does not match the bundle manifest")
        manifest_roles = {item.role: item for item in manifest.files}
        validation_roles = {item.role: item for item in validation.roles}
        if set(manifest_roles) != set(validation_roles):
            raise ValueError("validation artifact roles do not match the bundle manifest")
        for role, descriptor in manifest_roles.items():
            summary = validation_roles[role]
            if summary.status != "passed" or not summary.checksum_valid or not summary.schema_valid:
                raise ValueError(f"bundle role is not ready for PostgreSQL ingestion: {role}")
            if summary.actual_checksum_sha256 != descriptor.checksum_sha256:
                raise ValueError(f"validated checksum does not match manifest role: {role}")

    @staticmethod
    def _set_scope(connection: Any, manifest: DatasetBundleManifestV2) -> None:
        connection.execute(
            "SELECT set_config('app.organization_id', %s, true)",
            (manifest.organization_id,),
        )
        connection.execute(
            "SELECT set_config('app.project_id', %s, true)",
            (manifest.project_id,),
        )

    def _start_control_run(
        self,
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
    ) -> tuple[str, str]:
        psycopg, _, dict_row, Jsonb = _require_psycopg()
        manifest_record_id = f"manifest-{uuid.uuid5(uuid.NAMESPACE_URL, f'{manifest.organization_id}:{manifest.project_id}:{manifest.manifest_id}:{manifest.bundle_checksum_sha256}')}"
        run_id = str(uuid.uuid4())
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._set_scope(connection, manifest)
                workspace = connection.execute(
                    """
                    SELECT id FROM workspaces
                    WHERE id=%s AND organization_id=%s AND project_id=%s
                    """,
                    (manifest.workspace_id, manifest.organization_id, manifest.project_id),
                ).fetchone()
                if workspace is None:
                    raise ValueError("workspace does not belong to the bundle organization/project")
                connection.execute(
                    """
                    INSERT INTO dataset_manifests(
                        id,organization_id,project_id,workspace_id,adapter_code,dataset_name,
                        dataset_version,source_uri,source_checksum,media_type,manifest_json,
                        status,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'registered',%s,now())
                    ON CONFLICT(id) DO UPDATE SET
                        manifest_json=excluded.manifest_json,
                        status='registered',
                        updated_at=now()
                    """,
                    (
                        manifest_record_id,
                        manifest.organization_id,
                        manifest.project_id,
                        manifest.workspace_id,
                        manifest.adapter_code,
                        manifest.dataset_name,
                        manifest.dataset_version,
                        f"bundle:{manifest.bundle_checksum_sha256}",
                        manifest.bundle_checksum_sha256,
                        "application/vnd.ontology-dashboard.dataset-bundle+json",
                        Jsonb(manifest.model_dump(mode="json", by_alias=True)),
                        manifest.created_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO adapter_ingestion_runs(
                        id,organization_id,project_id,workspace_id,manifest_id,adapter_code,
                        status,source_record_count,accepted_record_count,quarantined_record_count,
                        bundle_checksum_sha256,validation_checksum_sha256,metrics_json,started_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,'running',%s,0,0,%s,%s,%s,now())
                    """,
                    (
                        run_id,
                        manifest.organization_id,
                        manifest.project_id,
                        manifest.workspace_id,
                        manifest_record_id,
                        manifest.adapter_code,
                        validation.source_record_count,
                        manifest.bundle_checksum_sha256,
                        validation.validation_checksum_sha256,
                        Jsonb({"validation_ingestion_run_id": validation.ingestion_run_id}),
                    ),
                )
        return manifest_record_id, run_id

    def _ingest_transaction(
        self,
        *,
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
        manifest_record_id: str,
        run_id: str,
        fail_after_role: str | None,
    ) -> PostgreSQLBundleIngestionResult:
        psycopg, _, dict_row, Jsonb = _require_psycopg()
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._set_scope(connection, manifest)
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"{manifest.project_id}:{manifest.manifest_id}",),
                )
                dataset_id = self._ensure_dataset(connection, manifest)
                existing = connection.execute(
                    """
                    SELECT id,version_number,source_version,status
                    FROM dataset_versions
                    WHERE dataset_id=%s AND checksum_sha256=%s
                    """,
                    (dataset_id, manifest.bundle_checksum_sha256),
                ).fetchone()
                if existing is not None:
                    row_counts = self._target_row_counts(
                        connection,
                        str(existing["id"]),
                        {item.role for item in validation.roles},
                    )
                    self._assert_row_count_parity(validation, row_counts)
                    result = PostgreSQLBundleIngestionResult(
                        ingestion_run_id=run_id,
                        manifest_record_id=manifest_record_id,
                        organization_id=manifest.organization_id,
                        project_id=manifest.project_id,
                        workspace_id=manifest.workspace_id,
                        dataset_id=dataset_id,
                        dataset_version_id=str(existing["id"]),
                        version_number=int(existing["version_number"]),
                        source_version=str(existing["source_version"]),
                        bundle_checksum_sha256=manifest.bundle_checksum_sha256,
                        validation_checksum_sha256=validation.validation_checksum_sha256,
                        reused_dataset_version=True,
                        row_counts=row_counts,
                        source_record_count=sum(row_counts.values()),
                        outbox_event_id=None,
                        completed_at=datetime.now(timezone.utc),
                    )
                    self._mark_control_run_completed(connection, result, Jsonb)
                    return result

                version_id, version_number = self._create_version_catalog(
                    connection,
                    manifest=manifest,
                    validation=validation,
                    manifest_record_id=manifest_record_id,
                    dataset_id=dataset_id,
                    jsonb=Jsonb,
                )
                self._ensure_observation_partitions(connection, manifest)
                runtime_roles = [item.role for item in manifest.files]
                self._create_staging_tables(connection, runtime_roles)
                for role in runtime_roles:
                    self._copy_role(connection, manifest, role)
                    if fail_after_role == role:
                        raise RuntimeError(f"injected bundle transaction failure after role {role}")
                self._validate_staging(connection, manifest, validation)
                self._merge_targets(connection, manifest, version_id)
                row_counts = self._target_row_counts(
                    connection,
                    version_id,
                    {item.role for item in validation.roles},
                )
                self._assert_row_count_parity(validation, row_counts)
                outbox_event_id = str(uuid.uuid4())
                profile = {
                    "bundle_checksum_sha256": manifest.bundle_checksum_sha256,
                    "validation_checksum_sha256": validation.validation_checksum_sha256,
                    "row_counts": row_counts,
                    "copy_protocol": "psycopg-copy",
                    "atomic_bundle_transaction": True,
                    "source_contract": manifest.source_contract.model_dump(
                        mode="json", exclude_none=True
                    ),
                    "governance_artifacts": [
                        item.model_dump(mode="json") for item in manifest.governance_artifacts
                    ],
                }
                connection.execute(
                    """
                    UPDATE dataset_versions
                    SET profile_json=%s,record_count=%s,status='projecting'
                    WHERE id=%s AND organization_id=%s AND project_id=%s
                    """,
                    (
                        Jsonb(profile),
                        sum(row_counts.values()),
                        version_id,
                        manifest.organization_id,
                        manifest.project_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE store_projections
                    SET status='ready',record_count=%s,attempt_count=attempt_count+1,
                        started_at=COALESCE(started_at,now()),completed_at=now(),updated_at=now(),last_error=NULL
                    WHERE dataset_version_id=%s AND store_kind='relational'
                    """,
                    (sum(row_counts.values()), version_id),
                )
                connection.execute(
                    """
                    INSERT INTO transactional_outbox(
                        id,organization_id,project_id,workspace_id,aggregate_type,
                        aggregate_id,event_type,payload_json,status,created_at,available_at
                    ) VALUES (%s,%s,%s,%s,'dataset_version',%s,
                              'dataset.version.relational_ready',%s,'pending',now(),now())
                    """,
                    (
                        outbox_event_id,
                        manifest.organization_id,
                        manifest.project_id,
                        manifest.workspace_id,
                        version_id,
                        Jsonb(
                            {
                                "dataset_id": dataset_id,
                                "dataset_version_id": version_id,
                                "source_version": manifest.dataset_version,
                                "bundle_checksum_sha256": manifest.bundle_checksum_sha256,
                                "row_counts": row_counts,
                            }
                        ),
                    ),
                )
                result = PostgreSQLBundleIngestionResult(
                    ingestion_run_id=run_id,
                    manifest_record_id=manifest_record_id,
                    organization_id=manifest.organization_id,
                    project_id=manifest.project_id,
                    workspace_id=manifest.workspace_id,
                    dataset_id=dataset_id,
                    dataset_version_id=version_id,
                    version_number=version_number,
                    source_version=manifest.dataset_version,
                    bundle_checksum_sha256=manifest.bundle_checksum_sha256,
                    validation_checksum_sha256=validation.validation_checksum_sha256,
                    reused_dataset_version=False,
                    row_counts=row_counts,
                    source_record_count=sum(row_counts.values()),
                    outbox_event_id=outbox_event_id,
                    completed_at=datetime.now(timezone.utc),
                )
                self._mark_control_run_completed(connection, result, Jsonb)
                return result

    def _ensure_dataset(self, connection: Any, manifest: DatasetBundleManifestV2) -> str:
        dataset_id = f"ds-{uuid.uuid5(uuid.NAMESPACE_URL, f'{manifest.organization_id}:{manifest.project_id}:{manifest.manifest_id}')}"
        existing = connection.execute(
            "SELECT id,workspace_id FROM datasets WHERE id=%s AND project_id=%s",
            (dataset_id, manifest.project_id),
        ).fetchone()
        if existing is not None:
            if str(existing["workspace_id"]) != manifest.workspace_id:
                raise ValueError("existing Dataset belongs to a different Workspace")
            return dataset_id
        connection.execute(
            """
            INSERT INTO datasets(
                id,organization_id,project_id,workspace_id,slug,display_name,
                description,source_type,status,created_at,updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active',now(),now())
            """,
            (
                dataset_id,
                manifest.organization_id,
                manifest.project_id,
                manifest.workspace_id,
                _slug(manifest.manifest_id),
                manifest.dataset_name,
                "Predictive Maintenance immutable runtime bundle",
                manifest.adapter_code,
            ),
        )
        return dataset_id

    def _create_version_catalog(
        self,
        connection: Any,
        *,
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
        manifest_record_id: str,
        dataset_id: str,
        jsonb: Any,
    ) -> tuple[str, int]:
        version_id = f"dsv-{uuid.uuid5(uuid.NAMESPACE_URL, f'{manifest.project_id}:{dataset_id}:{manifest.bundle_checksum_sha256}')}"
        row = connection.execute(
            "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM dataset_versions WHERE dataset_id=%s",
            (dataset_id,),
        ).fetchone()
        version_number = int(row["next_version"])
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id,organization_id,project_id,workspace_id,dataset_id,version_number,
                version_label,source_version,manifest_id,checksum_sha256,schema_json,
                profile_json,record_count,status,created_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,'profiling',now())
            """,
            (
                version_id,
                manifest.organization_id,
                manifest.project_id,
                manifest.workspace_id,
                dataset_id,
                version_number,
                f"{manifest.dataset_version} · {manifest.bundle_checksum_sha256[:12]}",
                manifest.dataset_version,
                manifest_record_id,
                manifest.bundle_checksum_sha256,
                jsonb(
                    {
                        "bundle_schema_version": manifest.schema_version,
                        "source_contract": manifest.source_contract.model_dump(
                            mode="json", exclude_none=True
                        ),
                        "roles": {
                            item.role: item.schema_.model_dump(mode="json")
                            for item in manifest.files
                        },
                    }
                ),
                jsonb(
                    {
                        "validation_checksum_sha256": validation.validation_checksum_sha256,
                        "status": "copying",
                        "governance_artifacts": [
                            item.model_dump(mode="json")
                            for item in manifest.governance_artifacts
                        ],
                    }
                ),
            ),
        )
        for descriptor in manifest.files:
            connection.execute(
                """
                INSERT INTO dataset_files(
                    id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                    uri,media_type,checksum_sha256,size_bytes,role,format,schema_json,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                """,
                (
                    f"file-{uuid.uuid5(uuid.NAMESPACE_URL, f'{version_id}:{descriptor.role}')}",
                    manifest.organization_id,
                    manifest.project_id,
                    manifest.workspace_id,
                    dataset_id,
                    version_id,
                    descriptor.uri,
                    descriptor.media_type,
                    descriptor.checksum_sha256,
                    descriptor.size_bytes,
                    descriptor.role,
                    descriptor.format,
                    jsonb(descriptor.schema_.model_dump(mode="json")),
                ),
            )
        namespace = f"{manifest.project_id}:{dataset_id}:{version_id}"
        for store_kind in ("relational", "graph", "vector"):
            connection.execute(
                """
                INSERT INTO store_projections(
                    id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                    store_kind,status,object_namespace,source_version,record_count,
                    attempt_count,updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,now())
                """,
                (
                    f"projection-{uuid.uuid5(uuid.NAMESPACE_URL, f'{version_id}:{store_kind}')}",
                    manifest.organization_id,
                    manifest.project_id,
                    manifest.workspace_id,
                    dataset_id,
                    version_id,
                    store_kind,
                    "indexing" if store_kind == "relational" else "pending",
                    namespace,
                    manifest.dataset_version,
                ),
            )
        return version_id, version_number

    def _ensure_observation_partitions(
        self,
        connection: Any,
        manifest: DatasetBundleManifestV2,
    ) -> None:
        _, sql, _, _ = _require_psycopg()
        current = _month_start(manifest.generation.period_start)
        while current < manifest.generation.period_end:
            following = _next_month(current)
            suffix = current.strftime("%Y%m")
            for parent in ("pm_compressor_observations", "pm_cnc_observations"):
                child = f"{parent}_{suffix}"
                connection.execute(
                    sql.SQL(
                        "CREATE TABLE IF NOT EXISTS {} PARTITION OF {} FOR VALUES FROM ({}) TO ({})"
                    ).format(
                        sql.Identifier(child),
                        sql.Identifier(parent),
                        sql.Literal(current),
                        sql.Literal(following),
                    )
                )
                connection.execute(
                    sql.SQL("ALTER TABLE {} ENABLE ROW LEVEL SECURITY").format(
                        sql.Identifier(child)
                    )
                )
                connection.execute(
                    sql.SQL("DROP POLICY IF EXISTS project_scope_policy ON {}").format(
                        sql.Identifier(child)
                    )
                )
                connection.execute(
                    sql.SQL(
                        "CREATE POLICY project_scope_policy ON {} "
                        "USING (organization_id=current_setting('app.organization_id',true) "
                        "AND project_id=current_setting('app.project_id',true)) "
                        "WITH CHECK (organization_id=current_setting('app.organization_id',true) "
                        "AND project_id=current_setting('app.project_id',true))"
                    ).format(sql.Identifier(child))
                )
            current = following

    @staticmethod
    def _create_staging_tables(connection: Any, roles: list[str]) -> None:
        for role in roles:
            connection.execute(STAGING_DDL[role])

    def _copy_role(
        self,
        connection: Any,
        manifest: DatasetBundleManifestV2,
        role: str,
    ) -> None:
        descriptor = next(item for item in manifest.files if item.role == role)
        path = bundle_source_path(descriptor.uri).expanduser().resolve(strict=True)
        if path.stat().st_size != descriptor.size_bytes:
            raise ValueError(f"runtime file size changed after validation: {role}")
        contract = ROLE_CONTRACTS[role]
        columns = ",".join(f'"{field}"' for field in contract.required_fields)
        digest = hashlib.sha256()
        if contract.format == "csv":
            statement = (
                f"COPY {STAGING_TABLES[role]} ({columns}) FROM STDIN "
                "WITH (FORMAT CSV, HEADER TRUE)"
            )
            with connection.cursor().copy(statement) as copy:
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                        copy.write(chunk)
        else:
            statement = f"COPY {STAGING_TABLES[role]} ({columns}) FROM STDIN"
            with connection.cursor().copy(statement) as copy:
                with path.open("rb") as source:
                    for raw_line in source:
                        digest.update(raw_line)
                        if not raw_line.strip():
                            continue
                        payload = json.loads(raw_line.decode("utf-8"))
                        copy.write_row(
                            tuple(_json_text(payload.get(field)) for field in contract.required_fields)
                        )
        if digest.hexdigest() != descriptor.checksum_sha256:
            raise ValueError(f"runtime file checksum changed after validation: {role}")

    def _validate_staging(
        self,
        connection: Any,
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
    ) -> None:
        summaries = {item.role: item for item in validation.roles}
        for role in summaries:
            staging = STAGING_TABLES[role]
            count = int(connection.execute(f"SELECT COUNT(*) AS count FROM {staging}").fetchone()["count"])
            if count != summaries[role].source_record_count:
                raise ValueError(
                    f"staging row count mismatch for {role}: expected={summaries[role].source_record_count}, actual={count}"
                )

        checks = [
            (
                "duplicate asset_id",
                "SELECT 1 FROM stg_pm_assets GROUP BY asset_id HAVING COUNT(*)>1 LIMIT 1",
            ),
            (
                "relation references unknown asset",
                """
                SELECT 1 FROM stg_pm_asset_relations r
                LEFT JOIN stg_pm_assets a1 ON a1.asset_id=r.from_asset_id
                LEFT JOIN stg_pm_assets a2 ON a2.asset_id=r.to_asset_id
                WHERE a1.asset_id IS NULL OR a2.asset_id IS NULL LIMIT 1
                """,
            ),
            (
                "compressor observation references unknown asset",
                """
                SELECT 1 FROM stg_pm_compressor_observations o
                LEFT JOIN stg_pm_assets a ON a.asset_id=o.asset_id AND a.asset_type='compressor'
                WHERE a.asset_id IS NULL LIMIT 1
                """,
            ),
            (
                "CNC observation references unknown asset",
                """
                SELECT 1 FROM stg_pm_cnc_observations o
                LEFT JOIN stg_pm_assets a ON a.asset_id=o.asset_id AND a.asset_type='cnc'
                WHERE a.asset_id IS NULL LIMIT 1
                """,
            ),
            (
                "production cycle references unknown CNC asset",
                """
                SELECT 1 FROM stg_pm_production_cycles c
                LEFT JOIN stg_pm_assets a ON a.asset_id=c.cnc_asset_id AND a.asset_type='cnc'
                WHERE a.asset_id IS NULL LIMIT 1
                """,
            ),
            (
                "maintenance event references unknown asset",
                """
                SELECT 1 FROM stg_pm_maintenance_events m
                LEFT JOIN stg_pm_assets a ON a.asset_id=m.asset_id
                WHERE a.asset_id IS NULL LIMIT 1
                """,
            ),
            (
                "prediction snapshot references unknown asset",
                """
                SELECT 1 FROM stg_pm_prediction_snapshots p
                LEFT JOIN stg_pm_assets a ON a.asset_id=p.asset_id
                WHERE a.asset_id IS NULL LIMIT 1
                """,
            ),
            (
                "prediction factor references unknown snapshot",
                """
                SELECT 1 FROM stg_pm_prediction_factors f
                LEFT JOIN stg_pm_prediction_snapshots p ON p.prediction_id=f.prediction_id
                WHERE p.prediction_id IS NULL LIMIT 1
                """,
            ),
            (
                "duplicate timeline prediction_id",
                """
                SELECT 1 FROM stg_pm_prediction_timeline
                GROUP BY prediction_id HAVING COUNT(*)>1 LIMIT 1
                """,
            ),
        ]
        if "result_artifact" in summaries:
            checks.extend(
                [
                    (
                        "result artifact references unknown snapshot",
                        """
                        SELECT 1 FROM stg_pm_result_artifacts a
                        LEFT JOIN stg_pm_prediction_snapshots p
                          ON p.prediction_id=(a.provenance::jsonb->>'prediction_id')
                        WHERE p.prediction_id IS NULL LIMIT 1
                        """,
                    ),
                    (
                        "result artifact does not cover assets exactly once",
                        """
                        SELECT 1
                        FROM stg_pm_assets a
                        FULL JOIN stg_pm_result_artifacts r ON r.asset_id=a.asset_id
                        GROUP BY COALESCE(a.asset_id,r.asset_id)
                        HAVING COUNT(a.asset_id)<>1 OR COUNT(r.asset_id)<>1
                        LIMIT 1
                        """,
                    ),
                ]
            )
        for label, statement in checks:
            if connection.execute(statement).fetchone() is not None:
                raise ValueError(f"PostgreSQL staging validation failed: {label}")

        start = manifest.generation.period_start
        end = manifest.generation.period_end
        timestamp_checks = {
            "compressor_sensor_observation": (
                "stg_pm_compressor_observations",
                "observed_at",
            ),
            "cnc_sensor_observation": ("stg_pm_cnc_observations", "observed_at"),
            "cnc_production_cycle": ("stg_pm_production_cycles", "cycle_completed_at"),
            "maintenance_event": ("stg_pm_maintenance_events", "started_at"),
            "prediction_snapshot": ("stg_pm_prediction_snapshots", "observed_at"),
            "prediction_timeline": ("stg_pm_prediction_timeline", "observed_at"),
        }
        if "result_artifact" in summaries:
            timestamp_checks["result_artifact"] = ("stg_pm_result_artifacts", "observed_at")
        for role, (table, field) in timestamp_checks.items():
            outside = connection.execute(
                f"SELECT 1 FROM {table} WHERE {field}::timestamptz < %s OR {field}::timestamptz > %s LIMIT 1",
                (start, end),
            ).fetchone()
            if outside is not None:
                raise ValueError(f"PostgreSQL staging timestamp is outside bundle period: {role}")

    def _merge_targets(
        self,
        connection: Any,
        manifest: DatasetBundleManifestV2,
        version_id: str,
    ) -> None:
        scope = (
            manifest.organization_id,
            manifest.project_id,
            manifest.workspace_id,
            version_id,
        )
        checksums = {item.role: item.checksum_sha256 for item in manifest.files}
        connection.execute(
            """
            INSERT INTO pm_assets(
                organization_id,project_id,workspace_id,dataset_version_id,
                asset_id,asset_type,site_id,cell_id,source_sha256
            )
            SELECT %s,%s,%s,%s,asset_id,asset_type,site_id,cell_id,%s
            FROM stg_pm_assets
            """,
            (*scope, checksums["asset_master"]),
        )
        connection.execute(
            """
            INSERT INTO pm_asset_relations(
                organization_id,project_id,workspace_id,dataset_version_id,
                from_asset_id,relation_type,to_asset_id,source_sha256
            )
            SELECT %s,%s,%s,%s,from_asset_id,relation_type,to_asset_id,%s
            FROM stg_pm_asset_relations
            """,
            (*scope, checksums["asset_relation"]),
        )
        connection.execute(
            """
            INSERT INTO pm_compressor_observations(
                organization_id,project_id,workspace_id,dataset_version_id,observed_at,
                asset_id,site_id,cell_id,is_operating,operating_state,voltage_raw,
                rotation_raw,pressure_raw,vibration_raw,relative_vibration_z,
                relative_vibration_zone,generator_version,source_sha256
            )
            SELECT %s,%s,%s,%s,observed_at::timestamptz,asset_id,site_id,cell_id,
                   is_operating::integer=1,operating_state,voltage_raw::double precision,
                   rotation_raw::double precision,pressure_raw::double precision,
                   vibration_raw::double precision,relative_vibration_z::double precision,
                   relative_vibration_zone,generator_version,%s
            FROM stg_pm_compressor_observations
            """,
            (*scope, checksums["compressor_sensor_observation"]),
        )
        connection.execute(
            """
            INSERT INTO pm_cnc_observations(
                organization_id,project_id,workspace_id,dataset_version_id,observed_at,
                asset_id,site_id,cell_id,is_operating,operating_state,product_type,
                air_temperature_k,process_temperature_k,rotational_speed_rpm,torque_nm,
                tool_wear_min,generator_version,source_sha256
            )
            SELECT %s,%s,%s,%s,observed_at::timestamptz,asset_id,site_id,cell_id,
                   is_operating::integer=1,operating_state,product_type,
                   air_temperature_k::double precision,process_temperature_k::double precision,
                   rotational_speed_rpm::double precision,torque_nm::double precision,
                   tool_wear_min::double precision,generator_version,%s
            FROM stg_pm_cnc_observations
            """,
            (*scope, checksums["cnc_sensor_observation"]),
        )
        connection.execute(
            """
            INSERT INTO pm_production_cycles(
                organization_id,project_id,workspace_id,dataset_version_id,product_id,
                cnc_asset_id,cycle_started_at,cycle_completed_at,product_type,
                cutting_minutes,tool_wear_increment_min,source_sha256
            )
            SELECT %s,%s,%s,%s,product_id,cnc_asset_id,cycle_started_at::timestamptz,
                   cycle_completed_at::timestamptz,product_type,cutting_minutes::double precision,
                   tool_wear_increment_min::double precision,%s
            FROM stg_pm_production_cycles
            """,
            (*scope, checksums["cnc_production_cycle"]),
        )
        connection.execute(
            """
            INSERT INTO pm_maintenance_events(
                organization_id,project_id,workspace_id,dataset_version_id,maintenance_id,
                asset_id,maintenance_type,started_at,completed_at,tool_replaced,
                source_event_id,source_sha256
            )
            SELECT %s,%s,%s,%s,maintenance_id,asset_id,maintenance_type,
                   started_at::timestamptz,completed_at::timestamptz,
                   tool_replaced::integer=1,NULLIF(source_event_id,''),%s
            FROM stg_pm_maintenance_events
            """,
            (*scope, checksums["maintenance_event"]),
        )

        connection.execute(
            """
            INSERT INTO prediction_results(
                prediction_id,organization_id,project_id,workspace_id,subject_object_type,
                subject_object_id,prediction_status,model_version,dataset_version,
                payload_json,created_at,received_at
            )
            SELECT 'pmpr-'||md5(%s::text||':'||%s::text||':'||prediction_id),%s,%s,%s,'equipment',
                   asset_id,status,model_version,%s,
                   jsonb_build_object(
                       'contract_version','1.0',
                       'source_prediction_id',prediction_id,
                       'dataset_version_id',%s::text,
                       'observed_at',observed_at,
                       'prediction_horizon_hours',prediction_horizon_hours::integer,
                       'failure_probability',failure_probability::double precision,
                       'predicted_failure_type',predicted_failure_type,
                       'confidence',confidence::double precision,
                       'feature_scope',feature_scope
                   ),observed_at::timestamptz,now()
            FROM stg_pm_prediction_snapshots
            """,
            (
                manifest.project_id,
                version_id,
                manifest.organization_id,
                manifest.project_id,
                manifest.workspace_id,
                manifest.dataset_version,
                version_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO pm_prediction_snapshots(
                organization_id,project_id,workspace_id,dataset_version_id,prediction_id,
                prediction_result_id,asset_id,asset_type,observed_at,prediction_horizon_hours,
                failure_probability,predicted_failure_type,confidence,status,model_version,
                feature_scope,source_sha256
            )
            SELECT %s,%s,%s,%s,prediction_id,
                   'pmpr-'||md5(%s::text||':'||%s::text||':'||prediction_id),
                   asset_id,asset_type,observed_at::timestamptz,prediction_horizon_hours::integer,
                   failure_probability::double precision,NULLIF(predicted_failure_type,''),
                   confidence::double precision,status,model_version,to_jsonb(feature_scope),%s
            FROM stg_pm_prediction_snapshots
            """,
            (*scope, manifest.project_id, version_id, checksums["prediction_snapshot"]),
        )
        connection.execute(
            """
            INSERT INTO pm_prediction_factors(
                organization_id,project_id,workspace_id,dataset_version_id,prediction_id,
                rank,feature,feature_value,signed_contribution,absolute_contribution,direction,
                explanation_method,source_type,source_sha256
            )
            SELECT %s,%s,%s,%s,prediction_id,rank::integer,feature,
                   feature_value::double precision,signed_contribution::double precision,
                   absolute_contribution::double precision,direction,explanation_method,
                   source_type,%s
            FROM stg_pm_prediction_factors
            """,
            (*scope, checksums["prediction_factor"]),
        )
        connection.execute(
            """
            INSERT INTO pm_prediction_timeline(
                organization_id,project_id,workspace_id,dataset_version_id,prediction_id,
                asset_id,asset_type,observed_at,prediction_horizon_hours,failure_probability,
                status,top_factors,model_version,feature_scope,source_type,source_sha256
            )
            SELECT %s,%s,%s,%s,prediction_id,asset_id,asset_type,observed_at::timestamptz,
                   prediction_horizon_hours::integer,failure_probability::double precision,
                   status,top_factors::jsonb,model_version,to_jsonb(feature_scope),source_type,%s
            FROM stg_pm_prediction_timeline
            """,
            (*scope, checksums["prediction_timeline"]),
        )

        if "result_artifact" in checksums:
            connection.execute(
                """
                INSERT INTO pm_result_artifacts(
                    organization_id,project_id,workspace_id,dataset_version_id,artifact_id,
                    prediction_id,prediction_result_id,asset_id,asset_type,observed_at,
                    prediction_horizon_hours,prediction_task,failure_probability,
                    predicted_failure_type,status_grade,confidence,top_factors,
                    recommended_action,provenance,schema_version,model_version,source_sha256
                )
                SELECT %s,%s,%s,%s,artifact_id,
                       provenance::jsonb->>'prediction_id',
                       'pmpr-'||md5(%s::text||':'||%s::text||':'||
                           (provenance::jsonb->>'prediction_id')),
                       asset_id,asset_type,observed_at::timestamptz,
                       prediction_horizon_hours::integer,prediction_task,
                       failure_probability::double precision,predicted_failure_type,
                       status_grade,confidence::double precision,top_factors::jsonb,
                       recommended_action::jsonb,provenance::jsonb,schema_version,
                       provenance::jsonb->>'model_version',%s
                FROM stg_pm_result_artifacts
                """,
                (
                    *scope,
                    manifest.project_id,
                    version_id,
                    checksums["result_artifact"],
                ),
            )

    @staticmethod
    def _target_row_counts(
        connection: Any,
        version_id: str,
        roles: set[str],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for role in sorted(roles):
            table = ROLE_TARGET_TABLES[role]
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE dataset_version_id=%s",
                (version_id,),
            ).fetchone()
            counts[role] = int(row["count"])
        return counts

    @staticmethod
    def _assert_row_count_parity(
        validation: BundleValidationResult,
        row_counts: dict[str, int],
    ) -> None:
        expected = {item.role: item.source_record_count for item in validation.roles}
        if row_counts != expected:
            raise RuntimeError(
                f"PostgreSQL/source row count parity failed: expected={expected}, actual={row_counts}"
            )

    @staticmethod
    def _mark_control_run_completed(
        connection: Any,
        result: PostgreSQLBundleIngestionResult,
        jsonb: Any,
    ) -> None:
        connection.execute(
            """
            UPDATE adapter_ingestion_runs
            SET status='completed',dataset_id=%s,dataset_version_id=%s,
                accepted_record_count=%s,quarantined_record_count=0,
                metrics_json=%s,error_message=NULL,completed_at=now()
            WHERE id=%s AND organization_id=%s AND project_id=%s
            """,
            (
                result.dataset_id,
                result.dataset_version_id,
                result.source_record_count,
                jsonb(
                    {
                        "row_counts": result.row_counts,
                        "reused_dataset_version": result.reused_dataset_version,
                        "outbox_event_id": result.outbox_event_id,
                    }
                ),
                result.ingestion_run_id,
                result.organization_id,
                result.project_id,
            ),
        )
        connection.execute(
            """
            UPDATE dataset_manifests SET status='completed',updated_at=now()
            WHERE id=%s AND organization_id=%s AND project_id=%s
            """,
            (
                result.manifest_record_id,
                result.organization_id,
                result.project_id,
            ),
        )

    def _fail_control_run(
        self,
        *,
        manifest: DatasetBundleManifestV2,
        run_id: str,
        error_message: str,
    ) -> None:
        psycopg, _, dict_row, Jsonb = _require_psycopg()
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._set_scope(connection, manifest)
                connection.execute(
                    """
                    UPDATE adapter_ingestion_runs
                    SET status='failed',accepted_record_count=0,quarantined_record_count=0,
                        metrics_json=%s,error_message=%s,completed_at=now()
                    WHERE id=%s AND organization_id=%s AND project_id=%s
                    """,
                    (
                        Jsonb({"atomic_bundle_transaction_rolled_back": True}),
                        error_message[:4000],
                        run_id,
                        manifest.organization_id,
                        manifest.project_id,
                    ),
                )
                connection.execute(
                    """
                    UPDATE dataset_manifests SET status='failed',updated_at=now()
                    WHERE organization_id=%s AND project_id=%s
                      AND source_checksum=%s
                    """,
                    (
                        manifest.organization_id,
                        manifest.project_id,
                        manifest.bundle_checksum_sha256,
                    ),
                )


__all__ = [
    "PostgreSQLPredictiveMaintenanceBundleIngestor",
    "ROLE_TARGET_TABLES",
]
