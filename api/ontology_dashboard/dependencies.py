"""Application service composition and request dependencies."""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Callable

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request, Response, status

from .adapters.service import AdapterService
from .adapters.prediction_repository import PredictionResultRepository
from .analysis_service import AnalysisService
from .connectors import ConnectorRepository, ConnectorService, FixtureConnectorAdapter
from .dashboard_service import DashboardService
from .distributed_runtime import DurableJobRepository
from .datasets import (
    AnalysisDatasetMaterializer,
    DatasetCatalogService,
    DatasetMaterializationSource,
    DatasetRepository,
)
from .export_service import ExportService
from .governance import GovernanceService
from .identity import CSRF_COOKIE, SESSION_COOKIE, AuthError, IdentityService, Principal
from .integrations.project3 import Project3Client
from .llm import configured_provider
from .modeling import ModelingService
from .migrations import migrate
from .planner import OntologyDashboardPlannerService
from .ontology_service import OntologyService
from .ontology_primitives import OntologyPrimitiveRepository
from .orchestration import AgentRunRepository, MultiStoreOrchestrator
from .orchestration.ports import Project3GraphPort, Project3VectorPort, RelationalOntologyPort
from .postgresql_ontology_repository import PostgreSQLOntologyInstanceRepository
from .postgresql_repositories import (
    PostgreSQLAdapterRepository,
    PostgreSQLAuditRepository,
    PostgreSQLDashboardRepository,
    PostgreSQLExportRepository,
    PostgreSQLIdentityRepository,
    PostgreSQLOntologyActionRepository,
    PostgreSQLPredictionResultRepository,
    PostgreSQLProjectRepository,
    PostgreSQLRoleWorkflowRepository,
    is_postgresql,
    seed_runtime_reference_data,
)
from .projects import ProjectRepository, ProjectService
from .predictive_maintenance_runtime import (
    PredictiveMaintenanceRuntimeRepository,
    PredictiveMaintenanceRuntimeService,
)
from .role_workflow_service import RoleWorkflowService
from .security import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from .service import ManufacturingPredictiveMaintenanceService
from .settings import database_location, trust_proxy_headers, trusted_proxy_networks

ROOT = Path(__file__).resolve().parents[2]
MANUFACTURING_WORKSPACE = "manufacturing-demo"
_MIGRATION_LOCK = Lock()


def database_target() -> str:
    return database_location(ROOT)


def database_path() -> str:
    """Compatibility alias for callers that only need the configured location."""
    return database_target()


@lru_cache(maxsize=1)
def ensure_database_migrations() -> tuple[str, ...]:
    # functools.lru_cache can execute concurrent cache misses more than once.
    # Serialize the initial migration pass so parallel FastAPI dependencies do
    # not race while inserting the same schema_migrations version in SQLite.
    with _MIGRATION_LOCK:
        return tuple(migrate(database_target()))


@lru_cache(maxsize=1)
def get_service() -> ManufacturingPredictiveMaintenanceService:
    ensure_database_migrations()
    target = database_target()
    if is_postgresql(target):
        return ManufacturingPredictiveMaintenanceService(
            ROOT,
            database_path=target,
            repository=PostgreSQLAuditRepository(target),
        )
    return ManufacturingPredictiveMaintenanceService(ROOT, database_path=target)


@lru_cache(maxsize=1)
def get_identity_service() -> IdentityService:
    ensure_database_migrations()
    target = database_target()
    if is_postgresql(target):
        password_hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
        )
        repository = PostgreSQLIdentityRepository(
            target,
            password_hasher=password_hasher,
            seed_reference_data=seed_runtime_reference_data(),
        )
        return IdentityService(target, repository=repository)
    return IdentityService(target)


@lru_cache(maxsize=1)
def get_project_service() -> ProjectService:
    ensure_database_migrations()
    target = database_target()
    repository = (
        PostgreSQLProjectRepository(target)
        if is_postgresql(target)
        else ProjectRepository(target)
    )
    return ProjectService(repository)


