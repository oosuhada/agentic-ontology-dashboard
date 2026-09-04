"""Minimal ordered SQL migration runner for SQLite and PostgreSQL."""

from __future__ import annotations

import sqlite3
import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_ORGANIZATION_ID = "org-ontology-demo"
DEFAULT_PROJECT_ID = "manufacturing-demo-project"
DEFAULT_WORKSPACE_ID = "manufacturing-demo"


def ensure_scope_columns(
    connection: sqlite3.Connection,
    *,
    table: str,
    workspace_column: str = "workspace_id",
) -> None:
    """Technical SQLite migration helper for legacy workspace-scoped tables."""

    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not exists:
        return
    columns = {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if "organization_id" not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN organization_id TEXT")
    if "project_id" not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN project_id TEXT")
    workspace_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'"
    ).fetchone()
    if workspace_table:
        connection.execute(
            f"""
            UPDATE {table}
            SET organization_id=COALESCE(
                    organization_id,
                    (SELECT organization_id FROM workspaces w WHERE w.id={table}.{workspace_column})
                ),
                project_id=COALESCE(
                    project_id,
                    (SELECT project_id FROM workspaces w WHERE w.id={table}.{workspace_column})
                )
            WHERE organization_id IS NULL OR project_id IS NULL
            """
        )
    connection.execute(
        f"UPDATE {table} SET organization_id=? "
        f"WHERE organization_id IS NULL AND {workspace_column}=?",
        (DEFAULT_ORGANIZATION_ID, DEFAULT_WORKSPACE_ID),
    )
    connection.execute(
        f"UPDATE {table} SET project_id=? "
        f"WHERE project_id IS NULL AND {workspace_column}=?",
        (DEFAULT_PROJECT_ID, DEFAULT_WORKSPACE_ID),
    )
    connection.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{table}_project_scope "
        f"ON {table}(organization_id,project_id,{workspace_column})"
    )

MIGRATION_ROOT = Path(
    os.getenv(
        "ONTOLOGY_DASHBOARD_MIGRATION_ROOT",
        str(Path(__file__).resolve().parents[3] / "migrations"),
    )
).expanduser()


def _migration_files(dialect: str) -> list[Path]:
    directory = MIGRATION_ROOT / dialect
    return sorted(directory.glob("*.sql"))


def _sqlite_path(database: str) -> Path:
    if database.startswith("sqlite:///"):
        return Path(database.removeprefix("sqlite:///"))
    return Path(database)


def migrate(database: str) -> list[str]:
    """Apply pending migrations and return the versions applied in this run."""
    if database.startswith(("postgresql://", "postgresql+psycopg://")):
        return _migrate_postgresql(database.replace("postgresql+psycopg://", "postgresql://", 1))
    return _migrate_sqlite(_sqlite_path(database))


def _migrate_sqlite(path: Path) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    applied: list[str] = []
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        existing = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for file_path in _migration_files("sqlite"):
            version = file_path.stem
            if version in existing:
                continue
            if version == "0019_tenant_transaction_convergence":
                # Pilot databases may already contain the action table because
                # OntologyActionRepository created it before migrations owned
                # the schema. Upgrade those legacy tables before the migration
                # creates indexes that reference the new recovery columns.
                action_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    ("ontology_action_invocations",),
                ).fetchone()
                if action_table:
                    action_columns = {
                        row[1]
                        for row in connection.execute(
                            "PRAGMA table_info(ontology_action_invocations)"
                        ).fetchall()
                    }
                    recovery_columns = {
                        "recovery_state": "TEXT NOT NULL DEFAULT 'none'",
                        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                        "last_error_at": "TEXT",
                        "outbox_event_id": "TEXT",
                    }
                    for name, ddl in recovery_columns.items():
                        if name not in action_columns:
                            connection.execute(
                                f"ALTER TABLE ontology_action_invocations ADD COLUMN {name} {ddl}"
                            )
            connection.executescript(file_path.read_text(encoding="utf-8"))
            if version == "0002_project_layer":
                workspace_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(workspaces)").fetchall()
                }
                if "project_id" not in workspace_columns:
                    connection.execute("ALTER TABLE workspaces ADD COLUMN project_id TEXT")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_workspaces_project "
                    "ON workspaces(organization_id,project_id,display_name)"
                )
            if version == "0003_project_scoped_operations":
                operational_tables = (
                    "dashboard_templates",
                    "dashboard_user_preferences",
                    "dashboard_saved_views",
                    "dashboard_shares",
                    "ontology_objects",
                    "ontology_links",
                    "ontology_ingestion_runs",
                    "ontology_action_invocations",
                    "audit_export_checkpoints",
                    "field_task_actions",
                    "template_publish_requests",
                    "model_release_requests",
                    "export_checkpoints",
                    "transactional_outbox",
                )
                for table in operational_tables:
                    ensure_scope_columns(connection, table=table)
            if version == "0037_agent_review_summary_runtime":
                summary_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    ("agent_review_summaries",),
                ).fetchone()
                if summary_table:
                    columns = {
                        row[1]
                        for row in connection.execute(
                            "PRAGMA table_info(agent_review_summaries)"
                        ).fetchall()
                    }
                    if "workflow_run_id" not in columns:
                        connection.execute(
                            "ALTER TABLE agent_review_summaries ADD COLUMN workflow_run_id TEXT"
                        )
            connection.execute(
                "INSERT INTO schema_migrations (version,applied_at) VALUES (?,?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            applied.append(version)
    return applied


def _migrate_postgresql(database_url: str) -> list[str]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL migrations require the api[postgres] optional dependency"
        ) from exc

    parsed = urlparse(database_url)
    if parsed.scheme != "postgresql":
        raise ValueError("unsupported PostgreSQL URL")

    applied: list[str] = []
    with closing(psycopg.connect(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('ontology_dashboard_schema_migrations'))")
            cursor.execute("SELECT version FROM schema_migrations")
            existing = {row[0] for row in cursor.fetchall()}
            for file_path in _migration_files("postgresql"):
                version = file_path.stem
                if version in existing:
                    continue
                cursor.execute(file_path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
                applied.append(version)
        connection.commit()
    return applied


def migration_status(database: str) -> dict[str, Any]:
    dialect = "postgresql" if database.startswith("postgresql") else "sqlite"
    return {
        "dialect": dialect,
        "available": [path.stem for path in _migration_files(dialect)],
    }
