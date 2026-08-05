from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ontology_dashboard.analysis_models import AnalysisRunRequest
from ontology_dashboard.analysis_service import AnalysisService
from ontology_dashboard.distributed_handlers import configured_handlers
from ontology_dashboard.distributed_runtime import DurableJobRepository, DurableWorker
from ontology_dashboard.identity import CSRF_COOKIE, IdentityService
from ontology_dashboard.main import app, get_identity_service, get_service
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = "manufacturing-demo"
ANALYSIS_ID = "risk-event-server-analysis"


@pytest.fixture()
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "analysis_path_test.db"


@pytest.fixture()
def identity(database_path: Path) -> IdentityService:
    return IdentityService(database_path, app_env="test", seed_demo=True)


@pytest.fixture()
def service(database_path: Path) -> ManufacturingPredictiveMaintenanceService:
    return ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)


@pytest.fixture()
def client(identity: IdentityService, service: ManufacturingPredictiveMaintenanceService):
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "fde@ontology.local", "password": "FDE!2026"},
    )
    assert response.status_code == 200, response.text


def run_analysis_worker_once(service: ManufacturingPredictiveMaintenanceService) -> None:
    database = str(service.repository.path)
    repository = DurableJobRepository(database)
    worker = DurableWorker(
        repository,
        worker_id="analysis-test-worker",
        worker_version="test",
        runtime_checksum="test-checksum",
        job_types=("analysis",),
        handlers=configured_handlers(database, ROOT),
    )
    completed = None
    for organization_id, project_id in repository.project_scopes():
        completed = worker.process_once(
            organization_id=organization_id,
            project_id=project_id,
        )
        if completed is not None:
            break
    assert completed is not None
    assert completed.state == "succeeded"


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def analysis_nodes(filter_value: str = "critical") -> list[dict]:
    return [
        {
            "id": "input:0",
            "type": "analysisStep",
            "position": {"x": 100, "y": 20},
            "data": {
                "kind": "input",
                "title": "Risk Event objects",
                "config": {"source": "risk_event", "version": "latest_published"},
                "rows": 0,
                "outputKind": "rows",
                "elapsedMs": 0,
                "status": "idle",
            },
        },
        {
            "id": "filter:1",
            "type": "analysisStep",
            "position": {"x": 100, "y": 180},
            "selected": True,
            "data": {
                "kind": "filter",
                "title": "Critical filter",
                "config": {"field": "status", "operator": "equals", "value": filter_value},
                "rows": 0,
                "outputKind": "rows",
                "elapsedMs": 0,
                "status": "idle",
            },
        },
        {
            "id": "group:2",
            "type": "analysisStep",
            "position": {"x": 100, "y": 340},
            "data": {
                "kind": "group",
                "title": "Group by line",
                "config": {"field": "line"},
                "rows": 0,
                "outputKind": "groups",
                "elapsedMs": 0,
                "status": "idle",
            },
        },
        {
            "id": "chart:3",
            "type": "analysisStep",
            "position": {"x": 100, "y": 500},
            "data": {
                "kind": "chart",
                "title": "Risk by line",
                "config": {"chart": "bar", "x": "line", "y": "average_risk"},
                "rows": 0,
                "outputKind": "chart",
                "elapsedMs": 0,
                "status": "idle",
            },
        },
    ]


def analysis_edges() -> list[dict]:
    return [
        {"id": "e1", "source": "input:0", "target": "filter:1", "type": "smoothstep"},
        {"id": "e2", "source": "filter:1", "target": "group:2", "type": "smoothstep"},
        {"id": "e3", "source": "group:2", "target": "chart:3", "type": "smoothstep"},
    ]


def test_ontology_aggregate_and_pagination(client: TestClient) -> None:
    login(client)

    aggregate = client.get(
        "/api/ontology/objects/aggregate",
        params=[
            ("workspace_id", WORKSPACE),
            ("object_type", "risk_event"),
            ("group_by", "status"),
            ("metrics", "count"),
            ("metrics", "avg:failure_probability"),
        ],
    )
    assert aggregate.status_code == 200, aggregate.text
    payload = aggregate.json()
    assert payload["source_rows"] >= 1
    assert payload["row_count"] >= 1
    assert {"status", "count", "avg_failure_probability"} <= set(payload["rows"][0])

    first_page = client.get(
        "/api/ontology/objects",
        params={"workspace_id": WORKSPACE, "object_type": "risk_event", "offset": 0, "limit": 1},
    )
    second_page = client.get(
        "/api/ontology/objects",
        params={"workspace_id": WORKSPACE, "object_type": "risk_event", "offset": 1, "limit": 1},
    )
    assert first_page.status_code == second_page.status_code == 200
    assert len(first_page.json()["items"]) == len(second_page.json()["items"]) == 1
    assert first_page.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]


