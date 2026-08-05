"""Field-level response contracts for every public API route.

The product initially focused on request validation and returned serialized
Pydantic objects from route handlers without declaring FastAPI ``response_model``
values.  That left successful OpenAPI responses as ``schema: {}``, which Swagger
UI misleadingly rendered as ``"string"``.

This module attaches real response models before routers are included in the
application.  Direct service calls inherit their existing Pydantic return type;
route-composed envelopes use explicit models defined below.  The resulting
contracts are used both by OpenAPI and by FastAPI response validation.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from copy import deepcopy
from datetime import datetime
from typing import Any, Generic, TypeVar, get_type_hints

from fastapi import APIRouter
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response, StreamingResponse

from .analysis_models import AnalysisRunResult
from .application_runtime import ApplicationRuntimeSnapshot
from .branching_lineage import BranchDiff, BranchingLineageSnapshot, PolicyDecision
from .contracts import GroundedReport, UILayout
from .connectors import ConnectorSnapshot
from .dashboard_models import (
    DashboardSharePayload,
    DashboardTemplateSnapshot,
    ReportDraftRecord,
    SavedViewRecord,
)
from .datasets.models import (
    DatasetDetail,
    DatasetPage,
    DatasetVersionRecord,
    MaterializationRecord,
    OntologyMappingRecord,
)
from .domain_packs.models import (
    DomainPackDefinition as PlatformDomainPackDefinition,
    ProjectApplicationDefinition,
)
from .enterprise_identity import EnterpriseIdentityReadiness
from .deployment import DeploymentReadiness, ProcessProbe, ReadinessProbe, StartupProbe
from .distributed_runtime import (
    DistributedRuntimeSnapshot,
    DurableJob,
    DurableJobEventPage,
)
from .export_models import ExportCheckpoint
from .governance.models import GovernanceAgentRunDetail, ProjectionRetryResult
from .identity_models import DisplayPreferenceUpdateRequest, Principal
from .integrations.project3.models import Project3IntegrationSnapshot
from .modeling.models import (
    CapabilityEvaluation,
    ExperimentRun,
    ExplanationArtifact,
    FeatureDatasetVersion,
    ManifestDraft,
    MappingSet,
    ModelReleaseRequestRecord,
    ModelScoreResult,
    ModelingContractSummary,
    ModelVersion,
)
from .ontology import (
    ActionTypeDefinition,
    DomainPackDefinition,
    LinkTypeDefinition,
    ObjectRecord,
    ObjectTypeDefinition,
)
from .ontology_primitives import ActionPreview, FunctionExecution, PrimitiveSnapshot
from .orchestration.models import AgentRunResponse
from .predictive_maintenance_runtime.models import (
    DatasetVersionRuntimeContext,
    ReplaySessionSnapshot,
    TimelinePrediction,
)
from .persistence_readiness import PersistenceReadiness
from .pipeline_runtime import PipelinePlan
from .projects.models import Project


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


T = TypeVar("T")


class ItemsResponse(ContractModel, Generic[T]):
    items: list[T]


PROJECT_LIST_EXAMPLE = {
    "items": [
        {
            "id": "manufacturing-demo-project",
            "organization_id": "org-ontology-demo",
            "slug": "manufacturing-demo-project",
            "display_name": "Manufacturing Demo Project",
            "description": "Predictive-maintenance ontology dashboard demo",
            "domain_pack_code": "manufacturing-predictive-maintenance",
            "status": "active",
            "default_workspace_id": "manufacturing-demo",
            "created_at": "2026-08-05T00:00:00Z",
            "updated_at": "2026-08-05T00:00:00Z",
        }
    ]
}


class ProjectListResponse(ContractModel):
    items: list[Project]

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": PROJECT_LIST_EXAMPLE},
    )


class StoreHealthResponse(ContractModel):
    store: str
    status: str
    configured: bool
    required: bool
    latency_ms: int | None = None
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolyglotHealthResponse(ContractModel):
    status: str
    stores: list[StoreHealthResponse]
    configuration: dict[str, Any]
    capability_boundaries: dict[str, Any]


class HealthResponse(ContractModel):
    status: str
    service: str
    mode: str
    domain_pack: str


class RegisterResponse(ContractModel):
    user_id: str
    email: str
    display_name: str
    status: str
    requested_organization_name: str
    requested_role: str


class AuthSessionResponse(ContractModel):
    user: Principal
    csrf_token: str


class CurrentUserResponse(ContractModel):
    user: Principal
    csrf_token: str | None = None


class ActiveProjectResponse(ContractModel):
    user: Principal


class DisplayPreferenceRecord(DisplayPreferenceUpdateRequest):
    updated_at: datetime | str


class DisplayPreferencesResponse(ContractModel):
    preferences: DisplayPreferenceRecord | None


class SessionRecord(ContractModel):
    id: str
    created_at: datetime | str
    last_seen_at: datetime | str
    expires_at: datetime | str
    user_agent_bound: bool
    ip_observed: bool
    rotated_from: str | None = None
    current: bool


class RevokedSessionsResponse(ContractModel):
    revoked: int


class PredictionResultRecord(ContractModel):
    prediction_id: str
    organization_id: str
    project_id: str
    workspace_id: str
    subject_object_type: str
    subject_object_id: str
    prediction_status: str
    model_version: str
    dataset_version: str
    created_at: datetime | str
    received_at: datetime | str


class OntologyRegistryResponse(ContractModel):
    domain_packs: list[DomainPackDefinition]
    object_types: list[ObjectTypeDefinition]
    link_types: list[LinkTypeDefinition]
    action_types: list[ActionTypeDefinition]


class OntologyObjectPage(ContractModel):
    workspace_id: str
    domain_pack: str
    object_type: str | None = None
    dataset_version_id: str | None = None
    search: str | None = None
    offset: int
    limit: int
    total: int
    items: list[ObjectRecord]


class OntologyAggregateResponse(ContractModel):
    workspace_id: str
    object_type: str
    dataset_version_id: str | None = None
    group_by: list[str]
    metrics: list[str]
    source_rows: int
    row_count: int
    rows: list[dict[str, Any]]
    generated_at: datetime | str


class ActionInvocationRecord(ContractModel):
    invocation_id: str
    action_type: str
    object_id: str
    workspace_id: str
    actor_user_id: str
    actor_display_name: str
    state: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | str | None = None
    audit_id: str | None = None
    created_at: datetime | str
    completed_at: datetime | str | None = None


class ReportDraftResponse(ContractModel):
    draft: ReportDraftRecord | None


class TimelineResponse(ContractModel):
    context: DatasetVersionRuntimeContext
    items: list[TimelinePrediction]
    total: int
    offset: int
    limit: int
    source: str
    model_retrained: bool


class ArtifactCapability(ContractModel):
    status: str
    reason: str | None = None
    canonical_uri_scheme: str
    local_path_is_identity: bool


class ModelingContractsResponse(ModelingContractSummary):
    artifact_capability: ArtifactCapability
    organization_id: str
    project_id: str
    workspace_id: str


class ManifestIngestionResponse(ContractModel):
    ingestion: dict[str, Any]
    dataset_id: str
    dataset_version: DatasetVersionRecord
    manifest_draft_id: str


class ExperimentCapabilitiesResponse(ContractModel):
    synchronous_training_endpoint: bool
    execution_mode: str
    algorithms: dict[str, Any]


class ModelReleaseDecisionResponse(ContractModel):
    release_request: ModelReleaseRequestRecord
    model_version: ModelVersion


class ModelScoreResponse(ContractModel):
    prediction: ModelScoreResult
    explanation: ExplanationArtifact


class ReportGenerationResponse(ContractModel):
    report: GroundedReport
    trace: list[dict[str, Any]] | dict[str, Any]


class LayoutGenerationResponse(ContractModel):
    layout: UILayout
    trace: list[dict[str, Any]] | dict[str, Any]


class AdminOverviewResponse(ContractModel):
    active_users: int
    pending_users: int
    disabled_users: int
    workspace_count: int
    unread_notifications: int
    recent_admin_changes: list[dict[str, Any]]


class WorkflowApprovalsResponse(ContractModel):
    template_publish_requests: list[dict[str, Any]]
    model_release_requests: list[dict[str, Any]]


class WorkflowRequestResponse(BaseModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    workflow_type: str
    status: str
    requested_by: str
    requested_by_name: str
    payload: dict[str, Any]
    created_at: datetime | str
    updated_at: datetime | str
    target_role: str | None = None
    decision_by: str | None = None
    decision_by_name: str | None = None
    decision_note: str | None = None
    audit_id: str | None = None
    published_template: DashboardTemplateSnapshot | None = None

    model_config = ConfigDict(extra="allow")


class DashboardBoardQueryResponse(ContractModel):
    board_id: str
    rows: list[dict[str, Any]]
    row_count: int
    matching_object_ids: list[str]
    offset: int
    limit: int
    render_spec: dict[str, Any]
    field_profile: list[dict[str, Any]]
    visualization_recommendation: dict[str, Any]
    generated_at: datetime | str
    source_freshness_at: datetime | str | None = None
    timezone: str
    warnings: list[str]


class ApprovedManifestSource(ContractModel):
    uri: str
    checksum_sha256: str
    media_type: str


class ApprovedManifestApproval(ContractModel):
    draft_id: str
    revision: int
    approved_by: str | None = None
    rationale: str | None = None


class ApprovedManifestResponse(ContractModel):
    source: ApprovedManifestSource
    format: str
    encoding: str
    delimiter: str | None = None
    sheet: str | None = None
    selected_fields: list[dict[str, Any]]
    quality_rules: list[dict[str, Any]]
    approval: ApprovedManifestApproval


class AuditExportCheckpointResponse(ContractModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    event_id: str
    export_format: str
    reason: str
    content_hash: str
    requested_by: str
    requested_by_name: str
    created_at: datetime | str
    audit_id: str


class EquipmentResponse(BaseModel):
    equipment_id: str
    display_name: str
    line: str
    criticality: str
    assigned_engineer: str | None = None
    last_maintenance_date: str | None = None
    estimated_downtime_minutes: int | float | None = None
    spare_part_available: bool | None = None

    model_config = ConfigDict(extra="allow")


class EventResponse(BaseModel):
    event_id: str
    project_id: str | None = None
    scenario_id: str
    equipment: dict[str, Any]
    observation: dict[str, Any]
    history: dict[str, Any] | list[Any]
    runtime: dict[str, Any]
    activity: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class EvidenceResponse(BaseModel):
    schema_version: str
    evidence_id: str
    event_id: str
    scenario_id: str
    equipment: dict[str, Any]
    model: dict[str, Any]
    status: str
    recommended_decision: str
    confidence: str | float
    failure_probability: float | None = None
    threshold: float | None = None
    predicted_failure_type: str | None = None
    observation: dict[str, Any]
    history: dict[str, Any] | list[Any]
    detected_interval: dict[str, Any] | None = None
    top_factors: list[dict[str, Any]]
    maintenance_context: dict[str, Any]
    data_quality_warnings: list[Any]
    lineage: dict[str, Any]
    generated_at: datetime | str

    model_config = ConfigDict(extra="allow")


class ActionMutationResponse(BaseModel):
    id: str | None = None
    event_id: str | None = None
    action: str | None = None
    decision: str | None = None
    note: str | None = None
    body: str | None = None
    actor_user_id: str | None = None
    actor_display_name: str | None = None
    created_at: datetime | str | None = None

    model_config = ConfigDict(extra="allow")


class EventActivityResponse(ContractModel):
    decisions: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    conversations: list[dict[str, Any]]


class AdminNotificationResponse(BaseModel):
    id: str
    organization_id: str | None = None
    notification_type: str
    target_user_id: str | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime | str
    read_at: datetime | str | None = None
    target_email: str | None = None
    target_display_name: str | None = None
    requested_role_code: str | None = None

    model_config = ConfigDict(extra="allow")


class AdminUserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    status: str
    organization_id: str | None = None
    organization_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    workspace_scopes: list[str] = Field(default_factory=list)
    project_scopes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ProjectMembershipResponse(BaseModel):
    user_id: str
    project_id: str
    roles: list[str] = Field(default_factory=list)
    active: bool | None = None

    model_config = ConfigDict(extra="allow")


class ModelingWorkbenchResponse(ContractModel):
    project_id: str
    workspace_id: str
    contracts: dict[str, Any] | list[Any] | None = None
    intake_profiles: list[dict[str, Any]] = Field(default_factory=list)
    manifest_drafts: list[dict[str, Any]] = Field(default_factory=list)
    mapping_sets: list[dict[str, Any]] = Field(default_factory=list)
    feature_recipe_sets: list[dict[str, Any]] = Field(default_factory=list)
    feature_dataset_versions: list[dict[str, Any]] = Field(default_factory=list)
    experiments: list[dict[str, Any]] = Field(default_factory=list)
    model_versions: list[dict[str, Any]] = Field(default_factory=list)
    release_requests: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class FlexibleObjectResponse(BaseModel):
    """Named object contract for inherently dynamic domain payloads."""

    model_config = ConfigDict(extra="allow")


class ConnectorRunQueuedResponse(ContractModel):
    job_id: str
    state: str
    reason: str


class GlobalSearchResponse(ContractModel):
    items: tuple[dict[str, Any], ...]


def _qname(endpoint: Any) -> str:
    return f"{endpoint.__module__}.{endpoint.__name__}"


_EXPLICIT_MODELS: dict[str, Any] = {
    "ontology_dashboard.routers.system.health": HealthResponse,
    "ontology_dashboard.routers.system.health_live": ProcessProbe,
    "ontology_dashboard.routers.system.health_startup": StartupProbe,
    "ontology_dashboard.routers.system.health_ready": ReadinessProbe,
    "ontology_dashboard.routers.system.polyglot_health": PolyglotHealthResponse,
    "ontology_dashboard.routers.system.openapi_contract": dict[str, Any],
    "ontology_dashboard.routers.auth.register": RegisterResponse,
    "ontology_dashboard.routers.auth.login": AuthSessionResponse,
    "ontology_dashboard.routers.auth.public_blueprint_comparison": AuthSessionResponse,
    "ontology_dashboard.routers.auth.me": CurrentUserResponse,
    "ontology_dashboard.routers.auth.get_display_preferences": DisplayPreferencesResponse,
    "ontology_dashboard.routers.auth.save_display_preferences": DisplayPreferenceRecord,
    "ontology_dashboard.routers.auth.set_active_project": ActiveProjectResponse,
    "ontology_dashboard.routers.auth.refresh_session": AuthSessionResponse,
    "ontology_dashboard.routers.auth.list_sessions": ItemsResponse[SessionRecord],
    "ontology_dashboard.routers.auth.revoke_other_sessions": RevokedSessionsResponse,
    "ontology_dashboard.routers.agent.inspect_agent_run": AgentRunResponse,
    "ontology_dashboard.routers.adapters.list_adapters": ItemsResponse[dict[str, str]],
    "ontology_dashboard.routers.adapters.list_project_datasets": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.adapters.list_project_predictions": ItemsResponse[PredictionResultRecord],
    "ontology_dashboard.routers.adapters.ingest_prediction_result": PredictionResultRecord,
    "ontology_dashboard.routers.datasets.list_datasets": DatasetPage,
    "ontology_dashboard.routers.datasets.dataset_detail": DatasetDetail,
    "ontology_dashboard.routers.datasets.create_dataset_version": DatasetVersionRecord,
    "ontology_dashboard.routers.datasets.save_ontology_mapping": OntologyMappingRecord,
    "ontology_dashboard.routers.datasets.create_materialization": MaterializationRecord,
    "ontology_dashboard.routers.ontology.list_workspaces": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.ontology.list_domain_packs": ItemsResponse[DomainPackDefinition],
    "ontology_dashboard.routers.ontology.ontology_registry": OntologyRegistryResponse,
    "ontology_dashboard.routers.ontology.list_object_types": ItemsResponse[ObjectTypeDefinition],
    "ontology_dashboard.routers.ontology.list_link_types": ItemsResponse[LinkTypeDefinition],
    "ontology_dashboard.routers.ontology.list_action_types": ItemsResponse[ActionTypeDefinition],
    "ontology_dashboard.routers.ontology.query_ontology_objects": OntologyObjectPage,
    "ontology_dashboard.routers.ontology.aggregate_ontology_objects": OntologyAggregateResponse,
    "ontology_dashboard.routers.ontology.list_ontology_action_invocations": ItemsResponse[ActionInvocationRecord],
    "ontology_dashboard.routers.analyses.queue_analysis_run": AnalysisRunResult,
    "ontology_dashboard.routers.projects.list_projects": ProjectListResponse,
    "ontology_dashboard.routers.projects.list_project_workspaces": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.projects.list_project_events": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.platform.domain_pack_catalog": ItemsResponse[PlatformDomainPackDefinition],
    "ontology_dashboard.routers.platform.project_v4_application": ProjectApplicationDefinition,
    "ontology_dashboard.routers.platform.project_persistence_readiness": PersistenceReadiness,
    "ontology_dashboard.routers.platform.project_enterprise_identity": EnterpriseIdentityReadiness,
    "ontology_dashboard.routers.platform.project_deployment_readiness": DeploymentReadiness,
    "ontology_dashboard.routers.platform.project_distributed_runtime": DistributedRuntimeSnapshot,
    "ontology_dashboard.routers.platform.project_connectors": ConnectorSnapshot,
    "ontology_dashboard.routers.platform.run_project_connector": ConnectorRunQueuedResponse,
    "ontology_dashboard.routers.platform.project_ontology_primitives": PrimitiveSnapshot,
    "ontology_dashboard.routers.platform.preview_project_action": ActionPreview,
    "ontology_dashboard.routers.platform.execute_project_function": FunctionExecution,
    "ontology_dashboard.routers.platform.project_branching_lineage": BranchingLineageSnapshot,
    "ontology_dashboard.routers.platform.create_project_branch_change": BranchDiff,
    "ontology_dashboard.routers.platform.merge_project_branch": BranchDiff,
    "ontology_dashboard.routers.platform.check_project_policy": PolicyDecision,
    "ontology_dashboard.routers.platform.project_application_runtime": ApplicationRuntimeSnapshot,
    "ontology_dashboard.routers.platform.project_global_search": GlobalSearchResponse,
    "ontology_dashboard.routers.platform.project_sample_pipeline_plan": PipelinePlan,
    "ontology_dashboard.routers.platform.project_pipeline_plan": PipelinePlan,
    "ontology_dashboard.routers.platform.project_distributed_job_events": DurableJobEventPage,
    "ontology_dashboard.routers.platform.cancel_distributed_job": DurableJob,
    "ontology_dashboard.routers.platform.replay_distributed_job": DurableJob,
    "ontology_dashboard.routers.dashboards.get_report_draft": ReportDraftResponse,
    "ontology_dashboard.routers.dashboards.dashboard_template_versions": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.dashboards.request_dashboard_template_publish": WorkflowRequestResponse,
    "ontology_dashboard.routers.dashboards.query_dashboard_board": DashboardBoardQueryResponse,
    "ontology_dashboard.routers.dashboards.list_dashboard_saved_views": ItemsResponse[SavedViewRecord],
    "ontology_dashboard.routers.dashboards.resolve_dashboard_share": DashboardSharePayload,
    "ontology_dashboard.routers.exports.list_export_checkpoints": ItemsResponse[ExportCheckpoint],
    "ontology_dashboard.routers.governance.governance_agent_run": GovernanceAgentRunDetail,
    "ontology_dashboard.routers.governance.retry_projection": ProjectionRetryResult,
    "ontology_dashboard.routers.project3.project3_status": Project3IntegrationSnapshot,
    "ontology_dashboard.routers.predictive_maintenance_runtime.prediction_timeline": TimelineResponse,
    "ontology_dashboard.routers.modeling.modeling_contracts": ModelingContractsResponse,
    "ontology_dashboard.routers.modeling.approved_manifest_payload": ApprovedManifestResponse,
    "ontology_dashboard.routers.modeling.ingest_approved_manifest_draft": ManifestIngestionResponse,
    "ontology_dashboard.routers.modeling.mapping_capabilities": ItemsResponse[CapabilityEvaluation],
    "ontology_dashboard.routers.modeling.experiment_capabilities": ExperimentCapabilitiesResponse,
    "ontology_dashboard.routers.modeling.list_experiments": ItemsResponse[ExperimentRun],
    "ontology_dashboard.routers.modeling.list_model_versions": ItemsResponse[ModelVersion],
    "ontology_dashboard.routers.modeling.list_model_release_requests": ItemsResponse[ModelReleaseRequestRecord],
    "ontology_dashboard.routers.modeling.decide_model_release": ModelReleaseDecisionResponse,
    "ontology_dashboard.routers.modeling.score_model_version": ModelScoreResponse,
    "ontology_dashboard.routers.modeling.modeling_workbench": ModelingWorkbenchResponse,
    "ontology_dashboard.routers.role_workspaces.create_audit_export_checkpoint": AuditExportCheckpointResponse,
    "ontology_dashboard.routers.role_workspaces.create_model_release_request": WorkflowRequestResponse,
    "ontology_dashboard.routers.manufacturing.list_equipment": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.manufacturing.get_equipment": EquipmentResponse,
    "ontology_dashboard.routers.manufacturing.list_events": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.manufacturing.get_event": EventResponse,
    "ontology_dashboard.routers.manufacturing.get_evidence": EvidenceResponse,
    "ontology_dashboard.routers.manufacturing.create_report": ReportGenerationResponse,
    "ontology_dashboard.routers.manufacturing.create_layout": LayoutGenerationResponse,
    "ontology_dashboard.routers.manufacturing.record_decision": ActionMutationResponse,
    "ontology_dashboard.routers.manufacturing.add_note": ActionMutationResponse,
    "ontology_dashboard.routers.manufacturing.event_activity": EventActivityResponse,
    "ontology_dashboard.routers.admin.admin_overview": AdminOverviewResponse,
    "ontology_dashboard.routers.admin.admin_notifications": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.admin.admin_mark_notification_read": AdminNotificationResponse,
    "ontology_dashboard.routers.admin.admin_users": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.admin.admin_project_members": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.admin.admin_update_project_membership": ProjectMembershipResponse,
    "ontology_dashboard.routers.admin.admin_update_user": AdminUserResponse,
    "ontology_dashboard.routers.admin.admin_roles": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.admin.admin_workspaces": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.admin.admin_audit": ItemsResponse[dict[str, Any]],
    "ontology_dashboard.routers.admin.admin_workflow_approvals": WorkflowApprovalsResponse,
    "ontology_dashboard.routers.admin.admin_decide_template_publish_request": WorkflowRequestResponse,
    "ontology_dashboard.routers.admin.admin_decide_model_release_request": WorkflowRequestResponse,
}


_EXPLICIT_MEDIA_EXAMPLES: dict[str, dict[str, Any]] = {
    "ontology_dashboard.routers.projects.list_projects": PROJECT_LIST_EXAMPLE,
}


_NO_CONTENT_ENDPOINTS = {
    "ontology_dashboard.routers.auth.logout",
    "ontology_dashboard.routers.dashboards.delete_dashboard_saved_view",
}

_BINARY_ENDPOINTS = {"ontology_dashboard.routers.exports.create_export"}
_SSE_ENDPOINTS = {
    "ontology_dashboard.routers.predictive_maintenance_runtime.replay_events"
}


def _safe_type_hints(target: Any) -> dict[str, Any]:
    try:
        return get_type_hints(target)
    except Exception:
        return getattr(target, "__annotations__", {})


def _resolve_call_expression(expression: ast.expr, assignments: dict[str, ast.expr]) -> tuple[str, str] | None:
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr == "model_dump"
    ):
        return _resolve_call_expression(expression.func.value, assignments)
    if isinstance(expression, ast.Name) and expression.id in assignments:
        return _resolve_call_expression(assignments[expression.id], assignments)
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and isinstance(expression.func.value, ast.Name)
    ):
        return expression.func.value.id, expression.func.attr
    return None


def _infer_service_response_model(endpoint: Any) -> Any | None:
    """Infer a Pydantic model from ``service.method(...).model_dump()`` returns."""

    try:
        source = textwrap.dedent(inspect.getsource(endpoint))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return None
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        None,
    )
    if function is None:
        return None

    assignments: dict[str, ast.expr] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                assignments[node.target.id] = node.value

    endpoint_hints = _safe_type_hints(endpoint)
    candidates: list[type[BaseModel]] = []
    for returned in (
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Return) and node.value is not None
    ):
        target = _resolve_call_expression(returned.value, assignments)
        if target is None:
            continue
        parameter_name, method_name = target
        owner = endpoint_hints.get(parameter_name)
        if owner is None or not hasattr(owner, method_name):
            continue
        annotation = _safe_type_hints(getattr(owner, method_name)).get("return")
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            candidates.append(annotation)

    if candidates and all(candidate is candidates[0] for candidate in candidates):
        return candidates[0]
    return None


def response_model_for(endpoint: Any, existing: Any = None) -> Any | None:
    explicit = _EXPLICIT_MODELS.get(_qname(endpoint))
    if explicit is not None:
        return explicit
    if existing is not None:
        return existing
    return _infer_service_response_model(endpoint)


def _clone_route(
    route: APIRoute,
    *,
    response_model: Any,
    response_class: Any | None = None,
    responses: dict[int | str, dict[str, Any]] | None = None,
) -> APIRoute:
    return APIRoute(
        path=route.path,
        endpoint=route.endpoint,
        response_model=response_model,
        status_code=route.status_code,
        tags=route.tags,
        dependencies=route.dependencies,
        summary=route.summary,
        description=route.description,
        response_description=route.response_description,
        responses=route.responses if responses is None else responses,
        deprecated=route.deprecated,
        name=route.name,
        methods=route.methods,
        operation_id=route.operation_id,
        response_model_include=route.response_model_include,
        response_model_exclude=route.response_model_exclude,
        response_model_by_alias=route.response_model_by_alias,
        response_model_exclude_unset=route.response_model_exclude_unset,
        response_model_exclude_defaults=route.response_model_exclude_defaults,
        response_model_exclude_none=route.response_model_exclude_none,
        include_in_schema=route.include_in_schema,
        response_class=route.response_class if response_class is None else response_class,
        dependency_overrides_provider=route.dependency_overrides_provider,
        callbacks=route.callbacks,
        openapi_extra=route.openapi_extra,
        generate_unique_id_function=route.generate_unique_id_function,
        strict_content_type=route.strict_content_type,
    )


def apply_response_contracts(router: APIRouter) -> None:
    """Attach response validation and documentation contracts to one router."""

    rebuilt: list[Any] = []
    for route in router.routes:
        if not isinstance(route, APIRoute):
            rebuilt.append(route)
            continue

        endpoint_name = _qname(route.endpoint)
        if endpoint_name in _NO_CONTENT_ENDPOINTS:
            rebuilt.append(_clone_route(route, response_model=None))
            continue
        if endpoint_name in _BINARY_ENDPOINTS:
            rebuilt.append(
                _clone_route(
                    route,
                    response_model=None,
                    response_class=Response,
                    responses={
                        200: {
                            "description": "Generated export artifact",
                            "content": {
                                "application/octet-stream": {
                                    "schema": {"type": "string", "format": "binary"}
                                }
                            },
                        }
                    },
                )
            )
            continue
        if endpoint_name in _SSE_ENDPOINTS:
            rebuilt.append(
                _clone_route(
                    route,
                    response_model=None,
                    response_class=StreamingResponse,
                    responses={
                        200: {
                            "description": "Replay event stream",
                            "content": {
                                "text/event-stream": {"schema": {"type": "string"}}
                            },
                        }
                    },
                )
            )
            continue

        model = response_model_for(route.endpoint, route.response_model)
        if model is None:
            raise RuntimeError(
                f"missing response contract for {next(iter(route.methods or []), '?')} {route.path} "
                f"({_qname(route.endpoint)})"
            )
        responses = route.responses
        media_example = _EXPLICIT_MEDIA_EXAMPLES.get(endpoint_name)
        if media_example is not None:
            responses = deepcopy(route.responses)
            success = responses.setdefault(
                route.status_code or 200,
                {"description": "Successful Response"},
            )
            content = success.setdefault("content", {})
            content.setdefault("application/json", {})["example"] = media_example
        rebuilt.append(
            _clone_route(route, response_model=model, responses=responses)
        )

    router.routes[:] = rebuilt


__all__ = ["apply_response_contracts", "response_model_for"]
