#!/usr/bin/env python3
"""Exercise the active Python repository graph against ephemeral PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from argon2 import PasswordHasher

from ontology_dashboard.adapters.models import DatasetManifest, PredictionResult
from ontology_dashboard.dashboard_service import DashboardService
from ontology_dashboard.identity import IdentityService, LoginRequest
from ontology_dashboard.outbox import default_outbox_worker
from ontology_dashboard.postgresql_pool import close_pools
from ontology_dashboard.postgresql_repositories import (
    PostgreSQLAdapterRepository,
    PostgreSQLAuditRepository,
    PostgreSQLDashboardRepository,
    PostgreSQLExportRepository,
    PostgreSQLIdentityRepository,
    PostgreSQLOntologyActionRepository,
    PostgreSQLPredictionResultRepository,
    PostgreSQLProjectRepository,
    PostgreSQLRoleWorkflowRepository,
)
from ontology_dashboard.projects import ProjectService

from check_postgresql_migration import MIGRATION_DIR, REQUIRED_BINARIES, free_port, run

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    missing = [name for name in REQUIRED_BINARIES if shutil.which(name) is None]
    try:
        import psycopg  # noqa: F401
        import psycopg_pool  # noqa: F401
    except ImportError:
        missing.extend(["psycopg", "psycopg_pool"])
    if missing:
        print(
            json.dumps(
                {
                    "check": "postgresql-runtime",
                    "skipped": True,
                    "missing": sorted(set(missing)),
                }
            )
        )
        return 0

    port = free_port()
    with tempfile.TemporaryDirectory(prefix="ontology-dashboard-postgres-runtime-") as temp_dir:
        data_dir = Path(temp_dir) / "data"
        run(["initdb", "-D", str(data_dir), "-A", "trust", "-U", "postgres"])
        started = False
        try:
            run(
                [
                    "pg_ctl",
                    "-D",
                    str(data_dir),
                    "-o",
                    f"-p {port} -h 127.0.0.1",
                    "-w",
                    "start",
                ]
            )
            started = True
            run(
                [
                    "createdb",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    "postgres",
                    "ontology_runtime",
                ]
            )
            for migration in sorted(MIGRATION_DIR.glob("*.sql")):
                run(
                    [
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
                        "ontology_runtime",
                        "-f",
                        str(migration),
                    ]
                )
            run(
                [
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
                    "ontology_runtime",
                    "-c",
                    """
                    CREATE ROLE ontology_app LOGIN;
                    GRANT USAGE ON SCHEMA public TO ontology_app;
                    GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO ontology_app;
                    GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO ontology_app;
                    GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ontology_app;
                    """,
                ]
            )

            database_url = f"postgresql://ontology_app@127.0.0.1:{port}/ontology_runtime"
            hasher = PasswordHasher(
                time_cost=1,
                memory_cost=8192,
                parallelism=1,
                hash_len=16,
                salt_len=16,
            )
            identity_repository = PostgreSQLIdentityRepository(
                database_url,
                password_hasher=hasher,
                seed_reference_data=True,
            )
            identity = IdentityService(
                database_url,
                app_env="test",
                seed_demo=True,
                repository=identity_repository,
            )
            principal, token, _, _ = identity.login(
                LoginRequest(email="manager@ontology.local", password="Manager!2026"),
                user_agent="postgres-runtime-check",
                client_ip="127.0.0.1",
            )
            restored = identity.principal_for_token(
                token,
                user_agent="postgres-runtime-check",
                client_ip="127.0.0.1",
            )
            assert restored.user_id == principal.user_id
            assert restored.active_project_id == "manufacturing-demo-project"

            projects = ProjectService(PostgreSQLProjectRepository(database_url)).list_for_principal(restored)
            assert {item.id for item in projects} >= {
                "manufacturing-demo-project",
                "azure-fleet-maintenance-project",
                "metropt-compressor-project",
            }

            admin_user = identity_repository.authenticate(
                "admin@ontology.local",
                "OntologyAdmin!2026",
            )
            identity_repository.update_project_membership(
                actor_user_id=admin_user["id"],
                organization_id="org-ontology-demo",
                project_id="azure-fleet-maintenance-project",
                target_user_id=restored.user_id,
                status="active",
                roles=["executive_viewer"],
            )
            identity_repository.set_session_active_project(
                token,
                user_id=restored.user_id,
                project_id="azure-fleet-maintenance-project",
            )
            azure_principal = identity.principal_for_token(
                token,
                user_agent="postgres-runtime-check",
                client_ip="127.0.0.1",
            )
            assert azure_principal.roles == ["executive_viewer"]
            assert "executive.overview.read" in azure_principal.permissions
            assert "events.decision" not in azure_principal.permissions
            identity_repository.set_session_active_project(
                token,
                user_id=restored.user_id,
                project_id="manufacturing-demo-project",
            )
            restored = identity.principal_for_token(
                token,
                user_agent="postgres-runtime-check",
                client_ip="127.0.0.1",
            )

            dashboard_repository = PostgreSQLDashboardRepository(database_url)
            dashboard = DashboardService(
                database_url,
                repository=dashboard_repository,
            ).resolve(principal=restored, workspace_id="manufacturing-demo")
            assert dashboard.workspace_id == "manufacturing-demo"

            audit_repository = PostgreSQLAuditRepository(database_url)
            decision = audit_repository.record_decision(
                "EVT-PG-1",
                actor=restored.display_name,
                decision="request_inspection",
                note="PostgreSQL runtime check",
            )
            assert decision["event_id"] == "EVT-PG-1"

            action_repository = PostgreSQLOntologyActionRepository(database_url)
            reserved, created = action_repository.reserve(
                idempotency_key="runtime-check-action",
                workspace_id="manufacturing-demo",
                action_type="record_operational_decision",
                object_id="risk-event:EVT-PG-1",
                actor_user_id=restored.user_id,
                actor_display_name=restored.display_name,
                request_hash="a" * 64,
                request={"decision": "request_inspection"},
            )
            assert created is True
            completed = action_repository.succeed(
                reserved["id"],
                project_id="manufacturing-demo-project",
                result={"status": "recorded"},
                audit_id="audit-runtime-check",
            )
            assert completed["state"] == "succeeded"

            workflow_repository = PostgreSQLRoleWorkflowRepository(database_url)
            field_action = workflow_repository.record_field_action(
                workspace_id="manufacturing-demo",
                event_id="EVT-PG-1",
                action="complete",
                actor_user_id=restored.user_id,
                actor_display_name=restored.display_name,
                payload={"measurement": 1.0},
            )
            assert field_action["project_id"] == "manufacturing-demo-project"
            outbox_worker = default_outbox_worker(database_url)
            assert outbox_worker.process_once() is True
            assert outbox_worker.process_once() is False

            export_repository = PostgreSQLExportRepository(database_url)
            checkpoint = export_repository.create_checkpoint(
                workspace_id="manufacturing-demo",
                scope="dashboard",
                export_format="json",
                event_id="EVT-PG-1",
                filename="runtime.json",
                media_type="application/json",
                content_bytes=2,
                snapshot_hash="b" * 64,
                content_hash="c" * 64,
                requested_by=restored.user_id,
                requested_by_name=restored.display_name,
                snapshot={},
            )
            assert checkpoint["project_id"] == "manufacturing-demo-project"

            fixture = ROOT / "data" / "fixtures" / "adapters" / "azure-fleet-maintenance-fixture.csv"
            manifest = DatasetManifest.model_validate(
                {
                    "manifest_version": "1.0",
                    "manifest_id": "postgres-runtime-manifest",
                    "organization_id": "org-ontology-demo",
                    "project_id": "azure-fleet-maintenance-project",
                    "workspace_id": "azure-fleet-maintenance",
                    "adapter_code": "azure-fleet-maintenance",
                    "dataset_name": "PostgreSQL Runtime Fixture",
                    "dataset_version": "runtime-v1",
                    "source": {
                        "uri": str(fixture),
                        "media_type": "text/csv",
                        "checksum_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                        "size_bytes": fixture.stat().st_size,
                        "encoding": "utf-8",
                    },
                    "schema": {
                        "format": "csv",
                        "required_fields": ["datetime", "machineID"],
                    },
                    "created_at": "2026-08-01T00:00:00Z",
                }
            )
            adapter_repository = PostgreSQLAdapterRepository(database_url)
            adapter_repository.save_manifest(manifest)
            assert adapter_repository.list_manifests(
                organization_id="org-ontology-demo",
                project_id="azure-fleet-maintenance-project",
            )[0]["id"] == manifest.manifest_id

            prediction = PredictionResult.model_validate(
                {
                    "contract_version": "1.0",
                    "prediction_id": "postgres-runtime-prediction",
                    "organization_id": "org-ontology-demo",
                    "project_id": "azure-fleet-maintenance-project",
                    "workspace_id": "azure-fleet-maintenance",
                    "subject": {"object_type": "equipment", "object_id": "machine-1"},
                    "prediction": {
                        "task": "classification",
                        "status": "warning",
                        "score": 0.8,
                        "confidence": 0.9,
                    },
                    "evidence": [
                        {
                            "evidence_id": "postgres-runtime-evidence",
                            "kind": "feature",
                            "label": "vibration",
                            "value": 2.1,
                            "source": {"system": "runtime-check", "reference": "row:1"},
                        }
                    ],
                    "model": {
                        "provider": "runtime-check",
                        "model_name": "risk",
                        "model_version": "v1",
                        "dataset_version": "runtime-v1",
                    },
                    "created_at": "2026-08-01T00:00:00Z",
                }
            )
            prediction_repository = PostgreSQLPredictionResultRepository(database_url)
            prediction_repository.save(prediction)
            assert len(
                prediction_repository.list(
                    organization_id="org-ontology-demo",
                    project_id="azure-fleet-maintenance-project",
                )
            ) == 1
            assert prediction_repository.list(
                organization_id="org-ontology-demo",
                project_id="manufacturing-demo-project",
            ) == []

            result = {
                "check": "postgresql-runtime",
                "skipped": False,
                "principal": restored.email,
                "project_count": len(projects),
                "project_role_switch": azure_principal.roles,
                "dashboard_workspace": dashboard.workspace_id,
                "action_state": completed["state"],
                "field_action_project": field_action["project_id"],
                "outbox_processed": True,
                "export_project": checkpoint["project_id"],
                "dataset_manifest": manifest.manifest_id,
                "prediction": prediction.prediction_id,
                "pass": True,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        finally:
            close_pools()
            if started:
                run(["pg_ctl", "-D", str(data_dir), "-m", "fast", "-w", "stop"])


if __name__ == "__main__":
    raise SystemExit(main())
