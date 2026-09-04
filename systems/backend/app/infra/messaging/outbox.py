"""Project-scoped transactional outbox delivery runtime.

The repository claims only the event types registered by this worker. This is
important while multiple bounded contexts share ``transactional_outbox``: a
Maintenance worker must never dead-letter an event owned by another consumer.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.infra.db.postgresql_compat import postgres_repository_connection
from app.infra.db.postgresql_repositories import is_postgresql


class OutboxLeaseLost(RuntimeError):
    """Raised when a worker no longer owns the message it is completing."""


@dataclass(frozen=True)
class OutboxMessage:
    id: str
    organization_id: str
    project_id: str
    workspace_id: str | None
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    attempt_count: int
    lease_token: str


OutboxHandler = Callable[[OutboxMessage], None]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ProjectOutboxRepository:
    """Claim and settle outbox rows inside one Organization/Project scope."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    @staticmethod
    def _event_clause(event_types: Sequence[str]) -> tuple[str, tuple[str, ...]]:
        normalized = tuple(dict.fromkeys(str(value) for value in event_types if value))
        if not normalized:
            raise ValueError("at least one outbox event type is required")
        return ",".join("?" for _ in normalized), normalized

    @staticmethod
    def _message(row: Mapping[str, Any], *, lease_token: str) -> OutboxMessage:
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("outbox payload must be a JSON object")
        return OutboxMessage(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            project_id=str(row["project_id"]),
            workspace_id=(
                None if row.get("workspace_id") is None else str(row["workspace_id"])
            ),
            aggregate_type=str(row["aggregate_type"]),
            aggregate_id=str(row["aggregate_id"]),
            event_type=str(row["event_type"]),
            payload=payload,
            attempt_count=int(row["attempt_count"]) + 1,
            lease_token=lease_token,
        )

    @staticmethod
    def _claimable(row: Mapping[str, Any], *, now: datetime, max_attempts: int) -> bool:
        return (
            str(row["status"]) in {"pending", "retry"}
            and int(row["attempt_count"]) < max_attempts
            and _timestamp(row["available_at"]) <= now
        )

    @staticmethod
    def _delivery_stream(row: Mapping[str, Any]) -> tuple[str, str]:
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(payload, dict):
            simulation_session_id = str(payload.get("simulation_session_id") or "")
            equipment_id = str(payload.get("equipment_id") or "")
            if simulation_session_id and equipment_id:
                return simulation_session_id, equipment_id
        return str(row["aggregate_type"]), str(row["aggregate_id"])

    @staticmethod
    def _state_version(row: Mapping[str, Any]) -> int:
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            return -1
        try:
            return int(payload.get("state_version", -1))
        except (TypeError, ValueError):
            return -1

    @classmethod
    def _first_claimable(
        cls,
        rows: Sequence[Mapping[str, Any]],
        *,
        now: datetime,
        max_attempts: int,
    ) -> dict[str, Any] | None:
        stream_heads: dict[tuple[str, str], dict[str, Any]] = {}
        for raw_row in rows:
            row = dict(raw_row)
            stream = cls._delivery_stream(row)
            existing = stream_heads.get(stream)
            if existing is None or (
                cls._state_version(row), str(row["created_at"]), str(row["id"])
            ) < (
                cls._state_version(existing),
                str(existing["created_at"]),
                str(existing["id"]),
            ):
                stream_heads[stream] = row
        eligible = [
            row
            for row in stream_heads.values()
            if cls._claimable(row, now=now, max_attempts=max_attempts)
        ]
        if not eligible:
            return None
        return min(eligible, key=lambda row: (str(row["created_at"]), str(row["id"])))

    def claim_one(
        self,
        *,
        organization_id: str,
        project_id: str,
        event_types: Sequence[str],
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> OutboxMessage | None:
        if not organization_id or not project_id:
            raise ValueError("organization_id and project_id are required")
        clause, normalized_types = self._event_clause(event_types)
        if self.postgresql:
            return self._claim_postgresql(
                organization_id=organization_id,
                project_id=project_id,
                clause=clause,
                event_types=normalized_types,
                max_attempts=max_attempts,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        return self._claim_sqlite(
            organization_id=organization_id,
            project_id=project_id,
            clause=clause,
            event_types=normalized_types,
            max_attempts=max_attempts,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    def _claim_sqlite(
        self,
        *,
        organization_id: str,
        project_id: str,
        clause: str,
        event_types: tuple[str, ...],
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> OutboxMessage | None:
        current = _utc_now()
        now = current.isoformat()
        lease_token = uuid.uuid4().hex + uuid.uuid4().hex
        lease_expires = (current + timedelta(seconds=max(5, lease_seconds))).isoformat()
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""
                UPDATE transactional_outbox
                SET status='retry',available_at=?,lease_owner=NULL,lease_token=NULL,
                    lease_expires_at=NULL,heartbeat_at=NULL,
                    last_error=coalesce(last_error,'worker lease expired')
                WHERE organization_id=? AND project_id=?
                  AND event_type IN ({clause})
                  AND status='processing' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at<=?
                """,
                (now, organization_id, project_id, *event_types, now),
            )
            rows = connection.execute(
                f"""
                SELECT * FROM transactional_outbox
                WHERE organization_id=? AND project_id=?
                  AND event_type IN ({clause}) AND status<>'processed'
                ORDER BY created_at,aggregate_id,id
                """,
                (organization_id, project_id, *event_types),
            ).fetchall()
            values = self._first_claimable(
                rows,
                now=current,
                max_attempts=max_attempts,
            )
            if values is None:
                return None
            updated = connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processing',attempt_count=attempt_count+1,last_error=NULL,
                    lease_owner=?,lease_token=?,lease_expires_at=?,heartbeat_at=?
                WHERE id=? AND organization_id=? AND project_id=?
                  AND status IN ('pending','retry')
                """,
                (
                    worker_id,
                    lease_token,
                    lease_expires,
                    now,
                    values["id"],
                    organization_id,
                    project_id,
                ),
            )
            if updated.rowcount != 1:
                return None
        return self._message(values, lease_token=lease_token)

    def _claim_postgresql(
        self,
        *,
        organization_id: str,
        project_id: str,
        clause: str,
        event_types: tuple[str, ...],
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> OutboxMessage | None:
        current = _utc_now()
        lease_token = uuid.uuid4().hex + uuid.uuid4().hex
        lease_expires = current + timedelta(seconds=max(5, lease_seconds))
        with postgres_repository_connection(
            self.database,
            organization_id=organization_id,
            project_id=project_id,
        ) as connection:
            connection.execute(
                f"""
                UPDATE transactional_outbox
                SET status='retry',available_at=least(available_at,now()),
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
                    heartbeat_at=NULL,last_error=coalesce(last_error,'worker lease expired')
                WHERE organization_id=? AND project_id=?
                  AND event_type IN ({clause})
                  AND status='processing' AND lease_expires_at IS NOT NULL
                  AND lease_expires_at<=now()
                """,
                (organization_id, project_id, *event_types),
            )
            rows = connection.execute(
                f"""
                SELECT * FROM transactional_outbox
                WHERE organization_id=? AND project_id=?
                  AND event_type IN ({clause}) AND status<>'processed'
                ORDER BY created_at,aggregate_id,id
                FOR UPDATE
                """,
                (organization_id, project_id, *event_types),
            ).fetchall()
            values = self._first_claimable(
                rows,
                now=current,
                max_attempts=max_attempts,
            )
            if values is None:
                return None
            updated = connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processing',attempt_count=attempt_count+1,last_error=NULL,
                    lease_owner=?,lease_token=?,lease_expires_at=?,heartbeat_at=?
                WHERE id=? AND organization_id=? AND project_id=?
                  AND status IN ('pending','retry')
                """,
                (
                    worker_id,
                    lease_token,
                    lease_expires.isoformat(),
                    current.isoformat(),
                    values["id"],
                    organization_id,
                    project_id,
                ),
            )
            if updated.rowcount != 1:
                return None
        return self._message(values, lease_token=lease_token)

    def mark_delivered(self, message: OutboxMessage, *, handler_code: str) -> None:
        delivered_at = _utc_now().isoformat()
        payload = json.dumps(message.payload, ensure_ascii=False, sort_keys=True)
        values = (
            str(uuid.uuid4()),
            message.organization_id,
            message.project_id,
            message.workspace_id,
            message.id,
            message.event_type,
            handler_code,
            payload,
            delivered_at,
        )
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=message.organization_id,
                project_id=message.project_id,
            ) as connection:
                connection.execute(
                    """
                    INSERT INTO outbox_delivery_log(
                        id,organization_id,project_id,workspace_id,outbox_id,event_type,
                        handler_code,payload_json,delivered_at
                    ) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(outbox_id) DO NOTHING
                    """,
                    values,
                )
                updated = connection.execute(
                    """
                    UPDATE transactional_outbox
                    SET status='processed',processed_at=?,last_error=NULL,
                        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL
                    WHERE id=? AND organization_id=? AND project_id=? AND lease_token=?
                    """,
                    (
                        delivered_at,
                        message.id,
                        message.organization_id,
                        message.project_id,
                        message.lease_token,
                    ),
                )
                if updated.rowcount != 1:
                    raise OutboxLeaseLost(message.id)
            return
        with sqlite3.connect(self.database) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO outbox_delivery_log(
                    id,organization_id,project_id,workspace_id,outbox_id,event_type,
                    handler_code,payload_json,delivered_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                values,
            )
            updated = connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processed',processed_at=?,last_error=NULL,
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL
                WHERE id=? AND organization_id=? AND project_id=? AND lease_token=?
                """,
                (
                    delivered_at,
                    message.id,
                    message.organization_id,
                    message.project_id,
                    message.lease_token,
                ),
            )
            if updated.rowcount != 1:
                raise OutboxLeaseLost(message.id)

    def mark_failed(
        self,
        message: OutboxMessage,
        *,
        error: str,
        max_attempts: int,
        retry_delay_seconds: int,
        retryable: bool,
    ) -> None:
        status = (
            "retry"
            if retryable and message.attempt_count < max_attempts
            else "dead_letter"
        )
        available_at = (
            _utc_now() + timedelta(seconds=max(1, retry_delay_seconds))
        ).isoformat()
        values = (
            status,
            error[:4000],
            available_at,
            message.id,
            message.organization_id,
            message.project_id,
            message.lease_token,
        )
        query = """
            UPDATE transactional_outbox
            SET status=?,last_error=?,available_at=?,lease_owner=NULL,lease_token=NULL,
                lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=? AND organization_id=? AND project_id=? AND lease_token=?
        """
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=message.organization_id,
                project_id=message.project_id,
            ) as connection:
                updated = connection.execute(query, values)
                if updated.rowcount != 1:
                    raise OutboxLeaseLost(message.id)
            return
        with sqlite3.connect(self.database) as connection:
            updated = connection.execute(query, values)
            if updated.rowcount != 1:
                raise OutboxLeaseLost(message.id)

    def replay_dead_letter(
        self,
        *,
        organization_id: str,
        project_id: str,
        event_id: str,
    ) -> None:
        values = (
            _utc_now().isoformat(),
            event_id,
            organization_id,
            project_id,
        )
        query = """
            UPDATE transactional_outbox
            SET status='pending',attempt_count=0,available_at=?,processed_at=NULL,
                last_error=NULL,lease_owner=NULL,lease_token=NULL,
                lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=? AND organization_id=? AND project_id=? AND status='dead_letter'
        """
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            ) as connection:
                updated = connection.execute(query, values)
                if updated.rowcount != 1:
                    raise ValueError("only dead-letter events can be replayed")
            return
        with sqlite3.connect(self.database) as connection:
            updated = connection.execute(query, values)
            if updated.rowcount != 1:
                raise ValueError("only dead-letter events can be replayed")


class ProjectOutboxWorker:
    """Deliver registered events with a durable lease and retry boundary."""

    def __init__(
        self,
        repository: ProjectOutboxRepository,
        *,
        organization_id: str,
        project_id: str,
        handlers: Mapping[str, tuple[str, OutboxHandler]],
        max_attempts: int = 5,
        retry_delay_seconds: int = 5,
        worker_id: str | None = None,
        lease_seconds: int = 60,
    ) -> None:
        if not handlers:
            raise ValueError("at least one outbox handler is required")
        self.repository = repository
        self.organization_id = organization_id
        self.project_id = project_id
        self.handlers = dict(handlers)
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-outbox"
        self.lease_seconds = max(5, lease_seconds)

    def process_once(self) -> bool:
        message = self.repository.claim_one(
            organization_id=self.organization_id,
            project_id=self.project_id,
            event_types=tuple(self.handlers),
            max_attempts=self.max_attempts,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if message is None:
            return False
        handler_code, handler = self.handlers[message.event_type]
        try:
            handler(message)
        except Exception as exc:
            retryable = bool(getattr(exc, "retryable", True))
            delay = min(
                3600,
                self.retry_delay_seconds * (2 ** max(0, message.attempt_count - 1)),
            )
            self.repository.mark_failed(
                message,
                error=f"{type(exc).__name__}: {exc}",
                max_attempts=self.max_attempts,
                retry_delay_seconds=delay,
                retryable=retryable,
            )
            return True
        self.repository.mark_delivered(message, handler_code=handler_code)
        return True

    def drain(self, *, max_messages: int = 1000) -> int:
        processed = 0
        while processed < max(0, max_messages) and self.process_once():
            processed += 1
        return processed

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        while True:
            if not self.process_once():
                time.sleep(max(0.1, poll_seconds))
