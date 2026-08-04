"""Deliver materialized predictive-maintenance ontology batches to Project 3."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ...outbox import OutboxMessage
from .client import (
    Project3Client,
    Project3ContractError,
    Project3Error,
    Project3Unavailable,
)
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
    "equipment_supplies_air_to_equipment": "SUPPLIES_AIR_TO",
    "equipment_has_risk_event": "HAS_RISK_EVENT",
    "equipment_has_prediction_result": "HAS_PREDICTION_RESULT",
    "risk_event_supported_by_prediction_result": (
        "SUPPORTED_BY_PREDICTION_RESULT"
    ),
    "equipment_has_work_order": "HAS_WORK_ORDER",
    "work_order_has_maintenance_action": "HAS_MAINTENANCE_ACTION",
    "equipment_completed_production_cycle": "COMPLETED_PRODUCTION_CYCLE",
}
ALLOWED_OBJECT_TYPES = {
    "site",
    "production_cell",
    "equipment",
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
    except ImportError as exc:
        raise RuntimeError(
            "Project 3 graph projection requires api[postgres]"
        ) from exc
    return psycopg


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("ontology payload_json must be an object")
    return value


def _source_sha256(reference: str, fallback: str) -> str:
    match = SHA_REFERENCE.search(reference)
    return match.group(1) if match else fallback


def _source_identity(
    *,
    object_id: str,
    project_id: str,
    dataset_id: str,
    dataset_version_id: str,
    object_type: str,
) -> str:
    prefix = (
        f"{project_id}:{dataset_id}:{dataset_version_id}:"
        f"{object_type}:"
    )
    if not object_id.startswith(prefix):
        raise ValueError(
            "ontology object identity does not match Dataset Version scope"
        )
    source_identity = object_id.removeprefix(prefix)
    if not source_identity:
        raise ValueError("ontology object source identity is blank")
    return source_identity


class PredictiveMaintenanceProject3ProjectionHandler:
    """Translate one Phase 3 outbox event and update graph projection state."""

    event_type = "ontology.materialization.completed"
    handler_code = "project3-v3.1-graph-projection"

    def __init__(
        self,
        database_url: str,
        client: Project3Client,
    ) -> None:
        normalized = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        if not normalized.startswith("postgresql://"):
            raise ValueError(
                "Project 3 graph projection requires a PostgreSQL URL"
            )
        self.database_url = normalized
        self.client = client

    @staticmethod
    def _set_scope(
        connection: Any,
        organization_id: str,
        project_id: str,
    ) -> None:
        connection.execute(
            "SELECT set_config('app.organization_id',%s,true)",
            (organization_id,),
        )
        connection.execute(
            "SELECT set_config('app.project_id',%s,true)",
            (project_id,),
        )

    @staticmethod
    def _validate_message(message: OutboxMessage) -> dict[str, Any]:
        if message.event_type != (
            PredictiveMaintenanceProject3ProjectionHandler.event_type
        ):
            raise ValueError(
                f"unsupported graph projection event: {message.event_type}"
            )
        payload = dict(message.payload)
        required = {
            "organization_id",
            "project_id",
            "workspace_id",
            "dataset_id",
            "dataset_version_id",
            "source_version",
            "bundle_checksum_sha256",
            "materialization_checksum_sha256",
            "mapping_id",
            "mapping_version",
            "role_checksums",
            "object_counts",
            "link_counts",
            "result_contract",
            "release_gates",
            "governance_artifacts",
            "topology_semantics",
            "excluded_sources",
            "graph_projection_status",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(
                f"graph projection outbox payload is incomplete: {missing}"
            )
        expected_scope = (
            message.organization_id,
            message.project_id,
            message.workspace_id,
            message.aggregate_id,
        )
        actual_scope = (
            str(payload["organization_id"]),
            str(payload["project_id"]),
            str(payload["workspace_id"]),
            str(payload["dataset_version_id"]),
        )
        if actual_scope != expected_scope:
            raise ValueError(
                "graph projection outbox envelope and payload scope differ"
            )
        if payload["graph_projection_status"] != "pending":
            raise ValueError(
                "materialization outbox graph status must be pending"
            )
        return payload

    def build_request(
        self,
        message: OutboxMessage,
    ) -> Project3GraphProjectionRequest:
        payload = self._validate_message(message)
        psycopg = _require_psycopg()
        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
        ) as connection:
            with connection.transaction():
                self._set_scope(
                    connection,
                    message.organization_id,
                    message.project_id,
                )
                version = connection.execute(
                    """
                    SELECT id,dataset_id,source_version,checksum_sha256,status
                    FROM dataset_versions
                    WHERE id=%s AND dataset_id=%s AND organization_id=%s
                      AND project_id=%s AND workspace_id=%s
                    """,
                    (
                        payload["dataset_version_id"],
                        payload["dataset_id"],
                        message.organization_id,
                        message.project_id,
                        message.workspace_id,
                    ),
                ).fetchone()
                if version is None:
                    raise ValueError(
                        "Dataset Version is outside graph projection scope"
                    )
                if str(version["source_version"]) != payload["source_version"]:
                    raise ValueError(
                        "graph projection source version differs from Dataset Version"
                    )
                if str(version["checksum_sha256"]) != (
                    payload["bundle_checksum_sha256"]
                ):
                    raise ValueError(
                        "graph projection checksum differs from Dataset Version"
                    )
                projection = connection.execute(
                    """
                    SELECT * FROM store_projections
                    WHERE dataset_version_id=%s AND store_kind='graph'
                    """,
                    (payload["dataset_version_id"],),
                ).fetchone()
                if projection is None:
                    raise ValueError(
                        "graph Store Projection is missing for Dataset Version"
                    )
                object_rows = connection.execute(
                    """
                    SELECT object_id,object_type,payload_json,source_sha256
                    FROM ontology_objects
                    WHERE dataset_version_id=%s
                    ORDER BY object_type,object_id
                    """,
                    (payload["dataset_version_id"],),
                ).fetchall()
                link_rows = connection.execute(
                    """
                    SELECT link_id,link_type,source_object_id,target_object_id,
                           payload_json,source_sha256
                    FROM ontology_links
                    WHERE dataset_version_id=%s
                    ORDER BY link_type,link_id
                    """,
                    (payload["dataset_version_id"],),
                ).fetchall()

        identities: dict[str, Project3ProjectionIdentity] = {}
        nodes: list[Project3ProjectionNode] = []
        for row in object_rows:
            object_type = str(row["object_type"])
            if object_type not in ALLOWED_OBJECT_TYPES:
                raise ValueError(
                    f"unsupported materialized object type: {object_type}"
                )
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
            if not isinstance(source_refs, list):
                raise ValueError(
                    "materialized ontology source_refs must be an array"
                )
            source_reference = (
                str(source_refs[0])
                if source_refs
                else (
                    f"dataset:{payload['dataset_id']}:"
                    f"version:{payload['dataset_version_id']}:"
                    f"role:ontology_object:"
                    f"sha256:{payload['bundle_checksum_sha256']}:"
                    f"object:{object_type}:{identity.source_identity}"
                )
            )
            properties = record.get("properties") or {}
            if not isinstance(properties, dict):
                raise ValueError(
                    "materialized ontology object properties must be an object"
                )
            nodes.append(
                Project3ProjectionNode(
                    identity=identity,
                    properties={
                        **properties,
                        "ontology_object_id": object_id,
                        "workspace_id": message.workspace_id,
                        "source_refs": source_refs,
                    },
                    source_reference=source_reference,
                    source_sha256=_source_sha256(
                        source_reference,
                        str(row["source_sha256"]),
                    ),
                )
            )
            identities[object_id] = identity

        relationships: list[Project3ProjectionRelationship] = []
        for row in link_rows:
            link_type = str(row["link_type"])
            relationship_type = RELATIONSHIP_TYPES.get(link_type)
            if relationship_type is None:
                raise ValueError(
                    f"unsupported materialized link type: {link_type}"
                )
            source_object_id = str(row["source_object_id"])
            target_object_id = str(row["target_object_id"])
            if (
                source_object_id not in identities
                or target_object_id not in identities
            ):
                raise ValueError(
                    "materialized link references an object outside its Dataset Version"
                )
            record = _payload(row["payload_json"])
            properties = record.get("properties") or {}
            if not isinstance(properties, dict):
                raise ValueError(
                    "materialized ontology link properties must be an object"
                )
            source_reference = str(
                properties.get("source_ref")
                or (
                    f"dataset:{payload['dataset_id']}:"
                    f"version:{payload['dataset_version_id']}:"
                    f"role:ontology_link:"
                    f"sha256:{payload['bundle_checksum_sha256']}:"
                    f"object:{link_type}:{row['link_id']}"
                )
            )
            relationships.append(
                Project3ProjectionRelationship(
                    relationship_type=relationship_type,
                    from_identity=identities[source_object_id],
                    to_identity=identities[target_object_id],
                    properties={
                        **properties,
                        "ontology_link_id": str(row["link_id"]),
                        "source_link_type": link_type,
                    },
                    source_reference=source_reference,
                    source_sha256=_source_sha256(
                        source_reference,
                        str(row["source_sha256"]),
                    ),
                )
            )

        object_counts = {
            str(key): int(value)
            for key, value in dict(payload["object_counts"]).items()
        }
        link_counts = {
            RELATIONSHIP_TYPES[str(key)]: int(value)
            for key, value in dict(payload["link_counts"]).items()
        }
        if sum(object_counts.values()) != len(nodes):
            raise ValueError(
                "materialized object counts differ from graph projection nodes"
            )
        if sum(link_counts.values()) != len(relationships):
            raise ValueError(
                "materialized link counts differ from graph projection relationships"
            )

        projection_id = (
            f"projection-{uuid.uuid5(uuid.NAMESPACE_URL, message.id)}"
        )
        idempotency_key = (
            f"graph-projection:{message.project_id}:"
            f"{payload['dataset_version_id']}:"
            f"{payload['mapping_version']}:"
            f"{payload['materialization_checksum_sha256']}"
        )
        return Project3GraphProjectionRequest(
            projection_id=projection_id,
            idempotency_key=idempotency_key,
            organization_id=message.organization_id,
            project_id=message.project_id,
            workspace_id=str(message.workspace_id),
            dataset_id=str(payload["dataset_id"]),
            dataset_version_id=str(payload["dataset_version_id"]),
            source_version=str(payload["source_version"]),
            bundle_checksum_sha256=str(
                payload["bundle_checksum_sha256"]
            ),
            materialization_checksum_sha256=str(
                payload["materialization_checksum_sha256"]
            ),
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

    def _mark_indexing(
        self,
        request: Project3GraphProjectionRequest,
    ) -> None:
        psycopg = _require_psycopg()
        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
        ) as connection:
            with connection.transaction():
                self._set_scope(
                    connection,
                    request.organization_id,
                    request.project_id,
                )
                row = connection.execute(
                    """
                    UPDATE store_projections
                    SET status='indexing',attempt_count=attempt_count+1,
                        started_at=COALESCE(started_at,now()),
                        completed_at=NULL,last_error=NULL,updated_at=now(),
                        provider_metadata_json=%s
                    WHERE dataset_version_id=%s AND store_kind='graph'
                      AND status IN ('pending','failed','indexing')
                    RETURNING id
                    """,
                    (
                        Jsonb(
                            {
                                "projection_id": request.projection_id,
                                "idempotency_key": request.idempotency_key,
                                "delivery_status": "indexing",
                            }
                        ),
                        request.dataset_version_id,
                    ),
                ).fetchone()
                if row is None:
                    current = connection.execute(
                        """
                        SELECT status FROM store_projections
                        WHERE dataset_version_id=%s AND store_kind='graph'
                        """,
                        (request.dataset_version_id,),
                    ).fetchone()
                    if current is None:
                        raise ValueError(
                            "graph Store Projection disappeared before delivery"
                        )
                    if current["status"] != "ready":
                        raise ValueError(
                            "graph Store Projection cannot be claimed for delivery"
                        )

    def _mark_ready(
        self,
        request: Project3GraphProjectionRequest,
        response: Project3GraphProjectionResponse,
    ) -> None:
        expected_nodes = len(request.nodes)
        expected_relationships = len(request.relationships)
        if (
            response.counts.nodes_written != expected_nodes
            or response.counts.relationships_written
            != expected_relationships
        ):
            raise Project3ProjectionDeliveryError(
                "Project 3 graph count reconciliation failed",
                retryable=False,
            )
        psycopg = _require_psycopg()
        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
        ) as connection:
            with connection.transaction():
                self._set_scope(
                    connection,
                    request.organization_id,
                    request.project_id,
                )
                connection.execute(
                    """
                    UPDATE store_projections
                    SET status='ready',record_count=%s,completed_at=now(),
                        updated_at=now(),last_error=NULL,provider_run_id=%s,
                        provider_metadata_json=%s
                    WHERE dataset_version_id=%s AND store_kind='graph'
                    """,
                    (
                        expected_nodes + expected_relationships,
                        response.project3_run_id,
                        Jsonb(
                            {
                                "projection_id": request.projection_id,
                                "idempotency_key": request.idempotency_key,
                                "projection_checksum_sha256": (
                                    response.projection_checksum_sha256
                                ),
                                "idempotent_replay": (
                                    response.idempotent_replay
                                ),
                                "nodes": expected_nodes,
                                "relationships": expected_relationships,
                                "dataset_version_id": (
                                    request.dataset_version_id
                                ),
                                "materialization_checksum_sha256": (
                                    request.materialization_checksum_sha256
                                ),
                            }
                        ),
                        request.dataset_version_id,
                    ),
                )

    def _mark_failed(
        self,
        request: Project3GraphProjectionRequest,
        error: Exception,
    ) -> None:
        psycopg = _require_psycopg()
        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
        ) as connection:
            with connection.transaction():
                self._set_scope(
                    connection,
                    request.organization_id,
                    request.project_id,
                )
                connection.execute(
                    """
                    UPDATE store_projections
                    SET status='failed',completed_at=now(),updated_at=now(),
                        last_error=%s,provider_metadata_json=%s
                    WHERE dataset_version_id=%s AND store_kind='graph'
                    """,
                    (
                        f"{type(error).__name__}: {error}"[:4000],
                        Jsonb(
                            {
                                "projection_id": request.projection_id,
                                "idempotency_key": request.idempotency_key,
                                "delivery_status": "failed",
                                "retryable": bool(
                                    getattr(error, "retryable", True)
                                ),
                            }
                        ),
                        request.dataset_version_id,
                    ),
                )

    def deliver(
        self,
        message: OutboxMessage,
    ) -> Project3GraphProjectionResponse:
        request = self.build_request(message)
        self._mark_indexing(request)
        try:
            response = self.client.project_graph(request)
            if response.status != "completed":
                raise Project3ProjectionDeliveryError(
                    f"Project 3 projection is not complete: {response.status}",
                    retryable=response.status in {"accepted", "processing"},
                )
            self._mark_ready(request, response)
            return response
        except Project3Unavailable as error:
            wrapped = Project3ProjectionDeliveryError(
                str(error), retryable=True
            )
            self._mark_failed(request, wrapped)
            raise wrapped from error
        except Project3ContractError as error:
            wrapped = Project3ProjectionDeliveryError(
                str(error), retryable=False
            )
            self._mark_failed(request, wrapped)
            raise wrapped from error
        except Project3ProjectionDeliveryError as error:
            self._mark_failed(request, error)
            raise
        except Project3Error as error:
            wrapped = Project3ProjectionDeliveryError(
                str(error), retryable=error.retryable
            )
            self._mark_failed(request, wrapped)
            raise wrapped from error
        except Exception as error:
            wrapped = Project3ProjectionDeliveryError(
                f"unexpected Project 3 projection failure: {error}",
                retryable=True,
            )
            self._mark_failed(request, wrapped)
            raise wrapped from error

    def __call__(self, message: OutboxMessage) -> None:
        self.deliver(message)


__all__ = [
    "PredictiveMaintenanceProject3ProjectionHandler",
    "Project3ProjectionDeliveryError",
]
