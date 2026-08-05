from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from ontology_dashboard.adapters import (
    BundleFileAdapter,
    DatasetBundleManifestV2,
    PostgreSQLPredictiveMaintenanceBundleIngestor,
    compute_bundle_checksum,
)
from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.models import DatasetIntakeProfile, canonical_checksum
from ontology_dashboard.modeling.repository import ModelingRepository
from ontology_dashboard.postgresql_pool import close_pools
from tests.test_predictive_maintenance_bundle_adapter import (
    build_manifest,
    create_small_package,
)


def _postgres_tools_available() -> bool:
    required = ("createdb", "dropdb", "pg_isready")
    if any(shutil.which(command) is None for command in required):
        return False
    return subprocess.run(
        ["pg_isready", "-h", "127.0.0.1", "-p", "5432"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _dsn_for_database(database: str) -> str:
    return f"postgresql://{subprocess.check_output(['whoami'], text=True).strip()}@127.0.0.1:5432/{database}"


def _dsn_for_user(database_url: str, user: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit(("postgresql", f"{user}@{host}", parsed.path, parsed.query, ""))


@pytest.fixture()
def postgresql_database():
    if not _postgres_tools_available():
        pytest.skip("local disposable PostgreSQL is unavailable")
    database = f"od_pm_test_{uuid.uuid4().hex[:12]}"
    subprocess.run(["createdb", database], check=True)
    dsn = _dsn_for_database(database)
    try:
        applied = migrate(dsn)
        assert applied[-1] == "0023_production_connectors_ingestion"
        assert migrate(dsn) == []
        import psycopg

        with psycopg.connect(dsn) as connection:
            connection.execute(
                """
                INSERT INTO organizations(id,slug,name) VALUES
                    ('org-test','org-test','Org Test');
                INSERT INTO projects(
                    id,organization_id,slug,display_name,domain_pack_code
                ) VALUES
                    ('project-test','org-test','project-test','Project Test','predictive-maintenance'),
                    ('project-other','org-test','project-other','Project Other','predictive-maintenance');
                INSERT INTO workspaces(
                    id,organization_id,project_id,slug,display_name,domain_pack
                ) VALUES
                    ('workspace-test','org-test','project-test','workspace-test','Workspace Test','predictive-maintenance'),
                    ('workspace-other','org-test','project-other','workspace-other','Workspace Other','predictive-maintenance');
                INSERT INTO users(id,organization_id,email,display_name,status) VALUES
                    ('runtime-user','org-test','runtime@example.com','Runtime User','active'),
                    ('runtime-user-other','org-test','runtime-other@example.com','Runtime Other','active');
                """
            )
        yield dsn
    finally:
        close_pools()
        subprocess.run(["dropdb", "--if-exists", database], check=False)


def _changed_schema_manifest(manifest: DatasetBundleManifestV2) -> DatasetBundleManifestV2:
    schema_version = f"{manifest.schema_version}.revision-2"
    checksum = compute_bundle_checksum(
        dataset_version=manifest.dataset_version,
        schema_version=schema_version,
        generation=manifest.generation,
        source_contract=manifest.source_contract,
        files=manifest.files,
    )
    return DatasetBundleManifestV2.model_validate(
        {
            **manifest.model_dump(mode="python", by_alias=True),
            "schema_version": schema_version,
            "bundle_checksum_sha256": checksum,
        }
    )


def test_postgresql_copy_idempotency_rls_and_atomic_rollback(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    package_root = create_small_package(tmp_path)
    manifest = build_manifest(package_root)
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    assert validation.status == "completed"
    expected = {item.role: item.source_record_count for item in validation.roles}
    ingestor = PostgreSQLPredictiveMaintenanceBundleIngestor(postgresql_database)

    first = ingestor.ingest_validated_bundle(manifest=manifest, validation=validation)
    assert first.reused_dataset_version is False
    assert first.row_counts == expected
    assert first.source_record_count == sum(expected.values())

    second = ingestor.ingest_validated_bundle(manifest=manifest, validation=validation)
    assert second.reused_dataset_version is True
    assert second.dataset_id == first.dataset_id
    assert second.dataset_version_id == first.dataset_version_id
    assert second.row_counts == expected
    assert second.outbox_event_id is None

    revised_manifest = _changed_schema_manifest(manifest)
    revised_validation = BundleFileAdapter(allowed_roots=[package_root]).validate(
        revised_manifest
    )
    revised = ingestor.ingest_validated_bundle(
        manifest=revised_manifest,
        validation=revised_validation,
    )
    assert revised.reused_dataset_version is False
    assert revised.dataset_id == first.dataset_id
    assert revised.dataset_version_id != first.dataset_version_id
    assert revised.version_number == first.version_number + 1
    assert revised.row_counts == expected

    other_manifest = DatasetBundleManifestV2.model_validate(
        {
            **manifest.model_dump(mode="python", by_alias=True),
            "project_id": "project-other",
            "workspace_id": "workspace-other",
        }
    )
    other_validation = BundleFileAdapter(allowed_roots=[package_root]).validate(
        other_manifest
    )
    with pytest.raises(RuntimeError, match="injected bundle transaction failure"):
        ingestor.ingest_validated_bundle(
            manifest=other_manifest,
            validation=other_validation,
            fail_after_role="asset_master",
        )

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        version_rows = connection.execute(
            "SELECT id,checksum_sha256 FROM dataset_versions WHERE dataset_id=%s ORDER BY version_number",
            (first.dataset_id,),
        ).fetchall()
        assert [str(row["id"]) for row in version_rows] == [
            first.dataset_version_id,
            revised.dataset_version_id,
        ]
        assert len({str(row["checksum_sha256"]) for row in version_rows}) == 2
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM transactional_outbox WHERE event_type='dataset.version.relational_ready'"
            ).fetchone()["count"]
        ) == 2
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM adapter_ingestion_runs WHERE project_id='project-test' AND status='completed'"
            ).fetchone()["count"]
        ) == 3
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM adapter_ingestion_runs WHERE project_id='project-other' AND status='failed'"
            ).fetchone()["count"]
        ) == 1
        for table in (
            "datasets",
            "dataset_versions",
            "pm_assets",
            "pm_asset_relations",
            "pm_compressor_observations",
            "pm_cnc_observations",
            "pm_production_cycles",
            "pm_maintenance_events",
            "pm_prediction_snapshots",
            "pm_prediction_factors",
            "pm_prediction_timeline",
            "transactional_outbox",
        ):
            count = int(
                connection.execute(
                    sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE project_id='project-other'").format(
                        sql.Identifier(table)
                    )
                ).fetchone()["count"]
            )
            assert count == 0, table

        orphan_checks = [
            """
            SELECT COUNT(*) AS count FROM pm_asset_relations r
            LEFT JOIN pm_assets a ON a.dataset_version_id=r.dataset_version_id
                AND a.asset_id=r.from_asset_id
            WHERE a.asset_id IS NULL
            """,
            """
            SELECT COUNT(*) AS count FROM pm_prediction_factors f
            LEFT JOIN pm_prediction_snapshots p
                ON p.dataset_version_id=f.dataset_version_id
                AND p.prediction_id=f.prediction_id
            WHERE p.prediction_id IS NULL
            """,
        ]
        assert all(
            int(connection.execute(statement).fetchone()["count"]) == 0
            for statement in orphan_checks
        )

    role = f"pm_rls_test_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(
                sql.SQL("GRANT SELECT ON pm_assets TO {}").format(sql.Identifier(role))
            )
        with psycopg.connect(_dsn_for_user(postgresql_database, role), row_factory=dict_row) as scoped:
            scoped.execute("SELECT set_config('app.organization_id','org-test',false)")
            scoped.execute("SELECT set_config('app.project_id','project-test',false)")
            visible = int(scoped.execute("SELECT COUNT(*) AS count FROM pm_assets").fetchone()["count"])
            scoped.execute("SELECT set_config('app.project_id','project-other',false)")
            hidden = int(scoped.execute("SELECT COUNT(*) AS count FROM pm_assets").fetchone()["count"])
        assert visible == expected["asset_master"] * 2
        assert hidden == 0
    finally:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def test_postgresql_adaptive_modeling_repository_jsonb_idempotency_and_rls(
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    repository = ModelingRepository(postgresql_database)
    source_checksum = "a" * 64
    profile = DatasetIntakeProfile(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        profile_id="profile-postgresql-runtime",
        source_uri="file:///tmp/governed-source.csv",
        source_checksum_sha256=source_checksum,
        parser_version="dataset-intake-v1",
        cache_key=canonical_checksum(
            {
                "source_checksum_sha256": source_checksum,
                "parser_version": "dataset-intake-v1",
            }
        ),
        byte_size=128,
        media_type="text/csv",
        status="ready_for_review",
        structure_type="tabular_column_as_attribute",
        row_count=2,
        idempotency_key="profile-postgresql-runtime",
    )
    first = repository.put(
        "intake_profile",
        profile.model_dump(mode="json"),
        idempotency_key=profile.idempotency_key,
    )
    repeated = repository.put(
        "intake_profile",
        profile.model_dump(mode="json"),
        idempotency_key=profile.idempotency_key,
    )
    assert repeated == first
    assert repository.get(
        "intake_profile",
        profile.profile_id,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
    )["source_checksum_sha256"] == source_checksum
    with pytest.raises(KeyError):
        repository.get(
            "intake_profile",
            profile.profile_id,
            organization_id="org-test",
            project_id="project-other",
            workspace_id="workspace-other",
        )
    repository.record_audit(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        actor_id="user-test",
        action="modeling.profile.verified",
        aggregate_type="DatasetIntakeProfile",
        aggregate_id=profile.profile_id,
        payload={"checksum": source_checksum},
    )
    assert repository.list_audit(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
    )[0]["payload"]["checksum"] == source_checksum

    role = f"modeling_rls_test_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(
                sql.SQL("GRANT SELECT ON modeling_intake_profiles TO {}").format(
                    sql.Identifier(role)
                )
            )
        with psycopg.connect(
            _dsn_for_user(postgresql_database, role), row_factory=dict_row
        ) as scoped:
            scoped.execute("SELECT set_config('app.organization_id','org-test',false)")
            scoped.execute("SELECT set_config('app.project_id','project-test',false)")
            visible = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM modeling_intake_profiles"
                ).fetchone()["count"]
            )
            scoped.execute("SELECT set_config('app.project_id','project-other',false)")
            hidden = int(
                scoped.execute(
                    "SELECT COUNT(*) AS count FROM modeling_intake_profiles"
                ).fetchone()["count"]
            )
        assert visible == 1
        assert hidden == 0
    finally:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
