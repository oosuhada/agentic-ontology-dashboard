"""Runtime settings and production safety checks for Ontology Dashboard."""

from __future__ import annotations

import ipaddress
import os
import warnings
from pathlib import Path
from urllib.parse import urlparse

CANONICAL_DATABASE_ENV = "ONTOLOGY_DASHBOARD_DATABASE_URL"
CANONICAL_SQLITE_ENV = "ONTOLOGY_DASHBOARD_DB"
LEGACY_DATABASE_ENV = "FACTORY_SIGNAL_DB"
ALLOWED_ORIGINS_ENV = "ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS"
TRUSTED_PROXIES_ENV = "ONTOLOGY_DASHBOARD_TRUSTED_PROXIES"
TRUST_PROXY_HEADERS_ENV = "ONTOLOGY_DASHBOARD_TRUST_PROXY_HEADERS"
REDIS_URL_ENV = "ONTOLOGY_DASHBOARD_REDIS_URL"


def app_environment() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def database_location(root: Path) -> str:
    """Resolve the database location while temporarily accepting the legacy key."""
    database_url = os.getenv(CANONICAL_DATABASE_ENV, "").strip()
    if database_url:
        return database_url

    sqlite_path = os.getenv(CANONICAL_SQLITE_ENV, "").strip()
    if sqlite_path:
        return sqlite_path

    legacy_path = os.getenv(LEGACY_DATABASE_ENV, "").strip()
    if legacy_path:
        warnings.warn(
            f"{LEGACY_DATABASE_ENV} is deprecated; use {CANONICAL_SQLITE_ENV} or "
            f"{CANONICAL_DATABASE_ENV} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy_path

    canonical_path = root / "data" / "local" / "ontology_dashboard.db"
    legacy_default = root / "data" / "local" / "factory_signal_board.db"
    return str(legacy_default if legacy_default.exists() and not canonical_path.exists() else canonical_path)


def allowed_origins() -> list[str]:
    configured = os.getenv(ALLOWED_ORIGINS_ENV, "")
    origins = [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]
    if origins:
        return origins
    if app_environment() in {"development", "demo", "test"}:
        return []
    return []


def trust_proxy_headers() -> bool:
    configured = os.getenv(TRUST_PROXY_HEADERS_ENV, "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    return app_environment() in {"development", "demo", "test"}


def trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    configured = os.getenv(TRUSTED_PROXIES_ENV, "")
    values = [item.strip() for item in configured.split(",") if item.strip()]
    if not values and app_environment() in {"development", "demo", "test"}:
        values = ["127.0.0.0/8", "::1/128"]
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in values:
        networks.append(ipaddress.ip_network(value, strict=False))
    return tuple(networks)


def validate_runtime_environment(root: Path) -> None:
    """Fail fast when a production process starts with unsafe demo defaults."""
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
    if not database.startswith(("postgresql://", "postgresql+psycopg://")) and os.getenv(
        "ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE",
        "0",
    ).strip().lower() not in {
        "1", "true", "yes", "on"
    }:
        errors.append(
            "production is blocked while persistence is SQLite-only; set "
            "ONTOLOGY_DASHBOARD_ALLOW_PRODUCTION_SQLITE=1 only for an explicitly accepted single-instance pilot"
        )

    if errors:
        joined = "\n- ".join(errors)
        raise RuntimeError(f"unsafe Ontology Dashboard production configuration:\n- {joined}")
