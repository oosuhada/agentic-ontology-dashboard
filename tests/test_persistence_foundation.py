from __future__ import annotations

import sqlite3
from pathlib import Path

from app.identity import IdentityService
from app.infra.db.migrations import migrate
from app.infra.db.ontology_action_repository import OntologyActionRepository
from app.infra.db.ontology_instance_repository import OntologyInstanceRepository
from app.infra.db.project_repository import SQLiteProjectContextResolver
from app.ontology.ontology_service import OntologyService
from app.infra.db.role_workflow_repository import RoleWorkflowRepository
from app.dependencies import build_manufacturing_service
from identity_test_support import build_identity_service

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
            "0030_closed_loop_operations",
            "0031_recommendation_materialization_strategy",
            "0032_operations_manual_recommendation",
            "0033_inspection_results",
            "0034_prediction_result_inbox",
            "0035_maintenance_cost_analyses",
            "0036_cost_option_recommendation_lineage",
            "0037_agent_review_summary_runtime",
            "0038_agent_review_summary_materialization",
            "0039_cooling_system_restore_cost_analysis",
            "0040_cooling_system_restore_execution",
            "0041_cost_analysis_reference_lineage",
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
    assert {
        "closed_loop_recommendations",
        "closed_loop_recommendation_decisions",
        "closed_loop_work_orders",
        "closed_loop_maintenance_actions",
        "closed_loop_maintenance_events",
        "closed_loop_equipment_state",
        "closed_loop_activities",
        "closed_loop_idempotency_records",
        "closed_loop_inspection_results",
        "closed_loop_maintenance_cost_analyses",
    } <= tables
    assert {
        "pm_prediction_result_inbox_batches",
        "pm_prediction_result_inbox_items",
    } <= tables
    with sqlite3.connect(database) as connection:
        indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(pm_prediction_result_inbox_batches)"
            )
        } | {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list(pm_prediction_result_inbox_items)"
            )
        }
    assert {
        "uq_pm_prediction_inbox_batches_accepted_identity",
        "uq_pm_prediction_inbox_items_accepted_identity",
    } <= indexes
    with sqlite3.connect(database) as connection:
        activity_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(closed_loop_activities)")
        }
    assert {
        "equipment_id",
        "recommendation_id",
        "work_order_id",
        "maintenance_action_id",
        "maintenance_event_id",
        "actor_user_id",
        "actor_display_name",
        "before_status",
        "after_status",
        "created_at",
    } <= activity_columns
    with sqlite3.connect(database) as connection:
        recommendation_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(closed_loop_recommendations)"
            )
        }
    assert {
        "source_inspection_work_order_id",
        "source_inspection_reference",
        "action_code",
        "authored_by",
        "authored_at",
    } <= recommendation_columns
    with sqlite3.connect(database) as connection:
        maintenance_action_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(closed_loop_maintenance_actions)")
        }
        maintenance_event_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(closed_loop_maintenance_events)")
        }
    assert "restart_at" in maintenance_action_columns
    assert "restart_at" not in maintenance_event_columns


def test_operations_manual_migration_preserves_existing_recommendation_lineage(
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration-upgrade.db"
    migration_root = (
        ROOT / "systems" / "backend" / "migrations" / "sqlite"
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            (migration_root / "0030_closed_loop_operations.sql").read_text(
                encoding="utf-8"
            )
        )
        connection.executescript(
            (
                migration_root
                / "0031_recommendation_materialization_strategy.sql"
            ).read_text(encoding="utf-8")
        )
        connection.execute(
            """
            INSERT INTO closed_loop_recommendations (
                recommendation_id,organization_id,project_id,workspace_id,event_id,
                asset_id,equipment_id,recommendation_origin,status,
                materialization_strategy,source_action_id,source_product_result_id,
                source_evidence_id,source_schema_version,source_policy_version,
                label,kind,requires_human_approval,basis_json,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "recommendation-001",
                "org-1",
                "project-1",
                "workspace-1",
                "event-001",
                "CNC-001",
                "CNC-001",
                "product_result_projection",
                "accepted",
                "runtime_generated",
                "source-action-001",
                "result-001",
                "evidence-001",
                "product-result-v1",
                "recommendation-policy-v1",
                "점검 요청",
                "request_inspection",
                1,
                '["evidence-001"]',
                "2026-08-21T09:00:00+00:00",
                "2026-08-21T09:00:00+00:00",
            ),
        )
        connection.execute(
            """
                INSERT INTO closed_loop_recommendation_decisions (
                    decision_id,organization_id,project_id,workspace_id,event_id,
                    recommendation_id,disposition,actor_id,note,decided_at,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "decision-001",
                "org-1",
                "project-1",
                "workspace-1",
                "event-001",
                "recommendation-001",
                "accept",
                "manager-001",
                "inspection approved",
                "2026-08-21T09:05:00+00:00",
                "2026-08-21T09:05:00+00:00",
            ),
        )
        connection.commit()
        connection.executescript(
            (migration_root / "0032_operations_manual_recommendation.sql").read_text(
                encoding="utf-8"
            )
        )
        connection.execute("PRAGMA foreign_keys=ON")

        recommendation = connection.execute(
            """
            SELECT recommendation_origin,materialization_strategy,
                   source_inspection_work_order_id,action_code
              FROM closed_loop_recommendations
             WHERE recommendation_id='recommendation-001'
            """
        ).fetchone()
        decision = connection.execute(
            """
            SELECT recommendation_id
              FROM closed_loop_recommendation_decisions
             WHERE decision_id='decision-001'
            """
        ).fetchone()
        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    assert recommendation == (
        "product_result_projection",
        "runtime_generated",
        None,
        None,
    )
    assert decision == ("recommendation-001",)
    assert foreign_key_violations == []


def test_ontology_adapter_materializes_persistent_objects_and_links(tmp_path: Path) -> None:
    database = tmp_path / "ontology.db"
    build_identity_service(database, app_env="test", seed_demo=True)
    service = build_manufacturing_service(database, root=ROOT)
    project_context = SQLiteProjectContextResolver(database)
    ontology = OntologyService(
        service,
        action_repository=OntologyActionRepository(database, project_context=project_context),
        instance_repository=OntologyInstanceRepository(database, project_context=project_context),
    )

    result = ontology.query_objects(
        workspace_id=WORKSPACE,
        object_type="risk_event",
        search=None,
    )
    assert result["total"] == 8

    repository = OntologyInstanceRepository(database, project_context=project_context)
    assert len(repository.list_objects(workspace_id=WORKSPACE)) >= 8
    assert len(repository.list_links(workspace_id=WORKSPACE)) >= 8
    ingestion = repository.latest_ingestion(workspace_id=WORKSPACE)
    assert ingestion is not None
    assert ingestion["source_system"] == "manufacturing-predictive-maintenance"


def test_field_action_and_outbox_are_committed_together(tmp_path: Path) -> None:
    database = tmp_path / "outbox.db"
    build_identity_service(database, app_env="test", seed_demo=True)
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
