"""Process-level PostgreSQL connection pool with transaction-scoped RLS context."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

_POOLS: dict[str, object] = {}
_POOL_LOCK = threading.Lock()


def require_psycopg_pool():
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL pooling requires the systems/backend postgres extra with psycopg_pool installed"
        ) from exc
    return ConnectionPool, dict_row


def get_pool(database_url: str):
    with _POOL_LOCK:
        existing = _POOLS.get(database_url)
        if existing is not None:
            return existing
        ConnectionPool, dict_row = require_psycopg_pool()
        min_size = max(1, int(os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_MIN", "1")))
        max_size = max(min_size, int(os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_MAX", "10")))
        timeout = max(1.0, float(os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_TIMEOUT", "10")))
        pool = ConnectionPool(
            conninfo=database_url,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            kwargs={"row_factory": dict_row},
            # Neon/serverless PostgreSQL may retire an idle backend while the
            # client-side pool still holds the socket. Check on checkout so a
            # stale AdminShutdown/broken connection is discarded and replaced
            # before an identity or tenant transaction begins.
            check=ConnectionPool.check_connection,
            open=True,
        )
        _POOLS[database_url] = pool
        return pool


@contextmanager
def pooled_identity_connection(database_url: str) -> Iterator[object]:
    """Open a trusted identity-service transaction before tenant discovery."""
    pool = get_pool(database_url)
    with pool.connection() as connection:
        with connection.transaction():
            connection.execute("SELECT set_config('app.organization_id', '', true)")
            connection.execute("SELECT set_config('app.project_id', '', true)")
            connection.execute("SELECT set_config('app.identity_access', 'on', true)")
            yield connection


@contextmanager
def pooled_system_connection(database_url: str) -> Iterator[object]:
    """Call narrow SECURITY DEFINER scope-resolution functions."""
    pool = get_pool(database_url)
    with pool.connection() as connection:
        with connection.transaction():
            connection.execute("SELECT set_config('app.organization_id', '', true)")
            connection.execute("SELECT set_config('app.project_id', '', true)")
            connection.execute("SELECT set_config('app.identity_access', 'off', true)")
            yield connection


@contextmanager
def pooled_tenant_connection(
    database_url: str,
    organization_id: str,
    *,
    project_id: str | None,
) -> Iterator[object]:
    if not organization_id:
        raise ValueError("organization_id is required for PostgreSQL RLS")
    pool = get_pool(database_url)
    with pool.connection() as connection:
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


def close_pools() -> None:
    """Close all process-level pools during graceful application shutdown."""
    with _POOL_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()
