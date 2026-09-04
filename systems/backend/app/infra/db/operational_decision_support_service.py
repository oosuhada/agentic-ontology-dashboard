"""Application facade for the bounded read-only operational decision support slice."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.infra.db.postgresql_compat import postgres_repository_connection
from app.infra.db.operational_context_postgresql import (
    PostgreSQLOperationalContextReadPort,
)
from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_decision_support_port import (
    DecisionSupportMaterializationInProgress,
    DecisionSupportTrace,
)
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_decision_agent import (
    BoundedOperationalDecisionAgent,
    OperationalAgentIntent,
    OperationalAgentRequest,
)
from app.operations.operational_decision_brief import (
    DecisionBriefRole,
    OperationalDecisionBrief,
    compose_operational_decision_brief,
)
from app.operations.operational_decision_materialization import (
    OperationalBriefSnapshot,
    materialize_operational_brief,
)
from app.operations.operational_impact_simulation import (
    ImpactOption,
    ImpactSimulationAssumptions,
)


DECISION_SUPPORT_RUNNING_LEASE_SECONDS = 120


@dataclass
class PersistedOperationalDecisionSupportService:
    root: Path
    database_path: Path | None = None
    database_url: str | None = None
    _snapshots: dict[str, OperationalBriefSnapshot] = field(default_factory=dict)
    _runs: list[dict[str, Any]] = field(default_factory=list)
    _active_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        if self.database_url is not None or self.database_path is None:
            return
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS operational_decision_briefs (
                    cache_key TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    stored_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operational_decision_workflow_runs (
                    workflow_run_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    cache_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    reason TEXT,
                    run_json TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS operational_decision_runs_lookup_idx
                ON operational_decision_workflow_runs (
                    project_id, asset_id, status, recorded_at DESC
                );
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(operational_decision_workflow_runs)"
                ).fetchall()
            }
            for name, definition in (
                ("cache_key", "TEXT NOT NULL DEFAULT ''"),
                ("started_at", "TEXT NOT NULL DEFAULT ''"),
                ("completed_at", "TEXT"),
                ("updated_at", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE operational_decision_workflow_runs "
                        f"ADD COLUMN {name} {definition}"
                    )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_operational_decision_workflow_runs_running_key
                ON operational_decision_workflow_runs (cache_key)
                WHERE status = 'running'
                """
            )

    def cached_brief(
        self,
        *,
        identity: OperationalRequestIdentity,
        actor_role: DecisionBriefRole,
    ) -> tuple[OperationalDecisionBrief | None, DecisionSupportTrace]:
        key = self._cache_key(identity=identity, actor_role=actor_role)
        snapshot = self._load_snapshot(key, identity=identity)
        if snapshot is None:
            return None, DecisionSupportTrace(
                status="pending",
                reason="not_materialized",
                reused=False,
                workflow_run_id=None,
                context_version_set={},
                temporal_validation="not_measured",
            )
        return snapshot.brief, DecisionSupportTrace(
            status="completed",
            reason=None,
            reused=True,
            workflow_run_id=None,
            context_version_set=snapshot.context_version_set,
            temporal_validation="passed",
        )

    def materialize(
        self,
        *,
        identity: OperationalRequestIdentity,
        actor_role: DecisionBriefRole,
        risk_status: str,
        trigger: str,
        now: datetime | None = None,
    ) -> tuple[OperationalDecisionBrief, DecisionSupportTrace]:
        now = now or datetime.now(timezone.utc)
        key = self._cache_key(identity=identity, actor_role=actor_role)
        existing = self._load_snapshot(key, identity=identity)
        if existing is not None and trigger == "manual_materialization":
            return existing.brief, DecisionSupportTrace(
                status="completed",
                reason=None,
                reused=True,
                workflow_run_id=None,
                context_version_set=existing.context_version_set,
                temporal_validation="passed",
            )

        request = OperationalAgentRequest(
            identity=identity,
            actor_role=actor_role.value,
            intent=OperationalAgentIntent.MAINTENANCE_TIMING_DECISION,
            risk_status=risk_status,
        )
        run_id = f"ODR-{uuid.uuid4().hex[:16]}"
        run = {
            "workflow_run_id": run_id,
            "asset_id": identity.asset_id,
            "organization_id": identity.organization_id,
            "project_id": identity.project_id,
            "workspace_id": identity.workspace_id,
            "cache_key": key,
            "status": "running",
            "reason": None,
            "context_version_set": {},
            "temporal_validation": "not_measured",
            "stale_recovered": False,
            "trajectory": [],
            "started_at": now.isoformat(),
            "completed_at": None,
            "updated_at": now.isoformat(),
            "recorded_at": now.isoformat(),
        }
        stale_recovered = self._reserve_run(key=key, run=run, now=now)
        try:
            result = self._agent(identity).run(
                request=request,
                retrieved_at=identity.decision_as_of,
                validated_at=identity.decision_as_of,
            )
            brief = compose_operational_decision_brief(request=request, result=result)
            snapshot = materialize_operational_brief(
                request=request,
                result=result,
                brief=brief,
                stored_at=now,
            )
            trajectory = tuple(
                step.model_dump(mode="json") for step in result.trajectory
            )
            trace = DecisionSupportTrace(
                status="completed",
                reason=None,
                reused=False,
                workflow_run_id=run_id,
                context_version_set=result.context_version_set,
                temporal_validation=(
                    "passed"
                    if result.temporal_validation.get("valid") is True
                    else "failed"
                ),
                stale_recovered=stale_recovered,
                trajectory=trajectory,
            )
            run.update(
                status=trace.status,
                reason=trace.reason,
                context_version_set=trace.context_version_set,
                temporal_validation=trace.temporal_validation,
                stale_recovered=stale_recovered,
                trajectory=list(trajectory),
                completed_at=now.isoformat(),
                updated_at=now.isoformat(),
            )
            self._store_snapshot_and_finish_run(key=key, snapshot=snapshot, run=run)
            return brief, trace
        except (ValueError, RuntimeError, TimeoutError) as exc:
            run.update(
                status="failed",
                reason=type(exc).__name__,
                temporal_validation="failed",
                stale_recovered=stale_recovered,
                completed_at=now.isoformat(),
                updated_at=now.isoformat(),
            )
            self._finish_run(run)
            raise

    def workflow_runs(
        self,
        *,
        project_id: str,
        asset_id: str | None,
        status: str | None,
        limit: int,
        organization_id: str = "org-ontology-demo",
    ) -> list[dict[str, Any]]:
        if self.database_url is not None:
            clauses = ["project_id = ?"]
            values: list[Any] = [project_id]
            if asset_id is not None:
                clauses.append("asset_id = ?")
                values.append(asset_id)
            if status is not None:
                clauses.append("status = ?")
                values.append(status)
            values.append(limit)
            with self._postgres_connection(
                organization_id=organization_id,
                project_id=project_id,
            ) as connection:
                rows = connection.execute(
                    f"""
                    SELECT run_json
                    FROM operational_decision_workflow_runs
                    WHERE {' AND '.join(clauses)}
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    values,
                ).fetchall()
            return [json.loads(str(row["run_json"])) for row in rows]
        if self.database_path is not None:
            clauses = ["project_id = ?"]
            values: list[Any] = [project_id]
            if asset_id is not None:
                clauses.append("asset_id = ?")
                values.append(asset_id)
            if status is not None:
                clauses.append("status = ?")
                values.append(status)
            values.append(limit)
            with sqlite3.connect(self.database_path) as connection:
                rows = connection.execute(
                    f"""
                    SELECT run_json
                    FROM operational_decision_workflow_runs
                    WHERE {' AND '.join(clauses)}
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    values,
                ).fetchall()
            return [json.loads(row[0]) for row in rows]
        with self._lock:
            rows = list(reversed(self._runs))
        return [
            row
            for row in rows
            if row["organization_id"] == organization_id
            and row["project_id"] == project_id
            and (asset_id is None or row["asset_id"] == asset_id)
            and (status is None or row["status"] == status)
        ][:limit]

    def _load_snapshot(
        self,
        key: str,
        *,
        identity: OperationalRequestIdentity,
    ) -> OperationalBriefSnapshot | None:
        if self.database_url is not None:
            with self._postgres_connection(
                organization_id=identity.organization_id,
                project_id=identity.project_id,
            ) as connection:
                row = connection.execute(
                    "SELECT snapshot_json FROM operational_decision_briefs WHERE cache_key = ?",
                    (key,),
                ).fetchone()
            return (
                OperationalBriefSnapshot.model_validate_json(row["snapshot_json"])
                if row is not None
                else None
            )
        if self.database_path is None:
            with self._lock:
                return self._snapshots.get(key)
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM operational_decision_briefs WHERE cache_key = ?",
                (key,),
            ).fetchone()
        return (
            OperationalBriefSnapshot.model_validate_json(row[0])
            if row is not None
            else None
        )

    def _reserve_run(
        self,
        *,
        key: str,
        run: dict[str, Any],
        now: datetime,
    ) -> bool:
        cutoff = now - timedelta(seconds=DECISION_SUPPORT_RUNNING_LEASE_SECONDS)
        if self.database_url is not None:
            return self._reserve_postgresql_run(
                key=key,
                run=run,
                now=now,
                cutoff=cutoff,
            )
        if self.database_path is None:
            with self._lock:
                active = self._active_runs.get(key)
                if active is not None:
                    started_at = datetime.fromisoformat(str(active["started_at"]))
                    if started_at > cutoff:
                        raise DecisionSupportMaterializationInProgress(
                            f"decision_support_materialization_in_progress:{key}"
                        )
                    self._expire_run_payload(active, now=now)
                    self._active_runs.pop(key, None)
                    stale_recovered = True
                else:
                    stale_recovered = False
                run["stale_recovered"] = stale_recovered
                self._runs.append(run)
                self._active_runs[key] = run
                return stale_recovered

        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT workflow_run_id, run_json, started_at
                FROM operational_decision_workflow_runs
                WHERE cache_key = ? AND status = 'running'
                LIMIT 1
                """,
                (key,),
            ).fetchone()
            stale_recovered = False
            if row is not None:
                started_at = datetime.fromisoformat(str(row[2]))
                if started_at > cutoff:
                    raise DecisionSupportMaterializationInProgress(
                        f"decision_support_materialization_in_progress:{key}"
                    )
                stale = json.loads(str(row[1]))
                self._expire_run_payload(stale, now=now)
                self._update_run(connection, stale)
                stale_recovered = True
            run["stale_recovered"] = stale_recovered
            self._insert_run(connection, run)
        return stale_recovered

    def _reserve_postgresql_run(
        self,
        *,
        key: str,
        run: dict[str, Any],
        now: datetime,
        cutoff: datetime,
    ) -> bool:
        try:
            with self._postgres_connection(
                organization_id=str(run["organization_id"]),
                project_id=str(run["project_id"]),
            ) as connection:
                row = connection.execute(
                    """
                    SELECT workflow_run_id, run_json, started_at
                    FROM operational_decision_workflow_runs
                    WHERE cache_key = ? AND status = 'running'
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (key,),
                ).fetchone()
                stale_recovered = False
                if row is not None:
                    started_at = datetime.fromisoformat(str(row["started_at"]))
                    if started_at > cutoff:
                        raise DecisionSupportMaterializationInProgress(
                            f"decision_support_materialization_in_progress:{key}"
                        )
                    stale = json.loads(str(row["run_json"]))
                    self._expire_run_payload(stale, now=now)
                    self._update_run(connection, stale)
                    stale_recovered = True
                run["stale_recovered"] = stale_recovered
                self._insert_postgresql_run(connection, run)
            return stale_recovered
        except sqlite3.IntegrityError as exc:
            raise DecisionSupportMaterializationInProgress(
                f"decision_support_materialization_in_progress:{key}"
            ) from exc

    def _store_snapshot_and_finish_run(
        self,
        *,
        key: str,
        snapshot: OperationalBriefSnapshot,
        run: dict[str, Any],
    ) -> None:
        if self.database_url is not None:
            with self._postgres_connection(
                organization_id=str(run["organization_id"]),
                project_id=str(run["project_id"]),
            ) as connection:
                connection.execute(
                    """
                    INSERT INTO operational_decision_briefs (
                        cache_key, organization_id, project_id, workspace_id,
                        asset_id, snapshot_json, stored_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (cache_key) DO UPDATE SET
                        snapshot_json = EXCLUDED.snapshot_json,
                        stored_at = EXCLUDED.stored_at
                    """,
                    (
                        key,
                        run["organization_id"],
                        run["project_id"],
                        run["workspace_id"],
                        run["asset_id"],
                        snapshot.model_dump_json(),
                        snapshot.stored_at,
                    ),
                )
                self._update_run(connection, run)
            return
        if self.database_path is None:
            with self._lock:
                self._snapshots[key] = snapshot
                self._active_runs.pop(key, None)
            return
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO operational_decision_briefs (
                    cache_key, snapshot_json, stored_at
                ) VALUES (?, ?, ?)
                """,
                (key, snapshot.model_dump_json(), snapshot.stored_at.isoformat()),
            )
            self._update_run(connection, run)

    def _finish_run(self, run: dict[str, Any]) -> None:
        if self.database_url is not None:
            with self._postgres_connection(
                organization_id=str(run["organization_id"]),
                project_id=str(run["project_id"]),
            ) as connection:
                self._update_run(connection, run)
            return
        if self.database_path is None:
            with self._lock:
                self._active_runs.pop(str(run["cache_key"]), None)
            return
        with sqlite3.connect(self.database_path) as connection:
            self._update_run(connection, run)

    @staticmethod
    def _expire_run_payload(run: dict[str, Any], *, now: datetime) -> None:
        run.update(
            status="failed",
            reason="stale_running_lease_expired",
            temporal_validation="failed",
            completed_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

    @staticmethod
    def _insert_run(
        connection: sqlite3.Connection,
        run: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO operational_decision_workflow_runs (
                workflow_run_id, project_id, asset_id, cache_key, status, reason,
                run_json, started_at, completed_at, updated_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["workflow_run_id"],
                run["project_id"],
                run["asset_id"],
                run["cache_key"],
                run["status"],
                run["reason"],
                json.dumps(run, ensure_ascii=False, sort_keys=True),
                run["started_at"],
                run["completed_at"],
                run["updated_at"],
                run["recorded_at"],
            ),
        )

    @staticmethod
    def _insert_postgresql_run(connection: Any, run: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO operational_decision_workflow_runs (
                workflow_run_id, organization_id, project_id, workspace_id,
                asset_id, cache_key, status, reason, run_json, started_at,
                completed_at, updated_at, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["workflow_run_id"],
                run["organization_id"],
                run["project_id"],
                run["workspace_id"],
                run["asset_id"],
                run["cache_key"],
                run["status"],
                run["reason"],
                json.dumps(run, ensure_ascii=False, sort_keys=True),
                run["started_at"],
                run["completed_at"],
                run["updated_at"],
                run["recorded_at"],
            ),
        )

    @staticmethod
    def _update_run(
        connection: sqlite3.Connection,
        run: dict[str, Any],
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE operational_decision_workflow_runs
            SET status = ?, reason = ?, run_json = ?, completed_at = ?, updated_at = ?
            WHERE workflow_run_id = ?
            """,
            (
                run["status"],
                run["reason"],
                json.dumps(run, ensure_ascii=False, sort_keys=True),
                run["completed_at"],
                run["updated_at"],
                run["workflow_run_id"],
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("operational_decision_workflow_run_not_found")

    def _postgres_connection(
        self,
        *,
        organization_id: str,
        project_id: str,
    ):
        if self.database_url is None:
            raise RuntimeError("operational_decision_postgresql_not_configured")
        return postgres_repository_connection(
            self.database_url,
            organization_id=organization_id,
            project_id=project_id,
        )

    def _agent(
        self, identity: OperationalRequestIdentity
    ) -> BoundedOperationalDecisionAgent:
        if self.database_url is not None:
            return BoundedOperationalDecisionAgent(
                ports={
                    domain: PostgreSQLOperationalContextReadPort(
                        database_url=self.database_url,
                        owner_domain=domain,
                        freshness_policy_version=f"{domain}-snapshot-freshness-v1",
                        max_age_seconds=172_800,
                    )
                    for domain in (
                        "production",
                        "maintenance_readiness",
                        "quality_delivery",
                    )
                },
                impact_assumptions=ImpactSimulationAssumptions(
                    policy_version="operational-impact-connected-context-v1",
                    primary_capacity_units={},
                    alternative_capacity_allowed={},
                    source_refs=("policy:operational-impact-connected-context-v1",),
                ),
            )

        fixture_root = self.root / "data" / "fixtures" / "operation_context"
        production = _load(fixture_root / "operational-decision-context-evidence-aligned-v1.json")
        maintenance = _load(fixture_root / "maintenance-readiness-context-evidence-aligned-v1.json")
        quality = _load(fixture_root / "quality-delivery-context-evidence-aligned-v1.json")
        for context in (production, maintenance, quality):
            context["scope"]["organization_id"] = identity.organization_id
            context["scope"]["project_id"] = identity.project_id
            context["scope"]["workspace_id"] = identity.workspace_id
        # Fixtures are retained only for SQLite-backed local tests.
        maintenance["inventory_snapshots"][0]["reserved_quantity"] = 0
        maintenance["inventory_snapshots"][0]["available_quantity"] = 2
        for lot in quality["quality_lots"]:
            lot["quality_state"] = "released"
            lot["release_required"] = False
        return BoundedOperationalDecisionAgent(
            ports={
                "production": FixtureProductionDecisionContextReadPort(
                    context=production,
                    source_ref="fixture:operational-decision-context-evidence-aligned-v1",
                ),
                "maintenance_readiness": FixtureMaintenanceReadinessContextReadPort(
                    context=maintenance,
                    source_ref="fixture:maintenance-readiness-context-evidence-aligned-v1",
                ),
                "quality_delivery": FixtureQualityDeliveryContextReadPort(
                    context=quality,
                    source_ref="fixture:quality-delivery-context-evidence-aligned-v1",
                ),
            },
            impact_assumptions=ImpactSimulationAssumptions(
                policy_version="operational-impact-demo-v1",
                primary_capacity_units={
                    ImpactOption.STOP_NOW: 0,
                    ImpactOption.PLANNED_MAINTENANCE: 120,
                    ImpactOption.CONTINUE_OPERATION: 200,
                },
                alternative_capacity_allowed={
                    ImpactOption.STOP_NOW: True,
                    ImpactOption.PLANNED_MAINTENANCE: True,
                    ImpactOption.CONTINUE_OPERATION: False,
                },
                source_refs=("policy:operational-impact-demo-v1",),
            ),
        )

    @staticmethod
    def _cache_key(
        *,
        identity: OperationalRequestIdentity,
        actor_role: DecisionBriefRole,
    ) -> str:
        return "|".join(
            (
                identity.organization_id,
                identity.project_id,
                identity.workspace_id,
                identity.asset_id,
                identity.evidence_snapshot_id,
                identity.decision_as_of.isoformat(),
                actor_role.value,
            )
        )


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
