"""Production startup validation composed from canonical runtime settings."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from app.common.runtime_settings import (
    ALLOWED_ORIGINS_ENV,
    TRUSTED_PROXIES_ENV,
    allowed_origins,
    app_environment,
    trust_proxy_headers,
    trusted_proxy_networks,
)
from app.infra.db.settings import database_location, is_postgresql_url

REDIS_URL_ENV = "ONTOLOGY_DASHBOARD_REDIS_URL"


def validate_runtime_environment(root: Path) -> None:
    if app_environment() != "production":
        return

    errors: list[str] = []
    seed_demo = os.getenv("SEED_DEMO_ACCOUNTS", "0").strip().lower()
    if seed_demo in {"1", "true", "yes", "on"}:
        errors.append("SEED_DEMO_ACCOUNTS must be disabled in production")

    origins = allowed_origins()
    if not origins:
        errors.append(f"{ALLOWED_ORIGINS_ENV} must contain at least one HTTPS origin")
    for origin in origins:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"production origin must be an absolute HTTPS URL: {origin}")

    if trust_proxy_headers() and not trusted_proxy_networks():
        errors.append(
            f"{TRUSTED_PROXIES_ENV} must define ingress CIDRs when proxy headers are trusted"
        )

    if not os.getenv(REDIS_URL_ENV, "").strip():
        errors.append(f"{REDIS_URL_ENV} is required for distributed production rate limiting")

    database = database_location(root)
    allow_sqlite = os.getenv("ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE", "0").strip().lower()
    if not is_postgresql_url(database) and allow_sqlite not in {"1", "true", "yes", "on"}:
        errors.append(
            "production is blocked while persistence is SQLite-only; set "
            "ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE=1 only for an explicitly accepted single-instance pilot"
        )

    if errors:
        joined = "\n- ".join(errors)
        raise RuntimeError(f"unsafe Ontology Dashboard production configuration:\n- {joined}")
