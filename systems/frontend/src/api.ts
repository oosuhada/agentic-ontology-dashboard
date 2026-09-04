import type {
  BoardRecommendationResponse,
  DashboardDraftResponse,
  ExportArtifact,
  GroundedNarrativeResponse,
  ObjectQueryPlanResponse,
  SemanticVisualizationPlanInput,
  SemanticVisualizationPlanResponse,
  VisualizationPlannerResponse,
} from "./features/planner/types";
import type { AgentQueryInput, AgentRunPage, AgentRunResponse } from "./features/agent/types";
import type {
  EvidenceSnapshotBasisWire,
  OperationsAgentReviewPacket,
  OperationsAgentReviewSummaryResponse,
  OperationsAgentReviewWorkflowRunsResponse,
} from "./features/operations/api/operationsContracts";
import type {
  AdminWorkflowApprovals,
  AuditReconstruction,
  ExecutiveOverview,
  FDEWorkbench,
  FieldTaskWorkspace,
  ModelConsole,
  WorkflowRequest,
} from "./features/roles/types";
import type {
  AnalysisMaterializationResult,
  DatasetCatalogDetail,
  DatasetCatalogItem,
  DatasetCatalogPage,
} from "./features/datasets/types";
import type {
  GovernanceOverview,
  ProjectionRetryResult,
} from "./features/governance/types";
import type {
  BoardCatalogDefinition,
  VisualizationCandidate,
  VisualizationFieldProfile,
  DashboardShareCreated,
  DashboardSharePayload,
  DashboardTab,
  DashboardTemplateVersion,
  ReportDraftRecord,
  ReportDraftSection,
  ResolvedDashboard,
  SavedView,
  SelectionFilter,
} from "./features/dashboard/types";
import type {
  AnalysisFlowEdge,
  AnalysisFlowNode,
  AnalysisNodeResultResponse,
  AnalysisNodeRowsPage,
  AnalysisRunResponse,
  AnalysisServerSnapshot,
} from "./features/analysis/types";
import type {
  PredictiveMaintenanceDatasetVersions,
  PredictiveMaintenanceDashboardResponse,
  PredictiveMaintenanceObservationResponse,
  PredictiveMaintenanceReleaseOverview,
  PredictiveMaintenanceRuntimeContext,
  GovernedProductResultSummary,
  ProductResultPage,
  ReplaySessionSnapshot,
} from "./features/predictive-maintenance/types";
import type {
  OntologyAggregateResult,
  OntologyObjectQueryResult,
  OntologyRegistry,
  OntologyTraversal,
  Project3DegradedResponse,
  Project3GraphSchema,
  Project3IntegrationSnapshot,
  Project3Subgraph,
} from "./features/ontology/types";
import type {
  AdminAuditEntry,
  AdminNotification,
  AdminUser,
  AppRole,
  AuthUser,
  Evidence,
  EventSummary,
  FollowUp,
  Intent,
  Layout,
  Project,
  ProjectMembership,
  Report,
  Role,
  RoleDefinition,
  UserStatus,
  Workspace,
} from "./types";

// Same-origin is the safe production default: Cloudflare and Vite proxy /api
// without creating an HTTPS -> loopback HTTP mixed-content boundary. Local
// scripts and isolated Playwright servers can still opt into an absolute URL.
export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let csrfTokenCache: string | null = null;

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}


function cookieValue(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const item of document.cookie.split(";")) {
    const value = item.trim();
    if (value.startsWith(prefix)) return decodeURIComponent(value.slice(prefix.length));
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (STATE_CHANGING_METHODS.has(method)) {
    const csrfToken = csrfTokenCache ?? cookieValue("ontology_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  const payload = response.status === 204 ? undefined : await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = payload?.error?.code ?? "api_request_failed";
    const message = payload?.error?.message ?? `API request failed: ${response.status}`;
    throw new ApiError(response.status, code, message);
  }
  return payload as T;
}

async function requestArtifact(path: string, init: RequestInit): Promise<ExportArtifact> {
  const method = (init.method ?? "POST").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (STATE_CHANGING_METHODS.has(method)) {
    const csrfToken = csrfTokenCache ?? cookieValue("ontology_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "api_request_failed",
      payload?.error?.message ?? `API request failed: ${response.status}`,
    );
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/i);
  return {
    blob: await response.blob(),
    filename: filenameMatch?.[1] ?? "ontology-dashboard-export",
    checkpointId: response.headers.get("X-Export-Checkpoint-ID") ?? "",
    contentHash: response.headers.get("X-Content-SHA256") ?? "",
    snapshotHash: response.headers.get("X-Snapshot-SHA256") ?? "",
  };
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser; csrf_token: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  csrfTokenCache = payload.csrf_token;
  return payload.user;
}

export async function openPublicBlueprintComparison(signal?: AbortSignal): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser; csrf_token: string }>(
    "/api/auth/public-blueprint-comparison",
    { method: "POST", signal },
  );
  csrfTokenCache = payload.csrf_token;
  return payload.user;
}

export function register(input: {
  display_name: string;
  email: string;
  password: string;
  organization_name: string;
  requested_role: Exclude<AppRole, "tenant_admin">;
  terms_accepted: boolean;
}) {
  return request<{
    user_id: string;
    email: string;
    display_name: string;
    status: "pending_approval";
    requested_organization_name: string;
    requested_role: Exclude<AppRole, "tenant_admin">;
  }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getCurrentUser(signal?: AbortSignal): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser; csrf_token: string | null }>("/api/auth/me", { signal });
  csrfTokenCache = payload.csrf_token;
  return payload.user;
}

export interface ServerDisplayPreferences {
  version: 3;
  textSize: "small" | "default" | "large" | "extra-large";
  density: "compact" | "standard" | "comfortable";
  theme: "light" | "dark" | "system";
  showTechnicalMetadata: boolean;
  updated_at?: string;
}

export async function getDisplayPreferences(): Promise<ServerDisplayPreferences | null> {
  return (await request<{ preferences: ServerDisplayPreferences | null }>("/api/auth/display-preferences")).preferences;
}

export function saveDisplayPreferences(input: Omit<ServerDisplayPreferences, "updated_at">): Promise<ServerDisplayPreferences> {
  return request<ServerDisplayPreferences>("/api/auth/display-preferences", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
  csrfTokenCache = null;
}

export async function setActiveProject(projectId: string): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser }>("/api/auth/active-project", {
    method: "PATCH",
    body: JSON.stringify({ project_id: projectId }),
  });
  return payload.user;
}

