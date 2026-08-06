from __future__ import annotations

import sqlite3
from pathlib import Path

from ontology_dashboard.identity import IdentityService
from ontology_dashboard.migrations import migrate
from ontology_dashboard.ontology_instance_repository import OntologyInstanceRepository
from ontology_dashboard.ontology_service import OntologyService
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"


def test_migrations_are_idempotent_and_keep_current_runtime_tables(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    first = migrate(str(database))
    second = migrate(str(database))
    assert first
    assert second == []

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {
        "schema_migrations",
        "organizations",
        "projects",
        "workspaces",
        "user_project_scopes",
        "datasets",
        "dataset_versions",
        "materializations",
        "store_projections",
        "prediction_results",
        "ontology_action_invocations",
        "transactional_outbox",
    } <= tables


def test_current_domain_pack_materializes_persistent_objects_and_links(tmp_path: Path) -> None:
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
