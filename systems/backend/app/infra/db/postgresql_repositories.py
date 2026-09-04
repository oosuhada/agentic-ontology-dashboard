"""PostgreSQL implementations for every active persistence repository.

Most repositories share the same conservative SQL contract as SQLite. The
compatibility connection supplies qmark conversion and transaction-scoped RLS;
only operations that begin from an opaque share token or fixed manufacturing
scope require explicit overrides.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher

from app.infra.db.prediction_result_repository import PredictionResultRepository
from app.infra.db.dataset_ingestion_repository import DatasetIngestionRepository as AdapterRepository
from app.infra.db.project_repository import ProjectRepository

from app.dashboard.catalog import seed_templates
from app.infra.db.dashboard_repository import DashboardRepository
from app.infra.db.identity_repository import IdentityRepository as SQLIdentityRepository
from app.infra.db.report_repository import ExportRepository
from app.infra.db.ontology_action_repository import OntologyActionRepository
from app.infra.db.operations_audit_repository import AuditRepository
from .role_workflow_repository import RoleWorkflowRepository
from .postgresql_compat import (
    PostgreSQLProjectContextResolver,
    postgres_repository_connection,
)


class PostgreSQLIdentityRepository(SQLIdentityRepository):
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
                    INSERT INTO dashboard_templates (
                        id,organization_id,project_id,workspace_id,role_code,display_name,
                        current_version,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT (project_id,workspace_id,role_code) DO UPDATE SET
                        display_name=EXCLUDED.display_name,
                        current_version=GREATEST(
                            dashboard_templates.current_version,
                            EXCLUDED.current_version
                        ),
                        updated_at=EXCLUDED.updated_at
                    RETURNING id,current_version
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
                ).fetchone()
                template_id = existing["id"]
                payload = template.model_copy(update={"template_id": template_id})
                connection.execute(
                    """
                    INSERT INTO dashboard_template_versions (
                        id,template_id,version,status,payload_json,created_by,created_at
                    ) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT (template_id,version) DO NOTHING
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

    def expire_stale_agent_review_workflow_run(self, **filters: Any) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        trace = {
            "stage": "expired",
            "reason": "stale_running_lease",
            "expired_before": str(filters["started_before"]),
        }
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE agent_review_workflow_runs
                SET status=?,
                    completed_at=?,
                    updated_at=?,
                    error_type=?,
                    error_message=?,
                    trace_json=?
                WHERE workflow_run_id = (
                    SELECT workflow_run_id
                    FROM agent_review_workflow_runs
                    WHERE organization_id=?
                      AND project_id=?
                      AND workspace_id=?
                      AND summary_key=?
                      AND status='running'
                      AND started_at<=?
                    ORDER BY started_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
                """,
                (
                    "failed",
                    now,
                    now,
                    "stale_running_lease_expired",
                    "running materialization lease expired before completion",
                    json.dumps(trace, ensure_ascii=False, sort_keys=True),
                    str(filters.get("organization_id") or "org-ontology-demo"),
                    str(filters["project_id"]),
                    str(filters.get("workspace_id") or "manufacturing-demo"),
                    str(filters["summary_key"]),
                    filters["started_before"],
                ),
            ).fetchone()
        if row is None:
            return None
        return self._workflow_run_record_from_row(dict(row))

    def reset(self) -> None:
        with self._connect() as connection:
            for table in (
                "decisions",
                "notes",
                "conversations",
                "audit_log",
                "agent_review_summaries",
                "agent_review_workflow_runs",
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