export async function getProjects(): Promise<Project[]> {
  return (await request<{ items: Project[] }>("/api/projects")).items;
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${encodeURIComponent(projectId)}`);
}


export async function getProjectWorkspaces(projectId: string): Promise<Workspace[]> {
  return (await request<{ items: Workspace[] }>(
    `/api/projects/${encodeURIComponent(projectId)}/workspaces`,
  )).items;
}

export async function getProjectMembers(projectId: string): Promise<ProjectMembership[]> {
  return (await request<{ items: ProjectMembership[] }>(
    `/api/admin/projects/${encodeURIComponent(projectId)}/members`,
  )).items;
}

export async function updateProjectMembership(
  projectId: string,
  userId: string,
  payload: { status: "active" | "suspended"; roles: string[] },
): Promise<ProjectMembership> {
  return request<ProjectMembership>(
    `/api/admin/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export async function getDatasetCatalog(projectId: string): Promise<DatasetCatalogItem[]> {
  return (await getDatasetCatalogPage({ project_id: projectId, offset: 0, limit: 200 })).items;
}

export function getDatasetCatalogPage(input: {
  project_id: string;
  offset?: number;
  limit?: number;
  search?: string;
  workspace_id?: string;
  status?: string;
  source_type?: string;
}): Promise<DatasetCatalogPage> {
  const params = new URLSearchParams({
    offset: String(input.offset ?? 0),
    limit: String(input.limit ?? 50),
  });
  if (input.search) params.set("search", input.search);
  if (input.workspace_id) params.set("workspace_id", input.workspace_id);
  if (input.status) params.set("status", input.status);
  if (input.source_type) params.set("source_type", input.source_type);
  return request<DatasetCatalogPage>(
    `/api/projects/${encodeURIComponent(input.project_id)}/dataset-catalog?${params.toString()}`,
  );
}

export function getDatasetCatalogDetail(
  projectId: string,
  datasetId: string,
): Promise<DatasetCatalogDetail> {
  return request<DatasetCatalogDetail>(
    `/api/projects/${encodeURIComponent(projectId)}/dataset-catalog/${encodeURIComponent(datasetId)}`,
  );
}

export async function getProjectEvents(projectId: string): Promise<EventSummary[]> {
  return (await request<{ items: EventSummary[] }>(
    `/api/projects/${encodeURIComponent(projectId)}/events`,
  )).items;
}

export async function getWorkspaces(): Promise<Workspace[]> {
  return (await request<{ items: Workspace[] }>("/api/workspaces")).items;
}

export function getOntologyRegistry(): Promise<OntologyRegistry> {
  return request<OntologyRegistry>("/api/ontology/registry");
}

export function queryOntologyObjects(input: {
  workspace_id: string;
  object_type?: string;
  search?: string;
  offset?: number;
  limit?: number;
}): Promise<OntologyObjectQueryResult> {
  const params = new URLSearchParams({ workspace_id: input.workspace_id });
  if (input.object_type) params.set("object_type", input.object_type);
  if (input.search) params.set("q", input.search);
  params.set("offset", String(input.offset ?? 0));
  params.set("limit", String(input.limit ?? 100));
  return request<OntologyObjectQueryResult>(`/api/ontology/objects?${params.toString()}`);
}

export function aggregateOntologyObjects(input: {
  workspace_id: string;
  object_type: string;
  group_by?: string[];
  metrics?: string[];
  search?: string;
}): Promise<OntologyAggregateResult> {
  const params = new URLSearchParams({ workspace_id: input.workspace_id, object_type: input.object_type });
  for (const field of input.group_by ?? []) params.append("group_by", field);
  for (const metric of input.metrics ?? []) params.append("metrics", metric);
  if (input.search) params.set("q", input.search);
  return request<OntologyAggregateResult>(`/api/ontology/objects/aggregate?${params.toString()}`);
}

export function traverseOntologyObject(
  objectId: string,
  input: {
    workspace_id: string;
    direction?: "outgoing" | "incoming" | "both";
    depth?: number;
    link_type?: string;
  },
): Promise<OntologyTraversal> {
  const params = new URLSearchParams({
    workspace_id: input.workspace_id,
    direction: input.direction ?? "both",
    depth: String(Math.min(2, Math.max(1, input.depth ?? 1))),
  });
  if (input.link_type) params.set("link_type", input.link_type);
  return request<OntologyTraversal>(
    `/api/ontology/objects/${encodeURIComponent(objectId)}/links?${params.toString()}`,
  );
}

export function getProject3Status(projectId: string): Promise<Project3IntegrationSnapshot> {
  const params = new URLSearchParams({ project_id: projectId });
  return request<Project3IntegrationSnapshot>(`/api/integrations/project3/status?${params.toString()}`);
}

function predictiveMaintenanceBase(projectId: string, workspaceId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/predictive-maintenance`;
}

export type MaintenanceExecutionTiming =
  | "immediate"
  | "planned_window"
  | "reinspect_after"
  | "no_action_baseline";

export type MaintenanceActionCode =
  | "TOOL_REPLACEMENT"
  | "COOLING_SYSTEM_RESTORE";

export type InspectionOutcome =
  | "no_action_required"
  | "maintenance_recommended"
  | "data_check_required";

export type InspectionChecklistStatus = "pass" | "fail" | "not_checked";

export interface InspectionCompletionPayload extends Record<string, unknown> {
  outcome: InspectionOutcome;
  checklist: Array<{
    item_id: string;
    status: InspectionChecklistStatus;
    note: string;
  }>;
  measurements: Array<{
    name: string;
    value: number;
    unit: string;
  }>;
  findings: string[];
  note: string;
}

export interface InspectionCompletionFacts {
  outcome: InspectionOutcome;
  toolWearStatus: InspectionChecklistStatus;
  toolWearMin: number | null;
  coolingPathStatus: InspectionChecklistStatus;
  coolantTemperatureC: number | null;
  inHouseStatus: "pass" | "fail" | "";
  sparePartAvailableStatus: "pass" | "fail" | "";
  vendorDispatchRequiredStatus: "pass" | "fail" | "";
  componentReplacementRequiredStatus: "pass" | "fail" | "";
  findings: string;
  note: string;
}

export function buildInspectionCompletionPayload(
  facts: InspectionCompletionFacts,
): InspectionCompletionPayload {
  const checklist: InspectionCompletionPayload["checklist"] = [
    {
      item_id: "tool-wear",
      status: facts.toolWearStatus,
      note: "현장 공구 마모 점검 결과",
    },
    {
      item_id: "cooling-path",
      status: facts.coolingPathStatus,
      note: "현장 냉각 경로 점검 결과",
    },
  ];
  const appendCostBasis = (
    itemId: string,
    status: "pass" | "fail" | "",
    note: string,
  ) => {
    if (status) checklist.push({ item_id: itemId, status, note });
  };
  appendCostBasis("cost-basis-in-house", facts.inHouseStatus, "사내 정비 수행 가능 여부");
  appendCostBasis(
    "cost-basis-spare-part-available",
    facts.sparePartAvailableStatus,
    "교체용 인서트 확보 여부",
  );
  appendCostBasis(
    "cost-basis-vendor-dispatch-required",
    facts.vendorDispatchRequiredStatus,
    "외부 업체 출동 필요 여부",
  );
  appendCostBasis(
    "cost-basis-component-replacement-required",
    facts.componentReplacementRequiredStatus,
    "냉각 계통 부품 교체 필요 여부",
  );

  const measurements: InspectionCompletionPayload["measurements"] = [];
  if (facts.toolWearMin !== null) {
    measurements.push({ name: "tool_wear_min", value: facts.toolWearMin, unit: "min" });
  }
  if (facts.coolantTemperatureC !== null) {
    measurements.push({
      name: "coolant_temperature_c",
      value: facts.coolantTemperatureC,
      unit: "C",
    });
  }

  return {
    outcome: facts.outcome,
    checklist,
    measurements,
    findings: [facts.findings.trim()],
    note: facts.note.trim(),
  };
}

export interface MaintenanceActionCandidateReadModel {
  action_candidate_id: string;
  inspection_result_id: string;
  event_id: string;
  asset_id: string;
  equipment_id: string;
  action_code: MaintenanceActionCode;
  basis_codes: string[];
}

export interface MaintenanceInspectionResultReadModel {
  inspection_result_id: string;
  work_order_id: string;
  event_id: string;
  asset_id: string;
  equipment_id: string;
  outcome: "no_action_required" | "maintenance_recommended" | "data_check_required";
  recorded_at: string;
}

export interface MaintenanceCostBand {
  low_minor: number;
  base_minor: number;
  high_minor: number;
}

export interface MaintenanceDurationBand {
  low_minutes: number;
  base_minutes: number;
  high_minutes: number;
}

export interface MaintenanceCostOptionReadModel {
  option_id: string;
  action_candidate_id: string;
  action_code: MaintenanceActionCode;
  execution_timing: MaintenanceExecutionTiming;
  assumed_execution_at?: string | null;
  labor_rate_type?: "normal" | "night" | "not_applicable" | null;
  labor_rate_base_minor_per_minute?: number | null;
  calculation_status: "calculated" | "insufficient";
  total_expected_cost: MaintenanceCostBand | null;
  expected_downtime: MaintenanceDurationBand | null;
  confidence: "high" | "medium" | "low" | "insufficient";
  missing_inputs: string[];
}

export interface MaintenanceCostAnalysisReadModel {
  schema_version: "maintenance-cost-scenario-v1.0";
  analysis_id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  asset_id: string;
  equipment_id: string;
  calculated_at: string;
  based_on: {
    product_result_id: string;
    evidence_id: string;
    inspection_work_order_id: string;
    inspection_result_id: string;
    sop_id: string;
    sop_version: string;
  };
  currency: string;
  currency_minor_unit: 0 | 2 | 3;
  options: MaintenanceCostOptionReadModel[];
  lowest_calculated_cost_option_id: string | null;
  assumptions: string[];
  missing_inputs: string[];
  price_version: string;
  calculation_policy_version: string;
  limitations: string[];
}

export interface MaintenanceEventLineageReadModel {
  event_id: string;
  decisions?: Array<{
    decision_id: string;
    recommendation_id: string;
    disposition: "accept" | "reject" | "defer";
  }>;
  work_orders: Array<{
    work_order_id: string;
    work_type: "inspection" | "maintenance";
    status: string;
    assigned_to?: string | null;
    assigned_at?: string | null;
  }>;
  inspection_results: MaintenanceInspectionResultReadModel[];
  cost_analyses: MaintenanceCostAnalysisReadModel[];
  recommendations: Array<{
    recommendation_id: string;
    status: string;
    source_inspection_work_order_id?: string | null;
    source_inspection_reference?: string | null;
    source_cost_analysis_id?: string | null;
    source_cost_option_id?: string | null;
    source_action_candidate_id?: string | null;
    action_code?: string | null;
  }>;
  maintenance_actions?: Array<{
    maintenance_action_id: string;
    work_order_id: string;
    status: string;
    action_code: MaintenanceActionCode;
    simulation_session_id: string;
    restart_at?: string | null;
  }>;
  maintenance_events?: Array<{
    maintenance_event_id: string;
    maintenance_action_id: string;
    completed_at: string;
    restart_at?: string | null;
  }>;
  activities?: Array<Record<string, unknown>>;
}

export interface OpenInspectionWorkOrderReadModel {
  work_order_id: string;
  event_id: string;
  asset_id: string;
  equipment_id: string;
  asset_type: string;
  work_type: "inspection";
  status: "requested" | "approved" | "in_progress" | "completed";
  assigned_to?: string | null;
  assigned_at?: string | null;
  inspection_outcome?: "no_action_required" | "maintenance_recommended" | "data_check_required" | null;
  current_step?:
    | "inspection_requested"
    | "inspection_approved"
    | "inspection_in_progress"
    | "inspection_completed"
    | "recommendation_proposed"
    | "maintenance_requested"
    | "maintenance_approved"
    | "maintenance_in_progress"
    | "post_maintenance_observation_pending"
    | "ready_for_reprediction";
}

export interface MaintenanceCostAnalysisRequest {
  action_code: MaintenanceActionCode;
  sop_id: string;
  sop_version: string;
}

export type ToolReplacementCostAnalysisRequest = MaintenanceCostAnalysisRequest;

function maintenanceBase(projectId: string, workspaceId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/maintenance`;
}

export function getMaintenanceEventLineage(
  projectId: string,
  workspaceId: string,
  eventId: string,
  signal?: AbortSignal,
): Promise<MaintenanceEventLineageReadModel> {
  return request<MaintenanceEventLineageReadModel>(
    `${maintenanceBase(projectId, workspaceId)}/events/${encodeURIComponent(eventId)}/lineage`,
    { signal },
  );
}

export function getOpenInspectionWorkOrders(
  projectId: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<{ items: OpenInspectionWorkOrderReadModel[] }> {
  return request<{ items: OpenInspectionWorkOrderReadModel[] }>(
    `${maintenanceBase(projectId, workspaceId)}/inspection-work-orders`,
    { signal },
  );
}

export function getMaintenanceActionCandidates(
  projectId: string,
  workspaceId: string,
  inspectionResultId: string,
  signal?: AbortSignal,
): Promise<{
  inspection_result_id: string;
  items: MaintenanceActionCandidateReadModel[];
}> {
  return request(
    `${maintenanceBase(projectId, workspaceId)}/inspection-results/${encodeURIComponent(inspectionResultId)}/action-candidates`,
    { signal },
  );
}

export function calculateMaintenanceCost(
  projectId: string,
  workspaceId: string,
  inspectionResultId: string,
  payload: MaintenanceCostAnalysisRequest,
  idempotencyKey: string,
): Promise<{
  analysis_id: string;
  calculation_status: "calculated" | "insufficient";
  cost_analysis: MaintenanceCostAnalysisReadModel;
  replayed: boolean;
}> {
  return request(
    `${maintenanceBase(projectId, workspaceId)}/inspection-results/${encodeURIComponent(inspectionResultId)}/cost-analyses`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    },
  );
}

export const calculateToolReplacementCost = calculateMaintenanceCost;

export function getPredictiveMaintenanceRuntimeContext(
  projectId: string,
  workspaceId: string,
  signal?: AbortSignal,
  datasetVersionId?: string,
): Promise<PredictiveMaintenanceRuntimeContext> {
  const params = new URLSearchParams();
  if (datasetVersionId) params.set("dataset_version_id", datasetVersionId);
  const query = params.size ? `?${params.toString()}` : "";
  return request<PredictiveMaintenanceRuntimeContext>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/context${query}`,
    { signal },
  );
}

export function getPredictiveMaintenanceVersions(
  projectId: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<PredictiveMaintenanceDatasetVersions> {
  return request<PredictiveMaintenanceDatasetVersions>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/versions`,
    { signal },
  );
}

