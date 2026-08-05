import { API_BASE } from "../../api";

export interface BoundedContextDefinition {
  id: string;
  display_name: string;
  kind: "core" | "supporting" | "integration";
  owns: string[];
  consumes: string[];
  publishes: string[];
}

export interface ProjectV4ApplicationDefinition {
  application_id: "ontology-commercial-v4";
  application_version: "v4";
  project_id: string;
  workspace_ids: string[];
  domain_pack: {
    code: string;
    version: string;
    display_name: string;
    description: string;
    status: "active" | "draft" | "disabled";
    namespace: string;
    vocabulary: {
      object_label: string;
      object_plural_label: string;
      event_label: string;
      action_label: string;
      risk_label: string;
    };
    bounded_contexts: BoundedContextDefinition[];
    object_type_ids: string[];
    interface_ids: string[];
    action_type_ids: string[];
    feature_flags: Record<string, boolean>;
  };
  platform_namespace: "ontology_dashboard";
  compatibility_namespaces: string[];
  configuration_source: "project_metadata" | "default_platform";
}

export interface PersistenceReadiness {
  state: "ready" | "blocked" | "degraded";
  canonical_database: "postgresql";
  active_database: "postgresql" | "sqlite";
  production_fail_fast: boolean;
  identity_repository: string;
  rls_scope_binding: string;
  identity_bypass: string;
  transaction_boundary: string[];
  action_recovery_states: string[];
  rls_coverage: Array<{
    category: string;
    tables: string[];
    scope: "organization" | "project" | "global";
    operations: string[];
    migration: string;
    state: "covered" | "not_applicable";
  }>;
  pool: { min_size: number; max_size: number; timeout_seconds: number };
  blockers: string[];
}

export interface EnterpriseIdentityReadiness {
  state: "ready" | "not_configured" | "blocked" | "error";
  providers: Array<{
    provider: "local" | "oidc";
    state: "ready" | "not_configured" | "blocked" | "error";
    issuer: string | null;
    client_id_configured: boolean;
    audience_configured: boolean;
    secret_reference_configured: boolean;
    discovery_url: string | null;
    callback_allowlist: string[];
    jit_policy: string;
    blockers: string[];
  }>;
  canonical_context: string;
  group_mapping: string;
  scim: Record<string, unknown>;
  mfa: Record<string, unknown>;
  service_identity: Record<string, unknown>;
  session: Record<string, unknown>;
  break_glass: Record<string, unknown>;
}

export interface DeploymentReadiness {
  state: "ready" | "blocked" | "degraded";
  environment: string;
  topology: string[];
  probes: Record<string, string>;
  routes: string[];
  ingress: Record<string, unknown>;
  containers: Record<string, unknown>;
  migration: Record<string, unknown>;
  resources: Record<string, Record<string, string>>;
  release_strategy: string;
  blockers: string[];
}

export interface DurableJob {
  id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string | null;
  job_type: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  state: "queued" | "running" | "retry" | "succeeded" | "failed" | "cancel_requested" | "cancelled" | "dead_letter";
  priority: number;
  attempt_count: number;
  max_attempts: number;
  available_at: string;
  lease_owner: string | null;
  lease_token: string | null;
  lease_expires_at: string | null;
  heartbeat_at: string | null;
  worker_version: string | null;
  runtime_checksum: string | null;
  cancellation_reason: string | null;
  failure_class: string | null;
  last_error: string | null;
  result: Record<string, unknown> | null;
  created_by: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface DistributedRuntimeSnapshot {
  readiness: {
    state: "ready" | "degraded" | "blocked";
    queue_backend: "postgresql" | "sqlite";
    queue_delivery: string;
    redis_state: "ready" | "not_configured" | "unavailable";
    redis_url_configured: boolean;
    redis_tls: boolean;
    rate_limit_policies: Record<string, {
      limit: number;
      window_seconds: number;
      fail_mode: "open" | "closed";
      key_dimensions: string[];
    }>;
    worker_types: string[];
    retry: Record<string, unknown>;
    event_transport: Record<string, unknown>;
    quotas: Record<string, number>;
    metrics: Record<string, number>;
    blockers: string[];
  };
  jobs: DurableJob[];
  dead_letters: DurableJob[];
}

export async function getProjectV4ApplicationDefinition(projectId: string): Promise<ProjectV4ApplicationDefinition> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/applications/v4`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error?.message ?? `V4 application definition failed: ${response.status}`);
  }
  return payload as ProjectV4ApplicationDefinition;
}

export async function getPersistenceReadiness(projectId: string): Promise<PersistenceReadiness> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/persistence-readiness`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Persistence readiness failed: ${response.status}`);
  return payload as PersistenceReadiness;
}

export async function getEnterpriseIdentityReadiness(projectId: string): Promise<EnterpriseIdentityReadiness> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/enterprise-identity`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Enterprise identity readiness failed: ${response.status}`);
  return payload as EnterpriseIdentityReadiness;
}

export async function getDeploymentReadiness(projectId: string): Promise<DeploymentReadiness> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/deployment-readiness`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Deployment readiness failed: ${response.status}`);
  return payload as DeploymentReadiness;
}

export async function getDistributedRuntime(projectId: string): Promise<DistributedRuntimeSnapshot> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/distributed-runtime`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Distributed runtime failed: ${response.status}`);
  return payload as DistributedRuntimeSnapshot;
}

function csrfToken(): string {
  const item = document.cookie.split("; ").find((value) => value.startsWith("ontology_csrf="));
  return item ? decodeURIComponent(item.slice("ontology_csrf=".length)) : "";
}

export async function operateDistributedJob(
  projectId: string,
  jobId: string,
  action: "cancel" | "replay",
  reason: string,
): Promise<DurableJob> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/distributed-jobs/${encodeURIComponent(jobId)}/${action}`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
      body: JSON.stringify({ reason }),
    },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? payload?.detail ?? `Job ${action} failed: ${response.status}`);
  return payload as DurableJob;
}
