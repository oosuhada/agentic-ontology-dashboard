"""Minimal application composition dependencies.

Only capabilities used by the current product runtime are wired here.  Removed
prototype workbenches are intentionally not dependencies of ``app.main``.
"""

from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request, Response, status

from app.common.rate_limit import RateLimiter
from app.common.company_context import company_documents, load_company_context
from app.common.runtime_settings import app_environment, project_root, trust_proxy_headers, trusted_proxy_networks
from app.dashboard import DashboardService
from app.dashboard.dashboard_schema import DashboardBoard, DashboardTab, DashboardTemplatePublishRequest
from app.dashboard.visualizations import (
    FieldProfile,
    SemanticVisualizationPlanRequest,
    SemanticVisualizationPlanResponse,
    VISUALIZATION_REGISTRY,
    VisualizationCandidate,
    build_typed_query_plan,
    build_v3_1_semantic_catalog,
    compile_postgresql_query,
    context_from_source,
    validate_override,
    validate_override_channel_mapping,
)
from app.dataset import DatasetCatalogService
from app.diagnosis.evidence import FixtureContextProvider, build_product_result_artifact
from app.diagnosis.predictor import configured_predictor
from app.diagnosis.runtime_service import (
    PredictiveMaintenanceRuntimeService,
    V3_1_MODEL_VERSION,
    V3_1_RESULT_SCHEMA,
    V3_1_SOURCE_VERSION,
)
from app.diagnosis.contracts import load_fixture
from app.governance import GovernanceService
from app.identity import CSRF_COOKIE, SESSION_COOKIE, AuthError, IdentityService, Principal
from app.infra.db.dashboard_repository import DashboardRepository
from app.infra.db.company_context_repository import CompanyContextRepository
from app.infra.db.agent_run_repository import AgentRunRepository
from app.knowledge import KnowledgeService
from app.knowledge.embedding import configured_embedding_provider
from app.knowledge.repository import KnowledgeRepository
from app.infra.db.dataset_ingestion_repository import DatasetIngestionRepository
from app.infra.db.dataset_repository import DatasetRepository
from app.infra.db.diagnosis_runtime_repository import PredictiveMaintenanceRuntimeRepository
from app.infra.db.identity_repository import IdentityRepository as SQLiteIdentityRepository
from app.infra.db.maintenance_repository import (
    MaintenanceRepository,
    PostgreSQLMaintenanceRepository,
)
from app.infra.db.migrations import migrate
from app.infra.db.ontology_action_repository import OntologyActionRepository
from app.infra.db.ontology_instance_repository import OntologyInstanceRepository
from app.infra.db.postgresql_bundle_ingestion import PostgreSQLPredictiveMaintenanceBundleIngestor
from app.infra.db.postgresql_compat import (
    PostgreSQLProjectContextResolver,
    postgres_repository_connection,
)
from app.infra.db.prediction_result_repository import PredictionResultRepository
from app.infra.db.project_repository import (
    ProjectRepository as SQLiteProjectRepository,
    SQLiteProjectContextResolver,
)
from app.infra.db.report_repository import ReportRepository
from app.infra.db.settings import database_location
from app.infra.context import Project3HttpContextProvider, ResilientContextProvider
from app.infra.llm import configured_provider
from app.operations.agent_answer_provider import GroundedAgentAnswerProvider
from app.infra.maintenance_cost_basis_provider import JsonMaintenanceCostBasisProvider
from app.infra.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.maintenance.live_service import LivePredictiveMaintenanceService
from app.maintenance.service import MaintenanceLoopService
from app.operations.asset_detail_view_model import AssetDetailViewModelService
from app.ontology import OntologyService
from app.planner import LayoutPlanner, OntologyDashboardPlannerService
from app.project import ProjectService
from app.report import ReportService
from app.report.generation_provider import ReportAgent

