from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from app.infra.db.migrations import ensure_scope_columns
from app.dashboard.catalog import seed_templates
from app.dashboard.dashboard_schema import DashboardTemplateSnapshot, SavedViewRecord
from app.dashboard.dashboard_exception import DashboardPreferenceConflict


class ProjectScope(Protocol):
    organization_id: str
    project_id: str
    workspace_id: str


class ProjectContextResolverPort(Protocol):
    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> ProjectScope: ...


class _SQLiteScope:
    def __init__(self, organization_id: str, project_id: str, workspace_id: str) -> None:
        self.organization_id = organization_id
        self.project_id = project_id
        self.workspace_id = workspace_id


class _SQLiteWorkspaceScopeLookup:
    """Persistence-only fallback used when composition has not injected Project context yet."""

    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: str | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> _SQLiteScope:
        if connection is None:
            raise RuntimeError("dashboard scope lookup requires an active repository connection")
        row = connection.execute(
            "SELECT organization_id,project_id FROM workspaces WHERE id=?",
            (workspace_id,),
        ).fetchone()
        if row is None:
            raise KeyError(workspace_id)
        organization_id = str(row[0])
        project_id = str(row[1])
        if expected_organization_id is not None and organization_id != expected_organization_id:
            raise PermissionError("workspace organization scope mismatch")
        if expected_project_id is not None and project_id != expected_project_id:
            raise PermissionError("workspace project scope mismatch")
        return _SQLiteScope(organization_id, project_id, workspace_id)


