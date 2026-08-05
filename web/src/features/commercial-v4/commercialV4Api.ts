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

export interface GovernedArtifact {
  id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string | null;
  resource_type: string;
  resource_id: string;
  resource_version: string;
  object_key: string;
  uri: string;
  backend: "local" | "s3" | "gcs" | "azure";
  checksum_sha256: string;
  media_type: string;
  size_bytes: number;
  metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
  state: "available" | "missing" | "checksum_mismatch" | "quarantined" | "retention_pending" | "deleted";
  retention_class: "ephemeral" | "standard" | "regulated" | "backup" | "legal_hold";
  retain_until: string | null;
  legal_hold: boolean;
  created_by: string;
  created_at: string;
  verified_at: string | null;
  deleted_at: string | null;
}

export interface ArtifactGovernanceSnapshot {
  readiness: {
    state: "ready" | "degraded" | "not_configured" | "blocked";
    backend: "local" | "s3" | "gcs" | "azure";
    bucket: string | null;
    endpoint_configured: boolean;
    credential_reference_configured: boolean;
    encryption: string;
    versioning: string;
    signed_downloads: string;
    deterministic_key_schema: string;
    checksum: string;
    retention_classes: string[];
    reconciliation: string;
    blockers: string[];
  };
  artifacts: GovernedArtifact[];
  retention_preview: Array<{
    artifact_id: string;
    object_key: string;
    retention_class: string;
    retain_until: string | null;
    legal_hold: boolean;
    action: "retain" | "delete" | "skip_legal_hold";
    reason: string;
  }>;
  last_reconciliation: null | {
    run_id: string;
    mode: "dry_run" | "apply";
    catalog_count: number;
    object_count: number;
    verified: string[];
    missing: string[];
    checksum_mismatch: string[];
    orphan_keys: string[];
    completed_at: string;
  };
}

export interface ObservabilityReadiness {
  state: "ready" | "degraded" | "not_configured" | "blocked";
  structured_logging: string;
  log_redaction: string;
  tracing: Record<string, unknown>;
  metrics: Record<string, unknown>;
  slos: Array<{
    id: string;
    name: string;
    objective: number;
    window_days: number;
    sli: string;
    good_event: string;
    total_event: string;
    alert_burn_rates: number[];
  }>;
  error_budgets: Array<{
    slo_id: string;
    objective: number;
    observed_success_ratio: number;
    budget_fraction: number;
    consumed_fraction: number;
    remaining_fraction: number;
    state: "healthy" | "at_risk" | "exhausted";
  }>;
  alerts: Array<{
    id: string;
    severity: "warning" | "critical";
    expression: string;
    duration: string;
    runbook: string;
    routing_key: string;
  }>;
  dashboards: string[];
  blockers: string[];
}

export interface ConnectorSnapshot {
  readiness: {
    state: "ready" | "degraded" | "not_configured" | "blocked";
    providers: Record<string, { state: string; credential_reference: boolean; environment?: string }>;
    checkpoint: string;
    schema_drift: string;
    quarantine: string;
    backpressure: string;
    secret_handling: string;
    blockers: string[];
  };
  connectors: Array<{
    id: string;
    name: string;
    connector_type: string;
    status: string;
    credential_reference: string | null;
    freshness_policy_seconds: number;
    max_batch_records: number;
    max_inflight_batches: number;
    schema_contract: Record<string, string>;
  }>;
  runs: Array<{
    id: string;
    connector_id: string;
    state: string;
    records_read: number;
    records_committed: number;
    records_quarantined: number;
    bytes_read: number;
    backpressure_events: number;
    schema_drift: { added: string[]; removed: string[]; type_changed: Record<string, [string, string]>; breaking: boolean };
    created_at: string;
    completed_at: string | null;
  }>;
  quarantine_count: number;
}