from app.dataset.ingestion.api_service import AdapterService
from app.equipment import EquipmentService
from app.equipment.adapters import FixtureEquipmentRepository
from app.infra.db.postgresql_ontology_repository import PostgreSQLOntologyInstanceRepository
from app.infra.db.postgresql_repositories import (
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
from app.infra.db.project_repository import SQLiteProjectContextResolver as RuntimeProjectContextResolver
from app.infra.db.operational_decision_support_service import (
    PersistedOperationalDecisionSupportService,
)
from app.infra.db.role_workflow_repository import RoleWorkflowRepository
from app.infra.db.operations_audit_repository import AuditRepository
from app.operations.role_workflow_service import RoleWorkflowService
from app.operations.agent_review_summary_provider import AgentReviewSummaryProvider
from app.operations.context_providers import default_agent_review_context_registry
from app.operations.domain_context_adapters import ManufacturingFixtureReviewContextAdapter
from app.operations.operational_decision_support_port import OperationalDecisionSupportService
from app.operations.service import ManufacturingPredictiveMaintenanceService


ROOT = project_root()
MANUFACTURING_WORKSPACE = "manufacturing-demo"
_MIGRATION_LOCK = Lock()
_SERVICE_BUILD_LOCK = Lock()
_KNOWLEDGE_BUILD_LOCK = Lock()


@lru_cache(maxsize=1)
def _cached_knowledge_service(target: str) -> KnowledgeService:
    migrate(target)
    service = KnowledgeService(KnowledgeRepository(target), configured_embedding_provider())
    try:
        repository = service.repository
        organization_id = repository.resolve_organization(
            project_id="manufacturing-demo-project",
            workspace_id=MANUFACTURING_WORKSPACE,
        )
        service.bootstrap(
            organization_id=organization_id,
            project_id="manufacturing-demo-project",
            workspace_id=MANUFACTURING_WORKSPACE,
            documents=company_documents(load_company_context()),
        )
    except Exception:
        # Knowledge bootstrap/indexing is an enrichment path. Core Operations
        # remains available while migrations or external embedding providers
        # are being repaired.
        pass
    return service


def get_knowledge_service() -> KnowledgeService:
    with _KNOWLEDGE_BUILD_LOCK:
        return _cached_knowledge_service(database_target())


def database_target() -> str:
    return database_location(ROOT)


@lru_cache(maxsize=1)
def ensure_database_migrations() -> tuple[str, ...]:
    with _MIGRATION_LOCK:
        return tuple(migrate(database_target()))


def _operations_fixture_masters(root: Path) -> list[tuple[str, dict[str, Any]]]:
    fixture_root = root / "data" / "fixtures"
    masters: list[tuple[str, dict[str, Any]]] = []
    for pattern in ("GS-*.json", "AZ-*.json", "MPT-*.json"):
        for path in fixture_root.glob(pattern):
            fixture = load_fixture(path)
            masters.append(
                (
                    str(fixture.get("project_id") or "manufacturing-demo-project"),
                    fixture["equipment"],
                )
            )
    return masters


def _operations_context_provider(fixture: dict[str, Any]):
    fallback = FixtureContextProvider()
    if fixture["runtime"]["context_provider"] == "project3_http":
        return ResilientContextProvider(Project3HttpContextProvider(), fallback)
    return fallback


def build_manufacturing_service(
    database_path: str | Path,
    *,
    root: Path = ROOT,
) -> ManufacturingPredictiveMaintenanceService:
    """Compose the Operations application service with concrete runtime adapters."""

    target = str(database_path)
    migrate(target)
    audit_repository = (
        PostgreSQLAuditRepository(target)
        if is_postgresql(target)
        else AuditRepository(target)
    )
    maintenance_lineage_query = (
        PostgreSQLMaintenanceRepository(
            target,
            project_context=PostgreSQLProjectContextResolver(target),
            connection_factory=postgres_repository_connection,
        )
        if is_postgresql(target)
        else MaintenanceRepository(
            target,
            project_context=RuntimeProjectContextResolver(target),
        )
    )
    provider = configured_provider()
    company_context_repository = CompanyContextRepository(target)
    try:
        if is_postgresql(target):
            company_scope = PostgreSQLProjectContextResolver(target).resolve(MANUFACTURING_WORKSPACE)
            company_organization_id = company_scope.organization_id
        else:
            company_organization_id = "org-ontology-demo"
        company_context_repository.seed_records(
            organization_id=company_organization_id,
            project_id="manufacturing-demo-project",
            workspace_id=MANUFACTURING_WORKSPACE,
            context=load_company_context(),
        )
    except Exception:
        # Context persistence is an enrichment path. Core Operations must remain
        # available while an older DB is being migrated or a read-only Team DB
        # connection is intentionally used.
        pass
    equipment_service = EquipmentService(
        FixtureEquipmentRepository(_operations_fixture_masters(root))
    )
    return ManufacturingPredictiveMaintenanceService(
        root,
        repository=audit_repository,
        equipment_service=equipment_service,
        report_agent=ReportAgent(root, provider),
        layout_planner=LayoutPlanner(root, provider),
        context_provider_factory=_operations_context_provider,
        agent_review_summary_provider=AgentReviewSummaryProvider(provider),
        agent_answer_provider=GroundedAgentAnswerProvider(provider),
        agent_review_context_registry=default_agent_review_context_registry(),
        domain_review_context_adapter=ManufacturingFixtureReviewContextAdapter(root),
        maintenance_lineage_query=maintenance_lineage_query,
        company_context_query=company_context_repository,
        knowledge_search=_cached_knowledge_service(target),
        workspace_id=MANUFACTURING_WORKSPACE,
    )


@lru_cache(maxsize=1)
def _cached_manufacturing_service(target: str) -> ManufacturingPredictiveMaintenanceService:
    return build_manufacturing_service(target)


def get_service() -> ManufacturingPredictiveMaintenanceService:
    # lru_cache protects repeated calls after initialization, but it does not
    # serialize concurrent first misses. The public preview opens several
    # Operations reads in parallel after login; without this lock, each cold
    # request can run migrations and create its own PostgreSQL pool before the
    # first service is cached, exhausting low-limit Team DB roles.
    with _SERVICE_BUILD_LOCK:
        return _cached_manufacturing_service(database_target())


@lru_cache(maxsize=1)
def get_operational_decision_support_service() -> OperationalDecisionSupportService:
    target = database_target()
    if is_postgresql(target):
        return PersistedOperationalDecisionSupportService(ROOT, database_url=str(target))
    return PersistedOperationalDecisionSupportService(ROOT, Path(target))

def _password_hasher() -> PasswordHasher:
    return PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)


