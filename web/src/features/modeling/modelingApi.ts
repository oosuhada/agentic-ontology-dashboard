import type { ExplanationArtifact, WorkbenchPayload } from "./types";

type Scope = { projectId: string; workspaceId: string };
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8100";
const STATE_CHANGING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function cookieValue(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const item of document.cookie.split(";")) {
    const value = item.trim();
    if (value.startsWith(prefix)) return decodeURIComponent(value.slice(prefix.length));
  }
  return null;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (STATE_CHANGING_METHODS.has(method)) {
    const csrfToken = cookieValue("ontology_csrf");
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${API_BASE}${url}`, {
    ...init,
    method,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.error?.message ?? payload?.detail ?? `Request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

function scopeQuery(scope: Scope): string {
  return new URLSearchParams({
    project_id: scope.projectId,
    workspace_id: scope.workspaceId,
  }).toString();
}

export function fetchModelingWorkbench(
  scope: Scope,
  selectedExperimentId?: string,
): Promise<WorkbenchPayload> {
  const query = new URLSearchParams({
    project_id: scope.projectId,
    workspace_id: scope.workspaceId,
  });
  if (selectedExperimentId) query.set("selected_experiment_id", selectedExperimentId);
  return requestJson(`/api/modeling/workbench?${query.toString()}`);
}

export function requestModelRelease(scope: Scope, modelVersionId: string): Promise<unknown> {
  return requestJson(`/api/modeling/model-versions/${encodeURIComponent(modelVersionId)}/release-requests`, {
    method: "POST",
    body: JSON.stringify({
      project_id: scope.projectId,
      workspace_id: scope.workspaceId,
      rationale: "ML Validator Workbench에서 validation metric과 lineage를 검토했습니다.",
    }),
  });
}

export function decideModelRelease(
  scope: Scope,
  releaseRequestId: string,
  revision: number,
  decision: "approve" | "reject",
): Promise<unknown> {
  return requestJson(`/api/modeling/model-release-requests/${encodeURIComponent(releaseRequestId)}/decision`, {
    method: "POST",
    body: JSON.stringify({
      project_id: scope.projectId,
      workspace_id: scope.workspaceId,
      expected_revision: revision,
      decision,
      rationale: `Workbench governance decision: ${decision}`,
    }),
  });
}

export function activateModel(scope: Scope, modelVersionId: string, revision: number): Promise<unknown> {
  return requestJson(`/api/modeling/model-versions/${encodeURIComponent(modelVersionId)}/activate`, {
    method: "POST",
    body: JSON.stringify({
      project_id: scope.projectId,
      workspace_id: scope.workspaceId,
      expected_revision: revision,
    }),
  });
}

export function rollbackModel(scope: Scope, targetModelVersionId: string): Promise<unknown> {
  return requestJson("/api/modeling/model-versions/rollback", {
    method: "POST",
    body: JSON.stringify({
      project_id: scope.projectId,
      workspace_id: scope.workspaceId,
      target_model_version_id: targetModelVersionId,
    }),
  });
}

export async function scoreModel(
  scope: Scope,
  modelVersionId: string,
  inputSchemaChecksum: string,
  features: Record<string, unknown>,
): Promise<{ prediction: Record<string, unknown>; explanation: ExplanationArtifact }> {
  return requestJson(`/api/modeling/model-versions/${encodeURIComponent(modelVersionId)}/score`, {
    method: "POST",
    body: JSON.stringify({
      project_id: scope.projectId,
      workspace_id: scope.workspaceId,
      observation_id: `workbench-${Date.now()}`,
      observed_at: new Date().toISOString(),
      features,
      expected_input_schema_checksum_sha256: inputSchemaChecksum,
    }),
  });
}

export { scopeQuery };
