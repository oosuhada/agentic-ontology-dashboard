from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    build_manufacturing_service,
    get_identity_service,
    get_operational_decision_support_service,
    get_service,
)
from app.identity import CSRF_COOKIE, IdentityService
from app.main import app
from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_decision_brief import DecisionBriefRole
from app.infra.db.operational_decision_support_service import (
    PersistedOperationalDecisionSupportService as OperationalDecisionSupportService,
)
from app.operations.operational_decision_support_port import (
    DECISION_SUPPORT_RUNNING_LEASE_SECONDS,
    DecisionSupportMaterializationInProgress,
)
from identity_test_support import build_identity_service


ROOT = Path(__file__).resolve().parents[1]
ASSET_ID = "CNC-S04-L02-03"
PARAMS = {
    "project_id": "manufacturing-demo-project",
    "workspace_id": "manufacturing-demo",
    "evidence_snapshot_id": "ARTIFACT-GS-004",
    "decision_as_of": "2026-08-01T00:00:00+09:00",
    "role": "process_manager",
}
IDENTITY = OperationalRequestIdentity(
    organization_id="org-ontology-demo",
    project_id=PARAMS["project_id"],
    workspace_id=PARAMS["workspace_id"],
    asset_id=ASSET_ID,
    evidence_snapshot_id=PARAMS["evidence_snapshot_id"],
    decision_as_of=datetime.fromisoformat(PARAMS["decision_as_of"]),
)


def running_record(
    service: OperationalDecisionSupportService,
    *,
    run_id: str,
    started_at: datetime,
) -> tuple[str, dict[str, object]]:
    key = service._cache_key(
        identity=IDENTITY,
        actor_role=DecisionBriefRole.PROCESS_MANAGER,
    )
    timestamp = started_at.isoformat()
    return key, {
        "workflow_run_id": run_id,
        "asset_id": ASSET_ID,
        "project_id": PARAMS["project_id"],
        "cache_key": key,
        "status": "running",
        "reason": None,
        "context_version_set": {},
        "temporal_validation": "not_measured",
        "stale_recovered": False,
        "trajectory": [],
        "started_at": timestamp,
        "completed_at": None,
        "updated_at": timestamp,
        "recorded_at": timestamp,
    }


@pytest.fixture()
def api_client(tmp_path: Path):
    database_path = tmp_path / "decision-support-api.db"
    identity: IdentityService = build_identity_service(
        database_path,
        app_env="test",
        seed_demo=True,
    )
    service = build_manufacturing_service(database_path, root=ROOT)
    decision_support = OperationalDecisionSupportService(ROOT, database_path)
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_operational_decision_support_service] = (
        lambda: decision_support
    )
    with TestClient(app) as client:
        yield client, decision_support
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": str(client.cookies.get(CSRF_COOKIE))}


def test_get_is_cache_only_then_manager_materializes_and_reuses(api_client) -> None:
    client, decision_support = api_client
    login(client, "manager@ontology.local", "Manager!2026")
    url = f"/api/objects/{ASSET_ID}/decision-support-brief"

    empty = client.get(url, params=PARAMS)
    assert empty.status_code == 202
    assert empty.json()["brief"] is None
    assert decision_support.workflow_runs(
        project_id="manufacturing-demo-project",
        asset_id=ASSET_ID,
        status=None,
        limit=20,
    ) == []

    created = client.post(url, params=PARAMS, headers=csrf(client))
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["brief"]["mutation_available"] is False
    assert body["brief"]["recommendation"] is None
    assert body["trace"]["reused"] is False
    assert body["trace"]["temporal_validation"] == "passed"

    cached = client.get(url, params=PARAMS)
    assert cached.status_code == 200
    assert cached.json()["brief"] == body["brief"]
    assert cached.json()["trace"]["reused"] is True

    reused = client.post(url, params=PARAMS, headers=csrf(client))
    assert reused.status_code == 200
    assert reused.json()["trace"]["reused"] is True
    assert len(decision_support.workflow_runs(
        project_id="manufacturing-demo-project",
        asset_id=ASSET_ID,
        status=None,
        limit=20,
    )) == 1
    restarted = OperationalDecisionSupportService(ROOT, decision_support.database_path)
    assert len(restarted.workflow_runs(
        project_id="manufacturing-demo-project",
        asset_id=ASSET_ID,
        status=None,
        limit=20,
    )) == 1


def test_materialize_requires_csrf_and_permission(api_client) -> None:
    client, _ = api_client
    login(client, "manager@ontology.local", "Manager!2026")
    url = f"/api/objects/{ASSET_ID}/decision-support-brief"
    assert client.post(url, params=PARAMS).status_code == 403

    login(client, "engineer@ontology.local", "Engineer!2026")
    denied = client.post(url, params=PARAMS, headers=csrf(client))
    assert denied.status_code == 403


