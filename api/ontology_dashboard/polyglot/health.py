"""Bounded health checks for PostgreSQL/pgvector, Neo4j and optional Redis."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .settings import PolyglotSettings


@dataclass(frozen=True)
class StoreHealth:
    store: str
    status: str
    configured: bool
    required: bool
    latency_ms: int | None = None
    detail: str = ""
    metadata: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "store": self.store,
            "status": self.status,
            "configured": self.configured,
            "required": self.required,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "metadata": self.metadata or {},
        }


class PolyglotHealthService:
    def __init__(
        self,
        settings: PolyglotSettings,
        *,
        postgres_probe: Callable[[str], dict[str, Any]] | None = None,
        neo4j_probe: Callable[[PolyglotSettings], dict[str, Any]] | None = None,
        redis_probe: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self.postgres_probe = postgres_probe or _probe_postgres
        self.neo4j_probe = neo4j_probe or _probe_neo4j
        self.redis_probe = redis_probe or _probe_redis

    def snapshot(self) -> dict[str, Any]:
        checks = [self._postgres(), self._neo4j(), self._redis()]
        required_failures = [
            item for item in checks if item.required and item.status not in {"ready", "not_configured"}
        ]
        configured_required = [item for item in checks if item.required and item.configured]
        status = (
            "degraded"
            if required_failures
            else "ready"
            if configured_required and all(item.status == "ready" for item in configured_required)
            else "offline_capable"
        )
        return {
            "status": status,
            "stores": [item.payload() for item in checks],
            "configuration": self.settings.safe_summary(),
            "capability_boundaries": {
                "local_pgvector": "infrastructure_and_projection_schema_only",
                "semantic_retrieval": "project3_rag_via_typed_http",
                "graph_queries": "project3_via_typed_http",
                "direct_sql_or_cypher_submission": False,
            },
        }

    def _postgres(self) -> StoreHealth:
        return self._run(
            store="postgres_pgvector",
            configured=self.settings.postgres_configured,
            required=True,
            probe=lambda: self.postgres_probe(self.settings.database_url),
        )

    def _neo4j(self) -> StoreHealth:
        return self._run(
            store="neo4j",
            configured=self.settings.neo4j_configured,
            required=True,
            probe=lambda: self.neo4j_probe(self.settings),
        )

    def _redis(self) -> StoreHealth:
        return self._run(
            store="redis",
            configured=self.settings.redis_configured,
            required=False,
            probe=lambda: self.redis_probe(self.settings.redis_url),
        )

    @staticmethod
    def _run(
        *,
        store: str,
        configured: bool,
        required: bool,
        probe: Callable[[], dict[str, Any]],
    ) -> StoreHealth:
        if not configured:
            return StoreHealth(
                store=store,
                status="not_configured",
                configured=False,
                required=required,
                detail="offline/degraded mode is available",
            )
        started = time.perf_counter()
        try:
            metadata = probe()
            return StoreHealth(
                store=store,
                status="ready",
                configured=True,
                required=required,
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail="connected",
                metadata=metadata,
            )
        except Exception as error:
            return StoreHealth(
                store=store,
                status="unavailable",
                configured=True,
                required=required,
                latency_ms=int((time.perf_counter() - started) * 1000),
                detail=f"{type(error).__name__}: {error}",
            )


def _probe_postgres(database_url: str) -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError("install api[postgres] or api[polyglot]") from error

    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized, connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT current_database(),
                       EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector'),
                       current_setting('server_version')
                """
            )
            database, vector_installed, server_version = cursor.fetchone()
    if not vector_installed:
        raise RuntimeError("pgvector extension is not installed")
    return {
        "database": database,
        "pgvector": True,
        "server_version": server_version,
    }


def _probe_neo4j(settings: PolyglotSettings) -> dict[str, Any]:
    try:
        from neo4j import GraphDatabase
    except ImportError as error:
        raise RuntimeError("install api[polyglot]") from error

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
        connection_timeout=3,
    )
    try:
        driver.verify_connectivity()
        with driver.session(database=settings.neo4j_database) as session:
            record = session.run("RETURN 1 AS ok").single(strict=True)
            if record["ok"] != 1:
                raise RuntimeError("unexpected Neo4j health response")
        return {"database": settings.neo4j_database}
    finally:
        driver.close()


def _probe_redis(redis_url: str) -> dict[str, Any]:
    try:
        import redis
    except ImportError as error:
        raise RuntimeError("install api[production] or api[polyglot]") from error

    client = redis.Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
    if client.ping() is not True:
        raise RuntimeError("Redis PING failed")
    return {"ping": "PONG"}
