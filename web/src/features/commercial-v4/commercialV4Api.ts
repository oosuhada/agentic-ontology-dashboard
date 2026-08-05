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