export function selectPredictiveMaintenanceVersion(
  projectId: string,
  workspaceId: string,
  datasetVersionId: string | null,
): Promise<PredictiveMaintenanceDatasetVersions> {
  return request<PredictiveMaintenanceDatasetVersions>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/selection`,
    { method: "PUT", body: JSON.stringify({ dataset_version_id: datasetVersionId }) },
  );
}

export function getPredictiveMaintenanceDashboard(
  projectId: string,
  workspaceId: string,
  input: {
    dataset_version_id?: string;
    selected_event_id?: string;
    role?: "manager" | "engineer" | "executive";
    report_type?: import("./types").ReportType;
    intent?: string;
    locale?: "ko-KR" | "en-US";
  } = {},
  signal?: AbortSignal,
): Promise<PredictiveMaintenanceDashboardResponse> {
  const params = new URLSearchParams();
  if (input.dataset_version_id) params.set("dataset_version_id", input.dataset_version_id);
  if (input.selected_event_id) params.set("selected_event_id", input.selected_event_id);
  if (input.role) params.set("role", input.role);
  if (input.report_type) params.set("report_type", input.report_type);
  if (input.intent) params.set("intent", input.intent);
  if (input.locale) params.set("locale", input.locale);
  const query = params.size ? `?${params.toString()}` : "";
  return request<PredictiveMaintenanceDashboardResponse>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/dashboard${query}`,
    { signal },
  );
}