@lru_cache(maxsize=1)
def get_identity_service() -> IdentityService:
    ensure_database_migrations()
    target = database_target()
    repository = (
        PostgreSQLIdentityRepository(
            target,
            password_hasher=_password_hasher(),
            seed_reference_data=seed_runtime_reference_data(),
        )
        if is_postgresql(target)
        else SQLiteIdentityRepository(target, password_hasher=_password_hasher())
    )
    return IdentityService(repository, rate_limit_namespace=f"identity:{target}")


@lru_cache(maxsize=1)
def get_project_service() -> ProjectService:
    ensure_database_migrations()
    target = database_target()
    repository = PostgreSQLProjectRepository(target) if is_postgresql(target) else SQLiteProjectRepository(target)
    return ProjectService(repository, audit_port=get_identity_service().repository)


@lru_cache(maxsize=1)
def get_adapter_service() -> AdapterService:
    return build_adapter_service(database_target())


def build_adapter_service(
    database_path: str | Path,
    *,
    root: Path = ROOT,
) -> AdapterService:
    """Compose Dataset ingestion with persistence and Diagnosis ports."""

    target = str(database_path)
    migrate(target)
    if is_postgresql(target):
        repository = PostgreSQLAdapterRepository(target)
        predictions = PostgreSQLPredictionResultRepository(target)
    else:
        repository = DatasetIngestionRepository(target)
        predictions = PredictionResultRepository(
            target,
            project_context=RuntimeProjectContextResolver(target),
        )
    return AdapterService(
        target,
        root=root,
        repository=repository,
        prediction_repository=predictions,
        dataset_catalog=DatasetCatalogService(DatasetRepository(target)),
        bundle_ingestor_factory=PostgreSQLPredictiveMaintenanceBundleIngestor,
    )


