from __future__ import annotations

from pathlib import Path

import pytest

from ontology_dashboard.dashboard_repository import DashboardRepository
from ontology_dashboard.export_repository import ExportRepository
from ontology_dashboard.identity import IdentityService
from ontology_dashboard.migrations import migrate
from ontology_dashboard.ontology_repository import OntologyActionRepository
from ontology_dashboard.role_workflow_repository import RoleWorkflowRepository


AZURE_PROJECT = "azure-fleet-maintenance-project"
AZURE_WORKSPACE = "azure-fleet-maintenance"
MANUFACTURING_PROJECT = "manufacturing-demo-project"
MANUFACTURING_WORKSPACE = "manufacturing-demo"
USER_ID = "project-isolation-user"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "project-isolation-matrix.db"
    migrate(str(path))
    IdentityService(path, app_env="test", seed_demo=True)
    return path


def test_dashboard_preferences_are_partitioned_by_project_workspace(database_path: Path) -> None:
    repository = DashboardRepository(database_path)
    template = repository.get_current_template(
        workspace_id=AZURE_WORKSPACE,
        role_code="process_manager",
    )
    assert template is not None

    repository.save_preferences(
        user_id=USER_ID,
        workspace_id=AZURE_WORKSPACE,
        template_id=template.template_id,
        template_version=template.version,
        base_revision=0,
        payload={"active_tab_id": template.tabs[0].id, "tabs": [], "parameter_state": {}},
    )

    assert repository.get_preferences(
        user_id=USER_ID,
        workspace_id=AZURE_WORKSPACE,
        template_id=template.template_id,
    ) is not None
    assert repository.get_preferences(
        user_id=USER_ID,
        workspace_id=MANUFACTURING_WORKSPACE,
        template_id=template.template_id,
    ) is None


def test_ontology_action_state_cannot_cross_project_boundary(database_path: Path) -> None:
    repository = OntologyActionRepository(database_path)
    reserved, created = repository.reserve(
        idempotency_key="project-isolation-action",
        workspace_id=AZURE_WORKSPACE,
        action_type="record_operational_decision",
        object_id="risk_event:EVT-AZ-001",
        actor_user_id=USER_ID,
        actor_display_name="Isolation Test",
        request_hash="a" * 64,
        request={"decision": "request_inspection"},
    )
    assert created is True
    assert reserved["project_id"] == AZURE_PROJECT

    assert repository.find_by_idempotency_key(
        workspace_id=MANUFACTURING_WORKSPACE,
        actor_user_id=USER_ID,
        idempotency_key="project-isolation-action",
    ) is None
    assert repository.list_for_object(
        workspace_id=MANUFACTURING_WORKSPACE,
        object_id="risk_event:EVT-AZ-001",
    ) == []

    with pytest.raises(RuntimeError):
        repository.succeed(
            reserved["id"],
            project_id=MANUFACTURING_PROJECT,
            result={"status": "wrong-project"},
            audit_id="audit-wrong-project",
        )

    completed = repository.succeed(
        reserved["id"],
        project_id=AZURE_PROJECT,
        result={"status": "recorded"},
        audit_id="audit-correct-project",
    )
    assert completed["state"] == "succeeded"
    assert completed["project_id"] == AZURE_PROJECT


def test_workflow_and_export_records_remain_in_their_project(database_path: Path) -> None:
    workflows = RoleWorkflowRepository(database_path)
    field_action = workflows.record_field_action(
        workspace_id=AZURE_WORKSPACE,
        event_id="EVT-AZ-001",
        action="complete",
        actor_user_id=USER_ID,
        actor_display_name="Isolation Test",
        payload={"note": "Azure-only action"},
    )
    assert field_action["project_id"] == AZURE_PROJECT
    assert workflows.list_field_actions(workspace_id=MANUFACTURING_WORKSPACE) == []

    exports = ExportRepository(database_path)
    checkpoint = exports.create_checkpoint(
        workspace_id=AZURE_WORKSPACE,
        scope="dashboard",
        export_format="json",
        event_id="EVT-AZ-001",
        filename="azure-isolation.json",
        media_type="application/json",
        content_bytes=2,
        snapshot_hash="b" * 64,
        content_hash="c" * 64,
        requested_by=USER_ID,
        requested_by_name="Isolation Test",
        snapshot={},
    )
    assert checkpoint["project_id"] == AZURE_PROJECT
    assert exports.list_checkpoints(workspace_id=MANUFACTURING_WORKSPACE) == []
    assert [item["id"] for item in exports.list_checkpoints(project_id=AZURE_PROJECT)] == [checkpoint["id"]]