export function getPredictiveMaintenanceReleaseOverview(
  projectId: string,
  workspaceId: string,
  datasetVersionId?: string,
  signal?: AbortSignal,
): Promise<PredictiveMaintenanceReleaseOverview> {
  const params = new URLSearchParams();
  if (datasetVersionId) params.set("dataset_version_id", datasetVersionId);
  const query = params.size ? `?${params.toString()}` : "";
  return request<PredictiveMaintenanceReleaseOverview>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/release${query}`,
    { signal },
  );
}

export function getPredictiveMaintenanceLatestResults(
  projectId: string,
  workspaceId: string,
  limit = 100,
  signal?: AbortSignal,
  datasetVersionId?: string,
): Promise<ProductResultPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (datasetVersionId) params.set("dataset_version_id", datasetVersionId);
  return request<ProductResultPage>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/results/latest?${params.toString()}`,
    { signal },
  );
}

export function getPostMaintenanceProductResults(
  projectId: string,
  workspaceId: string,
  assetId: string,
  maintenanceEventId: string,
  signal?: AbortSignal,
): Promise<GovernedProductResultSummary | null> {
  const params = new URLSearchParams({
    asset_id: assetId,
    maintenance_event_id: maintenanceEventId,
  });
  return request<GovernedProductResultSummary | null>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/results/post-maintenance?${params.toString()}`,
    { signal },
  );
}

export function getPredictiveMaintenanceObservations(
  projectId: string,
  workspaceId: string,
  input: {
    dataset_version_id?: string;
    asset_id?: string;
    start: string;
    end: string;
    grain?: "raw" | "10m" | "1h";
    derived_measures?: Array<"power_w" | "temperature_gap_k" | "overstrain_load">;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<PredictiveMaintenanceObservationResponse> {
  const params = new URLSearchParams({
    start: input.start,
    end: input.end,
    grain: input.grain ?? "10m",
    limit: String(input.limit ?? 200),
  });
  if (input.dataset_version_id) params.set("dataset_version_id", input.dataset_version_id);
  if (input.asset_id) params.set("asset_id", input.asset_id);
  for (const measure of input.derived_measures ?? []) params.append("derived_measure", measure);
  return request<PredictiveMaintenanceObservationResponse>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/observations?${params.toString()}`,
    { signal },
  );
}