def build_live_predictive_maintenance_service(
    database_url: str | None = None,
    *,
    runtime_pipeline_input_root: str | Path,
    simulation_session_id: str | None = None,
) -> LivePredictiveMaintenanceService:
    """Compose the live worker application service with its infrastructure adapter."""

    from app.infra.live_predictive_maintenance_runtime import (
        LiveDatasetIngestionAdapter,
        LiveDiagnosisApplicationAdapter,
        LiveMaintenanceOverlayAdapter,
        LiveOntologyProjectionAdapter,
    )
    from app.infra.generator_runtime_pipeline import GeneratorRuntimePipelineClient

    target = database_url or database_target()
    enqueue_client = GeneratorRuntimePipelineClient()
    shared = {
        "predictor_factory": configured_predictor,
        "artifact_builder": build_product_result_artifact,
    }
    simulation_session_id = simulation_session_id or (
        os.getenv("ONTOLOGY_DASHBOARD_SIMULATION_SESSION_ID", "").strip() or None
    )
    return LivePredictiveMaintenanceService(
        dataset=LiveDatasetIngestionAdapter(
            target,
            **shared,
            allow_accelerated_simulation=os.getenv(
                "ONTOLOGY_DASHBOARD_ALLOW_ACCELERATED_SIMULATION", "0"
            ).lower()
            in {"1", "true", "yes"},
            simulation_session_id=simulation_session_id,
        ),
        diagnosis=LiveDiagnosisApplicationAdapter(
            snapshot_root=runtime_pipeline_input_root,
            enqueue_client=enqueue_client,
            simulation_session_id=simulation_session_id,
        ),
        maintenance=LiveMaintenanceOverlayAdapter(
            snapshot_root=runtime_pipeline_input_root,
            enqueue_client=enqueue_client,
        ),
        ontology=LiveOntologyProjectionAdapter(),
    )


def _ontology_principal(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError("authentication_required", "로그인이 필요합니다.")
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
        project_id = principal.active_project_id or (principal.project_scopes[0] if len(principal.project_scopes) == 1 else None)
        if not project_id:
            raise AuthError("active_project_required", "Ontology를 조회하기 전에 Project를 활성화해야 합니다.")
        field_actions = PostgreSQLRoleWorkflowRepository(target)
        return OntologyService(
            service,
            action_repository=PostgreSQLOntologyActionRepository(target),
            instance_repository=PostgreSQLOntologyInstanceRepository(
                target,
                organization_id=principal.organization_id,
                project_id=project_id,
            ),
            field_actions=field_actions,
        )
    project_context = SQLiteProjectContextResolver(target)
    field_actions = RoleWorkflowRepository(target)
    return OntologyService(
        service,
        action_repository=OntologyActionRepository(target, project_context=project_context),
        instance_repository=OntologyInstanceRepository(target, project_context=project_context),
        field_actions=field_actions,
    )


def get_dashboard_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
) -> DashboardService:
    target = str(service.repository.path)
    repository = (
        PostgreSQLDashboardRepository(target)
        if is_postgresql(target)
        else DashboardRepository(target, project_context=SQLiteProjectContextResolver(target))
    )
    return DashboardService(repository=repository)


def get_role_workflow_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
) -> RoleWorkflowService:
    target = str(service.repository.path)
    repository = PostgreSQLRoleWorkflowRepository(target) if is_postgresql(target) else RoleWorkflowRepository(target)
    return RoleWorkflowService(service, repository=repository, ontology=ontology, dashboards=dashboards)


class _DashboardReportSnapshotAdapter:
    def __init__(self, dashboards: DashboardService) -> None:
        self.dashboards = dashboards

    def dashboard_snapshot(self, *, principal: Principal, workspace_id: str) -> dict[str, Any]:
        return self.dashboards.resolve(principal=principal, workspace_id=workspace_id).model_dump(mode="json")


class _DiagnosisReportSnapshotAdapter:
    def __init__(self, service: ManufacturingPredictiveMaintenanceService) -> None:
        self.service = service

    def event_report_snapshot(self, *, event_id: str, principal: Principal) -> dict[str, Any]:
        return {
            "event": self.service.event(event_id),
            "evidence": self.service.evidence_snapshot(event_id),
            "activity": self.service.repository.event_activity(event_id),
        }


class _RoleWorkspaceReportAdapter:
    def __init__(self, workflows: RoleWorkflowService, service: ManufacturingPredictiveMaintenanceService, dashboards: DashboardService) -> None:
        self.workflows = workflows
        self.service = service
        self.dashboards = dashboards

    def role_workspace_snapshot(self, *, principal: Principal, workspace_id: str) -> dict[str, Any]:
        return self.dashboards.resolve(principal=principal, workspace_id=workspace_id).model_dump(mode="json")


class _ReportAuditAdapter:
    def __init__(self, service: ManufacturingPredictiveMaintenanceService) -> None:
        self.service = service

    def record_report_audit(self, **command: Any) -> dict[str, Any]:
        return self.service.repository.record_audit(**command)


