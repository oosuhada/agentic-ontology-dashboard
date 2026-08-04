"""Version-scoped PostgreSQL ontology materialization for predictive maintenance.

Result Artifact is the product-facing risk contract. Canonical maintenance rows
are the only source of WorkOrder and MaintenanceAction objects. Raw sensor and
prediction-timeline rows remain typed PostgreSQL facts and are referenced through
registered time-window evidence rather than copied into ontology_objects.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...ontology import LinkRecord, ObjectRecord


DEFAULT_MAPPING_VERSION = "predictive-maintenance-v3.1"
SOURCE_SYSTEM = "predictive-maintenance-postgresql-materialization"

DEFAULT_MAPPING: dict[str, Any] = {
    "contract_version": "1.0",
    "mapping_version": DEFAULT_MAPPING_VERSION,
    "object_types": [
        "site",
        "production_cell",
        "equipment",
        "risk_event",
        "prediction_result",
        "work_order",
        "maintenance_action",
        "production_cycle",
    ],
    "link_types": [
        "site_contains_cell",
        "cell_contains_equipment",
        "equipment_supplies_air_to_equipment",
        "equipment_has_risk_event",
        "equipment_has_prediction_result",
        "risk_event_supported_by_prediction_result",
        "equipment_has_work_order",
        "work_order_has_maintenance_action",
        "equipment_completed_production_cycle",
    ],
    "result_artifact_precedence": True,
    "recommended_action_semantics": "policy_recommendation_not_execution",
    "prediction_task": "binary_failure_within_horizon",
    "binary_prediction_types": ["failure_risk", "no_significant_risk"],
    "topology_relation_semantics": {"SUPPLIES_AIR_TO": "topology_only_not_causal_truth"},
    "query_time_derived_measures": {
        "power_w": "torque_nm * rotational_speed_rpm * 2*pi/60",
        "temperature_gap_k": "process_temperature_k - air_temperature_k",
        "overstrain_load": "tool_wear_min * torque_nm",
    },
    "excluded_runtime_sources": [
        "canonical/evaluation_truth",
        "experiments/connected_air_supply/hidden_truth",
    ],
    "non_materialized_fact_roles": [
        "compressor_sensor_observation",
        "cnc_sensor_observation",
        "prediction_timeline",
    ],
}


class PredictiveMaintenanceMaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    source_version: str
    mapping_id: str
    mapping_version: str
    status: Literal["completed"] = "completed"
    object_counts: dict[str, int]
    link_counts: dict[str, int]
    object_count: int = Field(ge=0)
    link_count: int = Field(ge=0)
    materialization_checksum_sha256: str
    outbox_event_id: str
    completed_at: datetime


def _require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise RuntimeError("predictive maintenance materialization requires api[postgres]") from exc
    return psycopg, dict_row, Jsonb


def _scoped_object_id(
    project_id: str,
    dataset_id: str,
    dataset_version_id: str,
    object_type: str,
    source_identity: str,
) -> str:
    return f"{project_id}:{dataset_id}:{dataset_version_id}:{object_type}:{source_identity}"


def _scoped_link_id(
    project_id: str,
    dataset_id: str,
    dataset_version_id: str,
    link_type: str,
    source_identity: str,
) -> str:
    return f"{project_id}:{dataset_id}:{dataset_version_id}:{link_type}:{source_identity}"


def _source_ref(
    dataset_id: str,
    dataset_version_id: str,
    role: str,
    checksum: str,
    object_type: str,
    source_identity: str,
    *,
    suffix: str = "",
) -> str:
    reference = (
        f"dataset:{dataset_id}:version:{dataset_version_id}:role:{role}:sha256:{checksum}:"
        f"object:{object_type}:{source_identity}"
    )
    return reference + suffix


class PredictiveMaintenanceOntologyMaterializer:
    def __init__(self, database_url: str) -> None:
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not normalized.startswith("postgresql://"):
            raise ValueError("ontology materialization requires a PostgreSQL URL")
        self.database_url = normalized

    @staticmethod
    def _set_scope(connection: Any, organization_id: str, project_id: str) -> None:
        connection.execute(
            "SELECT set_config('app.organization_id',%s,true)", (organization_id,)
        )
        connection.execute("SELECT set_config('app.project_id',%s,true)", (project_id,))

    @staticmethod
    def _projection_contract(
        connection: Any,
        *,
        dataset_version_id: str,
        role_checksums: dict[str, str],
        version_profile: dict[str, Any],
    ) -> dict[str, Any]:
        result_rows = connection.execute(
            """
            SELECT DISTINCT schema_version,model_version,prediction_task,source_sha256
            FROM pm_result_artifacts
            WHERE dataset_version_id=%s
            ORDER BY schema_version,model_version,prediction_task,source_sha256
            """,
            (dataset_version_id,),
        ).fetchall()
        if result_rows:
            result_contract = {
                "source_role": "result_artifact",
                "schema_versions": sorted({str(row["schema_version"]) for row in result_rows}),
                "model_versions": sorted({str(row["model_version"]) for row in result_rows}),
                "prediction_tasks": sorted({str(row["prediction_task"]) for row in result_rows}),
                "predicted_failure_type_semantics": "generic_binary_risk_not_ai4i_failure_mode",
                "source_sha256": role_checksums.get("result_artifact"),
            }
        else:
            snapshot_rows = connection.execute(
                """
                SELECT DISTINCT model_version FROM pm_prediction_snapshots
                WHERE dataset_version_id=%s ORDER BY model_version
                """,
                (dataset_version_id,),
            ).fetchall()
            result_contract = {
                "source_role": "prediction_snapshot_compatibility",
                "schema_versions": ["prediction-snapshot-compat-v1"],
                "model_versions": [str(row["model_version"]) for row in snapshot_rows],
                "prediction_tasks": ["binary_failure_within_horizon"],
                "predicted_failure_type_semantics": "generic_binary_risk_not_ai4i_failure_mode",
                "source_sha256": role_checksums.get("prediction_snapshot"),
            }

        raw_governance_artifacts = version_profile.get("governance_artifacts", [])
        if not isinstance(raw_governance_artifacts, list):
            raw_governance_artifacts = []
        governance_artifacts = [
            {
                key: item.get(key)
                for key in ("role", "checksum_sha256", "media_type")
                if item.get(key) is not None
            }
            for item in raw_governance_artifacts
            if isinstance(item, dict)
        ]
        release_gates = version_profile.get("release_gates", {})
        if not isinstance(release_gates, dict):
            release_gates = {}
        return {
            "result_contract": result_contract,
            "release_gates": release_gates,
            "governance_artifacts": governance_artifacts,
            "topology_semantics": {
                "SUPPLIES_AIR_TO": "topology_only_not_causal_truth",
                "causal_claim_allowed": False,
            },
            "excluded_sources": [
                "compressor_sensor_observation",
                "cnc_sensor_observation",
                "prediction_timeline",
                "canonical/evaluation_truth",
                "experiments/connected_air_supply/hidden_truth",
            ],
        }

    def ensure_default_mapping(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        dataset_version_id: str,
        approve: bool = False,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        psycopg, dict_row, Jsonb = _require_psycopg()
        mapping_id = f"pm-map-{uuid.uuid5(uuid.NAMESPACE_URL, f'{dataset_version_id}:{DEFAULT_MAPPING_VERSION}')}"
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._set_scope(connection, organization_id, project_id)
                version = connection.execute(
                    """
                    SELECT id FROM dataset_versions
                    WHERE id=%s AND dataset_id=%s AND organization_id=%s AND project_id=%s
                      AND workspace_id=%s
                    """,
                    (
                        dataset_version_id,
                        dataset_id,
                        organization_id,
                        project_id,
                        workspace_id,
                    ),
                ).fetchone()
                if version is None:
                    raise ValueError("Dataset Version is outside the requested materialization scope")
                connection.execute(
                    """
                    INSERT INTO ontology_materialization_mappings(
                        id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                        mapping_version,status,mapping_json,created_at,updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,'draft',%s,now(),now())
                    ON CONFLICT(dataset_version_id,mapping_version) DO NOTHING
                    """,
                    (
                        mapping_id,
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset_id,
                        dataset_version_id,
                        DEFAULT_MAPPING_VERSION,
                        Jsonb(DEFAULT_MAPPING),
                    ),
                )
                if approve:
                    connection.execute(
                        """
                        UPDATE ontology_materialization_mappings
                        SET status='approved',approved_by=%s,approved_at=now(),updated_at=now()
                        WHERE id=%s AND organization_id=%s AND project_id=%s
                        """,
                        (approved_by or "system-phase3", mapping_id, organization_id, project_id),
                    )
                row = connection.execute(
                    "SELECT * FROM ontology_materialization_mappings WHERE id=%s",
                    (mapping_id,),
                ).fetchone()
        return dict(row)

    def materialize(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        dataset_version_id: str,
        mapping_version: str = DEFAULT_MAPPING_VERSION,
        fail_after_object_type: str | None = None,
    ) -> PredictiveMaintenanceMaterializationResult:
        psycopg, dict_row, Jsonb = _require_psycopg()
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            with connection.transaction():
                self._set_scope(connection, organization_id, project_id)
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"ontology:{project_id}:{dataset_version_id}",),
                )
                version = connection.execute(
                    """
                    SELECT v.*,d.display_name AS dataset_name
                    FROM dataset_versions v JOIN datasets d ON d.id=v.dataset_id
                    WHERE v.id=%s AND v.dataset_id=%s AND v.organization_id=%s
                      AND v.project_id=%s AND v.workspace_id=%s
                    """,
                    (
                        dataset_version_id,
                        dataset_id,
                        organization_id,
                        project_id,
                        workspace_id,
                    ),
                ).fetchone()
                if version is None:
                    raise ValueError("Dataset Version is outside the requested materialization scope")
                relational = connection.execute(
                    """
                    SELECT status FROM store_projections
                    WHERE dataset_version_id=%s AND store_kind='relational'
                    """,
                    (dataset_version_id,),
                ).fetchone()
                if relational is None or relational["status"] != "ready":
                    raise ValueError("relational projection must be ready before ontology materialization")
                mapping = connection.execute(
                    """
                    SELECT * FROM ontology_materialization_mappings
                    WHERE dataset_version_id=%s AND mapping_version=%s AND status='approved'
                    """,
                    (dataset_version_id, mapping_version),
                ).fetchone()
                if mapping is None:
                    raise ValueError("an approved predictive-maintenance mapping is required")

                role_checksums = {
                    str(row["role"]): str(row["checksum_sha256"])
                    for row in connection.execute(
                        """
                        SELECT role,checksum_sha256 FROM dataset_files
                        WHERE dataset_version_id=%s
                        """,
                        (dataset_version_id,),
                    ).fetchall()
                }
                version_profile = version["profile_json"]
                if not isinstance(version_profile, dict):
                    version_profile = {}
                projection_contract = self._projection_contract(
                    connection,
                    dataset_version_id=dataset_version_id,
                    role_checksums=role_checksums,
                    version_profile=version_profile,
                )
                objects, links = self._build_snapshot(
                    connection,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    dataset_version_id=dataset_version_id,
                    source_version=str(version["source_version"]),
                    role_checksums=role_checksums,
                )
                if fail_after_object_type:
                    if any(item.object_type == fail_after_object_type for item in objects):
                        raise RuntimeError(
                            f"injected ontology materialization failure after {fail_after_object_type}"
                        )

                connection.execute(
                    "DELETE FROM ontology_links WHERE dataset_version_id=%s",
                    (dataset_version_id,),
                )
                connection.execute(
                    "DELETE FROM ontology_objects WHERE dataset_version_id=%s",
                    (dataset_version_id,),
                )
                for item in objects:
                    connection.execute(
                        """
                        INSERT INTO ontology_objects(
                            organization_id,project_id,workspace_id,object_id,object_type,
                            payload_json,source_system,source_revision,updated_at,
                            dataset_id,dataset_version_id,source_sha256
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s)
                        """,
                        (
                            organization_id,
                            project_id,
                            workspace_id,
                            item.id,
                            item.object_type,
                            Jsonb(item.model_dump(mode="json")),
                            SOURCE_SYSTEM,
                            f"{str(version['source_version'])}:{str(version['checksum_sha256'])}",
                            dataset_id,
                            dataset_version_id,
                            str(version["checksum_sha256"]),
                        ),
                    )
                for item in links:
                    connection.execute(
                        """
                        INSERT INTO ontology_links(
                            organization_id,project_id,workspace_id,link_id,link_type,
                            source_object_id,target_object_id,payload_json,source_system,
                            source_revision,updated_at,dataset_id,dataset_version_id,source_sha256
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s)
                        """,
                        (
                            organization_id,
                            project_id,
                            workspace_id,
                            item.id,
                            item.link_type,
                            item.source_object_id,
                            item.target_object_id,
                            Jsonb(item.model_dump(mode="json")),
                            SOURCE_SYSTEM,
                            f"{str(version['source_version'])}:{str(version['checksum_sha256'])}",
                            dataset_id,
                            dataset_version_id,
                            str(version["checksum_sha256"]),
                        ),
                    )

                checksum = self._snapshot_checksum(objects, links)
                object_counts = self._count_objects(objects)
                link_counts = self._count_links(links)
                connection.execute(
                    """
                    INSERT INTO ontology_ingestion_runs(
                        id,organization_id,project_id,workspace_id,source_system,source_revision,
                        object_count,link_count,completed_at,dataset_id,dataset_version_id,
                        mapping_version,status,materialization_checksum_sha256
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,'completed',%s)
                    """,
                    (
                        uuid.uuid4(),
                        organization_id,
                        project_id,
                        workspace_id,
                        SOURCE_SYSTEM,
                        str(version["source_version"]),
                        len(objects),
                        len(links),
                        dataset_id,
                        dataset_version_id,
                        mapping_version,
                        checksum,
                    ),
                )
                outbox_event_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"ontology-materialization:{dataset_version_id}:{mapping_version}:{checksum}",
                    )
                )
                connection.execute(
                    """
                    INSERT INTO transactional_outbox(
                        id,organization_id,project_id,workspace_id,aggregate_type,aggregate_id,
                        event_type,payload_json,status,created_at,available_at
                    ) VALUES (%s,%s,%s,%s,'dataset_version',%s,
                              'ontology.materialization.completed',%s,'pending',now(),now())
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        outbox_event_id,
                        organization_id,
                        project_id,
                        workspace_id,
                        dataset_version_id,
                        Jsonb(
                            {
                                "organization_id": organization_id,
                                "project_id": project_id,
                                "workspace_id": workspace_id,
                                "dataset_id": dataset_id,
                                "dataset_version_id": dataset_version_id,
                                "source_version": str(version["source_version"]),
                                "bundle_checksum_sha256": str(version["checksum_sha256"]),
                                "mapping_id": str(mapping["id"]),
                                "mapping_version": mapping_version,
                                "materialization_checksum_sha256": checksum,
                                "object_counts": object_counts,
                                "link_counts": link_counts,
                                "role_checksums": role_checksums,
                                **projection_contract,
                                "graph_projection_status": "pending",
                            }
                        ),
                    ),
                )
                return PredictiveMaintenanceMaterializationResult(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    dataset_id=dataset_id,
                    dataset_version_id=dataset_version_id,
                    source_version=str(version["source_version"]),
                    mapping_id=str(mapping["id"]),
                    mapping_version=mapping_version,
                    object_counts=object_counts,
                    link_counts=link_counts,
                    object_count=len(objects),
                    link_count=len(links),
                    materialization_checksum_sha256=checksum,
                    outbox_event_id=outbox_event_id,
                    completed_at=datetime.now(timezone.utc),
                )

    def _build_snapshot(
        self,
        connection: Any,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        dataset_version_id: str,
        source_version: str,
        role_checksums: dict[str, str],
    ) -> tuple[list[ObjectRecord], list[LinkRecord]]:
        del organization_id, source_version
        objects: list[ObjectRecord] = []
        links: list[LinkRecord] = []
        object_ids: dict[tuple[str, str], str] = {}

        def add_object(
            object_type: str,
            source_identity: str,
            properties: dict[str, Any],
            source_refs: list[str],
        ) -> str:
            object_id = _scoped_object_id(
                project_id, dataset_id, dataset_version_id, object_type, source_identity
            )
            properties = {
                **properties,
                "dataset_id": dataset_id,
                "dataset_version_id": dataset_version_id,
            }
            objects.append(
                ObjectRecord(
                    id=object_id,
                    object_type=object_type,
                    workspace_id=workspace_id,
                    properties=properties,
                    source_refs=source_refs,
                )
            )
            object_ids[(object_type, source_identity)] = object_id
            return object_id

        def add_link(
            link_type: str,
            source_identity: str,
            source_object_id: str,
            target_object_id: str,
            properties: dict[str, Any] | None = None,
        ) -> None:
            links.append(
                LinkRecord(
                    id=_scoped_link_id(
                        project_id, dataset_id, dataset_version_id, link_type, source_identity
                    ),
                    link_type=link_type,
                    source_object_id=source_object_id,
                    target_object_id=target_object_id,
                    workspace_id=workspace_id,
                    properties={
                        "dataset_id": dataset_id,
                        "dataset_version_id": dataset_version_id,
                        **(properties or {}),
                    },
                )
            )

        assets = connection.execute(
            """
            SELECT asset_id,asset_type,site_id,cell_id,source_sha256
            FROM pm_assets WHERE dataset_version_id=%s ORDER BY asset_id
            """,
            (dataset_version_id,),
        ).fetchall()
        site_ids = sorted({str(row["site_id"]) for row in assets})
        cell_pairs = sorted({(str(row["site_id"]), str(row["cell_id"])) for row in assets})
        for site_id in site_ids:
            add_object(
                "site",
                site_id,
                {"display_name": site_id, "site_id": site_id},
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "asset_master",
                        role_checksums["asset_master"],
                        "site",
                        site_id,
                    )
                ],
            )
        for site_id, cell_id in cell_pairs:
            cell_oid = add_object(
                "production_cell",
                cell_id,
                {"display_name": cell_id, "cell_id": cell_id, "site_id": site_id},
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "asset_master",
                        role_checksums["asset_master"],
                        "production_cell",
                        cell_id,
                    )
                ],
            )
            add_link(
                "site_contains_cell",
                f"{site_id}->{cell_id}",
                object_ids[("site", site_id)],
                cell_oid,
            )
        for row in assets:
            asset_id = str(row["asset_id"])
            equipment_oid = add_object(
                "equipment",
                asset_id,
                {
                    "display_name": asset_id,
                    "asset_id": asset_id,
                    "asset_type": str(row["asset_type"]),
                    "site_id": str(row["site_id"]),
                    "cell_id": str(row["cell_id"]),
                    "line": str(row["cell_id"]),
                    "criticality": "standard",
                },
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "asset_master",
                        role_checksums["asset_master"],
                        "equipment",
                        asset_id,
                    )
                ],
            )
            add_link(
                "cell_contains_equipment",
                f"{row['cell_id']}->{asset_id}",
                object_ids[("production_cell", str(row["cell_id"]))],
                equipment_oid,
            )

        for row in connection.execute(
            """
            SELECT from_asset_id,relation_type,to_asset_id
            FROM pm_asset_relations WHERE dataset_version_id=%s
            ORDER BY from_asset_id,to_asset_id
            """,
            (dataset_version_id,),
        ).fetchall():
            source_id = str(row["from_asset_id"])
            target_id = str(row["to_asset_id"])
            add_link(
                "equipment_supplies_air_to_equipment",
                f"{source_id}->{target_id}",
                object_ids[("equipment", source_id)],
                object_ids[("equipment", target_id)],
                {
                    "source_relation_type": str(row["relation_type"]),
                    "semantics": "topology_only",
                    "causal_claim_allowed": False,
                    "source_ref": _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "asset_relation",
                        role_checksums["asset_relation"],
                        "relation",
                        f"{source_id}->{target_id}",
                    ),
                },
            )

        artifacts = self._latest_result_rows(connection, dataset_version_id)
        summaries = self._sensor_summaries(connection, dataset_version_id, artifacts)
        for row in artifacts:
            asset_id = str(row["asset_id"])
            artifact_id = str(row["artifact_id"])
            prediction_id = str(row["prediction_id"])
            model_version = str(row["model_version"])
            observed_at = row["observed_at"]
            window_start = observed_at - timedelta(hours=6)
            sensor_role = (
                "compressor_sensor_observation"
                if row["asset_type"] == "compressor"
                else "cnc_sensor_observation"
            )
            result_role = str(row["artifact_source_role"])
            result_ref = _source_ref(
                dataset_id,
                dataset_version_id,
                result_role,
                role_checksums[result_role],
                "risk_event",
                artifact_id,
                suffix=(
                    f":schema:{row['schema_version']}:model:{model_version}"
                ),
            )
            sensor_ref = _source_ref(
                dataset_id,
                dataset_version_id,
                sensor_role,
                role_checksums[sensor_role],
                "equipment",
                asset_id,
                suffix=f":window:{window_start.isoformat()}/{observed_at.isoformat()}",
            )
            prediction_oid = add_object(
                "prediction_result",
                prediction_id,
                {
                    "prediction_id": prediction_id,
                    "asset_id": asset_id,
                    "observed_at": observed_at.isoformat(),
                    "prediction_horizon_hours": int(row["prediction_horizon_hours"]),
                    "prediction_task": str(row["prediction_task"]),
                    "failure_probability": float(row["failure_probability"]),
                    "predicted_failure_type": str(row["predicted_failure_type"]),
                    "confidence": float(row["confidence"]),
                    "model_version": model_version,
                    "feature_scope": row["feature_scope"],
                    "failure_mode_semantics": "binary_risk_class_not_ai4i_multiclass",
                    "result_contract_source": result_role,
                },
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "prediction_snapshot",
                        role_checksums["prediction_snapshot"],
                        "prediction_result",
                        prediction_id,
                    ),
                    result_ref,
                ],
            )
            risk_oid = add_object(
                "risk_event",
                artifact_id,
                {
                    "artifact_id": artifact_id,
                    "asset_id": asset_id,
                    "status": str(row["status_grade"]),
                    "status_grade": str(row["status_grade"]),
                    "failure_probability": float(row["failure_probability"]),
                    "confidence": float(row["confidence"]),
                    "prediction_task": str(row["prediction_task"]),
                    "predicted_failure_type": str(row["predicted_failure_type"]),
                    "recommended_decision": row["recommended_action"]["action"],
                    "recommended_action": row["recommended_action"],
                    "recommendation_execution_state": "not_executed",
                    "top_factors": row["top_factors"],
                    "observed_at": observed_at.isoformat(),
                    "model_version": model_version,
                    "selected_sensor_summary": summaries.get(asset_id, {}),
                    "failure_mode_semantics": "binary_risk_class_not_ai4i_multiclass",
                    "result_contract_source": result_role,
                },
                [result_ref, sensor_ref],
            )
            equipment_oid = object_ids[("equipment", asset_id)]
            add_link(
                "equipment_has_prediction_result",
                f"{asset_id}->{prediction_id}",
                equipment_oid,
                prediction_oid,
            )
            add_link(
                "equipment_has_risk_event",
                f"{asset_id}->{artifact_id}",
                equipment_oid,
                risk_oid,
            )
            add_link(
                "risk_event_supported_by_prediction_result",
                f"{artifact_id}->{prediction_id}",
                risk_oid,
                prediction_oid,
                {"provenance": row["provenance"]},
            )

        for row in connection.execute(
            """
            SELECT maintenance_id,asset_id,maintenance_type,started_at,completed_at,
                   tool_replaced
            FROM pm_maintenance_events WHERE dataset_version_id=%s
            ORDER BY maintenance_id
            """,
            (dataset_version_id,),
        ).fetchall():
            maintenance_id = str(row["maintenance_id"])
            asset_id = str(row["asset_id"])
            work_oid = add_object(
                "work_order",
                maintenance_id,
                {
                    "status": "completed",
                    "work_type": str(row["maintenance_type"]),
                    "maintenance_id": maintenance_id,
                    "asset_id": asset_id,
                    "started_at": row["started_at"].isoformat(),
                    "completed_at": row["completed_at"].isoformat(),
                    "tool_replaced": bool(row["tool_replaced"]),
                    "actual_maintenance_event": True,
                    "origin": "canonical_maintenance_event",
                },
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "maintenance_event",
                        role_checksums["maintenance_event"],
                        "work_order",
                        maintenance_id,
                    )
                ],
            )
            action_oid = add_object(
                "maintenance_action",
                maintenance_id,
                {
                    "action": str(row["maintenance_type"]),
                    "actor": "canonical_maintenance_event",
                    "created_at": row["completed_at"].isoformat(),
                    "maintenance_id": maintenance_id,
                    "actual_maintenance_event": True,
                },
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "maintenance_event",
                        role_checksums["maintenance_event"],
                        "maintenance_action",
                        maintenance_id,
                    )
                ],
            )
            add_link(
                "equipment_has_work_order",
                f"{asset_id}->{maintenance_id}",
                object_ids[("equipment", asset_id)],
                work_oid,
                {"actual_maintenance_event": True},
            )
            add_link(
                "work_order_has_maintenance_action",
                f"{maintenance_id}->{maintenance_id}",
                work_oid,
                action_oid,
                {"actual_maintenance_event": True},
            )

        latest_cycles = connection.execute(
            """
            SELECT DISTINCT ON (cnc_asset_id)
                   product_id,cnc_asset_id,cycle_started_at,cycle_completed_at,
                   product_type,cutting_minutes,tool_wear_increment_min
            FROM pm_production_cycles WHERE dataset_version_id=%s
            ORDER BY cnc_asset_id,cycle_completed_at DESC,product_id DESC
            """,
            (dataset_version_id,),
        ).fetchall()
        for row in latest_cycles:
            product_id = str(row["product_id"])
            asset_id = str(row["cnc_asset_id"])
            cycle_oid = add_object(
                "production_cycle",
                product_id,
                {
                    "product_id": product_id,
                    "asset_id": asset_id,
                    "cycle_started_at": row["cycle_started_at"].isoformat(),
                    "cycle_completed_at": row["cycle_completed_at"].isoformat(),
                    "product_type": str(row["product_type"]),
                    "cutting_minutes": float(row["cutting_minutes"]),
                    "tool_wear_increment_min": float(row["tool_wear_increment_min"]),
                    "selection_policy": "latest_cycle_per_cnc",
                },
                [
                    _source_ref(
                        dataset_id,
                        dataset_version_id,
                        "cnc_production_cycle",
                        role_checksums["cnc_production_cycle"],
                        "production_cycle",
                        product_id,
                    )
                ],
            )
            add_link(
                "equipment_completed_production_cycle",
                f"{asset_id}->{product_id}",
                object_ids[("equipment", asset_id)],
                cycle_oid,
                {"selection_policy": "latest_cycle_per_cnc"},
            )

        return objects, links

    @staticmethod
    def _latest_result_rows(connection: Any, dataset_version_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT r.*,p.feature_scope,'result_artifact'::text AS artifact_source_role
            FROM pm_result_artifacts r
            JOIN pm_prediction_snapshots p
              ON p.dataset_version_id=r.dataset_version_id AND p.prediction_id=r.prediction_id
            WHERE r.dataset_version_id=%s ORDER BY r.asset_id
            """,
            (dataset_version_id,),
        ).fetchall()
        if rows:
            return [dict(row) for row in rows]

        snapshots = connection.execute(
            """
            SELECT * FROM pm_prediction_snapshots
            WHERE dataset_version_id=%s ORDER BY asset_id
            """,
            (dataset_version_id,),
        ).fetchall()
        factor_rows = connection.execute(
            """
            SELECT prediction_id,rank,feature,feature_value,signed_contribution,
                   direction,explanation_method
            FROM pm_prediction_factors
            WHERE dataset_version_id=%s ORDER BY prediction_id,rank
            """,
            (dataset_version_id,),
        ).fetchall()
        factors: dict[str, list[dict[str, Any]]] = {}
        for factor in factor_rows:
            factors.setdefault(str(factor["prediction_id"]), []).append(
                {
                    "rank": int(factor["rank"]),
                    "feature": str(factor["feature"]),
                    "feature_value": float(factor["feature_value"]),
                    "signed_contribution": float(factor["signed_contribution"]),
                    "direction": str(factor["direction"]),
                    "explanation_method": str(factor["explanation_method"]),
                }
            )
        action_policy = {
            "critical": {"action": "immediate_inspection_and_stop_review", "priority": "urgent"},
            "warning": {"action": "inspect_within_current_shift", "priority": "high"},
            "attention": {"action": "schedule_targeted_diagnostic_check", "priority": "medium"},
            "normal": {"action": "continue_monitoring", "priority": "routine"},
        }
        return [
            {
                **dict(row),
                "artifact_id": f"RESULT#{row['prediction_id']}",
                "prediction_id": str(row["prediction_id"]),
                "prediction_task": "binary_failure_within_horizon",
                "status_grade": str(row["status"]),
                "top_factors": factors.get(str(row["prediction_id"]), []),
                "recommended_action": action_policy[str(row["status"])],
                "provenance": {
                    "dataset_version_id": dataset_version_id,
                    "model_version": str(row["model_version"]),
                    "prediction_id": str(row["prediction_id"]),
                    "source_type": "prediction_snapshot_compatibility",
                    "canonical_source_mutated": False,
                },
                "schema_version": "prediction-snapshot-compat-v1",
                "artifact_source_role": "prediction_snapshot",
            }
            for row in snapshots
        ]

    @staticmethod
    def _sensor_summaries(
        connection: Any,
        dataset_version_id: str,
        artifacts: list[Any],
    ) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            asset_id = str(artifact["asset_id"])
            observed_at = artifact["observed_at"]
            if artifact["asset_type"] == "compressor":
                row = connection.execute(
                    """
                    SELECT observed_at,pressure_raw,vibration_raw,relative_vibration_z,
                           operating_state
                    FROM pm_compressor_observations
                    WHERE dataset_version_id=%s AND asset_id=%s AND observed_at<=%s
                    ORDER BY observed_at DESC LIMIT 1
                    """,
                    (dataset_version_id, asset_id, observed_at),
                ).fetchone()
                if row is not None:
                    summaries[asset_id] = {
                        "observed_at": row["observed_at"].isoformat(),
                        "pressure_raw": float(row["pressure_raw"]),
                        "vibration_raw": float(row["vibration_raw"]),
                        "relative_vibration_z": float(row["relative_vibration_z"]),
                        "operating_state": str(row["operating_state"]),
                    }
                continue
            row = connection.execute(
                """
                SELECT observed_at,air_temperature_k,process_temperature_k,
                       rotational_speed_rpm,torque_nm,tool_wear_min,product_type,
                       operating_state
                FROM pm_cnc_observations
                WHERE dataset_version_id=%s AND asset_id=%s AND observed_at<=%s
                ORDER BY observed_at DESC LIMIT 1
                """,
                (dataset_version_id, asset_id, observed_at),
            ).fetchone()
            if row is None:
                continue
            rpm = float(row["rotational_speed_rpm"])
            torque = float(row["torque_nm"])
            wear = float(row["tool_wear_min"])
            air = float(row["air_temperature_k"])
            process = float(row["process_temperature_k"])
            summaries[asset_id] = {
                "observed_at": row["observed_at"].isoformat(),
                "air_temperature_k": air,
                "process_temperature_k": process,
                "rotational_speed_rpm": rpm,
                "torque_nm": torque,
                "tool_wear_min": wear,
                "product_type": str(row["product_type"]),
                "operating_state": str(row["operating_state"]),
                "derived_measures": {
                    "power_w": torque * rpm * 2 * math.pi / 60,
                    "temperature_gap_k": process - air,
                    "overstrain_load": wear * torque,
                },
                "derived_measure_contract": "query_time_from_canonical_observation",
            }
        return summaries

    @staticmethod
    def _snapshot_checksum(objects: list[ObjectRecord], links: list[LinkRecord]) -> str:
        payload = {
            "objects": [
                item.model_dump(mode="json")
                for item in sorted(objects, key=lambda item: item.id)
            ],
            "links": [
                item.model_dump(mode="json")
                for item in sorted(links, key=lambda item: item.id)
            ],
        }
        rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(rendered.encode("utf-8")).hexdigest()

    @staticmethod
    def _count_objects(objects: list[ObjectRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in objects:
            counts[item.object_type] = counts.get(item.object_type, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _count_links(links: list[LinkRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in links:
            counts[item.link_type] = counts.get(item.link_type, 0) + 1
        return dict(sorted(counts.items()))


__all__ = [
    "DEFAULT_MAPPING",
    "DEFAULT_MAPPING_VERSION",
    "PredictiveMaintenanceMaterializationResult",
    "PredictiveMaintenanceOntologyMaterializer",
]