export function startPredictiveMaintenanceReplay(
  projectId: string,
  workspaceId: string,
  input: {
    dataset_version_id?: string;
    start_time?: string;
    speed_minutes_per_second?: number;
  },
): Promise<ReplaySessionSnapshot> {
  return request<ReplaySessionSnapshot>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/replay/sessions`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function controlPredictiveMaintenanceReplay(
  projectId: string,
  workspaceId: string,
  sessionId: string,
  action: "pause" | "resume" | "reset" | "seek" | "speed",
  input: { time?: string; speed_minutes_per_second?: number },
): Promise<ReplaySessionSnapshot> {
  return request<ReplaySessionSnapshot>(
    `${predictiveMaintenanceBase(projectId, workspaceId)}/replay/sessions/${encodeURIComponent(sessionId)}/${action}`,
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function predictiveMaintenanceReplayEventsUrl(
  projectId: string,
  workspaceId: string,
  sessionId: string,
): string {
  return `${API_BASE}${predictiveMaintenanceBase(projectId, workspaceId)}/replay/sessions/${encodeURIComponent(sessionId)}/events`;
}

export function getProject3Schema(
  projectId: string,
): Promise<Project3GraphSchema | Project3DegradedResponse> {
  const params = new URLSearchParams({ project_id: projectId });
  return request<Project3GraphSchema | Project3DegradedResponse>(
    `/api/integrations/project3/schema?${params.toString()}`,
  );
}

export function getProject3Subgraph(input: {
  project_id: string;
  label: string;
  identity: string;
  depth?: number;
  limit?: number;
}): Promise<Project3Subgraph | Project3DegradedResponse> {
  const params = new URLSearchParams({
    project_id: input.project_id,
    label: input.label,
    identity: input.identity,
    depth: String(input.depth ?? 2),
    limit: String(input.limit ?? 50),
  });
  return request<Project3Subgraph | Project3DegradedResponse>(
    `/api/integrations/project3/subgraph?${params.toString()}`,
  );
}

export function runAgentQuery(input: AgentQueryInput): Promise<AgentRunResponse> {
  return request<AgentRunResponse>("/api/agent/query", {
    method: "POST",
    body: JSON.stringify({ route: "auto", top_k: 8, ...input }),
  });
}

export function listAgentRuns(input: {
  project_id: string;
  workspace_id: string;
  offset?: number;
  limit?: number;
  status?: string;
  route?: string;
  search?: string;
}): Promise<AgentRunPage> {
  const params = new URLSearchParams({
    project_id: input.project_id,
    workspace_id: input.workspace_id,
    offset: String(input.offset ?? 0),
    limit: String(input.limit ?? 25),
  });
  if (input.status) params.set("status", input.status);
  if (input.route) params.set("route", input.route);
  if (input.search) params.set("search", input.search);
  return request<AgentRunPage>(`/api/agent/runs?${params.toString()}`);
}

export function getAgentRun(projectId: string, workspaceId: string, runId: string): Promise<AgentRunResponse> {
  const params = new URLSearchParams({ project_id: projectId, workspace_id: workspaceId });
  return request<AgentRunResponse>(`/api/agent/runs/${encodeURIComponent(runId)}?${params.toString()}`);
}

export function getOperationsAgentReviewPacket(input: {
  assetId: string;
  projectId?: string;
  datasetVersionId?: string | null;
  eventId?: string | null;
  historyWindow?: string;
}): Promise<OperationsAgentReviewPacket> {
  const params = new URLSearchParams({
    project_id: input.projectId ?? "manufacturing-demo-project",
    history_window: input.historyWindow ?? "24h",
  });
  if (input.datasetVersionId) params.set("dataset_version_id", input.datasetVersionId);
  if (input.eventId) params.set("event_id", input.eventId);
  return request<OperationsAgentReviewPacket>(
    `/api/objects/${encodeURIComponent(input.assetId)}/agent-review-packet?${params.toString()}`,
  );
}

export function getOperationsAgentReviewSummary(input: {
  assetId: string;
  projectId?: string;
  datasetVersionId?: string | null;
  eventId?: string | null;
  historyWindow?: string;
}): Promise<OperationsAgentReviewSummaryResponse> {
  const params = new URLSearchParams({
    project_id: input.projectId ?? "manufacturing-demo-project",
    history_window: input.historyWindow ?? "24h",
  });
  if (input.datasetVersionId) params.set("dataset_version_id", input.datasetVersionId);
  if (input.eventId) params.set("event_id", input.eventId);
  return request<OperationsAgentReviewSummaryResponse>(
    `/api/objects/${encodeURIComponent(input.assetId)}/agent-review-summary?${params.toString()}`,
  );
}

export function createOperationsAgentReviewSummary(input: {
  assetId: string;
  projectId?: string;
  datasetVersionId?: string | null;
  eventId?: string | null;
  historyWindow?: string;
  trigger?: "manual_materialization" | "ui_manual_regeneration";
}): Promise<OperationsAgentReviewSummaryResponse> {
  const params = new URLSearchParams({
    project_id: input.projectId ?? "manufacturing-demo-project",
    history_window: input.historyWindow ?? "24h",
    trigger: input.trigger ?? "ui_manual_regeneration",
  });
  if (input.datasetVersionId) params.set("dataset_version_id", input.datasetVersionId);
  if (input.eventId) params.set("event_id", input.eventId);
  return request<OperationsAgentReviewSummaryResponse>(
    `/api/objects/${encodeURIComponent(input.assetId)}/agent-review-summary?${params.toString()}`,
    { method: "POST" },
  );
}

export function getOperationsAgentReviewWorkflowRuns(input: {
  projectId?: string;
  assetId?: string | null;
  eventId?: string | null;
  datasetVersionId?: string | null;
  status?: "running" | "completed" | "partial" | "failed" | null;
  limit?: number;
}): Promise<OperationsAgentReviewWorkflowRunsResponse> {
  const projectId = input.projectId ?? "manufacturing-demo-project";
  const params = new URLSearchParams({
    limit: String(input.limit ?? 20),
  });
  if (input.assetId) params.set("asset_id", input.assetId);
  if (input.eventId) params.set("event_id", input.eventId);
  if (input.datasetVersionId) params.set("dataset_version_id", input.datasetVersionId);
  if (input.status) params.set("status", input.status);
  return request<OperationsAgentReviewWorkflowRunsResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/agent-review-workflow-runs?${params.toString()}`,
  );
}

export function getGovernanceOverview(
  projectId: string,
  workspaceId: string,
): Promise<GovernanceOverview> {
  return request<GovernanceOverview>(
    `/api/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/governance`,
  );
}

export function retryGovernanceProjection(
  projectId: string,
  workspaceId: string,
  projectionId: string,
): Promise<ProjectionRetryResult> {
  return request<ProjectionRetryResult>(
    `/api/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/governance/projections/${encodeURIComponent(projectionId)}/retry`,
    { method: "POST" },
  );
}