export interface OntologyPrimitiveSnapshot {
  interfaces: Array<{
    id: string;
    version: number;
    display_name: string;
    status: string;
    property_contract: Record<string, string>;
    capability_contract: string[];
    implementations: Array<{ object_type_id: string; property_mapping: Record<string, string> }>;
  }>;
  actions: Array<{
    id: string;
    version: number;
    display_name: string;
    target_interface_id: string;
    parameter_schema: Record<string, unknown>;
    execution_mode: string;
    approval_required: boolean;
    required_permission: string;
    status: string;
  }>;
  functions: Array<{
    id: string;
    version: number;
    display_name: string;
    input_schema: Record<string, string>;
    output_schema: Record<string, string>;
    runtime_checksum: string;
    timeout_ms: number;
    network_policy: string;
    status: string;
  }>;
  guarantees: Record<string, string>;
}

export interface BranchingLineageSnapshot {
  branches: Array<{
    id: string;
    name: string;
    base_branch_id: string | null;
    status: string;
    owner_user_id: string;
    head_revision: number;
  }>;
  lineage_edges: Array<{
    id: string;
    source_type: string;
    source_id: string;
    target_type: string;
    target_id: string;
    relation: string;
  }>;
  markings: Array<{
    resource_type: string;
    resource_id: string;
    field_name: string | null;
    marking: string;
    inherited_from: string | null;
  }>;
  branchable_resources: string[];
  merge_semantics: Record<string, string>;
}

export interface ApplicationRuntimeSnapshot {
  object_views: Array<{
    id: string;
    object_type_id: string;
    interface_id: string | null;
    form_factor: string;
    status: string;
    definition: { title_property: string; status_property: string; sections: string[]; property_order: string[] };
  }>;
  search_index: Array<{
    type: string;
    id: string;
    title: string;
    subtitle: string;
    markings: string[];
  }>;
  application: {
    id: string;
    version: number;
    pages: Array<{ id: string; layout: string; components: Array<{ type: string; version: number; input: string }> }>;
    variables: Record<string, { kind: string; interface?: string; source?: string }>;
    events: Array<{ source: string; target: string; action: string }>;
  };
  component_catalog: Array<{ type: string; version: number; a11y: string }>;
  renderer_registry: Record<string, string>;
  safety: Record<string, string>;
}

export interface PipelinePlan {
  valid: boolean;
  pushdown_provider: string;
  sql_preview: string;
  estimated_rows: number;
  estimated_bytes: number;
  keyset_pagination: string;
  cancellation: string;
  issues: string[];
  materialization: Record<string, unknown>;
  nodes: Array<{ id: string; type: string; state: string }>;
}

export interface MLOpsSnapshot {
  feature_view: Record<string, unknown>;
  deployment: Record<string, unknown>;
  drift: Record<string, unknown>;
  retraining: Record<string, unknown>;
  rollback: Record<string, unknown>;
  explanation: Record<string, unknown>;
  limitations: string[];
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

export async function getArtifactGovernance(projectId: string): Promise<ArtifactGovernanceSnapshot> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/artifact-governance`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Artifact governance failed: ${response.status}`);
  return payload as ArtifactGovernanceSnapshot;
}

async function artifactOperatorRequest<T>(
  url: string,
  purpose: string,
  requestPayload: Record<string, unknown> = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    body: JSON.stringify({ purpose, ...requestPayload }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? payload?.detail ?? `Artifact operation failed: ${response.status}`);
  return payload as T;
}

export function verifyArtifact(projectId: string, artifactId: string): Promise<GovernedArtifact> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/verify`,
    "Verify checksum from Commercial V4",
  );
}

export function signArtifactDownload(projectId: string, artifactId: string): Promise<{ url: string }> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/sign-download`,
    "Governed download from Commercial V4",
  );
}

