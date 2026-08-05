"""Tenant-scoped durable execution, Redis coordination and operator evidence."""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .postgresql_compat import postgres_repository_connection
from .postgresql_repositories import is_postgresql
from .security import RateLimitExceeded, RateLimitRule


JobType = Literal[
    "analysis",
    "modeling_experiment",
    "projection",
    "export",
    "automation",
    "connector_ingestion",
]
JobState = Literal[
    "queued",
    "running",
    "retry",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
    "dead_letter",
]
FailureClass = Literal["transient", "permanent", "validation", "cancelled"]
FailMode = Literal["open", "closed"]


class QueueUnavailable(RuntimeError):
    pass


class QueueSaturated(RuntimeError):
    def __init__(self, *, project_id: str, depth: int, limit: int) -> None:
        super().__init__(f"queue saturated for {project_id}: {depth}/{limit}")
        self.project_id = project_id
        self.depth = depth
        self.limit = limit


class LeaseLost(RuntimeError):
    pass


class DurableJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    organization_id: str
    project_id: str
    workspace_id: str | None = None
    job_type: JobType
    idempotency_key: str
    payload: dict[str, Any]
    state: JobState
    priority: int
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    worker_version: str | None = None
    runtime_checksum: str | None = None
    cancellation_reason: str | None = None
    failure_class: FailureClass | None = None
    last_error: str | None = None
    result: dict[str, Any] | None = None
    created_by: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class DurableJobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: int
    organization_id: str
    project_id: str
    workspace_id: str | None = None
    job_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class QueueMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    queued: int = 0
    running: int = 0
    retry: int = 0
    succeeded: int = 0
    failed: int = 0
    cancel_requested: int = 0
    cancelled: int = 0
    dead_letter: int = 0
    stale_leases: int = 0
    oldest_queued_seconds: float = 0


class DistributedRuntimeReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "degraded", "blocked"]
    queue_backend: Literal["postgresql", "sqlite"]
    queue_delivery: str
    redis_state: Literal["ready", "not_configured", "unavailable"]
    redis_url_configured: bool
    redis_tls: bool
    rate_limit_policies: dict[str, dict[str, Any]]
    worker_types: tuple[str, ...]
    retry: dict[str, Any]
    event_transport: dict[str, Any]
    quotas: dict[str, int]
    metrics: QueueMetrics
    blockers: tuple[str, ...]


class DistributedRuntimeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    readiness: DistributedRuntimeReadiness
    jobs: tuple[DurableJob, ...]
    dead_letters: tuple[DurableJob, ...]


class DurableJobEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[DurableJobEvent, ...]
    next_cursor: int


class JobOperatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=1000)


RATE_LIMIT_POLICIES: dict[str, tuple[RateLimitRule, FailMode, tuple[str, ...]]] = {
    "login": (RateLimitRule(12, 60), "closed", ("ip", "email")),
    "session": (RateLimitRule(20, 60), "closed", ("user", "ip")),
    "export": (RateLimitRule(20, 60), "closed", ("tenant", "user")),
    "planner": (RateLimitRule(30, 60), "open", ("tenant", "user")),
    "action": (RateLimitRule(30, 60), "closed", ("tenant", "user")),
    "agent": (RateLimitRule(20, 60), "closed", ("tenant", "user")),
}


class AtomicWindowStore(Protocol):
    def increment(self, key: str, window_ms: int) -> tuple[int, int]: ...


