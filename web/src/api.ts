import type {
  BoardRecommendationResponse,
  DashboardDraftResponse,
  ExportArtifact,
  GroundedNarrativeResponse,
  ObjectQueryPlanResponse,
} from "./features/planner/types";
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
  BoardCatalogDefinition,
  DashboardShareCreated,
  DashboardSharePayload,
  DashboardTab,
  DashboardTemplateVersion,
  ResolvedDashboard,
  SavedView,
  SelectionFilter,
} from "./features/dashboard/types";
import type {
  AnalysisFlowEdge,
  AnalysisFlowNode,
  AnalysisNodeResultResponse,
  AnalysisRunResponse,
  AnalysisServerSnapshot,
} from "./features/analysis/types";
import type {
  OntologyAggregateResult,
  OntologyObjectQueryResult,
  OntologyTraversal,
} from "./features/ontology/types";
import type {
  AdminAuditEntry,
  AdminUser,
  AppRole,
  AuthUser,
  DomainPack,
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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8100";
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

export function register(input: {
  display_name: string;
  email: string;
  password: string;
  organization_name: string;
  terms_accepted: boolean;
}) {
  return request<{
    user_id: string;
    email: string;
    display_name: string;
    status: "pending_approval";
    requested_organization_name: string;
  }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getCurrentUser(): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser; csrf_token: string | null }>("/api/auth/me");
  csrfTokenCache = payload.csrf_token;
  return payload.user;
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

export async function getProjectEvents(projectId: string): Promise<EventSummary[]> {
  return (await request<{ items: EventSummary[] }>(
    `/api/projects/${encodeURIComponent(projectId)}/events`,
  )).items;
}

export async function getWorkspaces(): Promise<Workspace[]> {
  return (await request<{ items: Workspace[] }>("/api/workspaces")).items;
}

export async function getDomainPacks(): Promise<DomainPack[]> {
  return (await request<{ items: DomainPack[] }>("/api/domain-packs")).items;
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
  return request<Evidence>(`/api/events/${eventId}/evidence`);
}

export async function getReport(eventId: string, role: Role, useLlm = true): Promise<Report> {
  const payload = await request<{ report: Report }>(`/api/events/${eventId}/report`, {
    method: "POST",
    body: JSON.stringify({ role, use_llm: useLlm }),
  });
  return payload.report;
}

export async function getLayout(eventId: string, role: Role, intent: Intent, useLlm = true): Promise<Layout> {
  const payload = await request<{ layout: Layout }>(`/api/events/${eventId}/layout`, {
    method: "POST",
    body: JSON.stringify({ role, intent, use_llm: useLlm }),
  });
  return payload.layout;
}

export function recordDecision(eventId: string, actor: string, decision: string, note: string) {
  return request(`/api/events/${eventId}/decision`, {
    method: "POST",
    body: JSON.stringify({ actor, decision, note }),
  });
}

export function addNote(eventId: string, actor: string, body: string) {
  return request(`/api/events/${eventId}/notes`, {
    method: "POST",
    body: JSON.stringify({ actor, body }),
  });
}

export function followUp(eventId: string, role: Role, question: string): Promise<FollowUp> {
  return request<FollowUp>(`/api/events/${eventId}/follow-up`, {
    method: "POST",
    body: JSON.stringify({ role, question }),
  });
}

export interface AdminOverview {
  active_users: number;
  pending_users: number;
  disabled_users: number;
  workspace_count: number;
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

export function updateAdminUser(
  userId: string,
  input: { status?: UserStatus; roles?: AppRole[]; workspace_scopes?: string[] },
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