@lru_cache(maxsize=1)
def get_adapter_service() -> AdapterService:
    ensure_database_migrations()
    target = database_target()
    if is_postgresql(target):
        return AdapterService(
            target,
            root=ROOT,
            repository=PostgreSQLAdapterRepository(target),
            prediction_repository=PostgreSQLPredictionResultRepository(target),
        )
    return AdapterService(target, root=ROOT)


def _ontology_principal(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
    return identity.principal_for_token(
        token,
        user_agent=request.headers.get("User-Agent"),
        client_ip=client_ip(request),
    )


def get_ontology_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    principal: Principal = Depends(_ontology_principal),
) -> OntologyService:
    target = str(service.repository.path)
    if is_postgresql(target):
        project_id = principal.active_project_id
        if not project_id and len(principal.project_scopes) == 1:
            project_id = principal.project_scopes[0]
        if not project_id:
            raise AuthError(
                409,
                "active_project_required",
                "Ontology를 조회하기 전에 Project를 활성화해야 합니다.",
            )
        return OntologyService(
            service,
            action_repository=PostgreSQLOntologyActionRepository(target),
            instance_repository=PostgreSQLOntologyInstanceRepository(
                target,
                organization_id=principal.organization_id,
                project_id=project_id,
            ),
            role_workflow_repository=PostgreSQLRoleWorkflowRepository(target),
        )
    return OntologyService(service)


def get_analysis_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
) -> AnalysisService:
    target = str(service.repository.path)
    dataset_source = DatasetMaterializationSource(DatasetRepository(target))
    return AnalysisService(target, dataset_loader=dataset_source.load)


def get_durable_job_repository(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
) -> DurableJobRepository:
    target = str(service.repository.path)
    migrate(target)
    return DurableJobRepository(
        target,
        max_queued_per_project=max(
            1,
            int(os.getenv("ONTOLOGY_DASHBOARD_MAX_QUEUED_JOBS_PER_PROJECT", "5000")),
        ),
    )


@lru_cache(maxsize=1)
def get_connector_repository() -> ConnectorRepository:
    ensure_database_migrations()
    return ConnectorRepository(database_target())


def get_connector_service(
    repository: ConnectorRepository = Depends(get_connector_repository),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
) -> ConnectorService:
    return ConnectorService(
        repository=repository,
        jobs=jobs,
        adapters={"fixture": FixtureConnectorAdapter()},
    )


@lru_cache(maxsize=1)
def get_ontology_primitive_repository() -> OntologyPrimitiveRepository:
    ensure_database_migrations()
    return OntologyPrimitiveRepository(database_target())


def get_dashboard_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
) -> DashboardService:
    target = str(service.repository.path)
    if is_postgresql(target):
        return DashboardService(
            target,
            repository=PostgreSQLDashboardRepository(target),
        )
    return DashboardService(target)


def get_role_workflow_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
) -> RoleWorkflowService:
    target = str(service.repository.path)
    if is_postgresql(target):
        return RoleWorkflowService(
            service,
            repository=PostgreSQLRoleWorkflowRepository(target),
            ontology=ontology,
            dashboards=dashboards,
        )
    return RoleWorkflowService(service)


def get_export_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
    role_workflows: RoleWorkflowService = Depends(get_role_workflow_service),
) -> ExportService:
    target = str(service.repository.path)
    if is_postgresql(target):
        return ExportService(
            service,
            dashboards=dashboards,
            role_workflows=role_workflows,
            repository=PostgreSQLExportRepository(target),
        )
    return ExportService(service)


@lru_cache(maxsize=1)
def get_dataset_catalog_service() -> DatasetCatalogService:
    target = database_target()
    migrate(target)
    return DatasetCatalogService(DatasetRepository(target))


def get_analysis_materializer(
    analyses: AnalysisService = Depends(get_analysis_service),
    ontology: OntologyService = Depends(get_ontology_service),
    datasets: DatasetCatalogService = Depends(get_dataset_catalog_service),
) -> AnalysisDatasetMaterializer:
    return AnalysisDatasetMaterializer(
        analysis=analyses,
        ontology=ontology,
        datasets=datasets,
        artifact_root=ROOT / "data" / "materializations",
    )


