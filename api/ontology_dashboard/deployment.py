"""Current MVP deployment probes and manifest evidence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .migrations import migration_status
from .postgresql_repositories import is_postgresql
from .settings import allowed_origins, app_environment, database_location


class DependencyProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    required: bool
    state: Literal["ready", "not_configured", "blocked"]
    detail: str


class ProcessProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["alive"] = "alive"
    service: str = "ontology-dashboard-api"
    purpose: str = "Predictive Maintenance MVP process liveness"


class StartupProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "starting", "blocked"]
    environment: str
    migration_compatible: bool
    applied_migrations: int
    pending_migrations: tuple[str, ...]


class ReadinessProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "degraded", "blocked"]
    environment: str
    dependencies: tuple[DependencyProbe, ...]
    migration_compatible: bool


class DeploymentReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "blocked", "degraded"]
    environment: str
    topology: tuple[str, ...]
    probes: dict[str, str]
    routes: tuple[str, ...]
    resources: dict[str, dict[str, str]]
    blockers: tuple[str, ...]


VERSIONED_ROUTES = (
    "/login",
    "/app/projects/manufacturing-demo-project/mvp",
)


def _migration_snapshot(root: Path) -> dict[str, object]:
    try:
        return migration_status(database_location(root))
    except Exception as error:  # bounded health response
        return {"applied": [], "pending": [], "error": type(error).__name__}


def process_probe() -> ProcessProbe:
    return ProcessProbe()


def startup_probe(root: Path) -> StartupProbe:
    snapshot = _migration_snapshot(root)
    pending = tuple(str(item) for item in snapshot.get("pending", []))
    error = snapshot.get("error")
    compatible = not pending and error is None
    return StartupProbe(
        state="ready" if compatible else "blocked" if error else "starting",
        environment=app_environment(),
        migration_compatible=compatible,
        applied_migrations=len(snapshot.get("applied", [])),
        pending_migrations=pending,
    )


def readiness_probe(root: Path) -> ReadinessProbe:
    environment = app_environment()
    database = database_location(root)
    startup = startup_probe(root)
    database_ready = is_postgresql(database) or environment in {"development", "demo", "test"}
    redis_configured = bool(os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip())
    dependencies = (
        DependencyProbe(
            name="database",
            required=True,
            state="ready" if database_ready else "blocked",
            detail=(
                "PostgreSQL Canonical V3.1 runtime"
                if is_postgresql(database)
                else "SQLite Gold Fixture fallback"
            ),
        ),
        DependencyProbe(
            name="migrations",
            required=True,
            state="ready" if startup.migration_compatible else "blocked",
            detail="schema compatible" if startup.migration_compatible else "migration required",
        ),
        DependencyProbe(
            name="redis-rate-limit",
            required=environment == "production",
            state="ready" if redis_configured else "not_configured",
            detail="shared limiter configured" if redis_configured else "optional outside production",
        ),
    )
    blocked = any(item.required and item.state != "ready" for item in dependencies)
    degraded = any(not item.required and item.state != "ready" for item in dependencies)
    return ReadinessProbe(
        state="blocked" if blocked else "degraded" if degraded else "ready",
        environment=environment,
        dependencies=dependencies,
        migration_compatible=startup.migration_compatible,
    )


def deployment_readiness(root: Path) -> DeploymentReadiness:
    environment = app_environment()
    blockers: list[str] = []
    if environment != "production":
        blockers.append("Production deployment evidence is not active in this environment.")
    if not os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "").strip():
        blockers.append("Production PostgreSQL URL is not configured.")
    if not os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip():
        blockers.append("Production Redis URL is not configured.")
    if not allowed_origins():
        blockers.append("Production HTTPS CORS allowlist is not configured.")
    return DeploymentReadiness(
        state="blocked" if blockers else "ready",
        environment=environment,
        topology=("postgresql", "api", "web", "redis-rate-limit"),
        probes={
            "liveness": "/health/live",
            "startup": "/health/startup",
            "readiness": "/health/ready",
        },
        routes=VERSIONED_ROUTES,
        resources={
            "api": {"request": "250m/512Mi", "limit": "1000m/1Gi"},
            "web": {"request": "50m/64Mi", "limit": "250m/128Mi"},
        },
        blockers=tuple(blockers),
    )


def verify_deployment_files(root: Path) -> dict[str, object]:
    required = {
        "api_dockerfile": root / "api/Dockerfile",
        "web_dockerfile": root / "web/Dockerfile",
        "nginx": root / "web/nginx.conf",
        "compose": root / "infra/docker-compose.yml",
        "production_manifest": root / "infra/production/platform.yaml",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    contents = {name: path.read_text(encoding="utf-8") for name, path in required.items() if path.exists()}
    checks = {
        "api_non_root": "USER 10001" in contents.get("api_dockerfile", ""),
        "web_non_root": "USER 101" in contents.get("web_dockerfile", ""),
        "spa_fallback": "try_files $uri $uri/ /index.html" in contents.get("nginx", ""),
        "current_mvp_route": VERSIONED_ROUTES[-1] in contents.get("production_manifest", ""),
        "postgres_runtime": "postgres:" in contents.get("compose", ""),
        "no_background_worker": "ontology-dashboard-workers" not in contents.get("production_manifest", ""),
    }
    return {"pass": not missing and all(checks.values()), "missing": missing, "checks": checks}


__all__ = [
    "DependencyProbe",
    "DeploymentReadiness",
    "ProcessProbe",
    "ReadinessProbe",
    "StartupProbe",
    "VERSIONED_ROUTES",
    "deployment_readiness",
    "process_probe",
    "readiness_probe",
    "startup_probe",
    "verify_deployment_files",
]
