#!/usr/bin/env python3
"""Apply the PostgreSQL migration to an ephemeral local server when available."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_DIR = ROOT / "api" / "migrations" / "postgresql"
REQUIRED_BINARIES = ("initdb", "pg_ctl", "createdb", "psql")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(command: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
    )
    return completed.stdout.strip() if capture else ""


def main() -> int:
    missing = [name for name in REQUIRED_BINARIES if shutil.which(name) is None]
    if missing:
        print(json.dumps({"check": "postgresql-migration", "skipped": True, "missing": missing}))
        return 0

    port = free_port()
    with tempfile.TemporaryDirectory(prefix="ontology-dashboard-postgres-") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        run(["initdb", "-D", str(data_dir), "-A", "trust", "-U", "postgres"])
        started = False
        try:
            run([
                "pg_ctl",
                "-D",
                str(data_dir),
                "-o",
                f"-p {port} -h 127.0.0.1 -k /tmp",
                "-w",
                "start",
            ])
            started = True
            run(["createdb", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "ontology_test"])
            for migration in sorted(MIGRATION_DIR.glob("*.sql")):
                run([
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    "postgres",
                    "-d",
                    "ontology_test",
                    "-f",
                    str(migration),
                ])
            for predictive_maintenance_migration in (
                MIGRATION_DIR / "0011_predictive_maintenance_domain_pack.sql",
                MIGRATION_DIR / "0012_predictive_maintenance_v3_materialization.sql",
            ):
                run([
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    "postgres",
                    "-d",
                    "ontology_test",
                    "-f",
                    str(predictive_maintenance_migration),
                ])
            tables = run([
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "postgres",
                "-d",
                "ontology_test",
                "-Atc",
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename",
            ], capture=True).splitlines()
            rls_rows = run([
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "postgres",
                "-d",
                "ontology_test",
                "-Atc",
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND rowsecurity ORDER BY tablename",
            ], capture=True).splitlines()
            project_rls_rows = run([
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "postgres",
                "-d",
                "ontology_test",
                "-Atc",
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename IN ('projects','workspaces') AND rowsecurity ORDER BY tablename",
            ], capture=True).splitlines()
            required = {
                "organizations",
                "projects",
                "workspaces",
                "users",
                "sessions",
                "dashboard_templates",
                "dashboard_user_preferences",
                "dashboard_saved_views",
                "dashboard_shares",
                "ontology_objects",
                "ontology_links",
                "ontology_ingestion_runs",
                "ontology_schema_versions",
                "ontology_source_mappings",
                "ontology_action_invocations",
                "field_task_actions",
                "template_publish_requests",
                "model_release_requests",
                "export_checkpoints",
                "dataset_manifests",
                "adapter_ingestion_runs",
                "adapter_quarantine_records",
                "prediction_results",
                "pm_assets",
                "pm_asset_relations",
                "pm_compressor_observations",
                "pm_compressor_observations_default",
                "pm_cnc_observations",
                "pm_cnc_observations_default",
                "pm_production_cycles",
                "pm_maintenance_events",
                "pm_prediction_snapshots",
                "pm_prediction_factors",
                "pm_prediction_timeline",
                "pm_result_artifacts",
                "ontology_materialization_mappings",
                "transactional_outbox",
                "schema_migrations",
            }
            required_rls = {
                "projects",
                "workspaces",
                "users",
                "sessions",
                "dashboard_templates",
                "dashboard_user_preferences",
                "dashboard_saved_views",
                "dashboard_shares",
                "ontology_objects",
                "ontology_links",
                "ontology_ingestion_runs",
                "ontology_schema_versions",
                "ontology_source_mappings",
                "ontology_action_invocations",
                "field_task_actions",
                "template_publish_requests",
                "model_release_requests",
                "export_checkpoints",
                "dataset_manifests",
                "adapter_ingestion_runs",
                "adapter_quarantine_records",
                "prediction_results",
                "pm_assets",
                "pm_asset_relations",
                "pm_compressor_observations",
                "pm_compressor_observations_default",
                "pm_cnc_observations",
                "pm_cnc_observations_default",
                "pm_production_cycles",
                "pm_maintenance_events",
                "pm_prediction_snapshots",
                "pm_prediction_factors",
                "pm_prediction_timeline",
                "pm_result_artifacts",
                "ontology_materialization_mappings",
                "transactional_outbox",
            }
            run([
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "postgres",
                "-d",
                "ontology_test",
                "-c",
                """
                INSERT INTO organizations(id,slug,name) VALUES
                  ('org-a','org-a','Org A'),('org-b','org-b','Org B');
                INSERT INTO projects(id,organization_id,slug,display_name,domain_pack_code) VALUES
                  ('project-a1','org-a','project-a1','Project A1','generic'),
                  ('project-a2','org-a','project-a2','Project A2','generic'),
                  ('project-b','org-b','project-b','Project B','generic');
                INSERT INTO workspaces(id,organization_id,project_id,slug,display_name,domain_pack) VALUES
                  ('ws-a1','org-a','project-a1','ws-a1','Workspace A1','generic'),
                  ('ws-a2','org-a','project-a2','ws-a2','Workspace A2','generic'),
                  ('ws-b','org-b','project-b','ws-b','Workspace B','generic');
                INSERT INTO ontology_objects(
                  organization_id,project_id,workspace_id,object_id,object_type,payload_json,source_system
                ) VALUES
                  ('org-a','project-a1','ws-a1','object-a1','asset','{}'::jsonb,'test'),
                  ('org-a','project-a2','ws-a2','object-a2','asset','{}'::jsonb,'test'),
                  ('org-b','project-b','ws-b','object-b','asset','{}'::jsonb,'test');
                INSERT INTO prediction_results(
                  prediction_id,organization_id,project_id,workspace_id,subject_object_type,
                  subject_object_id,prediction_status,model_version,dataset_version,payload_json,created_at
                ) VALUES
                  ('prediction-a1','org-a','project-a1','ws-a1','asset','object-a1','warning','v1','d1','{}'::jsonb,now()),
                  ('prediction-a2','org-a','project-a2','ws-a2','asset','object-a2','warning','v1','d1','{}'::jsonb,now()),
                  ('prediction-b','org-b','project-b','ws-b','asset','object-b','warning','v1','d1','{}'::jsonb,now());
                CREATE ROLE ontology_rls_test LOGIN;
                GRANT USAGE ON SCHEMA public TO ontology_rls_test;
                GRANT SELECT ON ontology_objects,prediction_results TO ontology_rls_test;
                """,
            ])
            rls_result = run([
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "ontology_rls_test",
                "-d",
                "ontology_test",
                "-Atc",
                "SET app.organization_id='org-a'; SET app.project_id='project-a1'; "
                "SELECT string_agg(object_id,',' ORDER BY object_id) FROM ontology_objects;",
            ], capture=True).splitlines()
            prediction_result = run([
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-p",
                str(port),
                "-U",
                "ontology_rls_test",
                "-d",
                "ontology_test",
                "-Atc",
                "SET app.organization_id='org-a'; SET app.project_id='project-a1'; "
                "SELECT string_agg(prediction_id,',' ORDER BY prediction_id) FROM prediction_results;",
            ], capture=True).splitlines()
            visible_objects = next((line for line in rls_result if line.startswith("object")), "")
            visible_predictions = next(
                (line for line in prediction_result if line.startswith("prediction")),
                "",
            )
            passed = (
                required.issubset(set(tables))
                and required_rls.issubset(set(rls_rows))
                and project_rls_rows == ["projects", "workspaces"]
                and visible_objects == "object-a1"
                and visible_predictions == "prediction-a1"
            )
            print(json.dumps({
                "check": "postgresql-migration",
                "skipped": False,
                "tables": tables,
                "rls_tables": rls_rows,
                "project_rls_tables": project_rls_rows,
                "rls_query_output": rls_result,
                "rls_visible_objects_for_org_a": visible_objects,
                "rls_prediction_query_output": prediction_result,
                "rls_visible_predictions_for_project_a1": visible_predictions,
                "required_rls_tables": sorted(required_rls),
                "predictive_maintenance_migrations_reapplied": ["0011", "0012"],
                "pass": passed,
            }, ensure_ascii=False, indent=2))
            return 0 if passed else 1
        finally:
            if started:
                subprocess.run(
                    ["pg_ctl", "-D", str(data_dir), "-m", "fast", "-w", "stop"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )


if __name__ == "__main__":
    raise SystemExit(main())