class InMemoryAtomicWindowStore:
    """Shared deterministic Redis emulator used for multi-instance tests."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._values: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self.available = True

    def increment(self, key: str, window_ms: int) -> tuple[int, int]:
        if not self.available:
            raise QueueUnavailable("Redis coordinator unavailable")
        now = self.clock()
        with self._lock:
            value, expires = self._values.get(key, (0, now + window_ms / 1000))
            if expires <= now:
                value, expires = 0, now + window_ms / 1000
            value += 1
            self._values[key] = (value, expires)
            return value, max(0, int((expires - now) * 1000))


class RedisAtomicWindowStore:
    _SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
    return {current, redis.call('PTTL', KEYS[1])}
    """

    def __init__(self, redis_url: str, *, connect_timeout: float = 2.0) -> None:
        try:
            import redis
        except ImportError as error:
            raise QueueUnavailable("redis dependency is not installed") from error
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=connect_timeout,
            socket_timeout=connect_timeout,
            retry_on_timeout=True,
            health_check_interval=30,
            max_connections=max(4, int(os.getenv("ONTOLOGY_DASHBOARD_REDIS_POOL_MAX", "20"))),
        )
        self.script = self.client.register_script(self._SCRIPT)

    def increment(self, key: str, window_ms: int) -> tuple[int, int]:
        try:
            current, ttl = self.script(keys=[key], args=[window_ms])
            return int(current), int(ttl)
        except Exception as error:
            raise QueueUnavailable(f"Redis rate limiter unavailable: {type(error).__name__}") from error

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False


