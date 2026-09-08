from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

from app.dataset.ingestion import (
    BundleFileAdapter,
    PredictiveMaintenanceCanonicalV2Adapter,
)
from app.infra.db.postgresql_bundle_ingestion import PostgreSQLPredictiveMaintenanceBundleIngestor
from app.infra.db.predictive_maintenance_ontology_projection import (
    PredictiveMaintenanceOntologyMaterializer,
    _aggregate_source_sha256,
)
from app.infra.db.postgresql_ontology_repository import (
    PostgreSQLOntologyInstanceRepository,
)
from app.infra.external.project3 import (
    PredictiveMaintenanceProject3ProjectionHandler,
    Project3ProjectionDeliveryError,
)
from app.infra.messaging.outbox import OutboxMessage
from app.project3_projection_worker import (
    _latest_materialization_message,
    _supersede_stale_materialization_messages,
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


def test_runtime_result_source_checksums_are_aggregated_deterministically() -> None:
    first = "1" * 64
    second = "2" * 64
    expected = hashlib.sha256(f"{first}\n{second}".encode("ascii")).hexdigest()

    assert _aggregate_source_sha256([second, first, second]) == expected
    assert _aggregate_source_sha256([first]) == first
    with pytest.raises(ValueError, match="at least one SHA-256"):
        _aggregate_source_sha256([])


def test_graph_bootstrap_selects_current_materialization_and_rejects_stale_event(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    root = create_small_v3_package(tmp_path / "v3-current")
    _manifest, ingestion = ingest(postgresql_database, root)
    materializer = PredictiveMaintenanceOntologyMaterializer(postgresql_database)
    materializer.ensure_default_mapping(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=ingestion.dataset_id,
        dataset_version_id=ingestion.dataset_version_id,
        approve=True,
        approved_by="test-current-materialization",
    )
    current = materializer.materialize(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=ingestion.dataset_id,
        dataset_version_id=ingestion.dataset_version_id,
    )

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        current_row = connection.execute(
            "SELECT payload_json FROM transactional_outbox WHERE id=%s",
            (current.outbox_event_id,),
        ).fetchone()
        assert current_row is not None
        stale_payload = dict(current_row["payload_json"])
        stale_payload["materialization_checksum_sha256"] = "0" * 64
        stale_payload["object_counts"] = {"equipment": 1}
        stale_payload["link_counts"] = {}
        stale_id = uuid.uuid4()
        historical_payload = dict(current_row["payload_json"])
        historical_payload["dataset_version_id"] = "dsv-historical"
        historical_payload["materialization_checksum_sha256"] = "1" * 64
        historical_id = uuid.uuid4()
        connection.execute(
            """
            INSERT INTO transactional_outbox(
                id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                event_type,payload_json,status,created_at,available_at
            ) VALUES (%s,'org-test','project-test','workspace-test','dataset_version',%s,
                      'ontology.materialization.completed',%s,'pending',now()+interval '10 minutes',now())
            """,
            (stale_id, ingestion.dataset_version_id, Jsonb(stale_payload)),
        )
        connection.execute(
            """
            INSERT INTO transactional_outbox(
                id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                event_type,payload_json,status,attempt_count,created_at,available_at,last_error
            ) VALUES (%s,'org-test','project-test','workspace-test','dataset_version','dsv-historical',
                      'ontology.materialization.completed',%s,'dead_letter',5,
                      now()-interval '10 minutes',now(),'historical projection failure')
            """,
            (historical_id, Jsonb(historical_payload)),
        )
        connection.commit()

    selected = _latest_materialization_message(
        postgresql_database,
        organization_id="org-test",
        project_id="project-test",
    )
    assert selected is not None
    assert selected.id == current.outbox_event_id
    assert selected.payload["materialization_checksum_sha256"] == (
        current.materialization_checksum_sha256
    )

    stale_message = OutboxMessage(
        id=str(stale_id),
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        aggregate_type="dataset_version",
        aggregate_id=ingestion.dataset_version_id,
        event_type="ontology.materialization.completed",
        payload=stale_payload,
        attempt_count=0,
        lease_token="stale-projection-test",
    )
    with pytest.raises(Project3ProjectionDeliveryError) as exc_info:
        PredictiveMaintenanceProject3ProjectionHandler(
            postgresql_database,
            client=object(),
        ).build_request(stale_message)
    assert exc_info.value.retryable is False
    assert "stale ontology materialization event" in str(exc_info.value)

    assert _supersede_stale_materialization_messages(
        postgresql_database,
        organization_id="org-test",
        project_id="project-test",
    ) == 2
    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        stale_state = connection.execute(
            "SELECT status,processed_at,last_error FROM transactional_outbox WHERE id=%s",
            (stale_id,),
        ).fetchone()
        delivery = connection.execute(
            "SELECT handler_code FROM outbox_delivery_log WHERE outbox_id=%s",
            (stale_id,),
        ).fetchone()
        historical_state = connection.execute(
            "SELECT status,processed_at,last_error FROM transactional_outbox WHERE id=%s",
            (historical_id,),
        ).fetchone()
        historical_delivery = connection.execute(
            "SELECT handler_code FROM outbox_delivery_log WHERE outbox_id=%s",
            (historical_id,),
        ).fetchone()
    assert stale_state is not None
    assert stale_state["status"] == "processed"
    assert stale_state["processed_at"] is not None
    assert stale_state["last_error"] is None
    assert delivery is not None
    assert delivery["handler_code"] == (
        "project3-versioned-graph-projection-v1:superseded"
    )
    assert historical_state is not None
    assert historical_state["status"] == "processed"
    assert historical_state["processed_at"] is not None
    assert historical_state["last_error"] is None
    assert historical_delivery is not None
    assert historical_delivery["handler_code"] == (
        "project3-versioned-graph-projection-v1:superseded"
    )


def ingest(database_url: str, root: Path):
    manifest = build(root)
    validation = BundleFileAdapter(allowed_roots=[root]).validate(manifest)
    assert validation.status == "completed"
    return manifest, PostgreSQLPredictiveMaintenanceBundleIngestor(
        database_url
    ).ingest_validated_bundle(manifest=manifest, validation=validation)


def _dsn_for_user(database_url: str, user: str, password: str | None = None) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    credentials = user if not password else f"{user}:{password}"
    return urlunsplit(("postgresql", f"{credentials}@{host}", parsed.path, parsed.query, ""))


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
        "component": 8,
        "equipment": 2,
        "maintenance_action": 1,
        "prediction_result": 2,
        "product": 1,
        "production_cell": 1,
        "production_cycle": 1,
        "risk_event": 2,
        "site": 1,
        "sop": 1,
        "work_order": 1,
    }
    assert first.link_count == second.link_count == 27
    assert first.materialization_checksum_sha256 == second.materialization_checksum_sha256
    assert first.outbox_event_id == second.outbox_event_id
    assert first.mapping_version == "predictive-maintenance-v3.2"

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        outbox_payload = connection.execute(
            """
            SELECT payload_json FROM transactional_outbox
            WHERE id=%s AND event_type='ontology.materialization.completed'
            """,
            (first.outbox_event_id,),
        ).fetchone()["payload_json"]
    assert outbox_payload["source_version"] == "canonical-ai4i-physics-v3.1"
    assert outbox_payload["bundle_checksum_sha256"] == v3_manifest.bundle_checksum_sha256
    assert outbox_payload["materialization_checksum_sha256"] == (
        first.materialization_checksum_sha256
    )
    assert outbox_payload["result_contract"] == {
        "source_role": "result_artifact",
        "schema_versions": ["result-artifact-v1.0"],
        "model_versions": ["independent-logreg-v3.1"],
        "prediction_tasks": ["binary_failure_within_horizon"],
        "predicted_failure_type_semantics": (
            "generic_binary_risk_not_ai4i_failure_mode"
        ),
        "source_sha256": outbox_payload["role_checksums"]["result_artifact"],
    }
    assert outbox_payload["release_gates"]["tool_wear_continuity"]["pass"] is True
    assert outbox_payload["release_gates"]["tool_wear_continuity"][
        "tool_replacement_event_count"
    ] == 731
    assert outbox_payload["release_gates"]["agent_example_evaluation"][
        "maintenance_evidence_accuracy"
    ] == 1.0
    assert {item["role"] for item in outbox_payload["governance_artifacts"]} == {
        "package_validation",
        "agent_example_evaluation",
    }
    assert outbox_payload["topology_semantics"] == {
        "SUPPLIES_AIR_TO": "topology_only_not_causal_truth",
        "causal_claim_allowed": False,
    }
    assert "canonical/evaluation_truth" in outbox_payload["excluded_sources"]

    projection_request = PredictiveMaintenanceProject3ProjectionHandler(
        postgresql_database,
        client=object(),  # build_request is a pure PostgreSQL -> contract translation.
    ).build_request(
        OutboxMessage(
            id=first.outbox_event_id,
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            aggregate_type="dataset_version",
            aggregate_id=v3_ingestion.dataset_version_id,
            event_type="ontology.materialization.completed",
            payload=outbox_payload,
            attempt_count=0,
            lease_token="projection-contract-test",
        )
    )
    assert {node.identity.object_type for node in projection_request.nodes}.issuperset(
        {"equipment", "component", "product", "sop", "risk_event"}
    )
    relationship_types = {
        relationship.relationship_type
        for relationship in projection_request.relationships
    }
    assert {"HAS_COMPONENT", "INSPECTED_BY", "PRODUCES_PRODUCT", "CURRENTLY_PRODUCES"}.issubset(
        relationship_types
    )
    assert all(node.identity.dataset_version_id == v3_ingestion.dataset_version_id for node in projection_request.nodes)

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
    assert len([item for item in v3_objects if item.object_type == "component"]) == 8
    assert len([item for item in v3_objects if item.object_type == "product"]) == 1
    assert len([item for item in v3_objects if item.object_type == "sop"]) == 1
    assert len([item for item in v3_links if item.link_type == "equipment_has_component"]) == 8
    assert len([item for item in v3_links if item.link_type == "component_inspected_by_sop"]) == 4
    assert len([item for item in v3_links if item.link_type == "equipment_produces_product"]) == 1
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
    assert v2_result.object_count == 21
    v2_components = [
        item
        for item in all_objects
        if item.object_type == "component"
        and item.properties.get("dataset_version_id") == v2_ingestion.dataset_version_id
    ]
    assert len(v2_components) == 8
    assert all(v2_ingestion.dataset_version_id in item.id for item in v2_components)
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
    role_password = "runtime-test-password"
    try:
        with psycopg.connect(postgresql_database, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role),
                    sql.Literal(role_password),
                )
            )
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT SELECT ON ontology_objects TO {}").format(sql.Identifier(role)))
        with psycopg.connect(
            _dsn_for_user(postgresql_database, role, role_password),
            row_factory=dict_row,
        ) as scoped:
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
