"""PostgreSQL runtime helpers with tenant-scoped sessions."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from .postgresql_pool import pooled_tenant_connection, require_psycopg_pool


def require_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL runtime requires the api[postgres] optional dependency"
        ) from exc
    return psycopg, dict_row


@contextmanager
def tenant_connection(
    database_url: str,
    organization_id: str,
    *,
    project_id: str | None = None,
) -> Iterator[object]:
    """Open a transaction and bind PostgreSQL RLS to one organization and project.

    Production uses the process pool by default. Development can fall back to a
    direct psycopg connection when the optional pooling package is not installed.
    """
    pooling_enabled = os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    if pooling_enabled:
        try:
            require_psycopg_pool()
        except RuntimeError:
            if os.getenv("APP_ENV", "development").lower() == "production":
                raise
        else:
            with pooled_tenant_connection(
                database_url,
                organization_id,
                project_id=project_id,
            ) as connection:
                yield connection
            return

    psycopg, dict_row = require_psycopg()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.transaction():
            connection.execute(
                "SELECT set_config('app.organization_id', %s, true)",
                (organization_id,),
            )
            connection.execute(
                "SELECT set_config('app.project_id', %s, true)",
                (project_id or "",),
            )
            yield connection
