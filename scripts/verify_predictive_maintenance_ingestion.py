#!/usr/bin/env python3
"""Verify predictive-maintenance PostgreSQL row parity, FK integrity, and RLS."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.dataset.ingestion import (
    BundleFileAdapter,
    PredictiveMaintenanceCanonicalV2Adapter,
)


ROLE_TABLES = {
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


def _require_psycopg():
    try:
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("verification requires api[postgres]") from exc
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
    package_root: Path,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    manifest_id: str,
) -> dict[str, object]:
    psycopg, sql, dict_row = _require_psycopg()
    manifest = PredictiveMaintenanceCanonicalV2Adapter.build_manifest(
        package_root,
        organization_id=organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        manifest_id=manifest_id,
    )
    validation = BundleFileAdapter(allowed_roots=[package_root]).validate(manifest)
    if validation.status != "completed":
        raise RuntimeError("source bundle no longer passes Phase 1 validation")
    expected = {item.role: item.source_record_count for item in validation.roles}

    normalized_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized_url, row_factory=dict_row) as connection:
        version = connection.execute(
            """
            SELECT v.id,v.dataset_id,v.version_number,v.source_version,v.status,
                   v.organization_id,v.project_id,v.workspace_id,v.profile_json
            FROM dataset_versions v
            WHERE v.organization_id=%s AND v.project_id=%s AND v.checksum_sha256=%s
            ORDER BY v.version_number DESC LIMIT 1
            """,
            (organization_id, project_id, manifest.bundle_checksum_sha256),
        ).fetchone()
        if version is None:
            raise RuntimeError("no Dataset Version exists for the source bundle checksum")
        version_id = str(version["id"])
        version_profile = version["profile_json"]
        if not isinstance(version_profile, dict):
            version_profile = {}
        release_gates = version_profile.get("release_gates", {})
        if not isinstance(release_gates, dict):
            release_gates = {}
        governance_artifacts = version_profile.get("governance_artifacts", [])
        if not isinstance(governance_artifacts, list):
            governance_artifacts = []
        actual: dict[str, int] = {}
        for role in expected:
            table = ROLE_TABLES[role]
            row = connection.execute(
                sql.SQL("SELECT COUNT(*) AS count FROM {} WHERE dataset_version_id=%s").format(
                    sql.Identifier(table)
                ),
                (version_id,),
            ).fetchone()
            actual[role] = int(row["count"])

        fk_checks = {
            "relations": """
                SELECT COUNT(*) AS count FROM pm_asset_relations r
                LEFT JOIN pm_assets source ON source.dataset_version_id=r.dataset_version_id
                    AND source.asset_id=r.from_asset_id
                LEFT JOIN pm_assets target ON target.dataset_version_id=r.dataset_version_id
                    AND target.asset_id=r.to_asset_id
                WHERE r.dataset_version_id=%s
                  AND (source.asset_id IS NULL OR target.asset_id IS NULL)
            """,
            "compressor_observations": """
                SELECT COUNT(*) AS count FROM pm_compressor_observations f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.asset_id
                WHERE f.dataset_version_id=%s AND a.asset_id IS NULL
            """,
            "cnc_observations": """
                SELECT COUNT(*) AS count FROM pm_cnc_observations f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.asset_id
                WHERE f.dataset_version_id=%s AND a.asset_id IS NULL
            """,
            "production_cycles": """
                SELECT COUNT(*) AS count FROM pm_production_cycles f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.cnc_asset_id
                WHERE f.dataset_version_id=%s AND a.asset_id IS NULL
            """,
            "maintenance_events": """
                SELECT COUNT(*) AS count FROM pm_maintenance_events f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.asset_id
                WHERE f.dataset_version_id=%s AND a.asset_id IS NULL
            """,
            "prediction_snapshots": """
                SELECT COUNT(*) AS count FROM pm_prediction_snapshots f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.asset_id
                LEFT JOIN prediction_results p ON p.prediction_id=f.prediction_result_id
                WHERE f.dataset_version_id=%s
                  AND (a.asset_id IS NULL OR p.prediction_id IS NULL)
            """,
            "prediction_factors": """
                SELECT COUNT(*) AS count FROM pm_prediction_factors f
                LEFT JOIN pm_prediction_snapshots p
                    ON p.dataset_version_id=f.dataset_version_id
                    AND p.prediction_id=f.prediction_id
                WHERE f.dataset_version_id=%s AND p.prediction_id IS NULL
            """,
            "prediction_timeline": """
                SELECT COUNT(*) AS count FROM pm_prediction_timeline f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.asset_id
                WHERE f.dataset_version_id=%s AND a.asset_id IS NULL
            """,
        }
        if "result_artifact" in expected:
            fk_checks["result_artifacts"] = """
                SELECT COUNT(*) AS count FROM pm_result_artifacts f
                LEFT JOIN pm_assets a ON a.dataset_version_id=f.dataset_version_id
                    AND a.asset_id=f.asset_id
                LEFT JOIN pm_prediction_snapshots p
                    ON p.dataset_version_id=f.dataset_version_id
                    AND p.prediction_id=f.prediction_id
                LEFT JOIN prediction_results pr ON pr.prediction_id=f.prediction_result_id
                WHERE f.dataset_version_id=%s
                  AND (a.asset_id IS NULL OR p.prediction_id IS NULL OR pr.prediction_id IS NULL)
            """
        fk_orphans = {
            name: int(connection.execute(statement, (version_id,)).fetchone()["count"])
            for name, statement in fk_checks.items()
        }
        time_checks = {}
        time_specs = [
            ("compressor_sensor_observation", "pm_compressor_observations", "observed_at"),
            ("cnc_sensor_observation", "pm_cnc_observations", "observed_at"),
            ("cnc_production_cycle", "pm_production_cycles", "cycle_completed_at"),
            ("maintenance_event", "pm_maintenance_events", "started_at"),
            ("prediction_snapshot", "pm_prediction_snapshots", "observed_at"),
            ("prediction_timeline", "pm_prediction_timeline", "observed_at"),
        ]
        if "result_artifact" in expected:
            time_specs.append(("result_artifact", "pm_result_artifacts", "observed_at"))
        for role, table, field in time_specs:
            row = connection.execute(
                sql.SQL("SELECT MIN({0}) AS minimum,MAX({0}) AS maximum FROM {1} WHERE dataset_version_id=%s").format(
                    sql.Identifier(field), sql.Identifier(table)
                ),
                (version_id,),
            ).fetchone()
            minimum = row["minimum"]
            maximum = row["maximum"]
            time_checks[role] = {
                "minimum": None if minimum is None else minimum.isoformat(),
                "maximum": None if maximum is None else maximum.isoformat(),
                "within_generation_period": (
                    minimum is not None
                    and maximum is not None
                    and manifest.generation.period_start <= minimum
                    and maximum <= manifest.generation.period_end
                ),
            }
        version_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM dataset_versions WHERE dataset_id=%s AND checksum_sha256=%s",
                (version["dataset_id"], manifest.bundle_checksum_sha256),
            ).fetchone()["count"]
        )
        outbox_count = int(
            connection.execute(
                """
                SELECT COUNT(*) AS count FROM transactional_outbox
                WHERE aggregate_id=%s AND event_type='dataset.version.relational_ready'
                """,
                (version_id,),
            ).fetchone()["count"]
        )

    role_name = f"pm_rls_verify_{uuid.uuid4().hex[:12]}"
    rls_result: dict[str, object] = {"checked": False}
    try:
        with psycopg.connect(normalized_url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role_name)))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role_name)))
            tables = ["datasets", "dataset_versions", *(ROLE_TABLES[role] for role in expected)]
            admin.execute(
                sql.SQL("GRANT SELECT ON {} TO {}").format(
                    sql.SQL(",").join(sql.Identifier(table) for table in tables),
                    sql.Identifier(role_name),
                )
            )
        with psycopg.connect(_dsn_for_user(normalized_url, role_name), row_factory=dict_row) as scoped:
            scoped.execute("SELECT set_config('app.organization_id', %s, false)", (organization_id,))
            scoped.execute("SELECT set_config('app.project_id', %s, false)", (project_id,))
            visible = int(scoped.execute("SELECT COUNT(*) AS count FROM pm_assets").fetchone()["count"])
            scoped.execute("SELECT set_config('app.project_id', %s, false)", (f"{project_id}-other",))
            hidden = int(scoped.execute("SELECT COUNT(*) AS count FROM pm_assets").fetchone()["count"])
        rls_result = {
            "checked": True,
            "visible_in_project": visible,
            "visible_in_other_project": hidden,
            "pass": visible == expected["asset_master"] and hidden == 0,
        }
    finally:
        try:
            with psycopg.connect(normalized_url, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role_name))
                )
                admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role_name)))
        except Exception:
            pass

    v3_1_release_gate_pass = True
    if manifest.dataset_version == "canonical-ai4i-physics-v3.1":
        continuity = release_gates.get("tool_wear_continuity", {})
        agent_evaluation = release_gates.get("agent_example_evaluation", {})
        v3_1_release_gate_pass = (
            isinstance(continuity, dict)
            and continuity.get("pass") is True
            and continuity.get("running_reset_count") == 0
            and continuity.get("tool_replacement_event_count") == 731
            and continuity.get("aligned_reset_transition_count") == 731
            and continuity.get("reset_without_matching_maintenance_count") == 0
            and continuity.get("replacement_without_reset_count") == 0
            and isinstance(agent_evaluation, dict)
            and agent_evaluation.get("maintenance_evidence_claims") == 1
            and agent_evaluation.get("maintenance_evidence_accuracy") == 1.0
            and agent_evaluation.get("false_upstream_claim_rate") == 0.0
            and {item.get("role") for item in governance_artifacts if isinstance(item, dict)}
            == {"package_validation", "agent_example_evaluation"}
        )

    passed = (
        actual == expected
        and all(count == 0 for count in fk_orphans.values())
        and all(bool(item["within_generation_period"]) for item in time_checks.values())
        and version_count == 1
        and outbox_count == 1
        and bool(rls_result.get("pass"))
        and v3_1_release_gate_pass
    )
    return {
        "pass": passed,
        "dataset_id": str(version["dataset_id"]),
        "dataset_version_id": version_id,
        "version_number": int(version["version_number"]),
        "source_version": str(version["source_version"]),
        "dataset_version_status": str(version["status"]),
        "bundle_checksum_sha256": manifest.bundle_checksum_sha256,
        "expected_row_counts": expected,
        "database_row_counts": actual,
        "fk_orphan_counts": fk_orphans,
        "time_range_checks": time_checks,
        "same_checksum_version_count": version_count,
        "relational_ready_outbox_count": outbox_count,
        "governance_artifacts": governance_artifacts,
        "release_gates": release_gates,
        "v3_1_release_gate_pass": v3_1_release_gate_pass,
        "rls": rls_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_root")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--organization-id", default="org-ontology-demo")
    parser.add_argument("--project-id", default="predictive-maintenance-v2")
    parser.add_argument("--workspace-id", default="predictive-maintenance-main")
    parser.add_argument("--manifest-id", default="predictive-maintenance-canonical-v2")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = verify(
        database_url=args.database_url,
        package_root=Path(args.package_root).expanduser().resolve(strict=True),
        organization_id=args.organization_id,
        project_id=args.project_id,
        workspace_id=args.workspace_id,
        manifest_id=args.manifest_id,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