export function reconcileArtifacts(projectId: string, apply = false): Promise<NonNullable<ArtifactGovernanceSnapshot["last_reconciliation"]>> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/artifact-reconciliation?apply=${apply ? "true" : "false"}`,
    apply ? "Apply artifact reconciliation from Commercial V4" : "Preview artifact reconciliation from Commercial V4",
  );
}

export async function getObservabilityReadiness(projectId: string): Promise<ObservabilityReadiness> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/observability`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Observability readiness failed: ${response.status}`);
  return payload as ObservabilityReadiness;
}

export async function getConnectorSnapshot(projectId: string): Promise<ConnectorSnapshot> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/connectors`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Connector snapshot failed: ${response.status}`);
  return payload as ConnectorSnapshot;
}

export function runConnector(projectId: string, connectorId: string): Promise<{ job_id: string; state: string }> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/connectors/${encodeURIComponent(connectorId)}/run`,
    "Run connector ingestion from Commercial V4",
  );
}

export async function getOntologyPrimitives(projectId: string): Promise<OntologyPrimitiveSnapshot> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/ontology-primitives`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Ontology primitives failed: ${response.status}`);
  return payload as OntologyPrimitiveSnapshot;
}

export function previewGovernedAction(projectId: string): Promise<{
  valid: boolean;
  target_count: number;
  approval_required: boolean;
  validation_errors: string[];
}> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/actions/preview`,
    "Preview governed Asset inspection action",
    {
      action_id: "request-asset-inspection",
      object_ids: ["equipment:M-001", "compressor:C-01"],
      parameters: { priority: "high", due_date: "2026-08-10" },
      reason: "Commercial V4 governed action preview",
    },
  );
}

export function executeRiskFunction(projectId: string): Promise<{
  state: string;
  output: { risk_score: number; band: string };
  runtime_checksum: string;
}> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/functions/execute`,
    "Execute governed Asset risk function",
    {
      function_id: "asset-risk-metric",
      inputs: { failure_probability: 0.81, criticality: 1.0 },
    },
  );
}

export async function getBranchingLineage(projectId: string): Promise<BranchingLineageSnapshot> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/branching-lineage`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Branching lineage failed: ${response.status}`);
  return payload as BranchingLineageSnapshot;
}

export function createBranchPreview(projectId: string): Promise<{
  branch: { id: string; name: string; status: string; head_revision: number };
  changes: Array<Record<string, unknown>>;
  mergeable: boolean;
}> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/branches/change`,
    "Create governed Commercial V4 branch preview",
    {
      branch_name: `v4-review-${Date.now()}`,
      resource_type: "application",
      resource_id: "commercial-v4",
      payload: { review_note: "Branch-scoped application change", external_side_effects: false },
    },
  );
}

export function checkRestrictedDatasetPolicy(projectId: string): Promise<{
  decision: "allow" | "deny";
  reason_code: string;
  effective_markings: string[];
  masked: boolean;
}> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/policy/check`,
    "Check marked Dataset access from Commercial V4",
    {
      resource_type: "dataset",
      resource_id: "canonical-v3.1",
      purpose: "export",
      eligible_markings: ["confidential", "export_restricted"],
    },
  );
}

export async function getApplicationRuntime(projectId: string): Promise<ApplicationRuntimeSnapshot> {
  const response = await fetch(
    `${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/application-runtime`,
    { credentials: "include" },
  );
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Application runtime failed: ${response.status}`);
  return payload as ApplicationRuntimeSnapshot;
}

export function globalObjectSearch(projectId: string, query: string): Promise<{
  items: Array<{ type: string; id: string; title: string; subtitle: string; score: number; explanation: string }>;
}> {
  return artifactOperatorRequest(
    `/api/platform/projects/${encodeURIComponent(projectId)}/global-search`,
    "Search Commercial V4 governed resources",
    {
      query,
      allowed_types: [],
      eligible_markings: ["confidential"],
    },
  );
}

export async function getSamplePipelinePlan(projectId: string): Promise<PipelinePlan> {
  const response = await fetch(`${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/pipeline/sample-plan`, { credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `Pipeline plan failed: ${response.status}`);
  return payload as PipelinePlan;
}

export async function getMLOpsSnapshot(projectId: string): Promise<MLOpsSnapshot> {
  const response = await fetch(`${API_BASE}/api/platform/projects/${encodeURIComponent(projectId)}/mlops`, { credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error?.message ?? `MLOps snapshot failed: ${response.status}`);
  return payload as MLOpsSnapshot;
}
