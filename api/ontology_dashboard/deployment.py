"""Production deployment contracts and bounded health-probe evidence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .migrations import migration_status
from .persistence_readiness import persistence_readiness
from .settings import (
    allowed_origins,
    app_environment,
    database_location,
    trust_proxy_headers,
    trusted_proxy_networks,
)


ProbeState = Literal["alive", "ready", "degraded", "blocked", "starting"]


class DependencyProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    required: bool
    state: Literal["ready", "not_configured", "degraded", "blocked"]
    detail: str


class ProcessProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["alive"] = "alive"
    service: str = "ontology-dashboard-api"
    purpose: str = "process liveness only"


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
    ingress: dict[str, object]
    containers: dict[str, object]
    migration: dict[str, object]
    resources: dict[str, dict[str, str]]
    release_strategy: str
    blockers: tuple[str, ...]


VERSIONED_ROUTES = (
    "/app/projects/manufacturing-demo-project",
    "/app/projects/manufacturing-demo-project/blueprint",
    "/app/projects/manufacturing-demo-project/blueprint-v2",
    "/app/projects/manufacturing-demo-project/blueprint-v4",
)


def _migration_snapshot(root: Path) -> dict[str, object]:
    database = database_location(root)
    try:
        return migration_status(database)
    except Exception as error:  # dependency probe must return bounded evidence
        return {"applied": [], "available": [], "pending": [], "error": type(error).__name__}


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
    persistence = persistence_readiness(database, app_env=environment)
    startup = startup_probe(root)
    redis_configured = bool(os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip())
    dependencies = (
        DependencyProbe(
            name="database",
            required=True,
            state=(
                "ready"
                if persistence.active_database == "postgresql"
                else "ready"
                if environment in {"development", "demo", "test"}
                else "blocked"
            ),
            detail=(
                "PostgreSQL canonical repository"
                if persistence.active_database == "postgresql"
                else "SQLite pilot repository; production blocked"
            ),
        ),
        DependencyProbe(
            name="migrations",
            required=True,
            state="ready" if startup.migration_compatible else "blocked",
            detail=(
                "schema is compatible"
                if startup.migration_compatible
                else f"pending migrations: {', '.join(startup.pending_migrations)}"
            ),
        ),
        DependencyProbe(
            name="redis",
            required=environment == "production",
            state="ready" if redis_configured else "not_configured",
            detail="distributed runtime configured" if redis_configured else "optional outside production",
        ),
    )
    required_blocked = any(item.required and item.state in {"blocked", "degraded"} for item in dependencies)
    optional_missing = any(not item.required and item.state != "ready" for item in dependencies)
    return ReadinessProbe(
        state="blocked" if required_blocked else "degraded" if optional_missing else "ready",
        environment=environment,
        dependencies=dependencies,
        migration_compatible=startup.migration_compatible,
    )


def deployment_readiness(root: Path) -> DeploymentReadiness:
    environment = app_environment()
    origins = allowed_origins()
    blockers: list[str] = []
    if environment != "production":
        blockers.append("Production deployment evidence is not active in this local environment.")
    if not os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "").strip():
        blockers.append("Production PostgreSQL URL is not configured.")
    if not os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip():
        blockers.append("Production Redis URL is not configured.")
    if not origins:
        blockers.append("Production HTTPS CORS allowlist is not configured.")
    if trust_proxy_headers() and not trusted_proxy_networks():
        blockers.append("Trusted proxy CIDRs are required when forwarded headers are trusted.")
    return DeploymentReadiness(
        state="blocked" if blockers else "ready",
        environment=environment,
        topology=(
            "migration-job",
            "api",
            "web-ingress",
            "analysis-worker",
            "modeling-worker",
            "outbox-automation-worker",
            "connector-worker-optional",
        ),
        probes={
            "liveness": "/health/live",
            "startup": "/health/startup",
            "readiness": "/health/ready",
        },
        routes=VERSIONED_ROUTES,
        ingress={
            "tls_termination": "external ingress/controller",
            "trusted_proxy_headers": trust_proxy_headers(),
            "trusted_proxy_networks": [str(item) for item in trusted_proxy_networks()],
            "cors_origins": origins,
            "spa_deep_link_fallback": True,
            "api_body_limit": os.getenv("ONTOLOGY_DASHBOARD_MAX_REQUEST_BYTES", "10485760"),
        },
        containers={
            "multi_stage": True,
            "non_root": True,
            "read_only_root_filesystem": True,
            "runtime_temp_mount": "/tmp",
            "secret_injection": "environment reference or mounted secret; no image rebuild",
        },
        migration={
            "execution": "single one-shot job before API rollout",
            "replica_startup_migration": False,
            "policy": "forward-fix; never edit an applied migration",
            "compatibility": "N-1 application compatibility required before rolling deployment",
        },
        resources={
            "api": {"request": "250m/512Mi", "limit": "1000m/1Gi"},
            "web": {"request": "50m/64Mi", "limit": "250m/128Mi"},
            "worker": {"request": "250m/512Mi", "limit": "2000m/2Gi"},
        },
        release_strategy="rolling deployment with migration gate and explicit rollback decision tree",
        blockers=tuple(blockers),
    )


def verify_deployment_files(root: Path) -> dict[str, object]:
    required = {
        "api_dockerfile": root / "api/Dockerfile",
        "web_dockerfile": root / "web/Dockerfile",
        "nginx": root / "web/nginx.conf",
        "production_manifest": root / "infra/production/platform.yaml",
        "kustomization": root / "infra/production/kustomization.yaml",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    contents = {name: path.read_text(encoding="utf-8") for name, path in required.items() if path.exists()}
    checks = {
        "api_multistage": " AS builder" in contents.get("api_dockerfile", ""),
        "api_non_root": "USER 10001" in contents.get("api_dockerfile", ""),
        "web_multistage": " AS build" in contents.get("web_dockerfile", ""),
        "web_non_root": "USER 101" in contents.get("web_dockerfile", ""),
        "spa_fallback": "try_files $uri $uri/ /index.html" in contents.get("nginx", ""),
        "v4_route_contract": VERSIONED_ROUTES[-1] in contents.get("production_manifest", ""),
        "migration_job": "kind: Job" in contents.get("production_manifest", ""),
        "read_only_filesystem": "readOnlyRootFilesystem: true" in contents.get("production_manifest", ""),
    }
    return {
        "pass": not missing and all(checks.values()),
        "missing": missing,
        "checks": checks,
    }


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
