"""Domain-neutral runtime and HTTP boundary configuration."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

ALLOWED_ORIGINS_ENV = "ONTOLOGY_DASHBOARD_ALLOWED_ORIGINS"
ALLOWED_ORIGIN_REGEX_ENV = "ONTOLOGY_DASHBOARD_ALLOWED_ORIGIN_REGEX"
TRUSTED_PROXIES_ENV = "ONTOLOGY_DASHBOARD_TRUSTED_PROXIES"
TRUST_PROXY_HEADERS_ENV = "ONTOLOGY_DASHBOARD_TRUST_PROXY_HEADERS"
PROJECT_ROOT_ENV = "ONTOLOGY_DASHBOARD_PROJECT_ROOT"
LEGACY_PROJECT_ROOT_ENV = "ONTOLOGY_DASHBOARD_ROOT"


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "contracts" / "schemas").is_dir()
        and (path / "prompts").is_dir()
        and (path / "data" / "fixtures").is_dir()
    )


def project_root() -> Path:
    """Resolve runtime assets independently of package installation depth."""
    for env_name in (PROJECT_ROOT_ENV, LEGACY_PROJECT_ROOT_ENV):
        configured = os.getenv(env_name, "").strip()
        if configured:
            return Path(configured).expanduser().resolve()

    for candidate in (Path.cwd().resolve(), Path("/app")):
        if _looks_like_project_root(candidate):
            return candidate

    for parent in Path(__file__).resolve().parents:
        if _looks_like_project_root(parent):
            return parent

    raise RuntimeError(
        "cannot resolve Backend project root; "
        f"set {PROJECT_ROOT_ENV} explicitly"
    )


def app_environment() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def allowed_origins() -> list[str]:
    configured = os.getenv(ALLOWED_ORIGINS_ENV, "")
    return [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]


def allowed_origin_regex() -> str | None:
    configured = os.getenv(ALLOWED_ORIGIN_REGEX_ENV, "").strip()
    return configured or None


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
    return tuple(ipaddress.ip_network(value, strict=False) for value in values)
