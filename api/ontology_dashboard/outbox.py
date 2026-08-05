from __future__ import annotations

import json
import hashlib
import os
import random
import socket
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .postgresql_compat import postgres_repository_connection
from .postgresql_pool import pooled_identity_connection
from .postgresql_repositories import is_postgresql


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
    lease_owner: str | None = None
    lease_token: str | None = None


OutboxHandler = Callable[[OutboxMessage], None]


class UnknownOutboxEvent(RuntimeError):
    pass


class OutboxRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def project_scopes(self) -> list[tuple[str, str]]:
        if self.postgresql:
            with pooled_identity_connection(self.database) as connection:
                rows = connection.execute(
                    "SELECT organization_id,id FROM projects WHERE status<>'archived' ORDER BY organization_id,id"
                ).fetchall()
            return [(str(row["organization_id"]), str(row["id"])) for row in rows]
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                "SELECT organization_id,id FROM projects WHERE status<>'archived' ORDER BY organization_id,id"
            ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def claim_one(
        self,
        *,
        organization_id: str,
        project_id: str,
        max_attempts: int,
        worker_id: str = "outbox-worker",
        lease_seconds: int = 60,
    ) -> OutboxMessage | None:
        if self.postgresql:
            return self._claim_postgresql(
                organization_id=organization_id,
                project_id=project_id,
                max_attempts=max_attempts,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        return self._claim_sqlite(
            organization_id=organization_id,
            project_id=project_id,
            max_attempts=max_attempts,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    def _claim_sqlite(
        self,
        *,
        organization_id: str,
        project_id: str,
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> OutboxMessage | None:
        current = self._now()
        now = current.isoformat()
        lease_token = uuid.uuid4().hex + uuid.uuid4().hex
        lease_expires = (current + timedelta(seconds=max(5, lease_seconds))).isoformat()
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE transactional_outbox
                SET status='retry',available_at=?,lease_owner=NULL,lease_token=NULL,
                    lease_expires_at=NULL,heartbeat_at=NULL,
                    last_error=coalesce(last_error,'worker lease expired')
                WHERE organization_id=? AND project_id=? AND status='processing'
                  AND lease_expires_at IS NOT NULL AND lease_expires_at<=?
                """,
                (now, organization_id, project_id, now),
            )
            row = connection.execute(
                """
                SELECT * FROM transactional_outbox
                WHERE organization_id=? AND project_id=?
                  AND status IN ('pending','retry')
                  AND attempt_count<? AND available_at<=?
                ORDER BY created_at,id
                LIMIT 1
                """,
                (organization_id, project_id, max_attempts, now),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processing',attempt_count=attempt_count+1,last_error=NULL,
                    lease_owner=?,lease_token=?,lease_expires_at=?,heartbeat_at=?
                WHERE id=? AND status IN ('pending','retry')
                """,
                (worker_id, lease_token, lease_expires, now, row["id"]),
            )
            if cursor.rowcount != 1:
                return None
            claimed = dict(row)
            claimed["attempt_count"] = int(row["attempt_count"]) + 1
            claimed["lease_owner"] = worker_id
            claimed["lease_token"] = lease_token
        return self._message(claimed)

    def _claim_postgresql(
        self,
        *,
        organization_id: str,
        project_id: str,
        max_attempts: int,
        worker_id: str,
        lease_seconds: int,
    ) -> OutboxMessage | None:
        current = self._now()
        lease_token = uuid.uuid4().hex + uuid.uuid4().hex
        lease_expires = current + timedelta(seconds=max(5, lease_seconds))
        with postgres_repository_connection(
            self.database,
            organization_id=organization_id,
            project_id=project_id,
        ) as connection:
            connection.execute(
                """
                UPDATE transactional_outbox
                SET status='retry',available_at=least(available_at,now()),
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                    last_error=coalesce(last_error,'worker lease expired')
                WHERE organization_id=? AND project_id=? AND status='processing'
                  AND lease_expires_at IS NOT NULL AND lease_expires_at<=now()
                """,
                (organization_id, project_id),
            )
            row = connection.execute(
                """
                SELECT * FROM transactional_outbox
                WHERE organization_id=? AND project_id=?
                  AND status IN ('pending','retry')
                  AND attempt_count<? AND available_at<=now()
                ORDER BY created_at,id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (organization_id, project_id, max_attempts),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processing',attempt_count=attempt_count+1,last_error=NULL,
                    lease_owner=?,lease_token=?,lease_expires_at=?,heartbeat_at=?
                WHERE id=?
                """,
                (
                    worker_id,
                    lease_token,
                    lease_expires.isoformat(),
                    current.isoformat(),
                    row["id"],
                ),
            )
            row["attempt_count"] = int(row["attempt_count"]) + 1
            row["lease_owner"] = worker_id
            row["lease_token"] = lease_token
        return self._message(row)

    @staticmethod
    def _message(row: Mapping[str, Any]) -> OutboxMessage:
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("outbox payload must be a JSON object")
        return OutboxMessage(
            id=str(row["id"]),
            organization_id=str(row["organization_id"]),
            project_id=str(row["project_id"]),
            workspace_id=None if row.get("workspace_id") is None else str(row["workspace_id"]),
            aggregate_type=str(row["aggregate_type"]),
            aggregate_id=str(row["aggregate_id"]),
            event_type=str(row["event_type"]),
            payload=payload,
            attempt_count=int(row["attempt_count"]),
            lease_owner=row.get("lease_owner"),
            lease_token=row.get("lease_token"),
        )

    def mark_delivered(self, message: OutboxMessage, *, handler_code: str) -> None:
        delivered_at = self._now().isoformat()
        payload = json.dumps(message.payload, ensure_ascii=False, sort_keys=True)
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
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(outbox_id) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        message.organization_id,
                        message.project_id,
                        message.workspace_id,
                        message.id,
                        message.event_type,
                        handler_code,
                        payload,
                        delivered_at,
                    ),
                )
                connection.execute(
                    """
                    UPDATE transactional_outbox
                    SET status='processed',processed_at=?,last_error=NULL,
                        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL
                    WHERE id=? AND project_id=? AND lease_token=?
                    """,
                    (delivered_at, message.id, message.project_id, message.lease_token),
                )
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
                (
                    str(uuid.uuid4()),
                    message.organization_id,
                    message.project_id,
                    message.workspace_id,
                    message.id,
                    message.event_type,
                    handler_code,
                    payload,
                    delivered_at,
                ),
            )
            connection.execute(
                """
                UPDATE transactional_outbox
                SET status='processed',processed_at=?,last_error=NULL,
                    lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL
                WHERE id=? AND project_id=? AND lease_token=?
                """,
                (delivered_at, message.id, message.project_id, message.lease_token),
            )

    def mark_failed(
        self,
        message: OutboxMessage,
        *,
        error: str,
        max_attempts: int,
        retry_delay_seconds: int,
        retryable: bool = True,
    ) -> None:
        status = (
            "dead_letter"
            if not retryable or message.attempt_count >= max_attempts
            else "retry"
        )
        available_at = (
            self._now() + timedelta(seconds=max(1, retry_delay_seconds))
        ).isoformat()
        values = (
            status,
            error[:4000],
            available_at,
            message.id,
            message.project_id,
            message.lease_token,
        )
        query = """
            UPDATE transactional_outbox
            SET status=?,last_error=?,available_at=?,
                lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=? AND project_id=? AND lease_token=?
        """
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=message.organization_id,
                project_id=message.project_id,
            ) as connection:
                connection.execute(query, values)
            return
        with sqlite3.connect(self.database) as connection:
            connection.execute(query, values)

    def replay_dead_letter(
        self,
        *,
        organization_id: str,
        project_id: str,
        event_id: str,
    ) -> OutboxMessage:
        now = self._now().isoformat()
        query = """
            UPDATE transactional_outbox SET
                status='pending',attempt_count=0,available_at=?,processed_at=NULL,last_error=NULL,
                lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL
            WHERE id=? AND organization_id=? AND project_id=? AND status='dead_letter'
        """
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            ) as connection:
                cursor = connection.execute(query, (now, event_id, organization_id, project_id))
                if cursor.rowcount != 1:
                    raise ValueError("only dead-letter outbox events can be replayed")
                row = connection.execute(
                    "SELECT * FROM transactional_outbox WHERE id=?",
                    (event_id,),
                ).fetchone()
            return self._message(row)
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(query, (now, event_id, organization_id, project_id))
            if cursor.rowcount != 1:
                raise ValueError("only dead-letter outbox events can be replayed")
            row = connection.execute(
                "SELECT * FROM transactional_outbox WHERE id=?",
                (event_id,),
            ).fetchone()
        return self._message(dict(row))

    def metrics(self, *, organization_id: str, project_id: str) -> dict[str, int | float]:
        query = """
            SELECT status,count(*) AS count,min(created_at) AS oldest
            FROM transactional_outbox
            WHERE organization_id=? AND project_id=? GROUP BY status
        """
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            ) as connection:
                rows = connection.execute(query, (organization_id, project_id)).fetchall()
        else:
            with sqlite3.connect(self.database) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(query, (organization_id, project_id)).fetchall()
        result: dict[str, int | float] = {
            "pending": 0,
            "retry": 0,
            "processing": 0,
            "processed": 0,
            "dead_letter": 0,
            "oldest_pending_seconds": 0,
        }
        oldest = None
        for row in rows:
            result[str(row["status"])] = int(row["count"])
            if row["status"] in {"pending", "retry"}:
                parsed = datetime.fromisoformat(str(row["oldest"]).replace("Z", "+00:00"))
                oldest = parsed if oldest is None else min(oldest, parsed)
        if oldest is not None:
            result["oldest_pending_seconds"] = max(
                0,
                (self._now() - oldest).total_seconds(),
            )
        return result