def get_export_service(
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
) -> ReportService:
    target = str(service.repository.path)
    repository = (
        PostgreSQLExportRepository(target)
        if is_postgresql(target)
        else ReportRepository(target, project_context=SQLiteProjectContextResolver(target))
    )
    return ReportService(
        repository=repository,
        dashboard=_DashboardReportSnapshotAdapter(dashboards),
        diagnosis=_DiagnosisReportSnapshotAdapter(service),
        maintenance=_RoleWorkspaceReportAdapter(workflows, service, dashboards),
        audit=_ReportAuditAdapter(service),
    )


@lru_cache(maxsize=1)
def get_dataset_catalog_service() -> DatasetCatalogService:
    target = database_target()
    migrate(target)
    return DatasetCatalogService(DatasetRepository(target))


def get_governance_service(
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
) -> GovernanceService:
    return GovernanceService(datasets=get_dataset_catalog_service().repository, approvals=workflows.repository)


@lru_cache(maxsize=1)
def get_agent_run_repository() -> AgentRunRepository:
    target = database_target()
    migrate(target)
    return AgentRunRepository(target)


@lru_cache(maxsize=1)
def get_predictive_maintenance_runtime_service() -> PredictiveMaintenanceRuntimeService:
    target = database_target()
    migrate(target)
    if not is_postgresql(target):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Predictive-maintenance live runtime requires PostgreSQL",
        )
    return PredictiveMaintenanceRuntimeService(PredictiveMaintenanceRuntimeRepository(target))


@lru_cache(maxsize=1)
def get_runtime_asset_detail_service() -> AssetDetailViewModelService | None:
    """Return the authoritative PostgreSQL AssetDetail read boundary when available."""

    target = database_target()
    if not is_postgresql(target):
        return None
    from app.infra.db.asset_detail_read_adapter import PostgreSQLAssetDetailReadAdapter

    return AssetDetailViewModelService(
        PostgreSQLAssetDetailReadAdapter(PredictiveMaintenanceRuntimeRepository(target))
    )


class _RuntimeThenDemoEvidenceProjection:
    """Resolve production runtime evidence first and local MVP fixtures second.

    The fallback is deliberately restricted to the local demonstration scope.
    It lets the two-role MVP exercise the real Maintenance command boundary
    without teaching Maintenance how fixture Product Results are built.
    """

    def __init__(
        self,
        runtime: PredictiveMaintenanceRuntimeService,
        demo: ManufacturingPredictiveMaintenanceService,
    ) -> None:
        self.runtime = runtime
        self.demo = demo

    def event_evidence_projection(self, **scope: Any) -> dict[str, Any] | None:
        projection = self.runtime.event_evidence_projection(**scope)
        if projection is not None:
            return projection
        if app_environment() not in {"development", "demo", "test"}:
            return None
        if (
            scope.get("project_id") != "manufacturing-demo-project"
            or scope.get("workspace_id") != MANUFACTURING_WORKSPACE
        ):
            return None
        event_id = str(scope.get("event_id") or "")
        try:
            if self.demo.project_id_for_event(event_id) != scope.get("project_id"):
                return None
            return self.demo.event_evidence_projection(event_id)
        except KeyError:
            return None


@lru_cache(maxsize=1)
def get_maintenance_loop_service() -> MaintenanceLoopService:
    """Compose the canonical Maintenance command/read boundary."""

    ensure_database_migrations()
    target = database_target()
    if is_postgresql(target):
        context = PostgreSQLProjectContextResolver(target)
        repository = PostgreSQLMaintenanceRepository(
            target,
            project_context=context,
            connection_factory=postgres_repository_connection,
        )
    else:
        repository = MaintenanceRepository(
            target,
            project_context=RuntimeProjectContextResolver(target),
        )
    diagnosis_runtime = get_predictive_maintenance_runtime_service()
    return MaintenanceLoopService(
        repository,
        event_evidence_query=_RuntimeThenDemoEvidenceProjection(
            diagnosis_runtime,
            get_service(),
        ),
        replay_session_query=diagnosis_runtime,
        cost_basis_provider=JsonMaintenanceCostBasisProvider(
            ROOT
            / "data"
            / "fixtures"
            / "maintenance_cost"
            / "tool-insert-cost-basis-v1.json",
            ROOT
            / "data"
            / "fixtures"
            / "maintenance_cost"
            / "cooling-system-restore-cost-basis-v1.json",
        ),
    )