export function createAnalysis(input: {
  id?: string;
  workspace_id: string;
  display_name: string;
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  publish?: boolean;
}): Promise<AnalysisServerSnapshot> {
  return request<AnalysisServerSnapshot>("/api/analyses", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getAnalysis(
  analysisId: string,
  workspaceId: string,
  version?: number,
): Promise<AnalysisServerSnapshot> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (version) params.set("version", String(version));
  return request<AnalysisServerSnapshot>(`/api/analyses/${encodeURIComponent(analysisId)}?${params.toString()}`);
}

export function updateAnalysis(
  analysisId: string,
  input: {
    workspace_id: string;
    display_name: string;
    nodes: AnalysisFlowNode[];
    edges: AnalysisFlowEdge[];
    base_version: number;
    publish?: boolean;
  },
): Promise<AnalysisServerSnapshot> {
  return request<AnalysisServerSnapshot>(`/api/analyses/${encodeURIComponent(analysisId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function queueAnalysisRun(
  analysisId: string,
  input: {
    workspace_id: string;
    version_policy: "pinned" | "latest_published";
    version?: number | null;
    parameters?: Record<string, unknown>;
    preview_limit?: number;
  },
): Promise<AnalysisRunResponse> {
  return request<AnalysisRunResponse>(`/api/analyses/${encodeURIComponent(analysisId)}/jobs`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getAnalysisRun(runId: string, workspaceId: string): Promise<AnalysisRunResponse> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  return request<AnalysisRunResponse>(`/api/analysis-runs/${encodeURIComponent(runId)}?${params.toString()}`);
}

export function cancelAnalysisRun(runId: string, workspaceId: string): Promise<AnalysisRunResponse> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  return request<AnalysisRunResponse>(`/api/analysis-runs/${encodeURIComponent(runId)}/cancel?${params.toString()}`, {
    method: "POST",
  });
}

export function getAnalysisNodeRows(input: {
  run_id: string;
  node_id: string;
  workspace_id: string;
  cursor?: string;
  limit?: number;
}): Promise<AnalysisNodeRowsPage> {
  const params = new URLSearchParams({
    workspace_id: input.workspace_id,
    limit: String(input.limit ?? 100),
  });
  if (input.cursor) params.set("cursor", input.cursor);
  return request<AnalysisNodeRowsPage>(
    `/api/analysis-runs/${encodeURIComponent(input.run_id)}/nodes/${encodeURIComponent(input.node_id)}/rows?${params.toString()}`,
  );
}

export function runAnalysis(
  analysisId: string,
  input: {
    workspace_id: string;
    version_policy: "pinned" | "latest_published";
    version?: number | null;
    parameters?: Record<string, unknown>;
    preview_limit?: number;
  },
): Promise<AnalysisRunResponse> {
  return request<AnalysisRunResponse>(`/api/analyses/${encodeURIComponent(analysisId)}/run`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function materializeAnalysisResult(
  analysisId: string,
  input: {
    project_id: string;
    workspace_id: string;
    node_id: string;
    version_policy: "pinned" | "latest_published";
    version?: number | null;
    dataset_id?: string;
    dataset_slug?: string;
    dataset_name?: string;
    preview_limit?: number;
    full_limit?: number;
  },
): Promise<AnalysisMaterializationResult> {
  return request<AnalysisMaterializationResult>(
    `/api/analyses/${encodeURIComponent(analysisId)}/materializations`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export function getAnalysisNodeResult(input: {
  analysis_id: string;
  node_id: string;
  workspace_id: string;
  version_policy: "pinned" | "latest_published";
  version?: number | null;
}): Promise<AnalysisNodeResultResponse> {
  const params = new URLSearchParams({
    workspace_id: input.workspace_id,
    version_policy: input.version_policy,
  });
  if (input.version) params.set("version", String(input.version));
  return request<AnalysisNodeResultResponse>(
    `/api/analyses/${encodeURIComponent(input.analysis_id)}/nodes/${encodeURIComponent(input.node_id)}/result?${params.toString()}`,
  );
}

export interface DashboardBoardQueryResponse {
  board_id: string;
  rows: Array<Record<string, unknown>>;
  row_count: number;
  matching_object_ids: string[];
  render_spec: Record<string, unknown>;
  generated_at: string;
  source_freshness_at: string | null;
  timezone: string;
  warnings: string[];
}

export function queryDashboardBoard(input: {
  dashboard_id: string;
  board_id: string;
  workspace_id: string;
  parameter_state: Record<string, unknown>;
  selection_filters: SelectionFilter[];
  offset?: number;
  limit?: number;
  search?: string;
}): Promise<DashboardBoardQueryResponse> {
  return request<DashboardBoardQueryResponse>(
    `/api/dashboards/${encodeURIComponent(input.dashboard_id)}/boards/${encodeURIComponent(input.board_id)}/query`,
    {
      method: "POST",
      body: JSON.stringify({
        workspace_id: input.workspace_id,
        parameter_state: input.parameter_state,
        selection_filters: input.selection_filters,
        offset: input.offset ?? 0,
        limit: input.limit ?? 100,
        search: input.search ?? null,
      }),
    },
  );
}

export async function getEvents(): Promise<EventSummary[]> {
  return (await request<{ items: EventSummary[] }>("/api/events")).items;
}

export function getEvidence(eventId: string): Promise<Evidence> {
  return request<Evidence>(`/api/events/${encodeURIComponent(eventId)}/evidence`);
}

export async function getReport(
  eventId: string,
  role: Role,
  useLlm = true,
  locale: "ko-KR" | "en-US" = "ko-KR",
  reportType?: import("./types").ReportType,
): Promise<Report> {
  const payload = await request<{ report: Report }>(`/api/events/${encodeURIComponent(eventId)}/report`, {
    method: "POST",
    body: JSON.stringify({ role, report_type: reportType, locale, use_llm: useLlm }),
  });
  return payload.report;
}

export async function getLayout(
  eventId: string,
  role: Role,
  intent: Intent,
  useLlm = true,
  locale: "ko-KR" | "en-US" = "ko-KR",
): Promise<Layout> {
  const payload = await request<{ layout: Layout }>(`/api/events/${encodeURIComponent(eventId)}/layout`, {
    method: "POST",
    body: JSON.stringify({ role, locale, intent, use_llm: useLlm }),
  });
  return payload.layout;
}

export function recordDecision(eventId: string, actor: string, decision: string, note: string) {
  return request(`/api/events/${encodeURIComponent(eventId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ actor, decision, note }),
  });
}

export function addNote(eventId: string, actor: string, body: string) {
  return request(`/api/events/${encodeURIComponent(eventId)}/notes`, {
    method: "POST",
    body: JSON.stringify({ actor, body }),
  });
}

export function requestInspectionWorkOrder(input: {
  projectId: string;
  workspaceId: string;
  eventId: string;
  snapshotBasis: EvidenceSnapshotBasisWire;
  idempotencyKey: string;
}) {
  return request<Record<string, unknown>>(
    `/api/projects/${encodeURIComponent(input.projectId)}/workspaces/${encodeURIComponent(input.workspaceId)}/maintenance/inspection-work-orders`,
    {
      method: "POST",
      headers: { "Idempotency-Key": input.idempotencyKey },
      body: JSON.stringify({
        event_id: input.eventId,
        snapshot_basis: input.snapshotBasis,
      }),
    },
  );
}

