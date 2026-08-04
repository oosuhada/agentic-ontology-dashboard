from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.dependencies import get_multistore_orchestrator
from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.migrations import migrate
from ontology_dashboard.orchestration import (
    AgentQueryRequest,
    AgentRunRepository,
    EvidenceItem,
    MultiStoreOrchestrator,
)
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]


class FixturePort:
    def __init__(self, store_name: str, *, fail: bool = False) -> None:
        self.store_name = store_name
        self.fail = fail
        self.calls = 0

    def search(self, state, *, top_k: int):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.store_name} unavailable")
        store = {
            "relational": "postgresql",
            "graph": "neo4j",
            "vector": "pgvector",
        }[self.store_name]
        return [
            EvidenceItem(
                evidence_id=f"ev-{self.store_name}-1",
                store=store,
                reference=f"{self.store_name}:fixture:1",
                project_id=state.project_id,
                workspace_id=state.workspace_id,
                dataset_version_id="dsv-fixture-v1",
                object_id="manufacturing-demo-project:ds-fixture:dsv-fixture-v1:Equipment:M-014",
                title=f"{self.store_name.title()} evidence",
                content=f"M-014 risk evidence from {self.store_name}",
                score=0.9,
                metadata={"top_k": top_k},
            )
        ]


@pytest.fixture()
def orchestration_setup(tmp_path: Path):
    database = tmp_path / "agent-orchestration.db"
    migrate(str(database))
    identity = IdentityService(database, app_env="test", seed_demo=True)
    user = identity.repository.authenticate("fde@ontology.local", "FDE!2026")
    principal = identity.repository.principal(
        user["id"],
        active_project_id="manufacturing-demo-project",
    )
    repository = AgentRunRepository(database)
    return database, identity, principal, repository


def orchestrator(repository: AgentRunRepository, *, graph_fail: bool = False, all_fail: bool = False):
    relational = FixturePort("relational", fail=all_fail)
    graph = FixturePort("graph", fail=graph_fail or all_fail)
    vector = FixturePort("vector", fail=all_fail)
    return (
        MultiStoreOrchestrator(
            repository,
            relational_port=relational,
            graph_port=graph,
            vector_port=vector,
        ),
        relational,
        graph,
        vector,
    )


def request(*, route: str = "hybrid", project_id: str = "manufacturing-demo-project"):
    return AgentQueryRequest(
        project_id=project_id,
        workspace_id="manufacturing-demo",
        question="Show equipment relationships and supporting document evidence",
        route=route,
        object_type="Equipment",
        object_id="M-014",
        top_k=5,
    )


def test_route_classifier_selects_each_store_and_hybrid() -> None:
    assert MultiStoreOrchestrator.classify("list latest equipment status") == "relational"
    assert MultiStoreOrchestrator.classify("show connected upstream relationships") == "graph"
    assert MultiStoreOrchestrator.classify("find similar maintenance manual") == "vector"
    assert MultiStoreOrchestrator.classify("show relationship and supporting manual") == "hybrid"
    assert MultiStoreOrchestrator.classify("explain this risk") == "hybrid"


def test_hybrid_run_is_grounded_checkpointed_and_audited(orchestration_setup) -> None:
    _, _, principal, repository = orchestration_setup
    service, relational, graph, vector = orchestrator(repository)

    response = service.run(principal=principal, request=request())

    assert response.state.status == "succeeded"
    assert response.state.route == "hybrid"
    assert len(response.state.evidence) == 3
    assert len(response.state.claims) == 3
    evidence_ids = {item.evidence_id for item in response.state.evidence}
    assert all(set(claim.evidence_ids).issubset(evidence_ids) for claim in response.state.claims)
    assert all(f"[{claim.evidence_ids[0]}]" in response.state.answer for claim in response.state.claims)
    assert response.state.checkpoint_sequence >= 4
    assert {trace.store_kind for trace in response.traces} == {
        "relational",
        "graph",
        "vector",
    }
    assert relational.calls == graph.calls == vector.calls == 1

    inspected = service.inspect(
        principal=principal,
        project_id="manufacturing-demo-project",
        run_id=response.state.run_id,
    )
    assert inspected.state.run_id == response.state.run_id
    assert len(inspected.traces) == 3


