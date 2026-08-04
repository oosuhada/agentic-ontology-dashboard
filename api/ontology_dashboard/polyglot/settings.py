"""Secrets-safe environment configuration for the three-store local stack."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class PolyglotSettings:
    database_url: str
    neo4j_uri: str
    neo4j_database: str
    neo4j_username: str
    neo4j_password: str
    redis_url: str
    vector_dimensions: int

    @classmethod
    def from_environment(cls) -> "PolyglotSettings":
        return cls(
            database_url=os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "").strip(),
            neo4j_uri=os.getenv("ONTOLOGY_DASHBOARD_NEO4J_URI", os.getenv("NEO4J_URI", "")).strip(),
            neo4j_database=os.getenv("ONTOLOGY_DASHBOARD_NEO4J_DATABASE", "neo4j").strip() or "neo4j",
            neo4j_username=os.getenv("ONTOLOGY_DASHBOARD_NEO4J_USERNAME", os.getenv("NEO4J_USERNAME", "neo4j")).strip() or "neo4j",
            neo4j_password=os.getenv("ONTOLOGY_DASHBOARD_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "")).strip(),
            redis_url=os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip(),
            vector_dimensions=int(os.getenv("ONTOLOGY_DASHBOARD_VECTOR_DIMENSIONS", "1536")),
        )

    @property
    def postgres_configured(self) -> bool:
        return self.database_url.startswith(("postgresql://", "postgresql+psycopg://"))

    @property
    def neo4j_configured(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_password)

    @property
    def redis_configured(self) -> bool:
        return bool(self.redis_url)

    def safe_summary(self) -> dict[str, object]:
        return {
            "postgres": {
                "configured": self.postgres_configured,
                "endpoint": redact_url(self.database_url),
            },
            "neo4j": {
                "configured": self.neo4j_configured,
                "endpoint": redact_url(self.neo4j_uri),
                "database": self.neo4j_database,
                "username": self.neo4j_username if self.neo4j_configured else "",
            },
            "redis": {
                "configured": self.redis_configured,
                "endpoint": redact_url(self.redis_url),
            },
            "vector_dimensions": self.vector_dimensions,
        }


def redact_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value.split("@")[-1]
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
