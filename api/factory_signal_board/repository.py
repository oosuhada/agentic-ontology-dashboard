from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    question TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    event_id TEXT,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    model_version TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_decision(self, event_id: str, actor: str, decision: str, note: str) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "actor": actor,
            "decision": decision,
            "note": note,
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO decisions (id,event_id,actor,decision,note,created_at) VALUES (?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    def add_note(self, event_id: str, actor: str, body: str) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "actor": actor,
            "body": body,
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO notes (id,event_id,actor,body,created_at) VALUES (?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    def add_conversation(
        self,
        thread_id: str,
        event_id: str,
        role: str,
        question: str,
        intent: str,
        answer: str,
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "event_id": event_id,
            "role": role,
            "question": question,
            "intent": intent,
            "answer": answer,
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id,thread_id,event_id,role,question,intent,answer,created_at) VALUES (?,?,?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return record

    def record_audit(
        self,
        *,
        event_id: str | None,
        run_id: str,
        action: str,
        model_version: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "run_id": run_id,
            "action": action,
            "model_version": model_version,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "created_at": self._now(),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log (id,event_id,run_id,action,model_version,payload_json,created_at) VALUES (?,?,?,?,?,?,?)",
                tuple(record.values()),
            )
        return {**record, "payload": payload}

    def event_activity(self, event_id: str) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as connection:
            decisions = [dict(row) for row in connection.execute("SELECT * FROM decisions WHERE event_id=? ORDER BY created_at", (event_id,))]
            notes = [dict(row) for row in connection.execute("SELECT * FROM notes WHERE event_id=? ORDER BY created_at", (event_id,))]
            conversations = [dict(row) for row in connection.execute("SELECT * FROM conversations WHERE event_id=? ORDER BY created_at", (event_id,))]
        return {"decisions": decisions, "notes": notes, "conversations": conversations}

    def reset(self) -> None:
        with self._connect() as connection:
            connection.executescript("DELETE FROM decisions; DELETE FROM notes; DELETE FROM conversations; DELETE FROM audit_log;")
            ontology_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ontology_action_invocations'"
            ).fetchone()
            if ontology_table is not None:
                connection.execute("DELETE FROM ontology_action_invocations")
