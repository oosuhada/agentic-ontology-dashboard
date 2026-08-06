"""PostgreSQL implementations for every active persistence repository.

Most repositories share the same conservative SQL contract as SQLite. The
compatibility connection supplies qmark conversion and transaction-scoped RLS;
only operations that begin from an opaque share token or fixed manufacturing
scope require explicit overrides.
"""

from __future__ import annotations

import os
from pathlib import Path

from argon2 import PasswordHasher

from ontology_dashboard.adapters.prediction_repository import PredictionResultRepository
from ontology_dashboard.adapters.repository import AdapterRepository
from ontology_dashboard.projects.repository import ProjectRepository

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
    "PostgreSQLIdentityRepository",
    "PostgreSQLOntologyActionRepository",
    "PostgreSQLPredictionResultRepository",
    "PostgreSQLProjectRepository",
    "PostgreSQLRoleWorkflowRepository",
    "is_postgresql",
    "seed_runtime_reference_data",
]