class DashboardRepository:
    def __init__(
        self,
        database_path: str | Path,
        *,
        project_context: ProjectContextResolverPort | None = None,
    ) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.project_context = project_context or _SQLiteWorkspaceScopeLookup()
        self._template_cache: dict[
            tuple[str, str], tuple[float, DashboardTemplateSnapshot]
        ] = {}
        self._initialize()
        self._seed_templates()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _iso(cls, value: datetime | None = None) -> str:
        return (value or cls._now()).isoformat()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS dashboard_templates (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    role_code TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (workspace_id, role_code)
                );
                CREATE TABLE IF NOT EXISTS dashboard_template_versions (
                    id TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (template_id, version),
                    FOREIGN KEY (template_id) REFERENCES dashboard_templates(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS dashboard_user_preferences (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    template_version INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (user_id, workspace_id, template_id),
                    FOREIGN KEY (template_id) REFERENCES dashboard_templates(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS dashboard_saved_views (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_shares (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    owner_user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_dashboard_templates_scope
                    ON dashboard_templates(workspace_id, role_code);
                CREATE INDEX IF NOT EXISTS idx_dashboard_preferences_user
                    ON dashboard_user_preferences(user_id, workspace_id);
                CREATE INDEX IF NOT EXISTS idx_dashboard_saved_views_user
                    ON dashboard_saved_views(user_id, workspace_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_dashboard_shares_token
                    ON dashboard_shares(token_hash);
                """
            )
            for table in (
                "dashboard_templates",
                "dashboard_user_preferences",
                "dashboard_saved_views",
                "dashboard_shares",
            ):
                ensure_scope_columns(connection, table=table)

    def _scope(self, connection: sqlite3.Connection, workspace_id: str):
        return self.project_context.resolve(workspace_id, connection=connection)

    def _seed_templates(self) -> None:
        now = self._iso()
        with self._connect() as connection:
            for template in seed_templates():
                scope = self._scope(connection, template.workspace_id)
                existing = connection.execute(
                    """
                    SELECT id,current_version FROM dashboard_templates
                    WHERE organization_id=? AND project_id=? AND workspace_id=? AND role_code=?
                    """,
                    (
                        scope.organization_id,
                        scope.project_id,
                        template.workspace_id,
                        template.role_code,
                    ),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO dashboard_templates (
                            id,organization_id,project_id,workspace_id,role_code,display_name,
                            current_version,created_at,updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            template.template_id,
                            scope.organization_id,
                            scope.project_id,
                            template.workspace_id,
                            template.role_code,
                            template.display_name,
                            template.version,
                            now,
                            now,
                        ),
                    )

                    existing = connection.execute(
                        """
                        SELECT id,current_version FROM dashboard_templates
                        WHERE workspace_id=? AND role_code=?
                        """,
                        (template.workspace_id, template.role_code),
                    ).fetchone()
                    if existing is None:
                        raise RuntimeError("dashboard template seed insert did not persist")
                template_id = existing["id"]

                seeded_version = connection.execute(
                    "SELECT 1 FROM dashboard_template_versions WHERE template_id=? AND version=?",
                    (template_id, template.version),
                ).fetchone()
                if seeded_version is None:
                    payload = template.model_copy(update={"template_id": template_id})
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO dashboard_template_versions (
                            id,template_id,version,status,payload_json,created_by,created_at
                        ) VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            str(uuid.uuid4()),
                            template_id,
                            template.version,
                            template.status,
                            payload.model_dump_json(),
                            template.created_by,
                            template.created_at,
                        ),
                    )
                if int(existing["current_version"]) < template.version:
                    connection.execute(
                        """
                        UPDATE dashboard_templates
                        SET display_name=?,current_version=?,updated_at=?
                        WHERE id=?
                        """,
                        (template.display_name, template.version, now, template_id),
                    )

    @staticmethod
    def _decode_json(value: str) -> dict[str, Any]:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError("dashboard persistence payload must be an object")
        return payload

    def get_current_template(self, *, workspace_id: str, role_code: str) -> DashboardTemplateSnapshot | None:
        cache_key = (workspace_id, role_code)
        cached = self._template_cache.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] <= 5.0:
            return cached[1]
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            row = connection.execute(
                """
                SELECT v.payload_json
                FROM dashboard_templates t
                JOIN dashboard_template_versions v
                  ON v.template_id=t.id AND v.version=t.current_version
                WHERE t.organization_id=? AND t.project_id=?
                  AND t.workspace_id=? AND t.role_code=?
                """,
                (scope.organization_id, scope.project_id, workspace_id, role_code),
            ).fetchone()
        if row is None:
            return None
        template = DashboardTemplateSnapshot.model_validate_json(row["payload_json"])
        self._template_cache[cache_key] = (time.monotonic(), template)
        return template

    def get_template_version(
        self,
        *,
        workspace_id: str,
        role_code: str,
        version: int,
    ) -> DashboardTemplateSnapshot | None:
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            row = connection.execute(
                """
                SELECT v.payload_json
                FROM dashboard_templates t
                JOIN dashboard_template_versions v ON v.template_id=t.id
                WHERE t.organization_id=? AND t.project_id=?
                  AND t.workspace_id=? AND t.role_code=? AND v.version=?
                """,
                (scope.organization_id, scope.project_id, workspace_id, role_code, version),
            ).fetchone()
        return DashboardTemplateSnapshot.model_validate_json(row["payload_json"]) if row else None

    def list_template_versions(self, *, workspace_id: str, role_code: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            rows = connection.execute(
                """
                SELECT t.id AS template_id,t.display_name,t.current_version,
                       v.version,v.status,v.created_by,v.created_at
                FROM dashboard_templates t
                JOIN dashboard_template_versions v ON v.template_id=t.id
                WHERE t.organization_id=? AND t.project_id=?
                  AND t.workspace_id=? AND t.role_code=?
                ORDER BY v.version DESC
                """,
                (scope.organization_id, scope.project_id, workspace_id, role_code),
            ).fetchall()
        return [dict(row) for row in rows]

    def publish_template(
        self,
        *,
        workspace_id: str,
        role_code: str,
        display_name: str,
        snapshot_payload: dict[str, Any],
        actor_user_id: str,
    ) -> DashboardTemplateSnapshot:
        now = self._iso()
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            template_row = connection.execute(
                """
                SELECT * FROM dashboard_templates
                WHERE organization_id=? AND project_id=? AND workspace_id=? AND role_code=?
                """,
                (scope.organization_id, scope.project_id, workspace_id, role_code),
            ).fetchone()
            if template_row is None:
                template_id = f"template:{workspace_id}:{role_code}"
                next_version = 1
                connection.execute(
                    """
                    INSERT INTO dashboard_templates (
                        id,organization_id,project_id,workspace_id,role_code,display_name,
                        current_version,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        template_id,
                        scope.organization_id,
                        scope.project_id,
                        workspace_id,
                        role_code,
                        display_name,
                        next_version,
                        now,
                        now,
                    ),
                )
            else:
                template_id = template_row["id"]
                next_version = int(template_row["current_version"]) + 1
                connection.execute(
                    """
                    UPDATE dashboard_templates
                    SET display_name=?,current_version=?,updated_at=?
                    WHERE id=?
                    """,
                    (display_name, next_version, now, template_id),
                )

            snapshot = DashboardTemplateSnapshot.model_validate(
                {
                    **snapshot_payload,
                    "template_id": template_id,
                    "workspace_id": workspace_id,
                    "role_code": role_code,
                    "display_name": display_name,
                    "version": next_version,
                    "status": "published",
                    "created_by": actor_user_id,
                    "created_at": now,
                }
            )
            connection.execute(
                """
                INSERT INTO dashboard_template_versions (
                    id,template_id,version,status,payload_json,created_by,created_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    template_id,
                    next_version,
                    "published",
                    snapshot.model_dump_json(),
                    actor_user_id,
                    now,
                ),
            )
        self._template_cache.pop((workspace_id, role_code), None)
        return snapshot

    def get_preferences(
        self,
        *,
        user_id: str,
        workspace_id: str,
        template_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            row = connection.execute(
                """
                SELECT * FROM dashboard_user_preferences
                WHERE organization_id=? AND project_id=?
                  AND user_id=? AND workspace_id=? AND template_id=?
                """,
                (scope.organization_id, scope.project_id, user_id, workspace_id, template_id),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = self._decode_json(result.pop("payload_json"))
        return result

    def save_preferences(
        self,
        *,
        user_id: str,
        workspace_id: str,
        template_id: str,
        template_version: int,
        base_revision: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._iso()
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            current = connection.execute(
                """
                SELECT * FROM dashboard_user_preferences
                WHERE organization_id=? AND project_id=?
                  AND user_id=? AND workspace_id=? AND template_id=?
                """,
                (scope.organization_id, scope.project_id, user_id, workspace_id, template_id),
            ).fetchone()
            if current is None:
                if base_revision != 0:
                    raise DashboardPreferenceConflict("dashboard preference revision changed")
                record_id = str(uuid.uuid4())
                revision = 1
                connection.execute(
                    """
                    INSERT INTO dashboard_user_preferences (
                        id,organization_id,project_id,user_id,workspace_id,template_id,
                        template_version,revision,payload_json,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record_id,
                        scope.organization_id,
                        scope.project_id,
                        user_id,
                        workspace_id,
                        template_id,
                        template_version,
                        revision,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                    ),
                )
            else:
                if int(current["revision"]) != base_revision:
                    raise DashboardPreferenceConflict("dashboard preference revision changed")
                record_id = current["id"]
                revision = base_revision + 1
                connection.execute(
                    """
                    UPDATE dashboard_user_preferences
                    SET template_version=?,revision=?,payload_json=?,updated_at=?
                    WHERE id=?
                    """,
                    (
                        template_version,
                        revision,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        record_id,
                    ),
                )
        saved = self.get_preferences(
            user_id=user_id,
            workspace_id=workspace_id,
            template_id=template_id,
        )
        if saved is None:
            raise RuntimeError("saved dashboard preferences could not be loaded")
        return saved

    def delete_preferences(self, *, user_id: str, workspace_id: str, template_id: str) -> None:
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            connection.execute(
                """
                DELETE FROM dashboard_user_preferences
                WHERE organization_id=? AND project_id=?
                  AND user_id=? AND workspace_id=? AND template_id=?
                """,
                (scope.organization_id, scope.project_id, user_id, workspace_id, template_id),
            )

    def create_saved_view(
        self,
        *,
        user_id: str,
        workspace_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> SavedViewRecord:
        now = self._iso()
        view_id = str(uuid.uuid4())
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            connection.execute(
                """
                INSERT INTO dashboard_saved_views (
                    id,organization_id,project_id,user_id,workspace_id,name,
                    payload_json,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    view_id,
                    scope.organization_id,
                    scope.project_id,
                    user_id,
                    workspace_id,
                    name,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        record = self.get_saved_view(view_id=view_id, user_id=user_id)
        if record is None:
            raise RuntimeError("saved dashboard view could not be loaded")
        return record

    def _saved_view_from_row(self, row: sqlite3.Row) -> SavedViewRecord:
        payload = self._decode_json(row["payload_json"])
        return SavedViewRecord.model_validate(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "workspace_id": row["workspace_id"],
                "name": row["name"],
                **payload,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    def list_saved_views(self, *, user_id: str, workspace_id: str) -> list[SavedViewRecord]:
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            rows = connection.execute(
                """
                SELECT * FROM dashboard_saved_views
                WHERE organization_id=? AND project_id=? AND user_id=? AND workspace_id=?
                ORDER BY updated_at DESC
                """,
                (scope.organization_id, scope.project_id, user_id, workspace_id),
            ).fetchall()
        return [self._saved_view_from_row(row) for row in rows]

    def get_saved_view(
        self,
        *,
        view_id: str,
        user_id: str,
        project_id: str | None = None,
    ) -> SavedViewRecord | None:
        clauses = ["id=?", "user_id=?"]
        parameters: list[Any] = [view_id, user_id]
        if project_id is not None:
            clauses.append("project_id=?")
            parameters.append(project_id)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM dashboard_saved_views WHERE {' AND '.join(clauses)}",
                parameters,
            ).fetchone()
        return self._saved_view_from_row(row) if row else None

    def delete_saved_view(
        self,
        *,
        view_id: str,
        user_id: str,
        project_id: str | None = None,
    ) -> bool:
        clauses = ["id=?", "user_id=?"]
        parameters: list[Any] = [view_id, user_id]
        if project_id is not None:
            clauses.append("project_id=?")
            parameters.append(project_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM dashboard_saved_views WHERE {' AND '.join(clauses)}",
                parameters,
            )
        return cursor.rowcount > 0

    def create_share(
        self,
        *,
        owner_user_id: str,
        workspace_id: str,
        payload: dict[str, Any],
        expires_in_hours: int,
    ) -> tuple[str, dict[str, Any]]:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        created_at = self._now()
        expires_at = created_at + timedelta(hours=expires_in_hours)
        share_id = str(uuid.uuid4())
        with self._connect() as connection:
            scope = self._scope(connection, workspace_id)
            connection.execute(
                """
                INSERT INTO dashboard_shares (
                    id,organization_id,project_id,token_hash,owner_user_id,workspace_id,
                    payload_json,created_at,expires_at,revoked_at
                ) VALUES (?,?,?,?,?,?,?,?,?,NULL)
                """,
                (
                    share_id,
                    scope.organization_id,
                    scope.project_id,
                    token_hash,
                    owner_user_id,
                    workspace_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    self._iso(created_at),
                    self._iso(expires_at),
                ),
            )
        return token, {
            "id": share_id,
            "organization_id": scope.organization_id,
            "project_id": scope.project_id,
            "owner_user_id": owner_user_id,
            "workspace_id": workspace_id,
            "payload": payload,
            "created_at": self._iso(created_at),
            "expires_at": self._iso(expires_at),
        }

    def get_share(self, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dashboard_shares WHERE token_hash=?",
                (token_hash,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= self._now():
            return None
        return {
            "id": row["id"],
            "organization_id": row["organization_id"],
            "project_id": row["project_id"],
            "owner_user_id": row["owner_user_id"],
            "workspace_id": row["workspace_id"],
            "payload": self._decode_json(row["payload_json"]),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }
