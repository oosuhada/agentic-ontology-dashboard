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

export async function getWorkspaces(): Promise<Workspace[]> {
  return (await request<{ items: Workspace[] }>("/api/workspaces")).items;
}

export async function getDomainPacks(): Promise<DomainPack[]> {
  return (await request<{ items: DomainPack[] }>("/api/domain-packs")).items;
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