def test_hybrid_run_degrades_when_one_store_fails(orchestration_setup) -> None:
    _, _, principal, repository = orchestration_setup
    service, _, graph, _ = orchestrator(repository, graph_fail=True)

    response = service.run(principal=principal, request=request())

    assert response.state.status == "succeeded"
    assert len(response.state.evidence) == 2
    assert any("graph evidence was unavailable" in caveat for caveat in response.state.caveats)
    failed_trace = next(trace for trace in response.traces if trace.store_kind == "graph")
    assert failed_trace.status == "failed"
    assert "graph unavailable" in failed_trace.output["error"]
    assert graph.calls == 1


def test_run_fails_closed_when_all_selected_stores_fail(orchestration_setup) -> None:
    _, _, principal, repository = orchestration_setup
    service, _, _, _ = orchestrator(repository, all_fail=True)

    response = service.run(principal=principal, request=request())

    assert response.state.status == "failed"
    assert response.state.claims == []
    assert response.state.answer == ""
    assert "all selected evidence stores are unavailable" in (response.state.error or "")
    assert len(response.traces) == 4
    assert response.traces[-1].step_name == "orchestration_failure"


def test_agent_run_enforces_project_and_workspace_scope(orchestration_setup) -> None:
    _, identity, principal, repository = orchestration_setup
    service, _, _, _ = orchestrator(repository)

    with pytest.raises(Exception) as project_error:
        service.run(principal=principal, request=request(project_id="other-project"))
    assert getattr(project_error.value, "code", "") == "project_scope_denied"

    user = identity.repository.authenticate("engineer@ontology.local", "Engineer!2026")
    engineer = identity.repository.principal(
        user["id"],
        active_project_id="manufacturing-demo-project",
    )
    foreign_workspace = request()
    foreign_workspace.workspace_id = "fda-review"
    with pytest.raises(Exception) as workspace_error:
        service.run(principal=engineer, request=foreign_workspace)
    assert getattr(workspace_error.value, "code", "") == "workspace_scope_denied"


@pytest.fixture()
def agent_api(orchestration_setup):
    database, identity, _, repository = orchestration_setup
    domain = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database)
    service, _, _, _ = orchestrator(repository, graph_fail=True)
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain
    app.dependency_overrides[get_multistore_orchestrator] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "fde@ontology.local", "password": "FDE!2026"},
    )
    assert response.status_code == 200, response.text
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def test_agent_query_list_pagination_filter_and_inspection_routes(agent_api: TestClient) -> None:
    csrf = login(agent_api)
    created = agent_api.post(
        "/api/agent/query",
        headers=csrf,
        json=request().model_dump(mode="json"),
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["state"]["status"] == "succeeded"
    assert payload["state"]["caveats"]
    run_id = payload["state"]["run_id"]

    listed = agent_api.get(
        "/api/agent/runs",
        params={
            "project_id": "manufacturing-demo-project",
            "workspace_id": "manufacturing-demo",
            "offset": 0,
            "limit": 10,
            "status": "succeeded",
            "route": "hybrid",
            "search": "equipment relationships",
        },
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["run_id"] == run_id
    assert listed.json()["items"][0]["evidence_count"] == 2

    empty = agent_api.get(
        "/api/agent/runs",
        params={
            "project_id": "manufacturing-demo-project",
            "workspace_id": "manufacturing-demo",
            "search": "not-present-question",
        },
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0

    inspected = agent_api.get(
        f"/api/agent/runs/{run_id}",
        params={"project_id": "manufacturing-demo-project"},
    )
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["state"]["run_id"] == run_id

    denied = agent_api.get(
        f"/api/agent/runs/{run_id}",
        params={"project_id": "other-project"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "project_scope_denied"

    wrong_workspace = agent_api.get(
        f"/api/agent/runs/{run_id}",
        params={
            "project_id": "manufacturing-demo-project",
            "workspace_id": "fda-review",
        },
    )
    assert wrong_workspace.status_code == 403
    assert wrong_workspace.json()["error"]["code"] == "workspace_scope_denied"
