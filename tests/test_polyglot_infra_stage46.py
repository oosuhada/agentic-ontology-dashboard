from __future__ import annotations

from pathlib import Path

import yaml

from ontology_dashboard.polyglot import PolyglotHealthService, PolyglotSettings
from ontology_dashboard.polyglot.settings import redact_url

ROOT = Path(__file__).resolve().parents[1]


def configured_settings() -> PolyglotSettings:
    return PolyglotSettings(
        database_url="postgresql://ontology:secret@postgres:5432/ontology_dashboard",
        neo4j_uri="bolt://neo4j:7687",
        neo4j_database="neo4j",
        neo4j_username="neo4j",
        neo4j_password="secret",
        redis_url="redis://:secret@redis:6379/0",
        vector_dimensions=1536,
    )


def test_polyglot_settings_redact_credentials() -> None:
    summary = configured_settings().safe_summary()
    assert summary["postgres"]["endpoint"] == "postgresql://postgres:5432/ontology_dashboard"
    assert summary["neo4j"]["endpoint"] == "bolt://neo4j:7687"
    assert summary["redis"]["endpoint"] == "redis://redis:6379/0"
    assert "secret" not in str(summary)
    assert redact_url("") == ""


def test_polyglot_health_supports_ready_degraded_and_offline_modes() -> None:
    ready = PolyglotHealthService(
        configured_settings(),
        postgres_probe=lambda _: {"pgvector": True},
        neo4j_probe=lambda _: {"database": "neo4j"},
        redis_probe=lambda _: {"ping": "PONG"},
    ).snapshot()
    assert ready["status"] == "ready"
    assert {item["status"] for item in ready["stores"]} == {"ready"}
    assert ready["capability_boundaries"] == {
        "local_pgvector": "infrastructure_and_projection_schema_only",
        "semantic_retrieval": "project3_rag_via_typed_http",
        "graph_queries": "project3_via_typed_http",
        "direct_sql_or_cypher_submission": False,
    }

    degraded = PolyglotHealthService(
        configured_settings(),
        postgres_probe=lambda _: (_ for _ in ()).throw(RuntimeError("postgres offline")),
        neo4j_probe=lambda _: {"database": "neo4j"},
        redis_probe=lambda _: {"ping": "PONG"},
    ).snapshot()
    assert degraded["status"] == "degraded"
    postgres = next(item for item in degraded["stores"] if item["store"] == "postgres_pgvector")
    assert postgres["status"] == "unavailable"
    assert "postgres offline" in postgres["detail"]

    offline = PolyglotHealthService(
        PolyglotSettings(
            database_url="",
            neo4j_uri="",
            neo4j_database="neo4j",
            neo4j_username="neo4j",
            neo4j_password="",
            redis_url="",
            vector_dimensions=1536,
        )
    ).snapshot()
    assert offline["status"] == "offline_capable"
    assert all(item["status"] == "not_configured" for item in offline["stores"])


def test_compose_defines_reproducible_polyglot_profile_and_health_checks() -> None:
    compose = yaml.safe_load((ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["postgres"]["profiles"] == ["polyglot"]
    assert services["postgres"]["image"].startswith("pgvector/pgvector:")
    assert "healthcheck" in services["postgres"]
    assert services["neo4j"]["profiles"] == ["polyglot"]
    assert services["neo4j"]["image"].endswith("-community")
    assert "healthcheck" in services["neo4j"]
    assert services["redis"]["profiles"] == ["cache"]
    assert services["migration-bootstrap"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["migration-bootstrap"]["depends_on"]["neo4j"]["condition"] == "service_healthy"
    assert services["migration-bootstrap"]["command"] == [
        "python",
        "-m",
        "ontology_dashboard.bootstrap",
    ]
    assert (
        ROOT / "infra" / "postgres" / "init" / "00-extensions.sql"
    ).read_text(encoding="utf-8").strip() == "CREATE EXTENSION IF NOT EXISTS vector;"


def test_api_package_discovery_and_runtime_dependencies_match_boundaries() -> None:
    pyproject = (ROOT / "api" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["ontology_dashboard*", "factory_signal_board*"]' in pyproject
    for dependency in (
        '"psycopg[binary]>=3.2"',
        '"psycopg_pool>=3.2"',
        '"neo4j>=5"',
        '"redis>=5.0"',
        '"pyarrow>=17"',
    ):
        assert dependency in pyproject
    for unused_dependency in (
        '"pgvector>=0.3"',
        '"langgraph>=0.2"',
        '"langgraph-checkpoint-postgres>=2"',
        '"llama-index-vector-stores-postgres>=0.3"',
    ):
        assert unused_dependency not in pyproject
