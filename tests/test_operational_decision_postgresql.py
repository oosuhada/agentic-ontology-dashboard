from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest

from app import dependencies
from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_decision_brief import DecisionBriefRole
from app.infra.db.operational_decision_support_service import (
    PersistedOperationalDecisionSupportService as OperationalDecisionSupportService,
)
from app.operations.operational_decision_support_port import (
    DECISION_SUPPORT_RUNNING_LEASE_SECONDS,
    DecisionSupportMaterializationInProgress,
)
from test_predictive_maintenance_postgresql import postgresql_database


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = OperationalRequestIdentity(
    organization_id="org-ontology-demo",
    project_id="manufacturing-demo-project",
    workspace_id="manufacturing-demo",
    asset_id="CNC-S04-L02-03",
    evidence_snapshot_id="ARTIFACT-GS-004",
    decision_as_of=datetime.fromisoformat("2026-08-01T00:00:00+09:00"),
)
ROLE = DecisionBriefRole.PROCESS_MANAGER


def _running_record(
    service: OperationalDecisionSupportService,
    *,
    run_id: str,
    started_at: datetime,
) -> tuple[str, dict[str, object]]:
    key = service._cache_key(identity=IDENTITY, actor_role=ROLE)
    timestamp = started_at.isoformat()
    return key, {
        "workflow_run_id": run_id,
        "asset_id": IDENTITY.asset_id,
        "organization_id": IDENTITY.organization_id,
        "project_id": IDENTITY.project_id,
        "workspace_id": IDENTITY.workspace_id,
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


def test_dependency_wires_postgresql_decision_support(
    postgresql_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependencies.get_operational_decision_support_service.cache_clear()
    monkeypatch.setattr(
        dependencies,
        "database_target",
        lambda: postgresql_database,
    )
    try:
        service = dependencies.get_operational_decision_support_service()
        assert service.database_url == postgresql_database
        assert service.database_path is None
    finally:
        dependencies.get_operational_decision_support_service.cache_clear()


def test_postgresql_persists_and_reuses_decision_brief(
    postgresql_database: str,
) -> None:
    service = OperationalDecisionSupportService(
        ROOT,
        database_url=postgresql_database,
    )

    brief, trace = service.materialize(
        identity=IDENTITY,
        actor_role=ROLE,
        risk_status="critical",
        trigger="manual_materialization",
    )
    restarted = OperationalDecisionSupportService(
        ROOT,
        database_url=postgresql_database,
    )
    cached, cached_trace = restarted.cached_brief(
        identity=IDENTITY,
        actor_role=ROLE,
    )
    runs = restarted.workflow_runs(
        organization_id=IDENTITY.organization_id,
        project_id=IDENTITY.project_id,
        asset_id=IDENTITY.asset_id,
        status=None,
        limit=10,
    )

    assert trace.status == "completed"
    assert cached == brief
    assert cached_trace.reused is True
    assert [run["status"] for run in runs] == ["completed"]


def test_postgresql_atomic_guard_serializes_same_key(
    postgresql_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = OperationalDecisionSupportService(
        ROOT,
        database_url=postgresql_database,
    )
    second = OperationalDecisionSupportService(
        ROOT,
        database_url=postgresql_database,
    )
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
            actor_role=ROLE,
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
                    actor_role=ROLE,
                    risk_status="critical",
                    trigger="ui_manual_regeneration",
                )
        finally:
            release.set()
        _brief, trace = future.result(timeout=5)

    assert trace.status == "completed"
    runs = second.workflow_runs(
        organization_id=IDENTITY.organization_id,
        project_id=IDENTITY.project_id,
        asset_id=IDENTITY.asset_id,
        status=None,
        limit=10,
    )
    assert [run["status"] for run in runs] == ["completed"]


def test_postgresql_expires_stale_running_lease(
    postgresql_database: str,
) -> None:
    service = OperationalDecisionSupportService(
        ROOT,
        database_url=postgresql_database,
    )
    now = datetime.now(timezone.utc)
    stale_started_at = now - timedelta(
        seconds=DECISION_SUPPORT_RUNNING_LEASE_SECONDS + 1
    )
    key, stale = _running_record(
        service,
        run_id="ODR-postgresql-stale",
        started_at=stale_started_at,
    )
    assert service._reserve_run(key=key, run=stale, now=stale_started_at) is False

    _brief, trace = service.materialize(
        identity=IDENTITY,
        actor_role=ROLE,
        risk_status="critical",
        trigger="ui_manual_regeneration",
        now=now,
    )
    runs = service.workflow_runs(
        organization_id=IDENTITY.organization_id,
        project_id=IDENTITY.project_id,
        asset_id=IDENTITY.asset_id,
        status=None,
        limit=10,
    )

    assert trace.stale_recovered is True
    assert [run["status"] for run in runs] == ["completed", "failed"]
    assert runs[1]["reason"] == "stale_running_lease_expired"


def test_postgresql_tables_have_rls_and_running_unique_index(
    postgresql_database: str,
) -> None:
    import psycopg

    with psycopg.connect(postgresql_database) as connection:
        rls_rows = connection.execute(
            """
            SELECT relname, relrowsecurity
            FROM pg_class
            WHERE relname IN (
                'operational_decision_briefs',
                'operational_decision_workflow_runs'
            )
            ORDER BY relname
            """
        ).fetchall()
        index = connection.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE indexname =
                'uq_operational_decision_workflow_runs_running_key'
            """
        ).fetchone()

    assert rls_rows == [
        ("operational_decision_briefs", True),
        ("operational_decision_workflow_runs", True),
    ]
    assert index is not None
    assert "WHERE (status = 'running'::text)" in index[0]