def test_analysis_persistence_run_and_reference_result(client: TestClient) -> None:
    login(client)
    headers = csrf_headers(client)

    created = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "id": ANALYSIS_ID,
            "workspace_id": WORKSPACE,
            "display_name": "Risk Event Server Analysis",
            "nodes": analysis_nodes(),
            "edges": analysis_edges(),
            "publish": True,
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["current_version"] == 1
    assert created.json()["published_version"] == 1

    run = client.post(
        f"/api/analyses/{ANALYSIS_ID}/run",
        headers=headers,
        json={
            "workspace_id": WORKSPACE,
            "version_policy": "pinned",
            "version": 1,
            "preview_limit": 500,
        },
    )
    assert run.status_code == 200, run.text
    run_payload = run.json()
    assert run_payload["status"] == "succeeded", run_payload
    assert set(run_payload["node_results"]) == {"input:0", "filter:1", "group:2", "chart:3"}
    assert run_payload["node_results"]["chart:3"]["render_spec"]["kind"] == "bar"
    assert run_payload["node_results"]["group:2"]["warnings"]
    assert run_payload["node_results"]["input:0"]["quality"]["computed_by"] == "server"
    assert run_payload["node_results"]["input:0"]["quality"]["row_count"] >= 1

    node_result = client.get(
        f"/api/analyses/{ANALYSIS_ID}/nodes/chart:3/result",
        params={"workspace_id": WORKSPACE, "version_policy": "latest_published"},
    )
    assert node_result.status_code == 200, node_result.text
    assert node_result.json()["analysis_version"] == 1
    assert node_result.json()["run_id"] == run_payload["id"]
    assert node_result.json()["result"]["row_count"] >= 1

    updated = client.put(
        f"/api/analyses/{ANALYSIS_ID}",
        headers=headers,
        json={
            "workspace_id": WORKSPACE,
            "display_name": "Risk Event Server Analysis v2",
            "nodes": analysis_nodes("warning"),
            "edges": analysis_edges(),
            "base_version": 1,
            "publish": True,
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["current_version"] == 2
    assert updated.json()["published_version"] == 2

    conflict = client.put(
        f"/api/analyses/{ANALYSIS_ID}",
        headers=headers,
        json={
            "workspace_id": WORKSPACE,
            "display_name": "stale update",
            "nodes": analysis_nodes(),
            "edges": analysis_edges(),
            "base_version": 1,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "analysis_version_conflict"


def test_analysis_definition_rejects_unknown_join_and_cycles_before_persistence(client: TestClient) -> None:
    login(client)
    headers = csrf_headers(client)
    join_nodes = analysis_nodes()
    join_nodes.insert(
        1,
        {
            "id": "join:blocked",
            "type": "analysisStep",
            "position": {"x": 100, "y": 120},
            "data": {
                "kind": "join",
                "title": "Unsafe join",
                "config": {"relationship": "risk_event_secret_table"},
                "rows": 0,
                "outputKind": "rows",
                "elapsedMs": 0,
                "status": "idle",
            },
        },
    )
    unknown_join = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "id": "unsafe-join-analysis",
            "workspace_id": WORKSPACE,
            "display_name": "Unsafe join",
            "nodes": join_nodes,
            "edges": [{"id": "e0", "source": "input:0", "target": "join:blocked"}],
        },
    )
    assert unknown_join.status_code == 422
    assert unknown_join.json()["error"]["code"] == "contract_validation_failed"
    assert "join relationship is not allowed" in unknown_join.json()["error"]["message"]

    cycle = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "id": "cyclic-analysis",
            "workspace_id": WORKSPACE,
            "display_name": "Cyclic analysis",
            "nodes": analysis_nodes()[:2],
            "edges": [
                {"id": "cycle-1", "source": "input:0", "target": "filter:1"},
                {"id": "cycle-2", "source": "filter:1", "target": "input:0"},
            ],
        },
    )
    assert cycle.status_code == 422
    assert cycle.json()["error"]["code"] == "contract_validation_failed"
    assert cycle.json()["error"]["message"] == "analysis graph must be acyclic"