def test_audit_runs_are_admin_only_and_read_only(api_client) -> None:
    client, _ = api_client
    login(client, "manager@ontology.local", "Manager!2026")
    url = f"/api/objects/{ASSET_ID}/decision-support-brief"
    assert client.post(url, params=PARAMS, headers=csrf(client)).status_code == 200

    denied = client.get(
        "/api/projects/manufacturing-demo-project/decision-support-workflow-runs"
    )
    assert denied.status_code == 403

    login(client, "admin@ontology.local", "OntologyAdmin!2026")
    response = client.get(
        "/api/projects/manufacturing-demo-project/decision-support-workflow-runs",
        params={"asset_id": ASSET_ID},
    )
    assert response.status_code == 200
    rows = response.json()["items"]
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert all(
        key not in rows[0]
        for key in ("recommendation", "work_order", "maintenance_action")
    )


def test_atomic_guard_rejects_concurrent_materialization_across_service_instances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "decision-support-concurrency.db"
    first = OperationalDecisionSupportService(ROOT, database_path)
    second = OperationalDecisionSupportService(ROOT, database_path)
    delegate = first._agent(IDENTITY)
    entered = Event()
    release = Event()

    class BlockingAgent:
        def run(self, **kwargs):
            entered.set()
            assert release.wait(timeout=5)
            return delegate.run(**kwargs)

    monkeypatch.setattr(first, "_agent", lambda _identity: BlockingAgent())
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(
            first.materialize,
            identity=IDENTITY,
            actor_role=DecisionBriefRole.PROCESS_MANAGER,
            risk_status="critical",
            trigger="ui_manual_regeneration",
        )
        assert entered.wait(timeout=5)
        try:
            with pytest.raises(
                DecisionSupportMaterializationInProgress,
                match="decision_support_materialization_in_progress",
            ):
                second.materialize(
                    identity=IDENTITY,
                    actor_role=DecisionBriefRole.PROCESS_MANAGER,
                    risk_status="critical",
                    trigger="ui_manual_regeneration",
                )
        finally:
            release.set()
        _brief, trace = future.result(timeout=5)

    assert trace.status == "completed"
    runs = second.workflow_runs(
        project_id=PARAMS["project_id"],
        asset_id=ASSET_ID,
        status=None,
        limit=10,
    )
    assert [run["status"] for run in runs] == ["completed"]


def test_stale_running_reservation_is_expired_before_retry(tmp_path: Path) -> None:
    service = OperationalDecisionSupportService(
        ROOT,
        tmp_path / "decision-support-stale.db",
    )
    now = datetime.now(timezone.utc)
    stale_started_at = now - timedelta(
        seconds=DECISION_SUPPORT_RUNNING_LEASE_SECONDS + 1
    )
    key, stale = running_record(
        service,
        run_id="ODR-stale-running",
        started_at=stale_started_at,
    )
    assert service._reserve_run(key=key, run=stale, now=stale_started_at) is False

    _brief, trace = service.materialize(
        identity=IDENTITY,
        actor_role=DecisionBriefRole.PROCESS_MANAGER,
        risk_status="critical",
        trigger="ui_manual_regeneration",
        now=now,
    )

    assert trace.stale_recovered is True
    runs = service.workflow_runs(
        project_id=PARAMS["project_id"],
        asset_id=ASSET_ID,
        status=None,
        limit=10,
    )
    assert [run["status"] for run in runs] == ["completed", "failed"]
    assert runs[1]["reason"] == "stale_running_lease_expired"


def test_api_maps_active_running_reservation_to_conflict(api_client) -> None:
    client, service = api_client
    login(client, "manager@ontology.local", "Manager!2026")
    now = datetime.now(timezone.utc)
    key, active = running_record(
        service,
        run_id="ODR-active-running",
        started_at=now,
    )
    assert service._reserve_run(key=key, run=active, now=now) is False

    response = client.post(
        f"/api/objects/{ASSET_ID}/decision-support-brief",
        params={**PARAMS, "trigger": "ui_manual_regeneration"},
        headers=csrf(client),
    )

    assert response.status_code == 409
    assert "decision_support_materialization_in_progress" in response.json()["detail"]


def test_scope_and_future_timestamp_are_rejected(api_client) -> None:
    client, _ = api_client
    login(client, "manager@ontology.local", "Manager!2026")
    url = f"/api/objects/{ASSET_ID}/decision-support-brief"
    bad_scope = client.get(url, params={**PARAMS, "workspace_id": "other"})
    assert bad_scope.status_code == 403
    future = client.get(
        url,
        params={**PARAMS, "decision_as_of": "2099-01-01T00:00:00Z"},
    )
    assert future.status_code == 422