class DistributedRateLimiter:
    def __init__(self, store: AtomicWindowStore, *, namespace: str) -> None:
        self.store = store
        self.namespace = namespace.rstrip(":")

    def check(self, *, policy: str, subject: str) -> bool:
        rule, fail_mode, _ = RATE_LIMIT_POLICIES[policy]
        key = f"{self.namespace}:{policy}:{hashlib.sha256(subject.encode()).hexdigest()}"
        try:
            current, ttl_ms = self.store.increment(key, rule.window_seconds * 1000)
        except QueueUnavailable:
            if fail_mode == "open":
                return False
            raise
        if current > rule.limit:
            raise RateLimitExceeded(
                bucket=policy,
                retry_after=max(1, (max(0, ttl_ms) + 999) // 1000),
            )
        return True


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class DurableJobRepository:
    def __init__(self, database: str | Path, *, max_queued_per_project: int = 5000) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)
        self.max_queued_per_project = max(1, max_queued_per_project)

    @staticmethod
    def _decode(row: Mapping[str, Any] | None) -> DurableJob | None:
        if row is None:
            return None
        payload = row["payload_json"]
        result = row.get("result_json")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(result, str):
            result = json.loads(result)
        return DurableJob(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            project_id=str(row["project_id"]),
            workspace_id=None if row.get("workspace_id") is None else str(row["workspace_id"]),
            job_type=str(row["job_type"]),
            idempotency_key=str(row["idempotency_key"]),
            payload=dict(payload),
            state=str(row["state"]),
            priority=int(row["priority"]),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            available_at=_parse_datetime(row["available_at"]),
            lease_owner=row.get("lease_owner"),
            lease_token=row.get("lease_token"),
            lease_expires_at=_parse_datetime(row.get("lease_expires_at")),
            heartbeat_at=_parse_datetime(row.get("heartbeat_at")),
            worker_version=row.get("worker_version"),
            runtime_checksum=row.get("runtime_checksum"),
            cancellation_reason=row.get("cancellation_reason"),
            failure_class=row.get("failure_class"),
            last_error=row.get("last_error"),
            result=None if result is None else dict(result),
            created_by=str(row["created_by"]),
            created_at=_parse_datetime(row["created_at"]),
            started_at=_parse_datetime(row.get("started_at")),
            completed_at=_parse_datetime(row.get("completed_at")),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    @staticmethod
    def _append_event(
        connection,
        *,
        postgresql: bool,
        job: Mapping[str, Any],
        event_type: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        values = (
            str(job["organization_id"]),
            str(job["project_id"]),
            job.get("workspace_id"),
            str(job["id"]),
            event_type,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            now.isoformat(),
        )
        connection.execute(
            """
            INSERT INTO durable_job_events(
                organization_id,project_id,workspace_id,job_id,event_type,payload_json,created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            values,
        )

    def _connect_sqlite(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def project_scopes(self) -> tuple[tuple[str, str], ...]:
        if self.postgresql:
            from .postgresql_pool import pooled_identity_connection

            with pooled_identity_connection(self.database) as connection:
                rows = connection.execute(
                    "SELECT organization_id,id FROM projects WHERE status<>'archived' ORDER BY organization_id,id"
                ).fetchall()
            return tuple((str(row["organization_id"]), str(row["id"])) for row in rows)
        with self._connect_sqlite() as connection:
            rows = connection.execute(
                "SELECT organization_id,id FROM projects WHERE status<>'archived' ORDER BY organization_id,id"
            ).fetchall()
        return tuple((str(row["organization_id"]), str(row["id"])) for row in rows)

    def record_worker_heartbeat(
        self,
        *,
        worker_id: str,
        worker_type: str,
        worker_version: str,
        runtime_checksum: str,
        state: Literal["starting", "ready", "draining", "stopped", "error"],
        queue_names: tuple[str, ...],
        current_job_id: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        now = _utcnow().isoformat()
        values = (
            worker_id,
            organization_id,
            project_id,
            worker_type,
            worker_version,
            runtime_checksum,
            state,
            current_job_id,
            json.dumps(queue_names),
            json.dumps(metrics or {}, ensure_ascii=False, sort_keys=True),
            now,
            now,
        )
        if self.postgresql:
            from .postgresql_pool import pooled_identity_connection

            with pooled_identity_connection(self.database) as connection:
                connection.execute(
                    "SELECT set_config('app.identity_access','1',true)"
                )
                connection.execute(
                    """
                    INSERT INTO worker_heartbeats(
                        worker_id,organization_id,project_id,worker_type,worker_version,
                        runtime_checksum,state,current_job_id,queue_names_json,metrics_json,
                        heartbeat_at,started_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(worker_id) DO UPDATE SET
                        organization_id=excluded.organization_id,
                        project_id=excluded.project_id,
                        worker_type=excluded.worker_type,
                        worker_version=excluded.worker_version,
                        runtime_checksum=excluded.runtime_checksum,
                        state=excluded.state,
                        current_job_id=excluded.current_job_id,
                        queue_names_json=excluded.queue_names_json,
                        metrics_json=excluded.metrics_json,
                        heartbeat_at=excluded.heartbeat_at
                    """,
                    values,
                )
            return
        with self._connect_sqlite() as connection:
            connection.execute(
                """
                INSERT INTO worker_heartbeats(
                    worker_id,organization_id,project_id,worker_type,worker_version,
                    runtime_checksum,state,current_job_id,queue_names_json,metrics_json,
                    heartbeat_at,started_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(worker_id) DO UPDATE SET
                    organization_id=excluded.organization_id,
                    project_id=excluded.project_id,
                    worker_type=excluded.worker_type,
                    worker_version=excluded.worker_version,
                    runtime_checksum=excluded.runtime_checksum,
                    state=excluded.state,
                    current_job_id=excluded.current_job_id,
                    queue_names_json=excluded.queue_names_json,
                    metrics_json=excluded.metrics_json,
                    heartbeat_at=excluded.heartbeat_at
                """,
                values,
            )

    def worker_status(self, *, stale_after_seconds: int = 90) -> tuple[dict[str, Any], ...]:
        cutoff = (_utcnow() - timedelta(seconds=max(5, stale_after_seconds))).isoformat()
        if self.postgresql:
            from .postgresql_pool import pooled_identity_connection

            with pooled_identity_connection(self.database) as connection:
                connection.execute("SELECT set_config('app.identity_access','1',true)")
                rows = connection.execute(
                    "SELECT * FROM worker_heartbeats ORDER BY worker_type,worker_id"
                ).fetchall()
        else:
            with self._connect_sqlite() as connection:
                rows = connection.execute(
                    "SELECT * FROM worker_heartbeats ORDER BY worker_type,worker_id"
                ).fetchall()
        result = []
        for raw in rows:
            row = dict(raw)
            row["queue_names"] = json.loads(row.pop("queue_names_json"))
            row["metrics"] = json.loads(row.pop("metrics_json"))
            row["stale"] = str(row["heartbeat_at"]) < cutoff
            result.append(row)
        return tuple(result)

    def enqueue(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None,
        job_type: JobType,
        idempotency_key: str,
        payload: dict[str, Any],
        created_by: str,
        priority: int = 100,
        max_attempts: int = 5,
    ) -> tuple[DurableJob, bool]:
        now = _utcnow()
        job_id = f"job-{uuid.uuid4()}"
        values = (
            job_id,
            organization_id,
            project_id,
            workspace_id,
            job_type,
            idempotency_key,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            max(0, min(1000, priority)),
            max(1, min(20, max_attempts)),
            now.isoformat(),
            created_by,
            now.isoformat(),
            now.isoformat(),
        )
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            ) as connection:
                existing = connection.execute(
                    """
                    SELECT * FROM durable_jobs
                    WHERE organization_id=? AND project_id=? AND job_type=? AND idempotency_key=?
                    """,
                    (organization_id, project_id, job_type, idempotency_key),
                ).fetchone()
                if existing:
                    return self._decode(existing), False
                depth = connection.execute(
                    """
                    SELECT count(*) AS count FROM durable_jobs
                    WHERE organization_id=? AND project_id=? AND state IN ('queued','retry','running','cancel_requested')
                    """,
                    (organization_id, project_id),
                ).fetchone()["count"]
                if int(depth) >= self.max_queued_per_project:
                    raise QueueSaturated(project_id=project_id, depth=int(depth), limit=self.max_queued_per_project)
                row = connection.execute(
                    """
                    INSERT INTO durable_jobs(
                        id,organization_id,project_id,workspace_id,job_type,idempotency_key,
                        payload_json,priority,max_attempts,available_at,created_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *
                    """,
                    values,
                ).fetchone()
                self._append_event(connection, postgresql=True, job=row, event_type="job.queued", payload={}, now=now)
                return self._decode(row), True
        with self._connect_sqlite() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT * FROM durable_jobs
                WHERE organization_id=? AND project_id=? AND job_type=? AND idempotency_key=?
                """,
                (organization_id, project_id, job_type, idempotency_key),
            ).fetchone()
            if existing:
                return self._decode(dict(existing)), False
            depth = int(connection.execute(
                """
                SELECT count(*) FROM durable_jobs
                WHERE organization_id=? AND project_id=? AND state IN ('queued','retry','running','cancel_requested')
                """,
                (organization_id, project_id),
            ).fetchone()[0])
            if depth >= self.max_queued_per_project:
                raise QueueSaturated(project_id=project_id, depth=depth, limit=self.max_queued_per_project)
            connection.execute(
                """
                INSERT INTO durable_jobs(
                    id,organization_id,project_id,workspace_id,job_type,idempotency_key,
                    payload_json,priority,max_attempts,available_at,created_by,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            row = dict(connection.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone())
            self._append_event(connection, postgresql=False, job=row, event_type="job.queued", payload={}, now=now)
            return self._decode(row), True

    def _recover_stale(self, connection, *, organization_id: str, project_id: str, now: datetime) -> None:
        stale = connection.execute(
            """
            SELECT * FROM durable_jobs
            WHERE organization_id=? AND project_id=?
              AND state IN ('running','cancel_requested')
              AND lease_expires_at IS NOT NULL AND lease_expires_at<=?
            """,
            (organization_id, project_id, now.isoformat()),
        ).fetchall()
        for raw in stale:
            row = dict(raw)
            cancelled = row["state"] == "cancel_requested"
            exhausted = int(row["attempt_count"]) >= int(row["max_attempts"])
            state = "cancelled" if cancelled else "dead_letter" if exhausted else "retry"
            connection.execute(
                """
                UPDATE durable_jobs
                SET state=?,available_at=?,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
                    heartbeat_at=NULL,last_error=?,completed_at=?,updated_at=?
                WHERE id=?
                """,
                (
                    state,
                    now.isoformat(),
                    "worker lease expired",
                    now.isoformat() if state in {"cancelled", "dead_letter"} else None,
                    now.isoformat(),
                    row["id"],
                ),
            )
            self._append_event(
                connection,
                postgresql=self.postgresql,
                job=row,
                event_type=f"job.{state}",
                payload={"reason": "lease_expired"},
                now=now,
            )

    def claim(
        self,
        *,
        organization_id: str,
        project_id: str,
        worker_id: str,
        worker_version: str,
        runtime_checksum: str,
        job_types: tuple[JobType, ...],
        lease_seconds: int = 60,
    ) -> DurableJob | None:
        now = _utcnow()
        token = secrets_token()
        placeholders = ",".join("?" for _ in job_types)
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            ) as connection:
                self._recover_stale(connection, organization_id=organization_id, project_id=project_id, now=now)
                row = connection.execute(
                    f"""
                    SELECT * FROM durable_jobs
                    WHERE organization_id=? AND project_id=?
                      AND state IN ('queued','retry') AND available_at<=now()
                      AND job_type IN ({placeholders})
                    ORDER BY priority,created_at,id
                    FOR UPDATE SKIP LOCKED LIMIT 1
                    """,
                    (organization_id, project_id, *job_types),
                ).fetchone()
                if row is None:
                    return None
                claimed = connection.execute(
                    """
                    UPDATE durable_jobs SET
                        state='running',attempt_count=attempt_count+1,lease_owner=?,lease_token=?,
                        lease_expires_at=?,heartbeat_at=?,worker_version=?,runtime_checksum=?,
                        started_at=coalesce(started_at,?),updated_at=?
                    WHERE id=? RETURNING *
                    """,
                    (
                        worker_id,
                        token,
                        (now + timedelta(seconds=max(5, lease_seconds))).isoformat(),
                        now.isoformat(),
                        worker_version,
                        runtime_checksum,
                        now.isoformat(),
                        now.isoformat(),
                        row["id"],
                    ),
                ).fetchone()
                self._append_event(connection, postgresql=True, job=claimed, event_type="job.claimed", payload={"worker_id": worker_id}, now=now)
                return self._decode(claimed)
        with self._connect_sqlite() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._recover_stale(connection, organization_id=organization_id, project_id=project_id, now=now)
            row = connection.execute(
                f"""
                SELECT * FROM durable_jobs
                WHERE organization_id=? AND project_id=?
                  AND state IN ('queued','retry') AND available_at<=?
                  AND job_type IN ({placeholders})
                ORDER BY priority,created_at,id LIMIT 1
                """,
                (organization_id, project_id, now.isoformat(), *job_types),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE durable_jobs SET
                    state='running',attempt_count=attempt_count+1,lease_owner=?,lease_token=?,
                    lease_expires_at=?,heartbeat_at=?,worker_version=?,runtime_checksum=?,
                    started_at=coalesce(started_at,?),updated_at=?
                WHERE id=? AND state IN ('queued','retry')
                """,
                (
                    worker_id,
                    token,
                    (now + timedelta(seconds=max(5, lease_seconds))).isoformat(),
                    now.isoformat(),
                    worker_version,
                    runtime_checksum,
                    now.isoformat(),
                    now.isoformat(),
                    row["id"],
                ),
            )
            claimed = dict(connection.execute("SELECT * FROM durable_jobs WHERE id=?", (row["id"],)).fetchone())
            self._append_event(connection, postgresql=False, job=claimed, event_type="job.claimed", payload={"worker_id": worker_id}, now=now)
            return self._decode(claimed)

    def heartbeat(self, job: DurableJob, *, lease_seconds: int = 60) -> DurableJob:
        if not job.lease_token:
            raise LeaseLost("job has no active lease")
        now = _utcnow()
        values = (
            (now + timedelta(seconds=max(5, lease_seconds))).isoformat(),
            now.isoformat(),
            now.isoformat(),
            job.id,
            job.project_id,
            job.lease_token,
        )
        query = """
            UPDATE durable_jobs SET lease_expires_at=?,heartbeat_at=?,updated_at=?
            WHERE id=? AND project_id=? AND lease_token=? AND state IN ('running','cancel_requested')
        """
        with self._connection(job.organization_id, job.project_id) as connection:
            cursor = connection.execute(query, values)
            if cursor.rowcount != 1:
                raise LeaseLost(job.id)
            row = connection.execute("SELECT * FROM durable_jobs WHERE id=?", (job.id,)).fetchone()
            return self._decode(dict(row))

    def complete(self, job: DurableJob, *, result: dict[str, Any]) -> DurableJob:
        return self._terminal_update(job, state="succeeded", result=result)

    def cancel(self, *, organization_id: str, project_id: str, job_id: str, reason: str) -> DurableJob:
        now = _utcnow()
        with self._connection(organization_id, project_id, immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM durable_jobs WHERE id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            current = dict(row)
            if current["state"] in {"succeeded", "failed", "cancelled", "dead_letter"}:
                return self._decode(current)
            state = "cancelled" if current["state"] in {"queued", "retry"} else "cancel_requested"
            connection.execute(
                """
                UPDATE durable_jobs SET state=?,cancellation_reason=?,completed_at=?,updated_at=?
                WHERE id=? AND project_id=?
                """,
                (
                    state,
                    reason[:1000],
                    now.isoformat() if state == "cancelled" else None,
                    now.isoformat(),
                    job_id,
                    project_id,
                ),
            )
            updated = dict(connection.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone())
            self._append_event(connection, postgresql=self.postgresql, job=updated, event_type=f"job.{state}", payload={"reason": reason[:1000]}, now=now)
            return self._decode(updated)

    def fail(
        self,
        job: DurableJob,
        *,
        failure_class: FailureClass,
        error: str,
        base_delay_seconds: int = 5,
    ) -> DurableJob:
        if failure_class == "cancelled":
            return self._terminal_update(job, state="cancelled", error=error, failure_class=failure_class)
        retryable = failure_class == "transient" and job.attempt_count < job.max_attempts
        if retryable:
            digest = int(hashlib.sha256(job.id.encode()).hexdigest()[:8], 16)
            jitter = random.Random(digest + job.attempt_count).uniform(0.8, 1.2)
            delay = min(3600, max(1, int(base_delay_seconds * (2 ** max(0, job.attempt_count - 1)) * jitter)))
            now = _utcnow()
            with self._connection(job.organization_id, job.project_id, immediate=True) as connection:
                cursor = connection.execute(
                    """
                    UPDATE durable_jobs SET state='retry',failure_class=?,last_error=?,available_at=?,
                        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,updated_at=?
                    WHERE id=? AND project_id=? AND lease_token=?
                    """,
                    (
                        failure_class,
                        error[:4000],
                        (now + timedelta(seconds=delay)).isoformat(),
                        now.isoformat(),
                        job.id,
                        job.project_id,
                        job.lease_token,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LeaseLost(job.id)
                row = dict(connection.execute("SELECT * FROM durable_jobs WHERE id=?", (job.id,)).fetchone())
                self._append_event(connection, postgresql=self.postgresql, job=row, event_type="job.retry", payload={"delay_seconds": delay, "failure_class": failure_class}, now=now)
                return self._decode(row)
        state: JobState = "dead_letter" if failure_class in {"transient", "permanent"} else "failed"
        return self._terminal_update(job, state=state, error=error, failure_class=failure_class)

    def replay(self, *, organization_id: str, project_id: str, job_id: str, actor_user_id: str) -> DurableJob:
        now = _utcnow()
        with self._connection(organization_id, project_id, immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM durable_jobs WHERE id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            current = dict(row)
            if current["state"] != "dead_letter":
                raise ValueError("only dead-letter jobs can be replayed")
            connection.execute(
                """
                UPDATE durable_jobs SET state='queued',attempt_count=0,available_at=?,failure_class=NULL,
                    last_error=NULL,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
                    heartbeat_at=NULL,completed_at=NULL,updated_at=? WHERE id=?
                """,
                (now.isoformat(), now.isoformat(), job_id),
            )
            updated = dict(connection.execute("SELECT * FROM durable_jobs WHERE id=?", (job_id,)).fetchone())
            self._append_event(connection, postgresql=self.postgresql, job=updated, event_type="job.replayed", payload={"actor_user_id": actor_user_id}, now=now)
            return self._decode(updated)

    def _terminal_update(
        self,
        job: DurableJob,
        *,
        state: Literal["succeeded", "failed", "cancelled", "dead_letter"],
        result: dict[str, Any] | None = None,
        error: str | None = None,
        failure_class: FailureClass | None = None,
    ) -> DurableJob:
        now = _utcnow()
        with self._connection(job.organization_id, job.project_id, immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE durable_jobs SET state=?,result_json=?,failure_class=?,last_error=?,completed_at=?,
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,updated_at=?
                WHERE id=? AND project_id=? AND lease_token=?
                """,
                (
                    state,
                    None if result is None else json.dumps(result, ensure_ascii=False, sort_keys=True),
                    failure_class,
                    None if error is None else error[:4000],
                    now.isoformat(),
                    now.isoformat(),
                    job.id,
                    job.project_id,
                    job.lease_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseLost(job.id)
            row = dict(connection.execute("SELECT * FROM durable_jobs WHERE id=?", (job.id,)).fetchone())
            self._append_event(connection, postgresql=self.postgresql, job=row, event_type=f"job.{state}", payload={}, now=now)
            return self._decode(row)

    def _connection(self, organization_id: str, project_id: str, *, immediate: bool = False):
        if self.postgresql:
            return postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            )
        repository = self

        class SQLiteContext:
            def __enter__(self):
                self.connection = repository._connect_sqlite()
                if immediate:
                    self.connection.execute("BEGIN IMMEDIATE")
                return self.connection

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
                self.connection.close()

        return SQLiteContext()

    def metrics(self, *, organization_id: str, project_id: str) -> QueueMetrics:
        now = _utcnow()
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT state,count(*) AS count,min(created_at) AS oldest
                FROM durable_jobs WHERE organization_id=? AND project_id=? GROUP BY state
                """,
                (organization_id, project_id),
            ).fetchall()
            stale = connection.execute(
                """
                SELECT count(*) AS count FROM durable_jobs
                WHERE organization_id=? AND project_id=? AND state IN ('running','cancel_requested')
                  AND lease_expires_at IS NOT NULL AND lease_expires_at<=?
                """,
                (organization_id, project_id, now.isoformat()),
            ).fetchone()
        counts = {str(row["state"]): int(row["count"]) for row in rows}
        oldest = min(
            (_parse_datetime(row["oldest"]) for row in rows if row["state"] in {"queued", "retry"}),
            default=None,
        )
        return QueueMetrics(
            **counts,
            stale_leases=int(stale["count"]),
            oldest_queued_seconds=0 if oldest is None else max(0, (now - oldest).total_seconds()),
        )

    def list_jobs(
        self,
        *,
        organization_id: str,
        project_id: str,
        states: tuple[JobState, ...] = (),
        limit: int = 50,
    ) -> tuple[DurableJob, ...]:
        params: list[Any] = [organization_id, project_id]
        state_sql = ""
        if states:
            state_sql = f" AND state IN ({','.join('?' for _ in states)})"
            params.extend(states)
        params.append(max(1, min(200, limit)))
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM durable_jobs WHERE organization_id=? AND project_id=?{state_sql}
                ORDER BY created_at DESC,id DESC LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return tuple(self._decode(dict(row)) for row in rows)

    def events_after(
        self,
        *,
        organization_id: str,
        project_id: str,
        cursor: int = 0,
        limit: int = 100,
    ) -> tuple[DurableJobEvent, ...]:
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                """
                SELECT * FROM durable_job_events
                WHERE organization_id=? AND project_id=? AND cursor>?
                ORDER BY cursor LIMIT ?
                """,
                (organization_id, project_id, max(0, cursor), max(1, min(500, limit))),
            ).fetchall()
        events = []
        for raw in rows:
            row = dict(raw)
            payload = row["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            events.append(DurableJobEvent(
                cursor=int(row["cursor"]),
                organization_id=str(row["organization_id"]),
                project_id=str(row["project_id"]),
                workspace_id=row.get("workspace_id"),
                job_id=str(row["job_id"]),
                event_type=str(row["event_type"]),
                payload=dict(payload),
                created_at=_parse_datetime(row["created_at"]),
            ))
        return tuple(events)


def secrets_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


class DurableWorker:
    def __init__(
        self,
        repository: DurableJobRepository,
        *,
        worker_id: str,
        worker_version: str,
        runtime_checksum: str,
        job_types: tuple[JobType, ...],
        handlers: Mapping[JobType, Callable[[DurableJob], dict[str, Any]]],
        lease_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self.worker_id = worker_id
        self.worker_version = worker_version
        self.runtime_checksum = runtime_checksum
        self.job_types = job_types
        self.handlers = dict(handlers)
        self.lease_seconds = max(5, lease_seconds)

    def process_once(self, *, organization_id: str, project_id: str) -> DurableJob | None:
        job = self.repository.claim(
            organization_id=organization_id,
            project_id=project_id,
            worker_id=self.worker_id,
            worker_version=self.worker_version,
            runtime_checksum=self.runtime_checksum,
            job_types=self.job_types,
            lease_seconds=self.lease_seconds,
        )
        if job is None:
            return None
        handler = self.handlers.get(job.job_type)
        if handler is None:
            return self.repository.fail(
                job,
                failure_class="permanent",
                error=f"no handler for {job.job_type}",
            )
        try:
            result = handler(job)
            return self.repository.complete(job, result=result)
        except Exception as error:
            failure_class: FailureClass = getattr(error, "failure_class", "transient")
            return self.repository.fail(
                job,
                failure_class=failure_class,
                error=f"{type(error).__name__}: {error}",
            )


def distributed_runtime_readiness(
    database: str | Path,
    *,
    organization_id: str,
    project_id: str,
) -> DistributedRuntimeReadiness:
    redis_url = os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip()
    redis_state: Literal["ready", "not_configured", "unavailable"] = "not_configured"
    blockers: list[str] = []
    if redis_url:
        try:
            redis_state = "ready" if RedisAtomicWindowStore(redis_url).ping() else "unavailable"
        except QueueUnavailable:
            redis_state = "unavailable"
    if redis_state != "ready":
        blockers.append("Managed Redis coordination is not available; local queue remains operational but multi-instance coordination is blocked.")
    repository = DurableJobRepository(database)
    metrics = repository.metrics(organization_id=organization_id, project_id=project_id)
    production = os.getenv("APP_ENV", "development").lower() == "production"
    tls_required = os.getenv("ONTOLOGY_DASHBOARD_REDIS_TLS_REQUIRED", "1").strip().lower() not in {"0", "false", "no"}
    if production and redis_url and tls_required and not redis_url.startswith("rediss://"):
        blockers.append("Production Redis transport must use rediss:// when TLS is required.")
        redis_state = "unavailable"
    state = "blocked" if production and redis_state != "ready" else "degraded" if redis_state != "ready" else "ready"
    return DistributedRuntimeReadiness(
        state=state,
        queue_backend="postgresql" if repository.postgresql else "sqlite",
        queue_delivery="at-least-once claim; idempotent handler and delivery log required",
        redis_state=redis_state,
        redis_url_configured=bool(redis_url),
        redis_tls=redis_url.startswith("rediss://"),
        rate_limit_policies={
            name: {
                "limit": rule.limit,
                "window_seconds": rule.window_seconds,
                "fail_mode": fail_mode,
                "key_dimensions": dimensions,
            }
            for name, (rule, fail_mode, dimensions) in RATE_LIMIT_POLICIES.items()
        },
        worker_types=(
            "analysis",
            "modeling_experiment",
            "projection",
            "export",
            "automation",
            "connector_ingestion",
        ),
        retry={
            "classes": ["transient", "permanent", "validation", "cancelled"],
            "strategy": "exponential backoff with deterministic jitter",
            "max_attempts": 20,
            "dead_letter_replay": "admin permission + immutable job event",
        },
        event_transport={
            "durable_cursor": True,
            "reconnect": "cursor greater-than query",
            "fanout": "Redis pub/sub when configured; database cursor is source of truth",
            "permission_channel": "organization + project + optional workspace",
        },
        quotas={
            "max_queued_per_project": repository.max_queued_per_project,
            "max_job_attempts": 20,
            "event_page_limit": 500,
        },
        metrics=metrics,
        blockers=tuple(blockers),
    )


__all__ = [
    "DistributedRateLimiter",
    "DistributedRuntimeReadiness",
    "DurableJob",
    "DurableJobEvent",
    "DurableJobRepository",
    "DurableWorker",
    "FailureClass",
    "InMemoryAtomicWindowStore",
    "JobState",
    "JobType",
    "LeaseLost",
    "QueueSaturated",
    "QueueUnavailable",
    "RATE_LIMIT_POLICIES",
    "RedisAtomicWindowStore",
    "distributed_runtime_readiness",
]