class OutboxWorker:
    def __init__(
        self,
        database: str | Path,
        *,
        handlers: Mapping[str, tuple[str, OutboxHandler]] | None = None,
        max_attempts: int = 5,
        retry_delay_seconds: int = 30,
        worker_id: str | None = None,
        lease_seconds: int = 60,
    ) -> None:
        self.repository = OutboxRepository(database)
        self.handlers = dict(handlers or {})
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-outbox"
        self.lease_seconds = max(5, lease_seconds)

    def register(self, event_type: str, handler_code: str, handler: OutboxHandler) -> None:
        if event_type in self.handlers:
            raise ValueError(f"handler already registered for {event_type}")
        self.handlers[event_type] = (handler_code, handler)

    def process_once(self) -> bool:
        for organization_id, project_id in self.repository.project_scopes():
            message = self.repository.claim_one(
                organization_id=organization_id,
                project_id=project_id,
                max_attempts=self.max_attempts,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if message is None:
                continue
            try:
                registered = self.handlers.get(message.event_type)
                if registered is None:
                    raise UnknownOutboxEvent(message.event_type)
                handler_code, handler = registered
                handler(message)
                self.repository.mark_delivered(message, handler_code=handler_code)
            except Exception as exc:
                digest = int(hashlib.sha256(message.id.encode()).hexdigest()[:8], 16)
                jitter = random.Random(digest + message.attempt_count).uniform(0.8, 1.2)
                retry_delay = min(
                    3600,
                    max(
                        1,
                        int(
                            self.retry_delay_seconds
                            * (2 ** max(0, message.attempt_count - 1))
                            * jitter
                        ),
                    ),
                )
                self.repository.mark_failed(
                    message,
                    error=f"{type(exc).__name__}: {exc}",
                    max_attempts=self.max_attempts,
                    retry_delay_seconds=retry_delay,
                    retryable=bool(getattr(exc, "retryable", True)),
                )
            return True
        return False

    def drain(self, *, max_messages: int = 1000) -> int:
        processed = 0
        while processed < max_messages and self.process_once():
            processed += 1
        return processed

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        while True:
            if not self.process_once():
                time.sleep(max(0.1, poll_seconds))


def delivery_log_handler(_: OutboxMessage) -> None:
    """Safe default handler: delivery is acknowledged in the immutable log."""


def default_outbox_worker(
    database: str | Path,
    *,
    project3_client: Any | None = None,
    enable_project3_projection: bool | None = None,
) -> OutboxWorker:
    worker = OutboxWorker(database)
    for event_type in (
        "field_task.complete",
        "field_task.issue_found",
        "field_task.blocked",
    ):
        worker.register(event_type, "delivery-log-v1", delivery_log_handler)
    enabled = (
        enable_project3_projection
        if enable_project3_projection is not None
        else os.getenv(
            "ONTOLOGY_DASHBOARD_PROJECT3_PROJECTION_ENABLED", "1"
        ).strip()
        not in {"0", "false", "no"}
    )
    if worker.repository.postgresql and enabled:
        from .integrations.project3 import (
            PredictiveMaintenanceProject3ProjectionHandler,
            Project3Client,
        )

        client = project3_client or Project3Client.from_environment()
        handler = PredictiveMaintenanceProject3ProjectionHandler(
            str(database),
            client,
        )
        worker.register(
            handler.event_type,
            handler.handler_code,
            handler,
        )
    return worker
