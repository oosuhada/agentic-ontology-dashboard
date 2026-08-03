"""Canonical identity and project-membership repository implementation."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .identity_models import (
    DEMO_ACCOUNTS,
    PERMISSION_DEFINITIONS,
    ROLE_DEFINITIONS,
    ROLE_PERMISSIONS,
    SESSION_IDLE_MINUTES,
    SESSION_TTL_HOURS,
    AdminUserUpdateRequest,
    AuthError,
    Principal,
    RegisterRequest,
)


class IdentityRepository:
    def __init__(self, database_path: str | Path, *, password_hasher: PasswordHasher) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.password_hasher = password_hasher
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime | None = None) -> str:
        return (value or IdentityRepository._now()).isoformat()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    domain_pack_code TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    default_workspace_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    UNIQUE (organization_id, slug)
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    project_id TEXT,
                    slug TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    domain_pack TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_organization_name TEXT,
                    requested_role_code TEXT,
                    terms_accepted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id)
                );
                CREATE TABLE IF NOT EXISTS password_credentials (
                    user_id TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS roles (
                    code TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS permissions (
                    code TEXT PRIMARY KEY,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS role_permissions (
                    role_code TEXT NOT NULL,
                    permission_code TEXT NOT NULL,
                    PRIMARY KEY (role_code, permission_code),
                    FOREIGN KEY (role_code) REFERENCES roles(code) ON DELETE CASCADE,
                    FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS user_roles (
                    user_id TEXT NOT NULL,
                    role_code TEXT NOT NULL,
                    PRIMARY KEY (user_id, role_code),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (role_code) REFERENCES roles(code) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS user_permission_overrides (
                    user_id TEXT NOT NULL,
                    permission_code TEXT NOT NULL,
                    allowed INTEGER NOT NULL CHECK (allowed IN (0,1)),
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, permission_code),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS user_display_preferences (
                    user_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS user_scopes (
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, workspace_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS user_project_scopes (
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS project_memberships (
                    user_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS project_membership_roles (
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    role_code TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id, role_code),
                    FOREIGN KEY (user_id, project_id)
                        REFERENCES project_memberships(user_id, project_id) ON DELETE CASCADE,
                    FOREIGN KEY (role_code) REFERENCES roles(code)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    user_agent_hash TEXT,
                    ip_hash TEXT,
                    rotated_from TEXT,
                    active_project_id TEXT,
                    revoked_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS admin_audit (
                    id TEXT PRIMARY KEY,
                    actor_user_id TEXT NOT NULL,
                    target_user_id TEXT,
                    action TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (actor_user_id) REFERENCES users(id),
                    FOREIGN KEY (target_user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS admin_notifications (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT,
                    notification_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    target_user_id TEXT,
                    created_at TEXT NOT NULL,
                    read_at TEXT,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_admin_audit_created_at ON admin_audit(created_at);
                CREATE INDEX IF NOT EXISTS idx_admin_notifications_scope
                    ON admin_notifications(organization_id,read_at,created_at);
                """
            )
        self._ensure_user_columns()
        self._ensure_session_columns()
        self._ensure_project_layer()
        self._seed_reference_data()

    def _ensure_user_columns(self) -> None:
        with self._connect() as connection:
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "requested_role_code" not in existing:
                connection.execute("ALTER TABLE users ADD COLUMN requested_role_code TEXT")

    def _ensure_session_columns(self) -> None:
        expected = {
            "last_seen_at": "TEXT",
            "user_agent_hash": "TEXT",
            "ip_hash": "TEXT",
            "rotated_from": "TEXT",
            "active_project_id": "TEXT",
        }
        with self._connect() as connection:
            existing = {
                row["name"] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
            }
            for name, data_type in expected.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE sessions ADD COLUMN {name} {data_type}")
            connection.execute(
                "UPDATE sessions SET last_seen_at=created_at WHERE last_seen_at IS NULL"
            )

    def _ensure_project_layer(self) -> None:
        with self._connect() as connection:
            workspace_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(workspaces)").fetchall()
            }
            if "project_id" not in workspace_columns:
                connection.execute("ALTER TABLE workspaces ADD COLUMN project_id TEXT")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    domain_pack_code TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    default_workspace_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id),
                    UNIQUE (organization_id, slug)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_project_scopes (
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_memberships (
                    user_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS project_membership_roles (
                    user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    role_code TEXT NOT NULL,
                    PRIMARY KEY (user_id, project_id, role_code),
                    FOREIGN KEY (user_id, project_id)
                        REFERENCES project_memberships(user_id, project_id) ON DELETE CASCADE,
                    FOREIGN KEY (role_code) REFERENCES roles(code)
                );
                CREATE INDEX IF NOT EXISTS idx_project_memberships_scope
                    ON project_memberships(organization_id,project_id,status,user_id);
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspaces_project ON workspaces(organization_id,project_id,display_name)"
            )

    def _seed_reference_data(self) -> None:
        now = self._iso()
        organization_id = "org-ontology-demo"
        project_id = "manufacturing-demo-project"
        workspace_id = "manufacturing-demo"
        fixture_projects = (
            (
                project_id,
                "manufacturing-demo",
                "Manufacturing Demo Project",
                "Gold/E2E regression baseline for the manufacturing domain pack.",
                "manufacturing-predictive-maintenance",
                workspace_id,
                "Manufacturing Demo",
            ),
            (
                "azure-fleet-maintenance-project",
                "azure-fleet-maintenance",
                "Azure Fleet Maintenance",
                "Primary multi-source showcase Project for predictive fleet maintenance.",
                "azure-fleet-maintenance",
                "azure-fleet-maintenance",
                "Azure Fleet Maintenance Workspace",
            ),
            (
                "metropt-compressor-project",
                "metropt-compressor-monitoring",
                "MetroPT Compressor Monitoring",
                "Second abstraction-validation Project for compressor telemetry.",
                "metropt-compressor-monitoring",
                "metropt-compressor-monitoring",
                "MetroPT Compressor Workspace",
            ),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO organizations (id,slug,name,created_at) VALUES (?,?,?,?)",
                (organization_id, "ontology-demo", "Ontology Demo Organization", now),
            )
            for (
                fixture_project_id,
                project_slug,
                project_name,
                project_description,
                domain_pack_code,
                fixture_workspace_id,
                workspace_name,
            ) in fixture_projects:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO projects(
                        id,organization_id,slug,display_name,description,domain_pack_code,
                        status,default_workspace_id,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        fixture_project_id,
                        organization_id,
                        project_slug,
                        project_name,
                        project_description,
                        domain_pack_code,
                        "active",
                        fixture_workspace_id,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO workspaces(
                        id,organization_id,project_id,slug,display_name,domain_pack,created_at
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        fixture_workspace_id,
                        organization_id,
                        fixture_project_id,
                        project_slug,
                        workspace_name,
                        domain_pack_code,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE workspaces SET project_id=? WHERE id=? AND organization_id=?",
                    (fixture_project_id, fixture_workspace_id, organization_id),
                )
            for code, (display_name, description) in ROLE_DEFINITIONS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO roles (code,display_name,description) VALUES (?,?,?)",
                    (code, display_name, description),
                )
            for code, description in PERMISSION_DEFINITIONS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO permissions (code,description) VALUES (?,?)",
                    (code, description),
                )
            for role_code, permissions in ROLE_PERMISSIONS.items():
                for permission_code in permissions:
                    connection.execute(
                        "INSERT OR IGNORE INTO role_permissions (role_code,permission_code) VALUES (?,?)",
                        (role_code, permission_code),
                    )

    def seed_demo_accounts(self) -> None:
        now = self._iso()
        fixture_scopes = (
            ("manufacturing-demo", "manufacturing-demo-project"),
            ("azure-fleet-maintenance", "azure-fleet-maintenance-project"),
            ("metropt-compressor-monitoring", "metropt-compressor-project"),
        )
        with self._connect() as connection:
            for account in DEMO_ACCOUNTS:
                email = account["email"].lower()
                existing = connection.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                if existing is None:
                    user_id = str(uuid.uuid4())
                    connection.execute(
                        """
                        INSERT INTO users (
                            id,organization_id,email,display_name,status,requested_organization_name,
                            terms_accepted_at,created_at,updated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            user_id,
                            "org-ontology-demo",
                            email,
                            account["display_name"],
                            "active",
                            "Ontology Demo Organization",
                            now,
                            now,
                            now,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO password_credentials (user_id,password_hash,changed_at) VALUES (?,?,?)",
                        (user_id, self.password_hasher.hash(account["password"]), now),
                    )
                    for role_code in account["roles"]:
                        connection.execute(
                            "INSERT INTO user_roles (user_id,role_code) VALUES (?,?)",
                            (user_id, role_code),
                        )
                else:
                    user_id = str(existing["id"])
                for fixture_workspace_id, fixture_project_id in fixture_scopes:
                    connection.execute(
                        "INSERT OR IGNORE INTO user_scopes (user_id,workspace_id) VALUES (?,?)",
                        (user_id, fixture_workspace_id),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO user_project_scopes (user_id,project_id) VALUES (?,?)",
                        (user_id, fixture_project_id),
                    )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO project_memberships(
                            user_id,organization_id,project_id,status,created_at,updated_at
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            user_id,
                            "org-ontology-demo",
                            fixture_project_id,
                            "active",
                            now,
                            now,
                        ),
                    )
                    for role_code in account["roles"]:
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO project_membership_roles(
                                user_id,project_id,role_code
                            ) VALUES (?,?,?)
                            """,
                            (user_id, fixture_project_id, role_code),
                        )
            connection.execute(
                """
                INSERT OR IGNORE INTO user_project_scopes(user_id,project_id)
                SELECT us.user_id,w.project_id
                FROM user_scopes us
                JOIN workspaces w ON w.id=us.workspace_id
                WHERE w.project_id IS NOT NULL
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO project_memberships(
                    user_id,organization_id,project_id,status,created_at,updated_at
                )
                SELECT ups.user_id,u.organization_id,ups.project_id,'active',?,?
                FROM user_project_scopes ups
                JOIN users u ON u.id=ups.user_id
                """,
                (now, now),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO project_membership_roles(user_id,project_id,role_code)
                SELECT pm.user_id,pm.project_id,ur.role_code
                FROM project_memberships pm
                JOIN user_roles ur ON ur.user_id=pm.user_id
                """
            )

    def create_pending_user(self, request: RegisterRequest) -> dict[str, Any]:
        now = self._iso()
        user_id = str(uuid.uuid4())
        email = request.email.lower()
        try:
            with self._connect() as connection:
                matched_organization = connection.execute(
                    "SELECT id FROM organizations WHERE lower(name)=lower(?) ORDER BY created_at LIMIT 1",
                    (request.organization_name,),
                ).fetchone()
                if matched_organization is None:
                    candidates = connection.execute(
                        "SELECT id FROM organizations ORDER BY created_at LIMIT 2"
                    ).fetchall()
                    matched_organization = candidates[0] if len(candidates) == 1 else None
                notification_organization_id = (
                    str(matched_organization["id"]) if matched_organization is not None else None
                )
                connection.execute(
                    """
                    INSERT INTO users (
                        id,organization_id,email,display_name,status,requested_organization_name,
                        requested_role_code,terms_accepted_at,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        user_id,
                        None,
                        email,
                        request.display_name,
                        "pending_approval",
                        request.organization_name,
                        request.requested_role,
                        now,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO password_credentials (user_id,password_hash,changed_at) VALUES (?,?,?)",
                    (user_id, self.password_hasher.hash(request.password), now),
                )
                connection.execute(
                    """
                    INSERT INTO admin_notifications (
                        id,organization_id,notification_type,title,body,target_user_id,created_at,read_at
                    ) VALUES (?,?,?,?,?,?,?,NULL)
                    """,
                    (
                        str(uuid.uuid4()),
                        notification_organization_id,
                        "signup_request",
                        "신규 가입 승인 요청",
                        f"{request.display_name} ({email}) · 희망 역할 {request.requested_role}",
                        user_id,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthError(409, "email_already_registered", "이미 가입된 이메일입니다.") from exc
        return self.get_user(user_id)

    def authenticate(self, email: str, password: str) -> dict[str, Any]:
        normalized_email = email.lower()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.*, pc.password_hash
                FROM users u
                JOIN password_credentials pc ON pc.user_id=u.id
                WHERE u.email=?
                """,
                (normalized_email,),
            ).fetchone()
        if row is None:
            raise AuthError(401, "invalid_credentials", "이메일 또는 비밀번호가 올바르지 않습니다.")
        try:
            verified = self.password_hasher.verify(row["password_hash"], password)
        except (VerifyMismatchError, InvalidHashError):
            verified = False
        if not verified:
            raise AuthError(401, "invalid_credentials", "이메일 또는 비밀번호가 올바르지 않습니다.")
        if row["status"] == "pending_approval":
            raise AuthError(403, "pending_approval", "관리자 승인을 기다리는 계정입니다.")
        if row["status"] == "disabled":
            raise AuthError(403, "account_disabled", "비활성화된 계정입니다. 관리자에게 문의하세요.")
        return dict(row)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(
        self,
        user_id: str,
        *,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
        rotated_from: str | None = None,
        active_project_id: str | None = None,
    ) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(48)
        now = self._now()
        expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id,user_id,token_hash,created_at,last_seen_at,expires_at,
                    user_agent_hash,ip_hash,rotated_from,active_project_id,revoked_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,NULL)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    self._token_hash(token),
                    self._iso(now),
                    self._iso(now),
                    self._iso(expires_at),
                    user_agent_hash,
                    ip_hash,
                    rotated_from,
                    active_project_id,
                ),
            )
        return token, expires_at

    def revoke_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (self._iso(), self._token_hash(token)),
            )

    def set_session_active_project(
        self,
        token: str,
        *,
        user_id: str,
        project_id: str,
    ) -> None:
        token_hash = self._token_hash(token)
        with self._connect() as connection:
            allowed = connection.execute(
                """
                SELECT 1
                FROM user_project_scopes ups
                JOIN projects p ON p.id=ups.project_id
                JOIN users u ON u.id=ups.user_id
                WHERE ups.user_id=? AND ups.project_id=?
                  AND p.organization_id=u.organization_id
                  AND p.status<>'archived'
                """,
                (user_id, project_id),
            ).fetchone()
            if allowed is None:
                roles = {
                    row["role_code"]
                    for row in connection.execute(
                        "SELECT role_code FROM user_roles WHERE user_id=?",
                        (user_id,),
                    ).fetchall()
                }
                if "tenant_admin" in roles:
                    allowed = connection.execute(
                        """
                        SELECT 1 FROM projects p
                        JOIN users u ON u.organization_id=p.organization_id
                        WHERE u.id=? AND p.id=? AND p.status<>'archived'
                        """,
                        (user_id, project_id),
                    ).fetchone()
            if allowed is None:
                raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
            cursor = connection.execute(
                """
                UPDATE sessions SET active_project_id=?,last_seen_at=?
                WHERE token_hash=? AND user_id=? AND revoked_at IS NULL
                """,
                (project_id, self._iso(), token_hash, user_id),
            )
            if cursor.rowcount == 0:
                raise AuthError(401, "authentication_required", "로그인이 필요합니다.")

    def user_for_session(
        self,
        token: str,
        *,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
        touch: bool = True,
    ) -> dict[str, Any]:
        token_hash = self._token_hash(token)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.*, s.id AS session_id, s.created_at AS session_created_at,
                       s.last_seen_at, s.expires_at, s.revoked_at,
                       s.user_agent_hash, s.ip_hash, s.rotated_from, s.active_project_id
                FROM sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=?
                """,
                (token_hash,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
        now = self._now()
        if datetime.fromisoformat(row["expires_at"]) <= now:
            self.revoke_session(token)
            raise AuthError(401, "session_expired", "세션이 만료되었습니다. 다시 로그인하세요.")
        last_seen_at = datetime.fromisoformat(row["last_seen_at"] or row["session_created_at"])
        if last_seen_at + timedelta(minutes=SESSION_IDLE_MINUTES) <= now:
            self.revoke_session(token)
            raise AuthError(401, "session_idle_timeout", "오랫동안 사용하지 않아 세션이 만료되었습니다.")
        if row["user_agent_hash"] and user_agent_hash and row["user_agent_hash"] != user_agent_hash:
            self.revoke_session(token)
            raise AuthError(401, "session_client_mismatch", "세션의 클라이언트 정보가 일치하지 않습니다.")
        if row["ip_hash"] and ip_hash and row["ip_hash"] != ip_hash:
            # IP changes are recorded but not fatal because mobile and corporate networks can legitimately rotate addresses.
            ip_hash = row["ip_hash"]
        if row["status"] != "active":
            raise AuthError(403, "account_inactive", "활성 계정만 접근할 수 있습니다.")
        if touch and (now - last_seen_at).total_seconds() >= 60:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE token_hash=? AND revoked_at IS NULL",
                    (self._iso(now), token_hash),
                )
        return dict(row)

    def rotate_session(
        self,
        token: str,
        *,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
    ) -> tuple[str, datetime, dict[str, Any]]:
        current = self.user_for_session(
            token,
            user_agent_hash=user_agent_hash,
            ip_hash=ip_hash,
            touch=False,
        )
        self.revoke_session(token)
        new_token, expires_at = self.create_session(
            current["id"],
            user_agent_hash=user_agent_hash or current.get("user_agent_hash"),
            ip_hash=ip_hash or current.get("ip_hash"),
            rotated_from=current["session_id"],
            active_project_id=current.get("active_project_id"),
        )
        return new_token, expires_at, current

    def list_active_sessions(self, *, user_id: str, current_token: str | None = None) -> list[dict[str, Any]]:
        current_hash = self._token_hash(current_token) if current_token else None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id,token_hash,created_at,last_seen_at,expires_at,
                       user_agent_hash,ip_hash,rotated_from
                FROM sessions
                WHERE user_id=? AND revoked_at IS NULL AND expires_at>?
                ORDER BY last_seen_at DESC
                """,
                (user_id, self._iso()),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"],
                "expires_at": row["expires_at"],
                "user_agent_bound": bool(row["user_agent_hash"]),
                "ip_observed": bool(row["ip_hash"]),
                "rotated_from": row["rotated_from"],
                "current": current_hash is not None and row["token_hash"] == current_hash,
            }
            for row in rows
        ]

    def revoke_other_sessions(self, *, user_id: str, current_token: str) -> int:
        now = self._iso()
        current_hash = self._token_hash(current_token)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions
                SET revoked_at=?
                WHERE user_id=? AND token_hash<>? AND revoked_at IS NULL
                """,
                (now, user_id, current_hash),
            )
        return int(cursor.rowcount)

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.*, o.name AS organization_name
                FROM users u
                LEFT JOIN organizations o ON o.id=u.organization_id
                WHERE u.id=?
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                raise AuthError(404, "user_not_found", "사용자를 찾을 수 없습니다.")
            roles = [
                item["role_code"]
                for item in connection.execute(
                    "SELECT role_code FROM user_roles WHERE user_id=? ORDER BY role_code",
                    (user_id,),
                )
            ]
            permission_overrides = {
                item["permission_code"]: bool(item["allowed"])
                for item in connection.execute(
                    """
                    SELECT permission_code,allowed
                    FROM user_permission_overrides
                    WHERE user_id=?
                    ORDER BY permission_code
                    """,
                    (user_id,),
                )
            }
            effective_permissions = {
                item["permission_code"]
                for role_code in roles
                for item in connection.execute(
                    "SELECT permission_code FROM role_permissions WHERE role_code=?",
                    (role_code,),
                )
            }
            for permission_code, allowed in permission_overrides.items():
                if allowed:
                    effective_permissions.add(permission_code)
                else:
                    effective_permissions.discard(permission_code)
            scopes = [
                item["workspace_id"]
                for item in connection.execute(
                    "SELECT workspace_id FROM user_scopes WHERE user_id=? ORDER BY workspace_id",
                    (user_id,),
                )
            ]
            membership_rows = connection.execute(
                """
                SELECT project_id,status
                FROM project_memberships
                WHERE user_id=?
                ORDER BY project_id
                """,
                (user_id,),
            ).fetchall()
            project_scopes = [
                item["project_id"]
                for item in membership_rows
                if item["status"] == "active"
            ]
            if not membership_rows:
                project_scopes = [
                    item["project_id"]
                    for item in connection.execute(
                        "SELECT project_id FROM user_project_scopes WHERE user_id=? ORDER BY project_id",
                        (user_id,),
                    )
                ]
            project_roles: dict[str, list[str]] = {}
            for item in connection.execute(
                """
                SELECT pmr.project_id,pmr.role_code
                FROM project_membership_roles pmr
                JOIN project_memberships pm
                  ON pm.user_id=pmr.user_id AND pm.project_id=pmr.project_id
                WHERE pmr.user_id=? AND pm.status='active'
                ORDER BY pmr.project_id,pmr.role_code
                """,
                (user_id,),
            ):
                project_roles.setdefault(item["project_id"], []).append(item["role_code"])
            if not project_roles:
                project_roles = {project_id: list(roles) for project_id in project_scopes}
        return {
            **dict(row),
            "roles": roles,
            "permission_overrides": permission_overrides,
            "effective_permissions": sorted(effective_permissions),
            "workspace_scopes": scopes,
            "project_scopes": project_scopes,
            "project_roles": project_roles,
        }

    def principal(self, user_id: str, *, active_project_id: str | None = None) -> Principal:
        user = self.get_user(user_id)
        global_roles = user["roles"]
        scopes = user["workspace_scopes"]
        project_scopes = user["project_scopes"]
        with self._connect() as connection:
            if "tenant_admin" in global_roles:
                scopes = [
                    row["id"]
                    for row in connection.execute(
                        "SELECT id FROM workspaces WHERE organization_id=? ORDER BY id",
                        (user["organization_id"],),
                    )
                ]
                project_scopes = [
                    row["id"]
                    for row in connection.execute(
                        "SELECT id FROM projects WHERE organization_id=? AND status<>'archived' ORDER BY id",
                        (user["organization_id"],),
                    )
                ]
        project_roles = {
            project_id: list(role_codes)
            for project_id, role_codes in user.get("project_roles", {}).items()
            if project_id in project_scopes
        }
        if "tenant_admin" in global_roles:
            for project_id in project_scopes:
                role_codes = project_roles.setdefault(project_id, [])
                if "tenant_admin" not in role_codes:
                    role_codes.append("tenant_admin")
                    role_codes.sort()
        organization_id = user.get("organization_id")
        if not organization_id:
            raise AuthError(403, "organization_required", "조직에 할당된 활성 계정만 접근할 수 있습니다.")
        default_project_id = (
            "manufacturing-demo-project"
            if "manufacturing-demo-project" in project_scopes
            else (project_scopes[0] if project_scopes else None)
        )
        resolved_active_project_id = (
            active_project_id if active_project_id in project_scopes else default_project_id
        )
        active_project_roles = (
            list(project_roles.get(resolved_active_project_id, []))
            if resolved_active_project_id
            else list(global_roles)
        )
        if not active_project_roles and resolved_active_project_id:
            active_project_roles = list(global_roles)
        with self._connect() as connection:
            permissions = sorted(
                {
                    row["permission_code"]
                    for role_code in active_project_roles
                    for row in connection.execute(
                        """
                        SELECT permission_code
                        FROM role_permissions
                        WHERE role_code=?
                        """,
                        (role_code,),
                    )
                }
            )
            permission_overrides = {
                row["permission_code"]: bool(row["allowed"])
                for row in connection.execute(
                    """
                    SELECT permission_code,allowed
                    FROM user_permission_overrides
                    WHERE user_id=?
                    """,
                    (user_id,),
                )
            }
        resolved_permissions = set(permissions)
        for permission_code, allowed in permission_overrides.items():
            if allowed:
                resolved_permissions.add(permission_code)
            else:
                resolved_permissions.discard(permission_code)
        permissions = sorted(resolved_permissions)
        primary_role = active_project_roles[0] if active_project_roles else "pending_approval"
        return Principal(
            user_id=user_id,
            organization_id=organization_id,
            email=user["email"],
            display_name=user["display_name"],
            status=user["status"],
            roles=active_project_roles,
            permissions=permissions,
            workspace_scopes=scopes,
            project_scopes=project_scopes,
            project_roles=project_roles,
            active_project_id=resolved_active_project_id,
            active_project_roles=active_project_roles,
            is_admin="tenant_admin" in active_project_roles,
            default_path="/admin" if "tenant_admin" in active_project_roles else "/app",
            landing_key=primary_role,
        )

    def list_users(
        self,
        *,
        organization_id: str | None = None,
        include_unassigned_pending: bool = False,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if organization_id is None:
                rows = connection.execute("SELECT id FROM users ORDER BY created_at DESC").fetchall()
            elif include_unassigned_pending:
                rows = connection.execute(
                    """
                    SELECT id FROM users
                    WHERE organization_id=? OR (organization_id IS NULL AND status='pending_approval')
                    ORDER BY created_at DESC
                    """,
                    (organization_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id FROM users WHERE organization_id=? ORDER BY created_at DESC",
                    (organization_id,),
                ).fetchall()
            ids = [row["id"] for row in rows]
        return [self.get_user(user_id) for user_id in ids]

    def list_roles(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT code,display_name,description FROM roles ORDER BY code").fetchall()
            return [
                {
                    **dict(row),
                    "permissions": [
                        item["permission_code"]
                        for item in connection.execute(
                            """
                            SELECT permission_code FROM role_permissions
                            WHERE role_code=? ORDER BY permission_code
                            """,
                            (row["code"],),
                        )
                    ],
                }
                for row in rows
            ]

    def list_workspaces(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if organization_id is not None:
            clauses.append("organization_id=?")
            parameters.append(organization_id)
        if project_id is not None:
            clauses.append("project_id=?")
            parameters.append(project_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,organization_id,project_id,slug,display_name,domain_pack FROM workspaces"
                f"{where} ORDER BY display_name",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_project_members(
        self,
        *,
        organization_id: str,
        project_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id=? AND organization_id=?",
                (project_id, organization_id),
            ).fetchone()
            if project is None:
                raise AuthError(404, "project_not_found", "Project를 찾을 수 없습니다.")
            rows = connection.execute(
                """
                SELECT pm.user_id,pm.organization_id,pm.project_id,pm.status,
                       pm.created_at,pm.updated_at,u.email,u.display_name,u.status AS user_status
                FROM project_memberships pm
                JOIN users u ON u.id=pm.user_id
                WHERE pm.organization_id=? AND pm.project_id=?
                ORDER BY u.display_name,u.email
                """,
                (organization_id, project_id),
            ).fetchall()
            items: list[dict[str, Any]] = []
            for row in rows:
                roles = [
                    item["role_code"]
                    for item in connection.execute(
                        """
                        SELECT role_code FROM project_membership_roles
                        WHERE user_id=? AND project_id=?
                        ORDER BY role_code
                        """,
                        (row["user_id"], project_id),
                    )
                ]
                items.append({**dict(row), "roles": roles})
        return items

    def update_project_membership(
        self,
        *,
        actor_user_id: str,
        organization_id: str,
        project_id: str,
        target_user_id: str,
        status: str,
        roles: list[str],
    ) -> dict[str, Any]:
        invalid_roles = sorted(set(roles) - set(ROLE_DEFINITIONS))
        if invalid_roles:
            raise AuthError(422, "invalid_role", f"알 수 없는 역할입니다: {', '.join(invalid_roles)}")
        if not roles:
            raise AuthError(422, "role_required", "Project membership에는 역할이 하나 이상 필요합니다.")
        now = self._iso()
        with self._connect() as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id=? AND organization_id=? AND status<>'archived'",
                (project_id, organization_id),
            ).fetchone()
            user = connection.execute(
                "SELECT id,email,display_name,status FROM users WHERE id=? AND organization_id=?",
                (target_user_id, organization_id),
            ).fetchone()
            if project is None:
                raise AuthError(404, "project_not_found", "Project를 찾을 수 없습니다.")
            if user is None:
                raise AuthError(404, "user_not_found", "사용자를 찾을 수 없습니다.")
            if actor_user_id == target_user_id and (
                status != "active" or "tenant_admin" not in roles
            ):
                actor_roles = {
                    item["role_code"]
                    for item in connection.execute(
                        """
                        SELECT role_code FROM project_membership_roles
                        WHERE user_id=? AND project_id=?
                        """,
                        (actor_user_id, project_id),
                    )
                }
                if "tenant_admin" in actor_roles:
                    raise AuthError(
                        409,
                        "self_lockout_blocked",
                        "현재 Project 관리자 membership을 스스로 제거할 수 없습니다.",
                    )
            before_rows = self.list_project_members(
                organization_id=organization_id,
                project_id=project_id,
            )
            before = next(
                (item for item in before_rows if item["user_id"] == target_user_id),
                None,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO project_memberships(
                    user_id,organization_id,project_id,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (target_user_id, organization_id, project_id, status, now, now),
            )
            connection.execute(
                """
                UPDATE project_memberships
                SET status=?,updated_at=?
                WHERE user_id=? AND organization_id=? AND project_id=?
                """,
                (status, now, target_user_id, organization_id, project_id),
            )
            connection.execute(
                "DELETE FROM project_membership_roles WHERE user_id=? AND project_id=?",
                (target_user_id, project_id),
            )
            for role_code in sorted(set(roles)):
                connection.execute(
                    """
                    INSERT INTO project_membership_roles(user_id,project_id,role_code)
                    VALUES (?,?,?)
                    """,
                    (target_user_id, project_id, role_code),
                )
            if status == "active":
                connection.execute(
                    "INSERT OR IGNORE INTO user_project_scopes(user_id,project_id) VALUES (?,?)",
                    (target_user_id, project_id),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO user_scopes(user_id,workspace_id)
                    SELECT ?,id FROM workspaces
                    WHERE organization_id=? AND project_id=?
                    """,
                    (target_user_id, organization_id, project_id),
                )
            else:
                connection.execute(
                    "DELETE FROM user_project_scopes WHERE user_id=? AND project_id=?",
                    (target_user_id, project_id),
                )
                connection.execute(
                    """
                    DELETE FROM user_scopes
                    WHERE user_id=? AND workspace_id IN (
                        SELECT id FROM workspaces WHERE organization_id=? AND project_id=?
                    )
                    """,
                    (target_user_id, organization_id, project_id),
                )
                connection.execute(
                    """
                    UPDATE sessions SET active_project_id=NULL
                    WHERE user_id=? AND active_project_id=? AND revoked_at IS NULL
                    """,
                    (target_user_id, project_id),
                )
        after = next(
            item
            for item in self.list_project_members(
                organization_id=organization_id,
                project_id=project_id,
            )
            if item["user_id"] == target_user_id
        )
        self.record_admin_audit(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action="project.membership.updated",
            before=before or {},
            after=after,
        )
        return after

    def update_user(
        self,
        *,
        actor_user_id: str,
        target_user_id: str,
        request: AdminUserUpdateRequest,
        organization_id: str | None = None,
    ) -> dict[str, Any]:
        tenant_organization_id = organization_id
        before = self.get_user(target_user_id)
        if (
            tenant_organization_id is not None
            and before.get("organization_id") not in {None, tenant_organization_id}
        ):
            raise AuthError(404, "user_not_found", "사용자를 찾을 수 없습니다.")
        if actor_user_id == target_user_id:
            if request.status == "disabled":
                raise AuthError(409, "self_lockout_blocked", "현재 관리자 계정은 스스로 비활성화할 수 없습니다.")
            if request.roles is not None and "tenant_admin" not in request.roles:
                raise AuthError(409, "self_lockout_blocked", "현재 관리자 계정에서 tenant_admin 역할을 제거할 수 없습니다.")
            if request.permission_overrides is not None:
                protected = {"admin.access", "admin.users.read", "admin.users.manage"}
                if any(
                    permission in protected and not allowed
                    for permission, allowed in request.permission_overrides.items()
                ):
                    raise AuthError(
                        409,
                        "self_lockout_blocked",
                        "현재 관리자 계정의 핵심 관리자 권한을 차단할 수 없습니다.",
                    )

        if request.roles is not None:
            invalid_roles = sorted(set(request.roles) - set(ROLE_DEFINITIONS))
            if invalid_roles:
                raise AuthError(422, "invalid_role", f"알 수 없는 역할입니다: {', '.join(invalid_roles)}")
        if request.workspace_scopes is not None:
            valid_scopes = {
                workspace["id"]
                for workspace in self.list_workspaces(organization_id=tenant_organization_id)
            }
            invalid_scopes = sorted(set(request.workspace_scopes) - valid_scopes)
            if invalid_scopes:
                raise AuthError(
                    422,
                    "invalid_workspace_scope",
                    f"알 수 없는 workspace입니다: {', '.join(invalid_scopes)}",
                )
        if request.permission_overrides is not None:
            invalid_permissions = sorted(
                set(request.permission_overrides) - set(PERMISSION_DEFINITIONS)
            )
            if invalid_permissions:
                raise AuthError(
                    422,
                    "invalid_permission",
                    f"알 수 없는 권한입니다: {', '.join(invalid_permissions)}",
                )

        now = self._iso()
        with self._connect() as connection:
            if request.status is not None:
                target_organization_id = before["organization_id"]
                if request.status == "active" and target_organization_id is None:
                    if tenant_organization_id is None:
                        raise AuthError(
                            422,
                            "organization_required",
                            "활성화할 조직을 확인할 수 없습니다.",
                        )
                    target_organization_id = tenant_organization_id
                connection.execute(
                    "UPDATE users SET status=?,organization_id=?,updated_at=? WHERE id=?",
                    (request.status, target_organization_id, now, target_user_id),
                )
            if request.roles is not None:
                connection.execute("DELETE FROM user_roles WHERE user_id=?", (target_user_id,))
                for role_code in sorted(set(request.roles)):
                    connection.execute(
                        "INSERT INTO user_roles (user_id,role_code) VALUES (?,?)",
                        (target_user_id, role_code),
                    )
            if request.permission_overrides is not None:
                connection.execute(
                    "DELETE FROM user_permission_overrides WHERE user_id=?",
                    (target_user_id,),
                )
                for permission_code, allowed in sorted(request.permission_overrides.items()):
                    connection.execute(
                        """
                        INSERT INTO user_permission_overrides(
                            user_id,permission_code,allowed,updated_at
                        ) VALUES (?,?,?,?)
                        """,
                        (target_user_id, permission_code, int(allowed), now),
                    )
            if request.workspace_scopes is not None:
                connection.execute("DELETE FROM user_scopes WHERE user_id=?", (target_user_id,))
                connection.execute("DELETE FROM user_project_scopes WHERE user_id=?", (target_user_id,))
                for workspace_id in sorted(set(request.workspace_scopes)):
                    connection.execute(
                        "INSERT INTO user_scopes (user_id,workspace_id) VALUES (?,?)",
                        (target_user_id, workspace_id),
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO user_project_scopes(user_id,project_id)
                    SELECT ?,project_id FROM workspaces
                    WHERE id IN (SELECT workspace_id FROM user_scopes WHERE user_id=?)
                      AND project_id IS NOT NULL
                    """,
                    (target_user_id, target_user_id),
                )
                selected_projects = {
                    item["project_id"]
                    for item in connection.execute(
                        "SELECT project_id FROM user_project_scopes WHERE user_id=?",
                        (target_user_id,),
                    )
                }
                membership_projects = {
                    item["project_id"]
                    for item in connection.execute(
                        "SELECT project_id FROM project_memberships WHERE user_id=?",
                        (target_user_id,),
                    )
                }
                target_organization_id = before.get("organization_id") or tenant_organization_id
                for project_id in sorted(selected_projects):
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO project_memberships(
                            user_id,organization_id,project_id,status,created_at,updated_at
                        ) VALUES (?,?,?,?,?,?)
                        """,
                        (
                            target_user_id,
                            target_organization_id,
                            project_id,
                            "active",
                            now,
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE project_memberships SET status='active',updated_at=?
                        WHERE user_id=? AND project_id=?
                        """,
                        (now, target_user_id, project_id),
                    )
                for project_id in sorted(membership_projects - selected_projects):
                    connection.execute(
                        """
                        UPDATE project_memberships SET status='suspended',updated_at=?
                        WHERE user_id=? AND project_id=?
                        """,
                        (now, target_user_id, project_id),
                    )
            if request.roles is not None:
                active_projects = [
                    item["project_id"]
                    for item in connection.execute(
                        """
                        SELECT project_id FROM project_memberships
                        WHERE user_id=? AND status='active'
                        """,
                        (target_user_id,),
                    )
                ]
                for project_id in active_projects:
                    connection.execute(
                        "DELETE FROM project_membership_roles WHERE user_id=? AND project_id=?",
                        (target_user_id, project_id),
                    )
                    for role_code in sorted(set(request.roles)):
                        connection.execute(
                            """
                            INSERT INTO project_membership_roles(user_id,project_id,role_code)
                            VALUES (?,?,?)
                            """,
                            (target_user_id, project_id, role_code),
                        )
            if request.status == "active":
                connection.execute(
                    """
                    UPDATE admin_notifications
                    SET read_at=COALESCE(read_at,?)
                    WHERE target_user_id=? AND notification_type='signup_request'
                    """,
                    (now, target_user_id),
                )

        after = self.get_user(target_user_id)
        self.record_admin_audit(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action="user.access.updated",
            before=before,
            after=after,
        )
        return after

    def list_admin_notifications(
        self,
        *,
        organization_id: str,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["(n.organization_id=? OR n.organization_id IS NULL)"]
        parameters: list[Any] = [organization_id]
        if unread_only:
            clauses.append("n.read_at IS NULL")
        parameters.append(max(1, min(limit, 500)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT n.*,u.email AS target_email,u.display_name AS target_display_name,
                       u.requested_role_code
                FROM admin_notifications n
                LEFT JOIN users u ON u.id=n.target_user_id
                WHERE {' AND '.join(clauses)}
                ORDER BY n.created_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_admin_notification_read(
        self,
        *,
        organization_id: str,
        notification_id: str,
    ) -> dict[str, Any]:
        now = self._iso()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM admin_notifications
                WHERE id=? AND (organization_id=? OR organization_id IS NULL)
                """,
                (notification_id, organization_id),
            ).fetchone()
            if row is None:
                raise AuthError(404, "notification_not_found", "관리자 알림을 찾을 수 없습니다.")
            connection.execute(
                "UPDATE admin_notifications SET read_at=COALESCE(read_at,?) WHERE id=?",
                (now, notification_id),
            )
        return next(
            item
            for item in self.list_admin_notifications(
                organization_id=organization_id,
                limit=500,
            )
            if item["id"] == notification_id
        )

    def get_display_preferences(self, *, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json,updated_at FROM user_display_preferences WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            return None
        return {**payload, "updated_at": row["updated_at"]}

    def save_display_preferences(
        self,
        *,
        user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_display_preferences(user_id,payload_json,updated_at)
                VALUES (?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (user_id, json.dumps(payload, ensure_ascii=False), now),
            )
        return {**payload, "updated_at": now}

    def record_admin_audit(
        self,
        *,
        actor_user_id: str,
        target_user_id: str | None,
        action: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_audit (id,actor_user_id,target_user_id,action,before_json,after_json,created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    actor_user_id,
                    target_user_id,
                    action,
                    json.dumps(before, ensure_ascii=False, sort_keys=True),
                    json.dumps(after, ensure_ascii=False, sort_keys=True),
                    self._iso(),
                ),
            )

    def list_admin_audit(
        self,
        *,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if organization_id is None:
                rows = connection.execute(
                    """
                    SELECT a.*, actor.email AS actor_email, target.email AS target_email
                    FROM admin_audit a
                    JOIN users actor ON actor.id=a.actor_user_id
                    LEFT JOIN users target ON target.id=a.target_user_id
                    ORDER BY a.created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT a.*, actor.email AS actor_email, target.email AS target_email
                    FROM admin_audit a
                    JOIN users actor ON actor.id=a.actor_user_id
                    LEFT JOIN users target ON target.id=a.target_user_id
                    WHERE actor.organization_id=?
                    ORDER BY a.created_at DESC
                    LIMIT ?
                    """,
                    (organization_id, limit),
                ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["before"] = json.loads(item.pop("before_json"))
            item["after"] = json.loads(item.pop("after_json"))
            result.append(item)
        return result

    def password_hash_for_email(self, email: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT pc.password_hash
                FROM password_credentials pc
                JOIN users u ON u.id=pc.user_id
                WHERE u.email=?
                """,
                (email.lower(),),
            ).fetchone()
        return None if row is None else str(row["password_hash"])
