from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.datasets import (
    DatasetCatalogService,
    DatasetCreateRequest,
    DatasetRepository,
    DatasetVersionCreateRequest,
)
from ontology_dashboard.dependencies import get_governance_service
from ontology_dashboard.governance import GovernanceService
from ontology_dashboard.identity import CSRF_COOKIE, AuthError, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.migrations import migrate
from ontology_dashboard.orchestration import AgentRunRepository
from ontology_dashboard.orchestration.models import AgentState, EvidenceItem, GroundedClaim
from ontology_dashboard.role_workflow_service import RoleWorkflowService
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def setup(tmp_path: Path):
    database = tmp_path / "governance.db"
    migrate(str(database))
    identity = IdentityService(database, app_env="test", seed_demo=True)
    domain = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database)
    datasets = DatasetRepository(database)
    catalog = DatasetCatalogService(datasets)
    agents = AgentRunRepository(database)
    workflows = RoleWorkflowService(domain)
    service = GovernanceService(datasets=datasets, agents=agents, workflows=workflows)

    fde_user = identity.repository.authenticate("fde@ontology.local", "FDE!2026")
    fde = identity.repository.principal(
        fde_user["id"],
        active_project_id="manufacturing-demo-project",
    )
    quality_user = identity.repository.authenticate("quality@ontology.local", "Quality!2026")
    quality = identity.repository.principal(
        quality_user["id"],
        active_project_id="manufacturing-demo-project",
    )

    dataset = catalog.create_dataset(
        principal=fde,
        request=DatasetCreateRequest(
            id="ds-governance-fixture",
            project_id="manufacturing-demo-project",
            workspace_id="manufacturing-demo",
            slug="governance-fixture",
            display_name="Governance Fixture",
            source_type="fixture",
        ),
    )
    version = catalog.create_version(
        principal=fde,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        request=DatasetVersionCreateRequest(
            source_version="fixture-governance-v1",
            checksum_sha256="b" * 64,
            schema={"fields": [{"name": "equipment_id", "type": "string"}]},
            profile={"null_ratio": 0.0},
            record_count=1,
        ),
    )
    graph = next(
        item
        for item in datasets.list_projections(
            organization_id=fde.organization_id,
            project_id=dataset.project_id,
            dataset_id=dataset.id,
            version_id=version.id,
        )
        if item["store_kind"] == "graph"
    )
    datasets.claim_projection(
        organization_id=fde.organization_id,
        project_id=dataset.project_id,
        projection_id=graph["id"],
    )
    datasets.fail_projection(
        organization_id=fde.organization_id,
        project_id=dataset.project_id,
        projection_id=graph["id"],
        error_message="neo4j fixture unavailable",
    )

    evidence = EvidenceItem(
        evidence_id="ev-governance-1",
        store="postgresql",
        reference="dataset:ds-governance-fixture",
        project_id=dataset.project_id,
        workspace_id="manufacturing-demo",
        dataset_version_id=version.id,
        object_id="equipment:M-014",
        title="Risk event",
        content="M-014 risk event evidence",
        score=0.94,
    )
    state = AgentState(
        run_id="agent-run-governance",
        organization_id=fde.organization_id,
        project_id=dataset.project_id,
        workspace_id="manufacturing-demo",
        user_id=fde.user_id,
        question="Show M-014 evidence",
        route="hybrid",
        status="succeeded",
        evidence=[evidence],
        claims=[
            GroundedClaim(
                claim_id="claim-1",
                text="M-014 has a recorded risk event.",
                evidence_ids=[evidence.evidence_id],
                confidence="high",
            )
        ],
        answer="M-014 has a recorded risk event. [ev-governance-1]",
    )
    checkpointed = agents.create(state)
    agents.trace(
        checkpointed,
        step_name="execute_relational",
        store_kind="relational",
        status="succeeded",
        input_payload={"query_id": "equipment-risk-events"},
        output_payload={"evidence_ids": [evidence.evidence_id]},
        latency_ms=12,
    )
    agents.finish(checkpointed)

    return database, identity, domain, service, fde, quality, graph["id"], version.id


def test_governance_overview_reconstructs_projection_agent_and_lineage(setup) -> None:
    _, _, _, service, _, quality, projection_id, version_id = setup
    overview = service.overview(
        principal=quality,
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
    )

    assert overview.counts.datasets == 1
    assert overview.counts.dataset_versions == 1
    assert overview.counts.failed_projections == 1
    assert overview.counts.agent_runs == 1
    assert overview.access.can_retry_projection is False
    failed = next(item for item in overview.projections if item.id == projection_id)
    assert failed.status == "failed"
    assert failed.dataset_version_id == version_id
    assert failed.can_retry is False
    assert overview.agent_runs[0].run_id == "agent-run-governance"
    assert overview.agent_runs[0].evidence_count == 1
    assert overview.lineage[0].latest_version_id == version_id
    assert overview.access.tenant_admin_controls_excluded is True

    detail = service.agent_run(
        principal=quality,
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        run_id="agent-run-governance",
    )
    assert detail.state.claims[0].evidence_ids == ["ev-governance-1"]
    assert detail.traces[0].step_name == "execute_relational"
    assert detail.checkpoints[0]["node_name"] == "start"


def test_projection_retry_requires_governance_permission_and_scope(setup) -> None:
    _, _, _, service, fde, quality, projection_id, _ = setup

    with pytest.raises(AuthError) as denied:
        service.retry_projection(
            principal=quality,
            project_id="manufacturing-demo-project",
            workspace_id="manufacturing-demo",
            projection_id=projection_id,
        )
    assert denied.value.code == "permission_denied"

    result = service.retry_projection(
        principal=fde,
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        projection_id=projection_id,
    )
    assert result.projection.status == "pending"

    with pytest.raises(AuthError) as scope_error:
        service.overview(
            principal=fde,
            project_id="azure-fleet-maintenance-project",
            workspace_id="manufacturing-demo",
        )
    assert scope_error.value.code == "active_project_mismatch"


@pytest.fixture()
def client(setup):
    _, identity, domain, service, *_ = setup
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain
    app.dependency_overrides[get_governance_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def test_governance_routes_are_project_scoped_and_retry_is_fde_only(client: TestClient, setup) -> None:
    *_, projection_id, _ = setup
    login(client, "quality@ontology.local", "Quality!2026")
    overview = client.get(
        "/api/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance"
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["counts"]["failed_projections"] == 1
    run = client.get(
        "/api/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance/agent-runs/agent-run-governance"
    )
    assert run.status_code == 200
    assert run.json()["state"]["claims"][0]["validated"] is True
    denied = client.post(
        f"/api/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance/projections/{projection_id}/retry"
    )
    assert denied.status_code == 403

    client.post("/api/auth/logout")
    csrf = login(client, "fde@ontology.local", "FDE!2026")
    retried = client.post(
        f"/api/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance/projections/{projection_id}/retry",
        headers=csrf,
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["projection"]["status"] == "pending"
