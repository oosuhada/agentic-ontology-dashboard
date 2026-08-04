from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from ontology_dashboard.adapters import (
    BundleFileAdapter,
    PostgreSQLPredictiveMaintenanceBundleIngestor,
    PredictiveMaintenanceCanonicalV2Adapter,
)
from ontology_dashboard.domain_packs.predictive_maintenance import (
    PredictiveMaintenanceOntologyMaterializer,
)
from ontology_dashboard.postgresql_ontology_repository import (
    PostgreSQLOntologyInstanceRepository,
)
from predictive_maintenance_v3_helpers import create_small_v3_package
from test_predictive_maintenance_bundle_adapter import create_small_package
from test_predictive_maintenance_postgresql import (
    _changed_schema_manifest,
    postgresql_database,
)


def build(root: Path):
    return PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        root,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        manifest_id="pm-versioned-dataset",
    )


def ingest(database_url: str, root: Path):
    manifest = build(root)
    validation = BundleFileAdapter(allowed_roots=[root]).validate(manifest)
    assert validation.status == "completed"
    return manifest, PostgreSQLPredictiveMaintenanceBundleIngestor(
        database_url
    ).ingest_validated_bundle(manifest=manifest, validation=validation)


def _dsn_for_user(database_url: str, user: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit(("postgresql", f"{user}@{host}", parsed.path, parsed.query, ""))


def test_v2_v3_materialization_is_versioned_governed_and_idempotent(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    v3_root = create_small_v3_package(tmp_path / "v3")
    v3_manifest, v3_ingestion = ingest(postgresql_database, v3_root)
    materializer = PredictiveMaintenanceOntologyMaterializer(postgresql_database)
    draft = materializer.ensure_default_mapping(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=v3_ingestion.dataset_id,
        dataset_version_id=v3_ingestion.dataset_version_id,
    )
    assert draft["status"] == "draft"
    with pytest.raises(ValueError, match="approved"):
        materializer.materialize(
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            dataset_id=v3_ingestion.dataset_id,
            dataset_version_id=v3_ingestion.dataset_version_id,
        )

    materializer.ensure_default_mapping(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=v3_ingestion.dataset_id,
        dataset_version_id=v3_ingestion.dataset_version_id,
        approve=True,
        approved_by="test-fde",
    )
    first = materializer.materialize(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=v3_ingestion.dataset_id,
        dataset_version_id=v3_ingestion.dataset_version_id,
    )
    second = materializer.materialize(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=v3_ingestion.dataset_id,
        dataset_version_id=v3_ingestion.dataset_version_id,
    )
    assert first.object_counts == second.object_counts == {
        "equipment": 2,
        "maintenance_action": 1,
        "prediction_result": 2,
        "production_cell": 1,
        "production_cycle": 1,
        "risk_event": 2,
        "site": 1,
        "work_order": 1,
    }
    assert first.link_count == second.link_count == 13
    assert first.materialization_checksum_sha256 == second.materialization_checksum_sha256
    assert first.outbox_event_id == second.outbox_event_id

    repository = PostgreSQLOntologyInstanceRepository(
        postgresql_database,
        organization_id="org-test",
        project_id="project-test",
    )
    objects = repository.list_objects(workspace_id="workspace-test")
    links = repository.list_links(workspace_id="workspace-test")
    v3_objects = [
        item
        for item in objects
        if item.properties.get("dataset_version_id") == v3_ingestion.dataset_version_id
    ]
    v3_links = [
        item
        for item in links
        if item.properties.get("dataset_version_id") == v3_ingestion.dataset_version_id
    ]
    assert len(v3_objects) == first.object_count
    assert len(v3_links) == first.link_count
    assert not any(item.object_type in {"sensor_observation", "prediction_timeline"} for item in v3_objects)
    risk_events = [item for item in v3_objects if item.object_type == "risk_event"]
    assert len(risk_events) == 2
    assert all(item.properties["result_contract_source"] == "result_artifact" for item in risk_events)
    assert all(item.properties["recommendation_execution_state"] == "not_executed" for item in risk_events)
    assert not any(item.link_type == "risk_event_requires_work_order" for item in v3_links)
    rendered = json.dumps(
        [item.model_dump(mode="json") for item in [*v3_objects, *v3_links]],
        ensure_ascii=False,
    ).lower()
    for forbidden in (
        "evaluation_truth",
        "hidden_truth",
        "condition_variant",
        "source_event_id",
    ):
        assert forbidden not in rendered
    assert {item.properties["predicted_failure_type"] for item in risk_events}.issubset(
        {"failure_risk", "no_significant_risk"}
    )

    v2_root = create_small_package(tmp_path / "v2")
    _, v2_ingestion = ingest(postgresql_database, v2_root)
    materializer.ensure_default_mapping(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=v2_ingestion.dataset_id,
        dataset_version_id=v2_ingestion.dataset_version_id,
        approve=True,
    )
    v2_result = materializer.materialize(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=v2_ingestion.dataset_id,
        dataset_version_id=v2_ingestion.dataset_version_id,
    )
    assert v2_ingestion.dataset_id == v3_ingestion.dataset_id
    assert v2_ingestion.dataset_version_id != v3_ingestion.dataset_version_id
    all_objects = repository.list_objects(workspace_id="workspace-test")
    v2_ids = {
        item.id
        for item in all_objects
        if item.properties.get("dataset_version_id") == v2_ingestion.dataset_version_id
    }
    v3_ids = {item.id for item in v3_objects}
    assert v2_ids and v3_ids and v2_ids.isdisjoint(v3_ids)
    v2_risk = [
        item
        for item in all_objects
        if item.object_type == "risk_event"
        and item.properties.get("dataset_version_id") == v2_ingestion.dataset_version_id
    ]
    assert v2_result.object_count == 11
    assert all(item.properties["result_contract_source"] == "prediction_snapshot" for item in v2_risk)

    revised_manifest = _changed_schema_manifest(v3_manifest)
    revised_validation = BundleFileAdapter(allowed_roots=[v3_root]).validate(revised_manifest)
    revised = PostgreSQLPredictiveMaintenanceBundleIngestor(
        postgresql_database
    ).ingest_validated_bundle(manifest=revised_manifest, validation=revised_validation)
    materializer.ensure_default_mapping(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=revised.dataset_id,
        dataset_version_id=revised.dataset_version_id,
        approve=True,
    )
    with pytest.raises(RuntimeError, match="injected ontology materialization failure"):
        materializer.materialize(
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            dataset_id=revised.dataset_id,
            dataset_version_id=revised.dataset_version_id,
            fail_after_object_type="equipment",
        )
    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM ontology_objects WHERE dataset_version_id=%s",
                (revised.dataset_version_id,),
            ).fetchone()["count"]
        ) == 0
        assert int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM transactional_outbox WHERE aggregate_id=%s AND event_type='ontology.materialization.completed'",
                (v3_ingestion.dataset_version_id,),
            ).fetchone()["count"]
        ) == 1

    role = f"pm_projection_rls_{uuid.uuid4().hex[:10]}"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT SELECT ON ontology_objects TO {}").format(sql.Identifier(role)))
        with psycopg.connect(_dsn_for_user(postgresql_database, role), row_factory=dict_row) as scoped:
            scoped.execute("SELECT set_config('app.organization_id','org-test',false)")
            scoped.execute("SELECT set_config('app.project_id','project-test',false)")
            visible = int(scoped.execute("SELECT COUNT(*) AS count FROM ontology_objects").fetchone()["count"])
            scoped.execute("SELECT set_config('app.project_id','project-other',false)")
            hidden = int(scoped.execute("SELECT COUNT(*) AS count FROM ontology_objects").fetchone()["count"])
        assert visible == first.object_count + v2_result.object_count
        assert hidden == 0
    finally:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
