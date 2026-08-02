import type { Evidence, EventSummary, FollowUp, Intent, Layout, Report, Role } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8100";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.error?.message ?? `API request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload as T;
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

export function resetDemo() {
  return request<{ status: string }>("/api/demo/reset", { method: "POST" });
}
