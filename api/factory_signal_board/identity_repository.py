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
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    domain_pack TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (organization_id) REFERENCES organizations(id)
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_organization_name TEXT,
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
                CREATE TABLE IF NOT EXISTS user_scopes (
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    PRIMARY KEY (user_id, workspace_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
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
                CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_admin_audit_created_at ON admin_audit(created_at);
                """
            )
        self._seed_reference_data()

    def _seed_reference_data(self) -> None:
        now = self._iso()
        organization_id = "org-ontology-demo"
        workspace_id = "manufacturing-demo"
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO organizations (id,slug,name,created_at) VALUES (?,?,?,?)",
                (organization_id, "ontology-demo", "Ontology Demo Organization", now),
            )
            connection.execute(
                "INSERT OR IGNORE INTO workspaces (id,organization_id,slug,display_name,domain_pack,created_at) VALUES (?,?,?,?,?,?)",
                (
                    workspace_id,
                    organization_id,
                    workspace_id,
                    "Manufacturing Demo",
                    "manufacturing-predictive-maintenance",
                    now,
                ),
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
        with self._connect() as connection:
            for account in DEMO_ACCOUNTS:
                email = account["email"].lower()
                existing = connection.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                if existing is not None:
                    continue
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
                connection.execute(
                    "INSERT INTO user_scopes (user_id,workspace_id) VALUES (?,?)",
                    (user_id, "manufacturing-demo"),
                )

    def create_pending_user(self, request: RegisterRequest) -> dict[str, Any]:
        now = self._iso()
        user_id = str(uuid.uuid4())
        email = request.email.lower()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users (
                        id,organization_id,email,display_name,status,requested_organization_name,
                        terms_accepted_at,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        user_id,
                        None,
                        email,
                        request.display_name,
                        "pending_approval",
                        request.organization_name,
                        now,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO password_credentials (user_id,password_hash,changed_at) VALUES (?,?,?)",
                    (user_id, self.password_hasher.hash(request.password), now),
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

    def create_session(self, user_id: str) -> tuple[str, datetime]:
        token = secrets.token_urlsafe(48)
        now = self._now()
        expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions (id,user_id,token_hash,created_at,expires_at,revoked_at) VALUES (?,?,?,?,?,NULL)",
                (
                    str(uuid.uuid4()),
                    user_id,
                    self._token_hash(token),
                    self._iso(now),
                    self._iso(expires_at),
                ),
            )
        return token, expires_at

    def revoke_session(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (self._iso(), self._token_hash(token)),
            )

    def user_for_session(self, token: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.*, s.expires_at, s.revoked_at
                FROM sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=?
                """,
                (self._token_hash(token),),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
        if datetime.fromisoformat(row["expires_at"]) <= self._now():
            self.revoke_session(token)
            raise AuthError(401, "session_expired", "세션이 만료되었습니다. 다시 로그인하세요.")
        if row["status"] != "active":
            raise AuthError(403, "account_inactive", "활성 계정만 접근할 수 있습니다.")
        return dict(row)

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
            scopes = [
                item["workspace_id"]
                for item in connection.execute(
                    "SELECT workspace_id FROM user_scopes WHERE user_id=? ORDER BY workspace_id",
                    (user_id,),
                )
            ]
        return {**dict(row), "roles": roles, "workspace_scopes": scopes}

    def principal(self, user_id: str) -> Principal:
        user = self.get_user(user_id)
        roles = user["roles"]
        with self._connect() as connection:
            permissions = sorted(
                {
                    row["permission_code"]
                    for row in connection.execute(
                        """
                        SELECT rp.permission_code
                        FROM role_permissions rp
                        JOIN user_roles ur ON ur.role_code=rp.role_code
                        WHERE ur.user_id=?
                        """,
                        (user_id,),
                    )
                }
            )
            scopes = user["workspace_scopes"]
            if "tenant_admin" in roles:
                scopes = [row["id"] for row in connection.execute("SELECT id FROM workspaces ORDER BY id")]
        primary_role = roles[0] if roles else "pending_approval"
        return Principal(
            user_id=user_id,
            email=user["email"],
            display_name=user["display_name"],
            status=user["status"],
            roles=roles,
            permissions=permissions,
            workspace_scopes=scopes,
            is_admin="tenant_admin" in roles,
            default_path="/admin" if "tenant_admin" in roles else "/app",
            landing_key=primary_role,
        )

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            ids = [row["id"] for row in connection.execute("SELECT id FROM users ORDER BY created_at DESC")]
        return [self.get_user(user_id) for user_id in ids]

    def list_roles(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT code,display_name,description FROM roles ORDER BY code").fetchall()
        return [dict(row) for row in rows]

    def list_workspaces(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,organization_id,slug,display_name,domain_pack FROM workspaces ORDER BY display_name"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_user(
        self,
        *,
        actor_user_id: str,
        target_user_id: str,
        request: AdminUserUpdateRequest,
    ) -> dict[str, Any]:
        before = self.get_user(target_user_id)
        if actor_user_id == target_user_id:
            if request.status == "disabled":
                raise AuthError(409, "self_lockout_blocked", "현재 관리자 계정은 스스로 비활성화할 수 없습니다.")
            if request.roles is not None and "tenant_admin" not in request.roles:
                raise AuthError(409, "self_lockout_blocked", "현재 관리자 계정에서 tenant_admin 역할을 제거할 수 없습니다.")

        if request.roles is not None:
            invalid_roles = sorted(set(request.roles) - set(ROLE_DEFINITIONS))
            if invalid_roles:
                raise AuthError(422, "invalid_role", f"알 수 없는 역할입니다: {', '.join(invalid_roles)}")
        if request.workspace_scopes is not None:
            valid_scopes = {workspace["id"] for workspace in self.list_workspaces()}
            invalid_scopes = sorted(set(request.workspace_scopes) - valid_scopes)
            if invalid_scopes:
                raise AuthError(
                    422,
                    "invalid_workspace_scope",
                    f"알 수 없는 workspace입니다: {', '.join(invalid_scopes)}",
                )

        now = self._iso()
        with self._connect() as connection:
            if request.status is not None:
                organization_id = before["organization_id"]
                if request.status == "active" and organization_id is None:
                    organization_id = "org-ontology-demo"
                connection.execute(
                    "UPDATE users SET status=?,organization_id=?,updated_at=? WHERE id=?",
                    (request.status, organization_id, now, target_user_id),
                )
            if request.roles is not None:
                connection.execute("DELETE FROM user_roles WHERE user_id=?", (target_user_id,))
                for role_code in sorted(set(request.roles)):
                    connection.execute(
                        "INSERT INTO user_roles (user_id,role_code) VALUES (?,?)",
                        (target_user_id, role_code),
                    )
            if request.workspace_scopes is not None:
                connection.execute("DELETE FROM user_scopes WHERE user_id=?", (target_user_id,))
                for workspace_id in sorted(set(request.workspace_scopes)):
                    connection.execute(
                        "INSERT INTO user_scopes (user_id,workspace_id) VALUES (?,?)",
                        (target_user_id, workspace_id),
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

    def list_admin_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
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
