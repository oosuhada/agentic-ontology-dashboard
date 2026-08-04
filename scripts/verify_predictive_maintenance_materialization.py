#!/usr/bin/env python3
"""Verify predictive-maintenance ontology lineage, traversal, isolation, and leakage gates."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


FORBIDDEN_TEXT = (
    "evaluation_truth",
    "hidden_truth",
    "condition_variant",
    "failure_occurred_at",
    "source_event_id",
)
FORBIDDEN_OBJECT_TYPES = (
    "sensor_observation",
    "compressor_sensor_observation",
    "cnc_sensor_observation",
    "prediction_timeline",
)


def _require_psycopg():
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("materialization verification requires api[postgres]") from exc
    return psycopg, sql, dict_row


def _dsn_for_user(database_url: str, user: str) -> str:
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or "127.0.0.1"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit(("postgresql", f"{user}@{host}", parsed.path, parsed.query, ""))


def verify(
    *,
    database_url: str,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    dataset_id: str,
    dataset_version_id: str,
) -> dict[str, object]:
    psycopg, sql, dict_row = _require_psycopg()
    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized, row_factory=dict_row) as connection:
        version = connection.execute(
            """
            SELECT id,source_version,checksum_sha256,status FROM dataset_versions
            WHERE id=%s AND dataset_id=%s AND organization_id=%s AND project_id=%s
              AND workspace_id=%s
            """,
            (dataset_version_id, dataset_id, organization_id, project_id, workspace_id),
        ).fetchone()
        if version is None:
            raise RuntimeError("Dataset Version is outside verification scope")
        object_counts = {
            str(row["object_type"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT object_type,COUNT(*) AS count FROM ontology_objects
                WHERE dataset_version_id=%s GROUP BY object_type ORDER BY object_type
                """,
                (dataset_version_id,),
            ).fetchall()
        }
        link_counts = {
            str(row["link_type"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT link_type,COUNT(*) AS count FROM ontology_links
                WHERE dataset_version_id=%s GROUP BY link_type ORDER BY link_type
                """,
                (dataset_version_id,),
            ).fetchall()
        }
        source_counts = {
            "assets": int(connection.execute(
                "SELECT COUNT(*) AS count FROM pm_assets WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"]),
            "relations": int(connection.execute(
                "SELECT COUNT(*) AS count FROM pm_asset_relations WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"]),
            "maintenance_events": int(connection.execute(
                "SELECT COUNT(*) AS count FROM pm_maintenance_events WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"]),
            "prediction_snapshots": int(connection.execute(
                "SELECT COUNT(*) AS count FROM pm_prediction_snapshots WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"]),
            "result_artifacts": int(connection.execute(
                "SELECT COUNT(*) AS count FROM pm_result_artifacts WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"]),
        }
        traversal = {
            "site_cell_equipment": int(connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM ontology_links sc
                JOIN ontology_links ce ON ce.source_object_id=sc.target_object_id
                WHERE sc.dataset_version_id=%s AND ce.dataset_version_id=%s
                  AND sc.link_type='site_contains_cell'
                  AND ce.link_type='cell_contains_equipment'
                """,
                (dataset_version_id, dataset_version_id),
            ).fetchone()["count"]),
            "compressor_supplies_cnc": int(connection.execute(
                """
                SELECT COUNT(*) AS count FROM ontology_links
                WHERE dataset_version_id=%s
                  AND link_type='equipment_supplies_air_to_equipment'
                """,
                (dataset_version_id,),
            ).fetchone()["count"]),
            "equipment_risk_prediction": int(connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM ontology_links er
                JOIN ontology_links rp ON rp.source_object_id=er.target_object_id
                WHERE er.dataset_version_id=%s AND rp.dataset_version_id=%s
                  AND er.link_type='equipment_has_risk_event'
                  AND rp.link_type='risk_event_supported_by_prediction_result'
                """,
                (dataset_version_id, dataset_version_id),
            ).fetchone()["count"]),
            "equipment_workorder_action": int(connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM ontology_links ew
                JOIN ontology_links wa ON wa.source_object_id=ew.target_object_id
                WHERE ew.dataset_version_id=%s AND wa.dataset_version_id=%s
                  AND ew.link_type='equipment_has_work_order'
                  AND wa.link_type='work_order_has_maintenance_action'
                """,
                (dataset_version_id, dataset_version_id),
            ).fetchone()["count"]),
        }
        lineage_missing = {
            "objects": int(connection.execute(
                """
                SELECT COUNT(*) AS count FROM ontology_objects
                WHERE dataset_version_id=%s AND (
                    dataset_id IS NULL OR source_sha256 IS NULL
                    OR payload_json->'properties'->>'dataset_version_id' IS DISTINCT FROM %s
                )
                """,
                (dataset_version_id, dataset_version_id),
            ).fetchone()["count"]),
            "links": int(connection.execute(
                """
                SELECT COUNT(*) AS count FROM ontology_links
                WHERE dataset_version_id=%s AND (
                    dataset_id IS NULL OR source_sha256 IS NULL
                    OR payload_json->'properties'->>'dataset_version_id' IS DISTINCT FROM %s
                )
                """,
                (dataset_version_id, dataset_version_id),
            ).fetchone()["count"]),
        }
        payload_text = "\n".join(
            str(row["payload_json"]).lower()
            for row in connection.execute(
                """
                SELECT payload_json FROM ontology_objects WHERE dataset_version_id=%s
                UNION ALL
                SELECT payload_json FROM ontology_links WHERE dataset_version_id=%s
                """,
                (dataset_version_id, dataset_version_id),
            ).fetchall()
        )
        leakage = {needle: needle in payload_text for needle in FORBIDDEN_TEXT}
        raw_objects = {
            object_type: object_counts.get(object_type, 0)
            for object_type in FORBIDDEN_OBJECT_TYPES
        }
        binary_types = {
            str(row["value"])
            for row in connection.execute(
                """
                SELECT DISTINCT payload_json->'properties'->>'predicted_failure_type' AS value
                FROM ontology_objects
                WHERE dataset_version_id=%s
                  AND object_type IN ('risk_event','prediction_result')
                """,
                (dataset_version_id,),
            ).fetchall()
            if row["value"] is not None
        }
        recommendation_workorder_links = int(connection.execute(
            """
            SELECT COUNT(*) AS count FROM ontology_links
            WHERE dataset_version_id=%s AND link_type='risk_event_requires_work_order'
            """,
            (dataset_version_id,),
        ).fetchone()["count"])
        recommendation_not_executed = int(connection.execute(
            """
            SELECT COUNT(*) AS count FROM ontology_objects
            WHERE dataset_version_id=%s AND object_type='risk_event'
              AND payload_json->'properties'->>'recommendation_execution_state'='not_executed'
            """,
            (dataset_version_id,),
        ).fetchone()["count"])
        materialization_runs = connection.execute(
            """
            SELECT object_count,link_count,materialization_checksum_sha256
            FROM ontology_ingestion_runs WHERE dataset_version_id=%s
              AND source_system='predictive-maintenance-postgresql-materialization'
            ORDER BY completed_at DESC LIMIT 2
            """,
            (dataset_version_id,),
        ).fetchall()
        materialization_idempotent = (
            len(materialization_runs) >= 2
            and len({int(row["object_count"]) for row in materialization_runs}) == 1
            and len({int(row["link_count"]) for row in materialization_runs}) == 1
            and len({str(row["materialization_checksum_sha256"]) for row in materialization_runs}) == 1
        )
        graph_projection = connection.execute(
            """
            SELECT status,record_count FROM store_projections
            WHERE dataset_version_id=%s AND store_kind='graph'
            """,
            (dataset_version_id,),
        ).fetchone()
        projection_outbox = connection.execute(
            """
            SELECT payload_json FROM transactional_outbox
            WHERE aggregate_id=%s AND event_type='ontology.materialization.completed'
            ORDER BY created_at DESC LIMIT 1
            """,
            (dataset_version_id,),
        ).fetchone()
        projection_payload = (
            projection_outbox["payload_json"] if projection_outbox is not None else None
        )

    role = f"pm_ontology_rls_{uuid.uuid4().hex[:12]}"
    rls: dict[str, object] = {"checked": False}
    try:
        with psycopg.connect(normalized, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            admin.execute(
                sql.SQL("GRANT SELECT ON ontology_objects,ontology_links TO {}").format(
                    sql.Identifier(role)
                )
            )
        with psycopg.connect(_dsn_for_user(normalized, role), row_factory=dict_row) as scoped:
            scoped.execute("SELECT set_config('app.organization_id',%s,false)", (organization_id,))
            scoped.execute("SELECT set_config('app.project_id',%s,false)", (project_id,))
            visible = int(scoped.execute(
                "SELECT COUNT(*) AS count FROM ontology_objects WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"])
            scoped.execute("SELECT set_config('app.project_id',%s,false)", (f"{project_id}-other",))
            hidden = int(scoped.execute(
                "SELECT COUNT(*) AS count FROM ontology_objects WHERE dataset_version_id=%s",
                (dataset_version_id,),
            ).fetchone()["count"])
        rls = {"checked": True, "visible": visible, "other_project_visible": hidden, "pass": visible > 0 and hidden == 0}
    finally:
        try:
            with psycopg.connect(normalized, autocommit=True) as admin:
                admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        except Exception:
            pass

    expected_risk = source_counts["result_artifacts"] or source_counts["prediction_snapshots"]
    phase4_payload_ready = isinstance(projection_payload, dict)
    if phase4_payload_ready:
        expected_source_role = (
            "result_artifact"
            if source_counts["result_artifacts"]
            else "prediction_snapshot_compatibility"
        )
        result_contract = projection_payload.get("result_contract", {})
        topology_semantics = projection_payload.get("topology_semantics", {})
        phase4_payload_ready = (
            projection_payload.get("organization_id") == organization_id
            and projection_payload.get("project_id") == project_id
            and projection_payload.get("workspace_id") == workspace_id
            and projection_payload.get("dataset_id") == dataset_id
            and projection_payload.get("dataset_version_id") == dataset_version_id
            and projection_payload.get("source_version") == str(version["source_version"])
            and projection_payload.get("bundle_checksum_sha256")
            == str(version["checksum_sha256"])
            and isinstance(projection_payload.get("materialization_checksum_sha256"), str)
            and result_contract.get("source_role") == expected_source_role
            and result_contract.get("prediction_tasks")
            == ["binary_failure_within_horizon"]
            and result_contract.get("predicted_failure_type_semantics")
            == "generic_binary_risk_not_ai4i_failure_mode"
            and topology_semantics
            == {
                "SUPPLIES_AIR_TO": "topology_only_not_causal_truth",
                "causal_claim_allowed": False,
            }
            and "canonical/evaluation_truth"
            in projection_payload.get("excluded_sources", [])
            and "experiments/connected_air_supply/hidden_truth"
            in projection_payload.get("excluded_sources", [])
        )
        if str(version["source_version"]) == "canonical-ai4i-physics-v3.1":
            release_gates = projection_payload.get("release_gates", {})
            continuity = release_gates.get("tool_wear_continuity", {})
            agent_evaluation = release_gates.get("agent_example_evaluation", {})
            phase4_payload_ready = phase4_payload_ready and (
                result_contract.get("schema_versions") == ["result-artifact-v1.0"]
                and result_contract.get("model_versions") == ["independent-logreg-v3.1"]
                and continuity.get("pass") is True
                and continuity.get("running_reset_count") == 0
                and continuity.get("tool_replacement_event_count") == 731
                and continuity.get("aligned_reset_transition_count") == 731
                and agent_evaluation.get("maintenance_evidence_accuracy") == 1.0
            )
    passed = (
        object_counts.get("equipment") == source_counts["assets"]
        and object_counts.get("risk_event") == expected_risk
        and object_counts.get("prediction_result") == source_counts["prediction_snapshots"]
        and object_counts.get("work_order") == source_counts["maintenance_events"]
        and object_counts.get("maintenance_action") == source_counts["maintenance_events"]
        and link_counts.get("equipment_supplies_air_to_equipment") == source_counts["relations"]
        and traversal["site_cell_equipment"] == source_counts["assets"]
        and traversal["equipment_risk_prediction"] == expected_risk
        and traversal["equipment_workorder_action"] == source_counts["maintenance_events"]
        and recommendation_workorder_links == 0
        and recommendation_not_executed == expected_risk
        and binary_types.issubset({"failure_risk", "no_significant_risk"})
        and all(value == 0 for value in raw_objects.values())
        and not any(leakage.values())
        and not any(lineage_missing.values())
        and materialization_idempotent
        and graph_projection is not None
        and graph_projection["status"] == "pending"
        and phase4_payload_ready
        and bool(rls.get("pass"))
    )
    return {
        "pass": passed,
        "dataset_id": dataset_id,
        "dataset_version_id": dataset_version_id,
        "source_version": str(version["source_version"]),
        "bundle_checksum_sha256": str(version["checksum_sha256"]),
        "object_counts": object_counts,
        "link_counts": link_counts,
        "source_counts": source_counts,
        "traversal": traversal,
        "lineage_missing": lineage_missing,
        "binary_prediction_types": sorted(binary_types),
        "recommended_action": {
            "risk_events_marked_not_executed": recommendation_not_executed,
            "automatic_risk_to_workorder_links": recommendation_workorder_links,
            "actual_workorders": object_counts.get("work_order", 0),
        },
        "raw_object_counts": raw_objects,
        "truth_leakage": leakage,
        "materialization_idempotent": materialization_idempotent,
        "graph_projection": None if graph_projection is None else dict(graph_projection),
        "phase4_projection_payload_ready": phase4_payload_ready,
        "phase4_projection_payload": projection_payload,
        "rls": rls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version-id", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = verify(
        database_url=args.database_url,
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        dataset_id=args.dataset_id,
        dataset_version_id=args.dataset_version_id,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