function maintenanceCommand(
  path: string,
  body: Record<string, unknown>,
  idempotencyKey: string,
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(path, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
}

export function acceptInspectionWorkOrder(input: {
  projectId: string;
  workspaceId: string;
  workOrderId: string;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/inspection-work-orders/${encodeURIComponent(input.workOrderId)}/accept`,
    {},
    input.idempotencyKey,
  );
}

export function startInspectionWorkOrder(input: {
  projectId: string;
  workspaceId: string;
  workOrderId: string;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/inspection-work-orders/${encodeURIComponent(input.workOrderId)}/start`,
    {},
    input.idempotencyKey,
  );
}

export function completeInspectionWorkOrder(input: {
  projectId: string;
  workspaceId: string;
  workOrderId: string;
  facts: InspectionCompletionFacts;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/inspection-work-orders/${encodeURIComponent(input.workOrderId)}/complete`,
    buildInspectionCompletionPayload(input.facts),
    input.idempotencyKey,
  );
}

export function createOperationsManualRecommendation(input: {
  projectId: string;
  workspaceId: string;
  inspectionResultId: string;
  actionCode: MaintenanceActionCode;
  costAnalysisId: string;
  actionCandidateId: string;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/inspection-results/${encodeURIComponent(input.inspectionResultId)}/recommendations`,
    buildOperationsManualRecommendationPayload(
      input.inspectionResultId,
      input.actionCode,
      input.costAnalysisId,
      input.actionCandidateId,
    ),
    input.idempotencyKey,
  );
}

export function buildOperationsManualRecommendationPayload(
  inspectionResultId: string,
  actionCode: MaintenanceActionCode,
  costAnalysisId: string,
  actionCandidateId: string,
) {
  return {
    action_code: actionCode,
    basis: [`inspection_result:${inspectionResultId}`],
    cost_analysis_id: costAnalysisId,
    action_candidate_id: actionCandidateId,
  };
}

export function decideOperationsManualRecommendation(input: {
  projectId: string;
  workspaceId: string;
  recommendationId: string;
  disposition: "accept" | "reject" | "defer";
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/recommendations/${encodeURIComponent(input.recommendationId)}/decisions`,
    { disposition: input.disposition, note: "사용자 명시적 판단" },
    input.idempotencyKey,
  );
}

export async function approveMaintenanceWorkOrder(input: {
  projectId: string;
  workspaceId: string;
  workOrderId: string;
  datasetVersionId: string;
  idempotencyKey: string;
}) {
  const endpoint = `${maintenanceBase(input.projectId, input.workspaceId)}/maintenance-work-orders/${encodeURIComponent(input.workOrderId)}/approve`;
  try {
    return await maintenanceCommand(endpoint, {}, input.idempotencyKey);
  } catch (reason) {
    if (!(reason instanceof ApiError) || reason.code !== "source_simulation_session_unavailable") {
      throw reason;
    }
    // Historical Product Results can predate source-session provenance. Only
    // in that compatibility case do we create a replay selector; current live
    // Results stay bound to the immutable source session resolved server-side.
    const replay = await startPredictiveMaintenanceReplay(input.projectId, input.workspaceId, {
      dataset_version_id: input.datasetVersionId,
      speed_minutes_per_second: 60,
    });
    return maintenanceCommand(
      endpoint,
      { simulation_session_id: replay.cursor.session_id },
      input.idempotencyKey,
    );
  }
}

export function startMaintenanceAction(input: {
  projectId: string;
  workspaceId: string;
  maintenanceActionId: string;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/maintenance-actions/${encodeURIComponent(input.maintenanceActionId)}/start`,
    {},
    input.idempotencyKey,
  );
}

export function completeMaintenanceAction(input: {
  projectId: string;
  workspaceId: string;
  maintenanceActionId: string;
  actionCode: MaintenanceActionCode;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/maintenance-actions/${encodeURIComponent(input.maintenanceActionId)}/complete`,
    {
      outcome: input.actionCode === "COOLING_SYSTEM_RESTORE"
        ? "냉각 계통을 복구하고 정상 상태를 확인했습니다."
        : "공구 인서트 1개를 교체하고 정상 체결을 확인했습니다.",
    },
    input.idempotencyKey,
  );
}

export function requestMaintenanceReplay(input: {
  projectId: string;
  workspaceId: string;
  maintenanceEventId: string;
  idempotencyKey: string;
}) {
  return maintenanceCommand(
    `${maintenanceBase(input.projectId, input.workspaceId)}/maintenance-events/${encodeURIComponent(input.maintenanceEventId)}/replay`,
    { restart_at: new Date().toISOString() },
    input.idempotencyKey,
  );
}

export function followUp(
  eventId: string,
  role: Role,
  question: string,
  locale: "ko-KR" | "en-US" = "ko-KR",
): Promise<FollowUp> {
  return request<FollowUp>(`/api/events/${encodeURIComponent(eventId)}/follow-up`, {
    method: "POST",
    body: JSON.stringify({ role, locale, question }),
  });
}

export interface AdminOverview {
  active_users: number;
  pending_users: number;
  disabled_users: number;
  workspace_count: number;
  unread_notifications: number;
  recent_admin_changes: AdminAuditEntry[];
}

export function getAdminOverview(): Promise<AdminOverview> {
  return request<AdminOverview>("/api/admin/overview");
}

export async function getAdminUsers(): Promise<AdminUser[]> {
  return (await request<{ items: AdminUser[] }>("/api/admin/users")).items;
}

export async function getAdminRoles(): Promise<RoleDefinition[]> {
  return (await request<{ items: RoleDefinition[] }>("/api/admin/roles")).items;
}

export async function getAdminWorkspaces(): Promise<Workspace[]> {
  return (await request<{ items: Workspace[] }>("/api/admin/workspaces")).items;
}

export async function getAdminAudit(): Promise<AdminAuditEntry[]> {
  return (await request<{ items: AdminAuditEntry[] }>("/api/admin/audit")).items;
}

export async function getAdminNotifications(unreadOnly = false): Promise<AdminNotification[]> {
  return (await request<{ items: AdminNotification[] }>(`/api/admin/notifications?unread_only=${unreadOnly ? "true" : "false"}`)).items;
}

export function markAdminNotificationRead(notificationId: string): Promise<AdminNotification> {
  return request<AdminNotification>(`/api/admin/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: "POST",
  });
}

