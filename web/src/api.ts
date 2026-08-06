import type {
  PredictiveMaintenanceDashboardResponse,
  ProductResultPage,
} from "./features/predictive-maintenance/types";
import type { AuthUser, Evidence, EventSummary, Project, Report, Role, Workspace } from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let csrfTokenCache: string | null = null;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (STATE_CHANGING_METHODS.has(method)) {
    const csrfToken = csrfTokenCache ?? cookieValue("ontology_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, method, headers, credentials: "include" });
  const payload = response.status === 204 ? undefined : await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "api_request_failed",
      payload?.error?.message ?? payload?.detail ?? `API request failed: ${response.status}`,
    );
  }
  return payload as T;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser; csrf_token: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  csrfTokenCache = payload.csrf_token;
  return payload.user;
}

export async function getCurrentUser(signal?: AbortSignal): Promise<AuthUser> {
  const payload = await request<{ user: AuthUser; csrf_token: string | null }>("/api/auth/me", { signal });
  csrfTokenCache = payload.csrf_token;
  return payload.user;
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
  csrfTokenCache = null;
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function getProjectWorkspaces(projectId: string): Promise<Workspace[]> {
  return (await request<{ items: Workspace[] }>(`/api/projects/${encodeURIComponent(projectId)}/workspaces`)).items;
}

export async function getProjectEvents(projectId: string): Promise<EventSummary[]> {
  return (await request<{ items: EventSummary[] }>(`/api/projects/${encodeURIComponent(projectId)}/events`)).items;
}

function predictiveMaintenanceBase(projectId: string, workspaceId: string) {
  return `/api/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/predictive-maintenance`;
}

export function getPredictiveMaintenanceDashboard(
  projectId: string,
  workspaceId: string,
  input: {
    dataset_version_id?: string;
    selected_event_id?: string;
    role?: "manager" | "engineer";
    intent?: string;
    locale?: "ko-KR" | "en-US";
  } = {},
): Promise<PredictiveMaintenanceDashboardResponse> {
  const params = new URLSearchParams();
  Object.entries(input).forEach(([key, value]) => value && params.set(key, value));
  const query = params.size ? `?${params.toString()}` : "";
  return request(`${predictiveMaintenanceBase(projectId, workspaceId)}/dashboard${query}`);
}

export function getPredictiveMaintenanceLatestResults(
  projectId: string,
  workspaceId: string,
  limit = 100,
): Promise<ProductResultPage> {
  return request(`${predictiveMaintenanceBase(projectId, workspaceId)}/results/latest?limit=${limit}`);
}

export function getEvidence(eventId: string): Promise<Evidence> {
  return request(`/api/events/${encodeURIComponent(eventId)}/evidence`);
}

export async function getReport(
  eventId: string,
  role: Role,
  useLlm = true,
  locale: "ko-KR" | "en-US" = "ko-KR",
): Promise<Report> {
  const payload = await request<{ report: Report }>(`/api/events/${encodeURIComponent(eventId)}/report`, {
    method: "POST",
    body: JSON.stringify({ role, locale, use_llm: useLlm }),
  });
  return payload.report;
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