def get_governance_service(
    datasets: DatasetCatalogService = Depends(get_dataset_catalog_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
) -> GovernanceService:
    target = database_target()
    migrate(target)
    return GovernanceService(
        datasets=datasets.repository,
        agents=AgentRunRepository(target),
        workflows=workflows,
    )


@lru_cache(maxsize=1)
def get_predictive_maintenance_runtime_service() -> PredictiveMaintenanceRuntimeService:
    target = database_target()
    migrate(target)
    if not is_postgresql(target):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "UCI AI4I 2020 Manufacturing Predictive Maintenance — "
                "Physics & Maintenance Canonical V3.1 runtime requires PostgreSQL"
            ),
        )
    return PredictiveMaintenanceRuntimeService(
        PredictiveMaintenanceRuntimeRepository(target)
    )


@lru_cache(maxsize=1)
def get_modeling_service() -> ModelingService:
    ensure_database_migrations()
    target = database_target()
    configured_roots = [
        Path(item).expanduser().resolve()
        for item in os.getenv(
            "ONTOLOGY_DASHBOARD_DATASET_ROOTS",
            str((ROOT / "data").resolve()),
        ).split(os.pathsep)
        if item.strip()
    ]
    artifact_root = os.getenv(
        "ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT",
        str((ROOT / "data" / "modeling-artifacts").resolve()),
    )
    prediction_repository = (
        PostgreSQLPredictionResultRepository(target)
        if is_postgresql(target)
        else PredictionResultRepository(target)
    )
    return ModelingService.configured(
        target,
        artifact_root,
        intake_roots=configured_roots,
        prediction_repository=prediction_repository,
    )


@lru_cache(maxsize=1)
def get_project3_client() -> Project3Client:
    return Project3Client.from_environment()


def get_multistore_orchestrator(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
    project3: Project3Client = Depends(get_project3_client),
) -> MultiStoreOrchestrator:
    target = str(service.repository.path)
    migrate(target)
    return MultiStoreOrchestrator(
        AgentRunRepository(target),
        relational_port=RelationalOntologyPort(ontology),
        graph_port=Project3GraphPort(project3),
        vector_port=Project3VectorPort(project3),
    )


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    redis_url = os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip()
    if redis_url:
        return RedisRateLimiter(redis_url)
    return InMemoryRateLimiter()


def get_ontology_planner_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
) -> OntologyDashboardPlannerService:
    provider_name = os.getenv("LLM_PROVIDER", "deterministic").strip().lower()
    provider = None if provider_name in {"", "none", "deterministic", "offline"} else configured_provider()
    return OntologyDashboardPlannerService(
        service,
        provider=provider,
        ontology=ontology,
        dashboards=dashboards,
    )


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client is not None else "unknown"
    if not trust_proxy_headers():
        return peer
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_address in network for network in trusted_proxy_networks()):
        return peer
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not forwarded:
        return peer
    try:
        return str(ipaddress.ip_address(forwarded))
    except ValueError:
        return peer


def rate_limit_subject(*parts: str) -> str:
    return InMemoryRateLimiter.anonymized_key(*parts)


def set_auth_cookies(
    *,
    response: Response,
    identity: IdentityService,
    token: str,
    csrf_token: str,
    expires_at: datetime,
) -> None:
    max_age = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        expires=expires_at,
        httponly=True,
        secure=identity.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        expires=expires_at,
        httponly=False,
        secure=identity.secure_cookies,
        samesite="lax",
        path="/",
    )


def current_principal(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
    return identity.principal_for_token(
        token,
        user_agent=request.headers.get("User-Agent"),
        client_ip=client_ip(request),
    )


def require_permission(permission: str) -> Callable[..., Principal]:
    def dependency(
        principal: Principal = Depends(current_principal),
        identity: IdentityService = Depends(get_identity_service),
    ) -> Principal:
        identity.require_permission(principal, permission)
        return principal

    return dependency


def require_manufacturing_scope(
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    identity.require_workspace(principal, MANUFACTURING_WORKSPACE)
    return principal


def require_csrf(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> None:
    identity.verify_csrf(request.cookies.get(CSRF_COOKIE), request.headers.get("X-CSRF-Token"))