def test_analysis_job_lifecycle_cache_cursor_and_cancel(
    client: TestClient,
    identity: IdentityService,
    service: ManufacturingPredictiveMaintenanceService,
) -> None:
    login(client)
    headers = csrf_headers(client)
    created = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "id": "analysis-job-lifecycle",
            "workspace_id": WORKSPACE,
            "display_name": "Analysis job lifecycle",
            "nodes": analysis_nodes(),
            "edges": analysis_edges(),
            "publish": True,
        },
    )
    assert created.status_code == 200, created.text

    queued = client.post(
        "/api/analyses/analysis-job-lifecycle/jobs",
        headers=headers,
        json={
            "workspace_id": WORKSPACE,
            "version_policy": "pinned",
            "version": 1,
            "preview_limit": 500,
        },
    )
    assert queued.status_code == 202, queued.text
    first_run_id = queued.json()["id"]
    run_analysis_worker_once(service)
    completed = client.get(
        f"/api/analysis-runs/{first_run_id}",
        params={"workspace_id": WORKSPACE},
    )
    assert completed.status_code == 200, completed.text
    first = completed.json()
    assert first["status"] == "succeeded"
    assert first["progress_percent"] == 100
    assert first["rows_scanned"] >= first["node_results"]["input:0"]["row_count"]
    assert first["cache_hit"] is False

    rows = client.get(
        f"/api/analysis-runs/{first_run_id}/nodes/input:0/rows",
        params={"workspace_id": WORKSPACE, "limit": 1},
    )
    assert rows.status_code == 200, rows.text
    assert len(rows.json()["rows"]) == 1
    assert rows.json()["total"] >= 1

    cached = client.post(
        "/api/analyses/analysis-job-lifecycle/jobs",
        headers=headers,
        json={
            "workspace_id": WORKSPACE,
            "version_policy": "pinned",
            "version": 1,
            "preview_limit": 500,
        },
    )
    assert cached.status_code == 202, cached.text
    run_analysis_worker_once(service)
    cached_result = client.get(
        f"/api/analysis-runs/{cached.json()['id']}",
        params={"workspace_id": WORKSPACE},
    ).json()
    assert cached_result["status"] == "succeeded"
    assert cached_result["cache_hit"] is True
    assert cached_result["node_results"] == first["node_results"]

    user = identity.repository.authenticate("fde@ontology.local", "FDE!2026")
    principal = identity.repository.principal(
        user["id"],
        active_project_id="manufacturing-demo-project",
    )
    analysis_service = AnalysisService(str(service.repository.path))
    request = AnalysisRunRequest(
        workspace_id=WORKSPACE,
        version_policy="pinned",
        version=1,
        preview_limit=100,
    )
    cancellable = analysis_service.queue_run(
        analysis_id="analysis-job-lifecycle",
        request=request,
        principal=principal,
    )
    cancel_requested = analysis_service.cancel_run(
        run_id=cancellable.id,
        workspace_id=WORKSPACE,
        principal=principal,
    )
    assert cancel_requested.cancel_requested is True
    cancelled = analysis_service.execute_queued_run(
        run_id=cancellable.id,
        request=request,
        principal=principal,
        ontology=None,  # cancellation is checked before an Ontology query is attempted
    )
    assert cancelled.status == "cancelled"
    assert cancelled.error and cancelled.error["code"] == "cancelled"


def test_dashboard_board_query_reapplies_selection_on_server(client: TestClient) -> None:
    login(client)
    headers = csrf_headers(client)
    dashboard = client.get("/api/dashboards/resolved", params={"workspace_id": WORKSPACE})
    assert dashboard.status_code == 200, dashboard.text
    resolved = dashboard.json()
    board = next(
        item
        for tab in resolved["tabs"]
        for item in tab["boards"]
        if item.get("source") is None
    )

    response = client.post(
        f"/api/dashboards/{resolved['dashboard_id']}/boards/{board['id']}/query",
        headers=headers,
        json={
            "workspace_id": WORKSPACE,
            "parameter_state": {"status_filter": "all"},
            "selection_filters": [
                {
                    "id": "filter-1",
                    "source_board_id": "source-chart",
                    "field": "status",
                    "operator": "eq",
                    "values": ["critical"],
                }
            ],
            "offset": 0,
            "limit": 1,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["limit"] == 1
    assert len(payload["rows"]) <= 1
    assert all(row["status"] == "critical" for row in payload["rows"])
    assert payload["matching_object_ids"]
    assert len(payload["matching_object_ids"]) == payload["row_count"]
    assert all(not object_id.startswith("risk_event:") for object_id in payload["matching_object_ids"])
    assert payload["timezone"] == "UTC"
