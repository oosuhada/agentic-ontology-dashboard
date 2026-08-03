"""PostgreSQL implementations for every active persistence repository.

Most repositories share the same conservative SQL contract as SQLite. The
compatibility connection supplies qmark conversion and transaction-scoped RLS;
only operations that begin from an opaque share token or fixed manufacturing
scope require explicit overrides.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher

from ontology_dashboard.adapters.prediction_repository import PredictionResultRepository
from ontology_dashboard.adapters.repository import AdapterRepository
from ontology_dashboard.projects.repository import ProjectRepository

from .dashboard_catalog import seed_templates
from .dashboard_repository import DashboardRepository
from .export_repository import ExportRepository
from .identity_repository import IdentityRepository
from .ontology_repository import OntologyActionRepository
from .repository import AuditRepository
from .role_workflow_repository import RoleWorkflowRepository
from .postgresql_compat import (
    PostgreSQLProjectContextResolver,
    postgres_repository_connection,
)


class PostgreSQLIdentityRepository(IdentityRepository):
    def __init__(
        self,
        database_url: str,
        *,
        password_hasher: PasswordHasher,
        seed_reference_data: bool = True,
    ) -> None:
        self.database_url = database_url
        self.path = database_url
        self.password_hasher = password_hasher
        if seed_reference_data:
            self._seed_reference_data()

    def _connect(self):
        return postgres_repository_connection(self.database_url, identity_access=True)

    def _initialize(self) -> None:
        return None


class PostgreSQLProjectRepository(ProjectRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )


class PostgreSQLDashboardRepository(DashboardRepository):
    def __init__(self, database_url: str, *, seed_templates: bool = True) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)
        self._template_cache = {}
        if seed_templates:
            self._seed_templates()

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )

    def _initialize(self) -> None:
        return None

    def _seed_templates(self) -> None:
        now = self._iso()
        for template in seed_templates():
            with self._connect() as connection:
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
                        INSERT INTO dashboard_templates (
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
                    template_id = template.template_id
                else:
                    template_id = existing["id"]
                seeded_version = connection.execute(
                    "SELECT 1 FROM dashboard_template_versions WHERE template_id=? AND version=?",
                    (template_id, template.version),
                ).fetchone()
                if seeded_version is None:
                    payload = template.model_copy(update={"template_id": template_id})
                    connection.execute(
                        """
                        INSERT INTO dashboard_template_versions (
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
                if existing is not None and int(existing["current_version"]) < template.version:
                    connection.execute(
                        """
                        UPDATE dashboard_templates
                        SET display_name=?,current_version=?,updated_at=?
                        WHERE id=?
                        """,
                        (template.display_name, template.version, now, template_id),
                    )

    def get_share(self, *, token: str) -> dict[str, Any] | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        scope = self.project_context.resolve_share(token_hash)
        if scope is None:
            return None
        with postgres_repository_connection(
            self.database_url,
            organization_id=scope.organization_id,
            project_id=scope.project_id,
            resolver=self.project_context,
        ) as connection:
            row = connection.execute(
                "SELECT * FROM dashboard_shares WHERE token_hash=?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return self._share_from_row(row)


class PostgreSQLRoleWorkflowRepository(RoleWorkflowRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )

    def _initialize(self) -> None:
        return None


class PostgreSQLExportRepository(ExportRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )

    def _initialize(self) -> None:
        return None


class PostgreSQLAdapterRepository(AdapterRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )


class PostgreSQLPredictionResultRepository(PredictionResultRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )


class PostgreSQLOntologyActionRepository(OntologyActionRepository):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = database_url
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            resolver=self.project_context,
        )

    def _initialize(self) -> None:
        return None


class PostgreSQLAuditRepository(AuditRepository):
    """Manufacturing regression activity store bound to its canonical Project."""

    def __init__(
        self,
        database_url: str,
        *,
        organization_id: str = "org-ontology-demo",
        project_id: str = "manufacturing-demo-project",
        workspace_id: str = "manufacturing-demo",
    ) -> None:
        self.database_url = database_url
        self.path = database_url
        self.organization_id = organization_id
        self.project_id = project_id
        self.workspace_id = workspace_id
        self.project_context = PostgreSQLProjectContextResolver(database_url)

    def _connect(self):
        return postgres_repository_connection(
            self.database_url,
            organization_id=self.organization_id,
            project_id=self.project_id,
            resolver=self.project_context,
        )

    def _initialize(self) -> None:
        return None

    def reset(self) -> None:
        with self._connect() as connection:
            for table in (
                "decisions",
                "notes",
                "conversations",
                "audit_log",
                "ontology_action_invocations",
            ):
                connection.execute(f"DELETE FROM {table}")


def is_postgresql(database: str | Path) -> bool:
    value = str(database)
    return value.startswith(("postgresql://", "postgresql+psycopg://"))


def seed_runtime_reference_data() -> bool:
    configured = os.getenv("ONTOLOGY_DASHBOARD_SEED_REFERENCE_DATA", "true")
    return configured.strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "PostgreSQLAdapterRepository",
    "PostgreSQLAuditRepository",
    "PostgreSQLDashboardRepository",
    "PostgreSQLExportRepository",
    "PostgreSQLIdentityRepository",
    "PostgreSQLOntologyActionRepository",
    "PostgreSQLPredictionResultRepository",
    "PostgreSQLProjectRepository",
    "PostgreSQLRoleWorkflowRepository",
    "is_postgresql",
    "seed_runtime_reference_data",
]