export function updateAdminUser(
  userId: string,
  input: {
    status?: UserStatus;
    roles?: AppRole[];
    workspace_scopes?: string[];
    permission_overrides?: Record<string, boolean>;
  },
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function getResolvedDashboard(workspaceId: string): Promise<ResolvedDashboard> {
  return request<ResolvedDashboard>(`/api/dashboards/resolved?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export async function getBoardCatalog(
  workspaceId: string,
  options?: { q?: string; category?: string; role_code?: AppRole },
): Promise<BoardCatalogDefinition[]> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (options?.q) params.set("q", options.q);
  if (options?.category) params.set("category", options.category);
  if (options?.role_code) params.set("role_code", options.role_code);
  return (await request<{ items: BoardCatalogDefinition[] }>(`/api/boards/catalog?${params.toString()}`)).items;
}

export function saveDashboardPreferences(input: {
  workspace_id: string;
  base_revision: number;
  active_tab_id: string;
  tabs: DashboardTab[];
  parameter_state: Record<string, unknown>;
}): Promise<ResolvedDashboard> {
  return request<ResolvedDashboard>("/api/dashboards/preferences", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function restoreDashboardDefaults(workspaceId: string): Promise<ResolvedDashboard> {
  return request<ResolvedDashboard>("/api/dashboards/preferences/restore", {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
}

export async function getReportDraft(
  workspaceId: string,
  eventId: string,
  role: Role,
  locale: "ko-KR" | "en-US",
): Promise<ReportDraftRecord | null> {
  const params = new URLSearchParams({ workspace_id: workspaceId, event_id: eventId, role, locale });
  const payload = await request<{ draft: ReportDraftRecord | null }>(`/api/reports/draft?${params.toString()}`);
  return payload.draft;
}

export function saveReportDraft(input: {
  workspace_id: string;
  event_id: string;
  role: Role;
  locale: "ko-KR" | "en-US";
  base_revision: number;
  headline: string;
  summary: string;
  sections: ReportDraftSection[];
  content_origin?: "generated" | "edited" | "translated";
  source_locale?: "ko-KR" | "en-US" | null;
  source_revision?: number | null;
}): Promise<ReportDraftRecord> {
  return request<ReportDraftRecord>("/api/reports/draft", {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export async function getSavedViews(workspaceId: string): Promise<SavedView[]> {
  return (await request<{ items: SavedView[] }>(`/api/dashboards/saved-views?workspace_id=${encodeURIComponent(workspaceId)}`)).items;
}

export function createSavedView(input: {
  workspace_id: string;
  name: string;
  active_tab_id: string;
  tabs: DashboardTab[];
  parameter_state: Record<string, unknown>;
}): Promise<SavedView> {
  return request<SavedView>("/api/dashboards/saved-views", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getSavedView(viewId: string): Promise<SavedView> {
  return request<SavedView>(`/api/dashboards/saved-views/${encodeURIComponent(viewId)}`);
}

export function deleteSavedView(viewId: string): Promise<void> {
  return request<void>(`/api/dashboards/saved-views/${encodeURIComponent(viewId)}`, { method: "DELETE" });
}

export function createDashboardShare(input: {
  workspace_id: string;
  active_tab_id: string;
  parameter_state: Record<string, unknown>;
  expires_in_hours?: number;
}): Promise<DashboardShareCreated> {
  return request<DashboardShareCreated>("/api/dashboards/shares", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function resolveDashboardShare(token: string): Promise<DashboardSharePayload> {
  return request<DashboardSharePayload>(`/api/dashboards/shares/${encodeURIComponent(token)}`);
}

export function getDashboardTemplatePreview(
  workspaceId: string,
  roleCode: AppRole,
  version?: number,
): Promise<ResolvedDashboard> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (version) params.set("version", String(version));
  return request<ResolvedDashboard>(`/api/dashboard-templates/${roleCode}/preview?${params.toString()}`);
}

export async function getDashboardTemplateVersions(
  workspaceId: string,
  roleCode: AppRole,
): Promise<DashboardTemplateVersion[]> {
  return (await request<{ items: DashboardTemplateVersion[] }>(
    `/api/dashboard-templates/${roleCode}/versions?workspace_id=${encodeURIComponent(workspaceId)}`,
  )).items;
}

export function publishDashboardTemplate(
  roleCode: AppRole,
  input: {
    workspace_id: string;
    display_name: string;
    tabs: DashboardTab[];
    parameter_definitions: ResolvedDashboard["parameter_definitions"];
  },
) {
  return request(`/api/dashboard-templates/${roleCode}/publish`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function requestDashboardTemplatePublish(
  roleCode: AppRole,
  input: {
    workspace_id: string;
    target_role: AppRole;
    display_name: string;
    tabs: DashboardTab[];
    parameter_definitions: ResolvedDashboard["parameter_definitions"];
    change_summary: string;
  },
): Promise<WorkflowRequest> {
  return request<WorkflowRequest>(`/api/dashboard-templates/${roleCode}/publish-requests`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getExecutiveWorkspace(workspaceId: string): Promise<ExecutiveOverview> {
  return request<ExecutiveOverview>(`/api/role-workspaces/executive?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function getAuditWorkspace(workspaceId: string, eventId: string): Promise<AuditReconstruction> {
  const params = new URLSearchParams({ workspace_id: workspaceId, event_id: eventId });
  return request<AuditReconstruction>(`/api/role-workspaces/audit?${params.toString()}`);
}

export function createAuditExportCheckpoint(input: {
  workspace_id: string;
  event_id: string;
  export_format: "json" | "csv" | "pdf";
  reason: string;
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/role-workspaces/audit/export-checkpoints", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getFieldWorkspace(workspaceId: string): Promise<FieldTaskWorkspace> {
  return request<FieldTaskWorkspace>(`/api/role-workspaces/field?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function invokeOntologyAction(input: {
  action_type: string;
  object_id: string;
  workspace_id: string;
  parameters: Record<string, unknown>;
  idempotency_key: string;
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/ontology/actions/invoke", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getFDEWorkspace(workspaceId: string): Promise<FDEWorkbench> {
  return request<FDEWorkbench>(`/api/role-workspaces/fde?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function getModelConsole(workspaceId: string): Promise<ModelConsole> {
  return request<ModelConsole>(`/api/role-workspaces/ml?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function createModelReleaseRequest(input: {
  workspace_id: string;
  model_version: string;
  dataset_version: string;
  policy_version: string;
  metrics: Record<string, string | number>;
  threshold_evaluation: Record<string, string | number>;
  notes: string;
}): Promise<WorkflowRequest> {
  return request<WorkflowRequest>("/api/role-workspaces/ml/release-requests", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function planObjectQuery(input: {
  workspace_id: string;
  query: string;
  use_llm?: boolean;
  limit?: number;
}): Promise<ObjectQueryPlanResponse> {
  return request<ObjectQueryPlanResponse>("/api/planner/object-query", {
    method: "POST",
    body: JSON.stringify({ use_llm: true, limit: 20, ...input }),
  });
}

export function recommendBoards(input: {
  workspace_id: string;
  goal: string;
  use_llm?: boolean;
  limit?: number;
}): Promise<BoardRecommendationResponse> {
  return request<BoardRecommendationResponse>("/api/planner/board-recommendations", {
    method: "POST",
    body: JSON.stringify({ use_llm: true, limit: 5, ...input }),
  });
}

export function generateDashboardDraft(input: {
  workspace_id: string;
  target_role: AppRole;
  goal: string;
  use_llm?: boolean;
  max_new_boards?: number;
}): Promise<DashboardDraftResponse> {
  return request<DashboardDraftResponse>("/api/planner/dashboard-drafts", {
    method: "POST",
    body: JSON.stringify({ use_llm: true, max_new_boards: 4, ...input }),
  });
}

export function recommendVisualization(input: {
  workspace_id: string;
  dashboard_id: string;
  board_id: string;
  goal: string;
  field_profile: VisualizationFieldProfile[];
  deterministic_candidates: VisualizationCandidate[];
  use_llm?: boolean;
}): Promise<VisualizationPlannerResponse> {
  return request<VisualizationPlannerResponse>("/api/planner/visualizations/recommend", {
    method: "POST",
    body: JSON.stringify({ use_llm: true, ...input }),
  });
}

export function planSemanticVisualization(
  input: SemanticVisualizationPlanInput,
): Promise<SemanticVisualizationPlanResponse> {
  return request<SemanticVisualizationPlanResponse>("/api/planner/visualizations/semantic-plan", {
    method: "POST",
    body: JSON.stringify({
      dimensions: [],
      measures: [],
      filters: [],
      order: [],
      limit: 500,
      field_cardinalities: {},
      result_profile: [],
      clamp_limits: true,
      use_llm: true,
      ...input,
    }),
  });
}

export function generateGroundedNarrative(input: {
  workspace_id: string;
  event_id: string;
  goal: string;
  use_llm?: boolean;
}): Promise<GroundedNarrativeResponse> {
  return request<GroundedNarrativeResponse>("/api/planner/grounded-narrative", {
    method: "POST",
    body: JSON.stringify({ use_llm: true, ...input }),
  });
}

export function createExport(input: {
  workspace_id: string;
  format: "json" | "csv" | "pdf";
  scope: "dashboard" | "event" | "role_workspace";
  event_id?: string;
  title?: string;
}): Promise<ExportArtifact> {
  return requestArtifact("/api/exports", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getAdminWorkflowApprovals(): Promise<AdminWorkflowApprovals> {
  return request<AdminWorkflowApprovals>("/api/admin/workflow-approvals");
}

export function decideTemplatePublishRequest(
  requestId: string,
  decision: "approve" | "reject",
  note: string,
): Promise<WorkflowRequest> {
  return request<WorkflowRequest>(`/api/admin/template-publish-requests/${requestId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
}

export function decideModelReleaseRequest(
  requestId: string,
  decision: "approve" | "reject",
  note: string,
): Promise<WorkflowRequest> {
  return request<WorkflowRequest>(`/api/admin/model-release-requests/${requestId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
}
