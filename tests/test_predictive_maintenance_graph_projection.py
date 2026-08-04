from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from ontology_dashboard.adapters import (
    BundleFileAdapter,
    PostgreSQLPredictiveMaintenanceBundleIngestor,
    PredictiveMaintenanceCanonicalV2Adapter,
)
from ontology_dashboard.domain_packs.predictive_maintenance import (
    PredictiveMaintenanceOntologyMaterializer,
)
from ontology_dashboard.integrations.project3 import (
    PredictiveMaintenanceProject3ProjectionHandler,
    Project3Client,
    Project3ProjectionDeliveryError,
)
from ontology_dashboard.outbox import OutboxMessage
from predictive_maintenance_v3_helpers import create_small_v3_package
from test_predictive_maintenance_postgresql import postgresql_database


def build(root: Path):
    return PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        root,
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        manifest_id="pm-versioned-dataset",
    )


def materialize(postgresql_database: str, root: Path):
    manifest = build(root)
    validation = BundleFileAdapter(allowed_roots=[root]).validate(manifest)
    assert validation.status == "completed"
    ingestion = PostgreSQLPredictiveMaintenanceBundleIngestor(
        postgresql_database
    ).ingest_validated_bundle(manifest=manifest, validation=validation)
    materializer = PredictiveMaintenanceOntologyMaterializer(postgresql_database)
    materializer.ensure_default_mapping(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=ingestion.dataset_id,
        dataset_version_id=ingestion.dataset_version_id,
        approve=True,
        approved_by="phase4-test",
    )
    result = materializer.materialize(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        dataset_id=ingestion.dataset_id,
        dataset_version_id=ingestion.dataset_version_id,
    )
    return manifest, ingestion, result


