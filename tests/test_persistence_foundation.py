from __future__ import annotations

import sqlite3
from pathlib import Path

from ontology_dashboard.identity import IdentityService
from ontology_dashboard.migrations import migrate
from ontology_dashboard.ontology_instance_repository import OntologyInstanceRepository
from ontology_dashboard.ontology_service import OntologyService
from ontology_dashboard.role_workflow_repository import RoleWorkflowRepository
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


def test_migrations_are_idempotent_and_create_outbox(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    first = migrate(str(database))
    second = migrate(str(database))
    assert first == [
        "0001_platform_core",
        "0002_project_layer",
        "0003_project_scoped_operations",
        "0004_prediction_results",
        "0005_project_memberships",
        "0006_outbox_worker",
        "0007_analysis_engine",
        "0008_dataset_projection_pipeline",
            "0009_agent_orchestration",
            "0010_analysis_run_lifecycle",
            "0011_adaptive_modeling_foundation",
            "0012_adaptive_model_registry",
            "0019_tenant_transaction_convergence",
            "0020_enterprise_identity_access",
            "0021_distributed_execution_runtime",
            "0022_object_storage_artifact_governance",
            "0023_production_connectors_ingestion",
            "0024_ontology_interfaces_actions_functions",
            "0025_global_branching_lineage_markings",
            "0026_object_views_search_application_runtime",
            "0027_scalable_pipeline_analysis",
            "0028_continuous_mlops_runtime",
            "0029_governed_event_automation",
        ]
    assert second == []

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "schema_migrations" in tables
    assert "transactional_outbox" in tables
    assert "ontology_schema_versions" in tables
    assert "ontology_source_mappings" in tables
    assert {"analyses", "analysis_boards", "analysis_runs"} <= tables


def test_ontology_adapter_materializes_persistent_objects_and_links(tmp_path: Path) -> None:
    database = tmp_path / "ontology.db"
    IdentityService(database, app_env="test", seed_demo=True)
    service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database)
    ontology = OntologyService(service)

    result = ontology.query_objects(
        workspace_id=WORKSPACE,
        object_type="risk_event",
        search=None,
    )
    assert result["total"] == 8

    repository = OntologyInstanceRepository(database)
    assert len(repository.list_objects(workspace_id=WORKSPACE)) >= 8
    assert len(repository.list_links(workspace_id=WORKSPACE)) >= 8
    ingestion = repository.latest_ingestion(workspace_id=WORKSPACE)
    assert ingestion is not None
    assert ingestion["source_system"] == "manufacturing-predictive-maintenance-pack"


def test_field_action_and_outbox_are_committed_together(tmp_path: Path) -> None:
    database = tmp_path / "outbox.db"
    IdentityService(database, app_env="test", seed_demo=True)
    migrate(str(database))
    repository = RoleWorkflowRepository(database)

    result = repository.record_field_action(
        workspace_id=WORKSPACE,
        event_id="EVT-GS-002",
        action="complete",
        actor_user_id="test-user",
        actor_display_name="Test User",
        payload={"checklist": ["visual inspection"], "measurements": {}},
    )
    assert result["status"] == "completed"

    with sqlite3.connect(database) as connection:
        action_count = connection.execute(
            "SELECT COUNT(*) FROM field_task_actions WHERE id=?",
            (result["id"],),
        ).fetchone()[0]
        outbox = connection.execute(
            """
            SELECT organization_id,workspace_id,aggregate_id,event_type,status
            FROM transactional_outbox
            WHERE aggregate_type='field_task' AND aggregate_id=?
            """,
            ("EVT-GS-002",),
        ).fetchone()
    assert action_count == 1
    assert outbox == (
        "org-ontology-demo",
        WORKSPACE,
        "EVT-GS-002",
        "field_task.complete",
        "pending",
    )