class DashboardPlannerAdapter:
    def __init__(self, service: DashboardService) -> None:
        self.service = service

    def resolve(self, *, principal: Principal, workspace_id: str):
        return self.service.resolve(principal=principal, workspace_id=workspace_id)

    def catalog(self, *, principal: Principal, role_code: str):
        return self.service.catalog(principal=principal, role_code=role_code)

    def current_template(self, *, workspace_id: str, role_code: str):
        return self.service.current_template(workspace_id=workspace_id, role_code=role_code)

    @staticmethod
    def make_board(**values):
        return DashboardBoard(**values)

    @staticmethod
    def make_tab(**values):
        return DashboardTab(**values)

    @staticmethod
    def make_publish_request(**values):
        return DashboardTemplatePublishRequest(**values)

    def validate_template_draft(self, *, role_code: str, template, request):
        return self.service.validate_template_draft(role_code=role_code, template=template, request=request)


class VisualizationPlannerAdapter:
    source_version = V3_1_SOURCE_VERSION
    model_version = V3_1_MODEL_VERSION
    result_schema_version = V3_1_RESULT_SCHEMA
    registry_kinds = frozenset(item.kind for item in VISUALIZATION_REGISTRY)

    @staticmethod
    def _payload(value):
        return value.model_dump(mode="python") if hasattr(value, "model_dump") else value

    def parse_field_profile(self, value):
        return FieldProfile.model_validate(self._payload(value))

    def parse_candidate(self, value):
        return VisualizationCandidate.model_validate(self._payload(value))

    def parse_semantic_request(self, value):
        return value if isinstance(value, SemanticVisualizationPlanRequest) else SemanticVisualizationPlanRequest.model_validate(self._payload(value))

    @staticmethod
    def context_from_source(source):
        return context_from_source(source)

    @staticmethod
    def build_semantic_catalog(context):
        return build_v3_1_semantic_catalog(context)

    @staticmethod
    def build_typed_query_plan(request, catalog, *, selected_kind=None):
        return build_typed_query_plan(request, catalog, selected_kind=selected_kind)

    @staticmethod
    def validate_override(override, plan, catalog):
        return validate_override(override, plan, catalog)

    @staticmethod
    def validate_override_channel_mapping(override, plan) -> None:
        validate_override_channel_mapping(override, plan)

    @staticmethod
    def compile_query(plan, catalog, *, clamp_limits: bool):
        return compile_postgresql_query(plan, catalog, clamp_limits=clamp_limits)

    @staticmethod
    def make_semantic_response(**values):
        return SemanticVisualizationPlanResponse(**values)


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
        dashboards=DashboardPlannerAdapter(dashboards),
        visualizations=VisualizationPlannerAdapter(),
    )


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    redis_url = os.getenv("ONTOLOGY_DASHBOARD_REDIS_URL", "").strip()
    return RedisRateLimiter(redis_url) if redis_url else InMemoryRateLimiter()


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
    try:
        return str(ipaddress.ip_address(forwarded)) if forwarded else peer
    except ValueError:
        return peer


def rate_limit_subject(*parts: str) -> str:
    return InMemoryRateLimiter.anonymized_key(*parts)


def set_auth_cookies(*, response: Response, identity: IdentityService, token: str, csrf_token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, expires=expires_at, httponly=True, secure=identity.secure_cookies, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=max_age, expires=expires_at, httponly=False, secure=identity.secure_cookies, samesite="lax", path="/")


def current_principal(request: Request, identity: IdentityService = Depends(get_identity_service)) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError("authentication_required", "로그인이 필요합니다.")
    return identity.principal_for_token(token, user_agent=request.headers.get("User-Agent"), client_ip=client_ip(request))


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


def require_csrf(request: Request, identity: IdentityService = Depends(get_identity_service)) -> None:
    identity.verify_csrf(request.cookies.get(CSRF_COOKIE), request.headers.get("X-CSRF-Token"))


__all__ = [name for name in globals() if name.startswith("get_") or name in {
    "MANUFACTURING_WORKSPACE", "client_ip", "current_principal", "rate_limit_subject",
    "require_csrf", "require_manufacturing_scope", "require_permission", "set_auth_cookies",
}]