def outbox_message(database_url: str, dataset_version_id: str) -> OutboxMessage:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT * FROM transactional_outbox
            WHERE aggregate_id=%s
              AND event_type='ontology.materialization.completed'
            """,
            (dataset_version_id,),
        ).fetchone()
    assert row is not None
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return OutboxMessage(
        id=str(row["id"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
        workspace_id=str(row["workspace_id"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        event_type=str(row["event_type"]),
        payload=dict(payload),
        attempt_count=int(row["attempt_count"]),
    )


def test_outbox_projection_preserves_v3_contract_and_marks_graph_ready(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    root = create_small_v3_package(tmp_path)
    _, ingestion, materialization = materialize(postgresql_database, root)
    message = outbox_message(
        postgresql_database,
        ingestion.dataset_version_id,
    )
    seen: list[dict] = []

    def responder(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            "/api/v1/projects/project-test/graph/projections"
        )
        assert request.headers["X-Organization-ID"] == "org-test"
        assert request.headers["X-Project-ID"] == "project-test"
        assert request.headers["X-Workspace-ID"] == "workspace-test"
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            request=request,
            json={
                "contract_version": "1.0",
                "message_type": "graph_projection_response",
                "projection_id": body["projection_id"],
                "project_id": body["project_id"],
                "dataset_version_id": body["dataset_version_id"],
                "status": "completed",
                "project3_run_id": "p3-run-001",
                "projection_checksum_sha256": "f" * 64,
                "idempotent_replay": len(seen) > 1,
                "counts": {
                    "nodes_received": len(body["nodes"]),
                    "relationships_received": len(body["relationships"]),
                    "nodes_written": len(body["nodes"]),
                    "relationships_written": len(body["relationships"]),
                },
                "error": None,
                "updated_at": "2026-08-04T10:00:00Z",
            },
        )

    client = Project3Client(
        base_url="http://project3.test",
        max_retries=0,
        transport=httpx.MockTransport(responder),
    )
    handler = PredictiveMaintenanceProject3ProjectionHandler(
        postgresql_database,
        client,
    )
    request = handler.build_request(message)
    assert len(request.nodes) == materialization.object_count == 11
    assert len(request.relationships) == materialization.link_count == 13
    assert request.mapping_id.startswith("pm-map-")
    assert request.mapping_version == "predictive-maintenance-v3.1"
    assert request.result_contract.source_role == "result_artifact"
    assert request.result_contract.schema_versions == ["result-artifact-v1.0"]
    assert request.result_contract.model_versions == ["independent-logreg-v3.1"]
    assert request.release_gates["tool_wear_continuity"][
        "tool_replacement_event_count"
    ] == 731
    assert request.release_gates["agent_example_evaluation"][
        "maintenance_evidence_accuracy"
    ] == 1.0
    assert request.topology_semantics.causal_claim_allowed is False
    assert not any(
        item.relationship_type in {"CAUSES", "ROOT_CAUSE_OF"}
        for item in request.relationships
    )
    assert not any(
        item.identity.object_type
        in {
            "sensor_observation",
            "compressor_sensor_observation",
            "cnc_sensor_observation",
            "prediction_timeline",
        }
        for item in request.nodes
    )
    risk_nodes = [
        item for item in request.nodes
        if item.identity.object_type == "risk_event"
    ]
    work_nodes = [
        item for item in request.nodes
        if item.identity.object_type == "work_order"
    ]
    assert all(
        item.properties["recommendation_execution_state"] == "not_executed"
        for item in risk_nodes
    )
    assert all(
        item.properties["origin"] == "canonical_maintenance_event"
        for item in work_nodes
    )

    first = handler.deliver(message)
    second = handler.deliver(message)
    assert first.status == second.status == "completed"
    assert second.idempotent_replay is True
    assert seen[0]["idempotency_key"] == seen[1]["idempotency_key"]
    assert seen[0]["nodes"] == seen[1]["nodes"]
    assert seen[0]["relationships"] == seen[1]["relationships"]

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        graph = connection.execute(
            """
            SELECT status,record_count,attempt_count,last_error,
                   provider_run_id,provider_metadata_json
            FROM store_projections
            WHERE dataset_version_id=%s AND store_kind='graph'
            """,
            (ingestion.dataset_version_id,),
        ).fetchone()
        relational = connection.execute(
            """
            SELECT status FROM store_projections
            WHERE dataset_version_id=%s AND store_kind='relational'
            """,
            (ingestion.dataset_version_id,),
        ).fetchone()
        objects = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count FROM ontology_objects
                WHERE dataset_version_id=%s
                """,
                (ingestion.dataset_version_id,),
            ).fetchone()["count"]
        )
        links = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count FROM ontology_links
                WHERE dataset_version_id=%s
                """,
                (ingestion.dataset_version_id,),
            ).fetchone()["count"]
        )
    assert graph["status"] == "ready"
    assert int(graph["record_count"]) == 24
    assert int(graph["attempt_count"]) == 1
    assert graph["last_error"] is None
    assert graph["provider_run_id"] == "p3-run-001"
    assert graph["provider_metadata_json"]["nodes"] == 11
    assert graph["provider_metadata_json"]["relationships"] == 13
    assert relational["status"] == "ready"
    assert objects == 11
    assert links == 13


def test_project3_unavailable_degrades_only_graph_projection(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    import psycopg
    from psycopg.rows import dict_row

    root = create_small_v3_package(tmp_path)
    _, ingestion, materialization = materialize(postgresql_database, root)
    message = outbox_message(
        postgresql_database,
        ingestion.dataset_version_id,
    )

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    handler = PredictiveMaintenanceProject3ProjectionHandler(
        postgresql_database,
        Project3Client(
            base_url="http://project3.test",
            max_retries=0,
            transport=httpx.MockTransport(offline),
        ),
    )
    with pytest.raises(Project3ProjectionDeliveryError) as raised:
        handler.deliver(message)
    assert raised.value.retryable is True

    with psycopg.connect(postgresql_database, row_factory=dict_row) as connection:
        graph = connection.execute(
            """
            SELECT status,last_error,provider_metadata_json
            FROM store_projections
            WHERE dataset_version_id=%s AND store_kind='graph'
            """,
            (ingestion.dataset_version_id,),
        ).fetchone()
        relational = connection.execute(
            """
            SELECT status,record_count FROM store_projections
            WHERE dataset_version_id=%s AND store_kind='relational'
            """,
            (ingestion.dataset_version_id,),
        ).fetchone()
        object_count = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count FROM ontology_objects
                WHERE dataset_version_id=%s
                """,
                (ingestion.dataset_version_id,),
            ).fetchone()["count"]
        )
    assert graph["status"] == "failed"
    assert "unavailable" in graph["last_error"].lower() or "offline" in graph[
        "last_error"
    ].lower()
    assert graph["provider_metadata_json"]["retryable"] is True
    assert relational["status"] == "ready"
    assert int(relational["record_count"]) > 0
    assert object_count == materialization.object_count


def test_outbox_payload_scope_cannot_be_reused_for_another_project(
    tmp_path: Path,
    postgresql_database: str,
) -> None:
    root = create_small_v3_package(tmp_path)
    _, ingestion, _ = materialize(postgresql_database, root)
    message = outbox_message(
        postgresql_database,
        ingestion.dataset_version_id,
    )
    wrong_project = OutboxMessage(
        id=message.id,
        organization_id=message.organization_id,
        project_id="project-other",
        workspace_id="workspace-other",
        aggregate_type=message.aggregate_type,
        aggregate_id=message.aggregate_id,
        event_type=message.event_type,
        payload=message.payload,
        attempt_count=message.attempt_count,
    )
    handler = PredictiveMaintenanceProject3ProjectionHandler(
        postgresql_database,
        Project3Client(base_url="http://project3.test"),
    )
    with pytest.raises(ValueError, match="envelope and payload scope differ"):
        handler.build_request(wrong_project)
