"""Deliver materialized Dataset-Version ontology snapshots to Project 3."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
import uuid

from app.infra.messaging.outbox import OutboxMessage
from .client import Project3Client, Project3Unavailable
from .models import (
    Project3GraphProjectionRequest,
    Project3GraphProjectionResponse,
    Project3ProjectionIdentity,
    Project3ProjectionNode,
    Project3ProjectionRelationship,
)


RELATIONSHIP_TYPES = {
    "site_contains_cell": "SITE_CONTAINS_CELL",
    "cell_contains_equipment": "CELL_CONTAINS_EQUIPMENT",
    "equipment_has_component": "HAS_COMPONENT",
    "component_inspected_by_sop": "INSPECTED_BY",
    "equipment_supplies_air_to_equipment": "SUPPLIES_AIR_TO",
    "equipment_has_risk_event": "HAS_RISK_EVENT",
    "equipment_has_prediction_result": "HAS_PREDICTION_RESULT",
    "risk_event_supported_by_prediction_result": "SUPPORTED_BY_PREDICTION_RESULT",
    "equipment_has_work_order": "HAS_WORK_ORDER",
    "work_order_has_maintenance_action": "HAS_MAINTENANCE_ACTION",
    "equipment_completed_production_cycle": "COMPLETED_PRODUCTION_CYCLE",
    "production_cycle_produces_product": "PRODUCES_PRODUCT",
    "equipment_produces_product": "CURRENTLY_PRODUCES",
}
ALLOWED_OBJECT_TYPES = {
    "site",
    "production_cell",
    "equipment",
    "component",
    "product",
    "sop",
    "risk_event",
    "prediction_result",
    "work_order",
    "maintenance_action",
    "production_cycle",
}
SHA_REFERENCE = re.compile(r":sha256:([a-f0-9]{64})(?::|$)")


class Project3ProjectionDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def _require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("Project 3 graph projection requires the backend postgres extra") from exc
    return psycopg, dict_row, Jsonb


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("ontology payload_json must be an object")
    return value


def _source_sha256(reference: str, fallback: str) -> str:
    match = SHA_REFERENCE.search(reference)
    return match.group(1) if match else fallback


def _source_identity(*, object_id: str, project_id: str, dataset_id: str, dataset_version_id: str, object_type: str) -> str:
    prefix = f"{project_id}:{dataset_id}:{dataset_version_id}:{object_type}:"
    if not object_id.startswith(prefix):
        raise ValueError("ontology object identity does not match Dataset Version scope")
    identity = object_id.removeprefix(prefix)
    if not identity:
        raise ValueError("ontology object source identity is blank")
    return identity


class PredictiveMaintenanceProject3ProjectionHandler:
    event_type = "ontology.materialization.completed"
    handler_code = "project3-versioned-graph-projection-v1"

    def __init__(self, database_url: str, client: Project3Client) -> None:
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not normalized.startswith("postgresql://"):
            raise ValueError("Project 3 graph projection requires PostgreSQL")
        self.database_url = normalized
        self.client = client

    @staticmethod
    def _scope(connection: Any, organization_id: str, project_id: str) -> None:
        connection.execute("SELECT set_config('app.organization_id',%s,true)", (organization_id,))
        connection.execute("SELECT set_config('app.project_id',%s,true)", (project_id,))

    @staticmethod
    def _validate_message(message: OutboxMessage) -> dict[str, Any]:
        if message.event_type != PredictiveMaintenanceProject3ProjectionHandler.event_type:
            raise ValueError(f"unsupported graph projection event: {message.event_type}")
        payload = dict(message.payload)
        required = {
            "organization_id", "project_id", "workspace_id", "dataset_id",
            "dataset_version_id", "source_version", "bundle_checksum_sha256",
            "materialization_checksum_sha256", "mapping_id", "mapping_version",
            "role_checksums", "object_counts", "link_counts", "result_contract",
            "release_gates", "governance_artifacts", "topology_semantics",
            "excluded_sources", "graph_projection_status",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"graph projection outbox payload is incomplete: {missing}")
        if (
            str(payload["organization_id"]), str(payload["project_id"]),
            str(payload["workspace_id"]), str(payload["dataset_version_id"]),
        ) != (message.organization_id, message.project_id, message.workspace_id, message.aggregate_id):
            raise ValueError("graph projection outbox envelope and payload scope differ")
        return payload

    def build_request(self, message: OutboxMessage) -> Project3GraphProjectionRequest:
        payload = self._validate_message(message)
        psycopg, dict_row, _ = _require_psycopg()
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._scope(connection, message.organization_id, message.project_id)
                version = connection.execute(
                    """
                    SELECT id,dataset_id,source_version,checksum_sha256 FROM dataset_versions
                    WHERE id=%s AND dataset_id=%s AND organization_id=%s AND project_id=%s AND workspace_id=%s
                    """,
                    (payload["dataset_version_id"], payload["dataset_id"], message.organization_id, message.project_id, message.workspace_id),
                ).fetchone()
                if version is None:
                    raise ValueError("Dataset Version is outside graph projection scope")
                current_materialization = connection.execute(
                    """
                    SELECT materialization_checksum_sha256,object_count,link_count
                    FROM ontology_ingestion_runs
                    WHERE organization_id=%s AND project_id=%s AND workspace_id=%s
                      AND dataset_version_id=%s AND status='completed'
                      AND materialization_checksum_sha256 IS NOT NULL
                    ORDER BY completed_at DESC,id DESC
                    LIMIT 1
                    """,
                    (
                        message.organization_id,
                        message.project_id,
                        message.workspace_id,
                        payload["dataset_version_id"],
                    ),
                ).fetchone()
                if current_materialization is None:
                    raise Project3ProjectionDeliveryError(
                        "current ontology materialization is unavailable",
                        retryable=False,
                    )
                if str(current_materialization["materialization_checksum_sha256"]) != str(
                    payload["materialization_checksum_sha256"]
                ):
                    raise Project3ProjectionDeliveryError(
                        "stale ontology materialization event does not match the current snapshot",
                        retryable=False,
                    )
                object_rows = connection.execute(
                    "SELECT object_id,object_type,payload_json,source_sha256 FROM ontology_objects WHERE dataset_version_id=%s ORDER BY object_type,object_id",
                    (payload["dataset_version_id"],),
                ).fetchall()
                link_rows = connection.execute(
                    """
                    SELECT link_id,link_type,source_object_id,target_object_id,payload_json,source_sha256
                    FROM ontology_links WHERE dataset_version_id=%s ORDER BY link_type,link_id
                    """,
                    (payload["dataset_version_id"],),
                ).fetchall()

        identities: dict[str, Project3ProjectionIdentity] = {}
        nodes: list[Project3ProjectionNode] = []
        for row in object_rows:
            object_type = str(row["object_type"])
            if object_type not in ALLOWED_OBJECT_TYPES:
                raise ValueError(f"unsupported materialized object type: {object_type}")
            record = _payload(row["payload_json"])
            object_id = str(row["object_id"])
            identity = Project3ProjectionIdentity(
                organization_id=message.organization_id,
                project_id=message.project_id,
                dataset_id=str(payload["dataset_id"]),
                dataset_version_id=str(payload["dataset_version_id"]),
                object_type=object_type,
                source_identity=_source_identity(
                    object_id=object_id,
                    project_id=message.project_id,
                    dataset_id=str(payload["dataset_id"]),
                    dataset_version_id=str(payload["dataset_version_id"]),
                    object_type=object_type,
                ),
            )
            source_refs = record.get("source_refs") or []
            source_reference = str(source_refs[0]) if source_refs else f"ontology:{object_id}"
            properties = record.get("properties") or {}
            nodes.append(Project3ProjectionNode(
                identity=identity,
                properties={**properties, "ontology_object_id": object_id, "workspace_id": message.workspace_id, "source_refs": source_refs},
                source_reference=source_reference,
                source_sha256=_source_sha256(source_reference, str(row["source_sha256"])),
            ))
            identities[object_id] = identity

        relationships: list[Project3ProjectionRelationship] = []
        for row in link_rows:
            link_type = str(row["link_type"])
            relationship_type = RELATIONSHIP_TYPES.get(link_type)
            if relationship_type is None:
                raise ValueError(f"unsupported materialized link type: {link_type}")
            source_object_id = str(row["source_object_id"])
            target_object_id = str(row["target_object_id"])
            if source_object_id not in identities or target_object_id not in identities:
                raise ValueError("materialized link references an object outside its Dataset Version")
            record = _payload(row["payload_json"])
            properties = record.get("properties") or {}
            source_reference = str(properties.get("source_ref") or f"ontology:{row['link_id']}")
            relationships.append(Project3ProjectionRelationship(
                relationship_type=relationship_type,
                from_identity=identities[source_object_id],
                to_identity=identities[target_object_id],
                properties={**properties, "ontology_link_id": str(row["link_id"]), "source_link_type": link_type},
                source_reference=source_reference,
                source_sha256=_source_sha256(source_reference, str(row["source_sha256"])),
            ))

        object_counts = {str(key): int(value) for key, value in dict(payload["object_counts"]).items()}
        link_counts = {RELATIONSHIP_TYPES[str(key)]: int(value) for key, value in dict(payload["link_counts"]).items()}
        if sum(object_counts.values()) != len(nodes) or sum(link_counts.values()) != len(relationships):
            raise Project3ProjectionDeliveryError(
                "stale ontology materialization counts differ from the current snapshot",
                retryable=False,
            )
        if int(current_materialization["object_count"]) != len(nodes) or int(
            current_materialization["link_count"]
        ) != len(relationships):
            raise Project3ProjectionDeliveryError(
                "current ontology materialization counts differ from the current snapshot",
                retryable=False,
            )
        return Project3GraphProjectionRequest(
            projection_id=f"projection-{uuid.uuid5(uuid.NAMESPACE_URL, message.id)}",
            idempotency_key=f"graph-projection:{message.project_id}:{payload['dataset_version_id']}:{payload['mapping_version']}:{payload['materialization_checksum_sha256']}",
            organization_id=message.organization_id,
            project_id=message.project_id,
            workspace_id=str(message.workspace_id),
            dataset_id=str(payload["dataset_id"]),
            dataset_version_id=str(payload["dataset_version_id"]),
            source_version=str(payload["source_version"]),
            bundle_checksum_sha256=str(payload["bundle_checksum_sha256"]),
            materialization_checksum_sha256=str(payload["materialization_checksum_sha256"]),
            mapping_id=str(payload["mapping_id"]),
            mapping_version=str(payload["mapping_version"]),
            role_checksums=dict(payload["role_checksums"]),
            object_counts=object_counts,
            link_counts=link_counts,
            result_contract=payload["result_contract"],
            release_gates=dict(payload["release_gates"]),
            governance_artifacts=list(payload["governance_artifacts"]),
            topology_semantics=payload["topology_semantics"],
            excluded_sources=list(payload["excluded_sources"]),
            graph_projection_status="pending",
            nodes=nodes,
            relationships=relationships,
            requested_at=datetime.now(timezone.utc),
        )

    def _set_projection_state(self, request: Project3GraphProjectionRequest, *, status: str, response: Project3GraphProjectionResponse | None = None, error: Exception | None = None) -> None:
        psycopg, dict_row, Jsonb = _require_psycopg()
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._scope(connection, request.organization_id, request.project_id)
                metadata = {
                    "projection_id": request.projection_id,
                    "idempotency_key": request.idempotency_key,
                    "dataset_version_id": request.dataset_version_id,
                    "nodes": len(request.nodes),
                    "relationships": len(request.relationships),
                }
                if response is not None:
                    metadata.update({
                        "projection_checksum_sha256": response.projection_checksum_sha256,
                        "idempotent_replay": response.idempotent_replay,
                    })
                connection.execute(
                    """
                    UPDATE store_projections
                    SET status=%s,
                        record_count=%s,
                        attempt_count=attempt_count + CASE WHEN %s='indexing' THEN 1 ELSE 0 END,
                        started_at=CASE WHEN %s='indexing' THEN COALESCE(started_at,now()) ELSE started_at END,
                        completed_at=CASE WHEN %s IN ('ready','failed') THEN now() ELSE NULL END,
                        last_error=%s,provider_run_id=%s,provider_metadata_json=%s,updated_at=now()
                    WHERE dataset_version_id=%s AND store_kind='graph'
                    """,
                    (
                        status,
                        len(request.nodes) + len(request.relationships) if status == "ready" else 0,
                        status,
                        status,
                        status,
                        None if error is None else f"{type(error).__name__}: {error}"[:4000],
                        response.project3_run_id if response is not None else None,
                        Jsonb(metadata),
                        request.dataset_version_id,
                    ),
                )

    def deliver(self, message: OutboxMessage) -> Project3GraphProjectionResponse:
        request = self.build_request(message)
        self._set_projection_state(request, status="indexing")
        try:
            response = self.client.project_graph(request)
            if response.status != "completed":
                raise Project3ProjectionDeliveryError(
                    f"Project 3 projection is not complete: {response.status}",
                    retryable=response.status in {"accepted", "processing"},
                )
            if response.counts.nodes_written != len(request.nodes) or response.counts.relationships_written != len(request.relationships):
                raise Project3ProjectionDeliveryError("Project 3 graph count reconciliation failed", retryable=False)
            self._set_projection_state(request, status="ready", response=response)
            return response
        except Project3Unavailable as exc:
            wrapped = Project3ProjectionDeliveryError(str(exc), retryable=True)
            self._set_projection_state(request, status="failed", error=wrapped)
            raise wrapped from exc
        except Exception as exc:
            self._set_projection_state(request, status="failed", error=exc)
            raise


__all__ = ["PredictiveMaintenanceProject3ProjectionHandler", "Project3ProjectionDeliveryError"]
