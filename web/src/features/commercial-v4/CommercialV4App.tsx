import { Component, useEffect, useMemo, useState, type ErrorInfo, type ReactNode } from "react";
import {
  Activity,
  Archive,
  Boxes,
  BrainCircuit,
  ChevronRight,
  CircleAlert,
  Database,
  Container,
  FileClock,
  GitBranch,
  LockKeyhole,
  Settings2,
  ServerCog,
  Users,
  Workflow,
} from "lucide-react";
import {
  ApiError,
  getDatasetCatalogPage,
  getProject,
  getProjectWorkspaces,
} from "../../api";
import { useAuth } from "../auth/AuthContext";
import type { DatasetCatalogItem } from "../datasets/types";
import type { Project, Workspace } from "../../types";
import { blueprintV4ProjectPath, navigate } from "../../routing";
import {
  COMMERCIAL_V4_APPLICATION,
  accessibleCommercialSurfaces,
  type CommercialSurfaceId,
} from "../../platform/application/applicationRegistry";
import {
  applicationStorageKey,
  readApplicationPreference,
  writeApplicationPreference,
} from "../../platform/application/applicationState";
import {
  getProjectV4ApplicationDefinition,
  getPersistenceReadiness,
  getEnterpriseIdentityReadiness,
  getDeploymentReadiness,
  getDistributedRuntime,
  getArtifactGovernance,
  getObservabilityReadiness,
  getConnectorSnapshot,
  getOntologyPrimitives,
  getBranchingLineage,
  getApplicationRuntime,
  getSamplePipelinePlan,
  getMLOpsSnapshot,
  getAutomationSnapshot,
  simulateHighRiskAutomation,
  globalObjectSearch,
  createBranchPreview,
  checkRestrictedDatasetPolicy,
  previewGovernedAction,
  executeRiskFunction,
  runConnector,
  reconcileArtifacts,
  signArtifactDownload,
  verifyArtifact,
  type ArtifactGovernanceSnapshot,
  type ObservabilityReadiness,
  type ConnectorSnapshot,
  type OntologyPrimitiveSnapshot,
  type BranchingLineageSnapshot,
  type ApplicationRuntimeSnapshot,
  type PipelinePlan,
  type MLOpsSnapshot,
  type AutomationSnapshot,
  operateDistributedJob,
  type DistributedRuntimeSnapshot,
  type DeploymentReadiness,
  type EnterpriseIdentityReadiness,
  type PersistenceReadiness,
  type ProjectV4ApplicationDefinition,
} from "./commercialV4Api";
import "./commercial-v4.css";

const ICONS = {
  overview: Activity,
  identity: Users,
  deployment: Container,
  runtime: ServerCog,
  artifacts: Archive,
  operations: Activity,
  ingestion: Database,
  objects: Boxes,
  analysis: Workflow,
  models: BrainCircuit,
  lineage: GitBranch,
  governance: FileClock,
  actions: LockKeyhole,
  automation: Workflow,
  settings: Settings2,
} as const;

interface CommercialContext {
  project: Project;
  workspaces: Workspace[];
  datasets: DatasetCatalogItem[];
  application: ProjectV4ApplicationDefinition;
  persistence: PersistenceReadiness;
  identity: EnterpriseIdentityReadiness;
  deployment: DeploymentReadiness;
  distributed: DistributedRuntimeSnapshot;
  artifacts: ArtifactGovernanceSnapshot | null;
  observability: ObservabilityReadiness | null;
  connectors: ConnectorSnapshot | null;
  primitives: OntologyPrimitiveSnapshot;
  branching: BranchingLineageSnapshot | null;
  applicationRuntime: ApplicationRuntimeSnapshot;
  pipeline: PipelinePlan;
  mlops: MLOpsSnapshot | null;
  automation: AutomationSnapshot;
}

function currentSurface(): CommercialSurfaceId {
  const value = new URLSearchParams(window.location.search).get("surface");
  return COMMERCIAL_V4_APPLICATION.surfaces.some((item) => item.id === value)
    ? value as CommercialSurfaceId
    : "overview";
}

function stateLabel(state: string) {
  if (state === "ready") return "Ready";
  if (state === "planned") return "Planned";
  if (state === "not_configured") return "Not configured";
  return "Blocked";
}

async function optionalSurfaceSnapshot<T>(
  allowed: boolean,
  surface: CommercialSurfaceId,
  loader: () => Promise<T>,
): Promise<T | null> {
  if (!allowed) return null;
  try {
    return await loader();
  } catch (reason) {
    console.error("commercial-v4-surface-load-failed", { surface, reason });
    return null;
  }
}

class CommercialV4ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("commercial-v4-render-failed", { error, info });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="commercial-v4 commercial-v4-fatal" data-application-version="v4">
        <CircleAlert aria-hidden="true" />
        <p className="commercial-v4-eyebrow">COMMERCIAL V4 · ERROR</p>
        <h1>Application composition could not be rendered</h1>
        <p>The previous product versions remain available. Reload V4 or return to the Original application.</p>
        <button type="button" onClick={() => window.location.reload()}>Reload V4</button>
      </main>
    );
  }
}

function CommercialV4Runtime({ projectId }: { projectId: string }) {
  const { user } = useAuth();
  const [context, setContext] = useState<CommercialContext | null>(null);
  const [error, setError] = useState<string>("");
  const [surface, setSurface] = useState<CommercialSurfaceId>(() => currentSurface());
  const [compactNavigation, setCompactNavigation] = useState(false);
  const [operationMessage, setOperationMessage] = useState("");
  const [searchQuery, setSearchQuery] = useState("asset");
  const [searchResults, setSearchResults] = useState<Array<{ type: string; id: string; title: string; subtitle: string; score: number }>>([]);
  const workspace = context?.workspaces.find((item) => item.id === context.project.default_workspace_id)
    ?? context?.workspaces[0]
    ?? null;
  const preferenceKey = useMemo(() => user ? applicationStorageKey({
    version: "v4",
    projectId,
    userId: user.user_id,
    key: "application-preference",
  }) : "", [projectId, user]);
  const surfaces = useMemo(() => accessibleCommercialSurfaces(user?.permissions ?? []), [user?.permissions]);

  useEffect(() => {
    if (!preferenceKey) return;
    const stored = readApplicationPreference(preferenceKey);
    if (!stored) return;
    setCompactNavigation(stored.compactNavigation);
    if (!new URLSearchParams(window.location.search).has("surface")) setSurface(stored.surface);
  }, [preferenceKey]);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    const permissions = new Set(user.permissions);
    setContext(null);
    setError("");
    Promise.all([
      getProject(projectId),
      getProjectWorkspaces(projectId),
      getDatasetCatalogPage({ project_id: projectId, offset: 0, limit: 8 }),
      getProjectV4ApplicationDefinition(projectId),
      getPersistenceReadiness(projectId),
      getEnterpriseIdentityReadiness(projectId),
      getDeploymentReadiness(projectId),
      getDistributedRuntime(projectId),
      optionalSurfaceSnapshot(permissions.has("governance.read"), "artifacts", () => getArtifactGovernance(projectId)),
      optionalSurfaceSnapshot(permissions.has("governance.read"), "operations", () => getObservabilityReadiness(projectId)),
      optionalSurfaceSnapshot(permissions.has("governance.read"), "ingestion", () => getConnectorSnapshot(projectId)),
      getOntologyPrimitives(projectId),
      optionalSurfaceSnapshot(permissions.has("governance.read"), "lineage", () => getBranchingLineage(projectId)),
      getApplicationRuntime(projectId),
      getSamplePipelinePlan(projectId),
      optionalSurfaceSnapshot(permissions.has("ml.console.read"), "models", () => getMLOpsSnapshot(projectId)),
      getAutomationSnapshot(projectId),
    ])
      .then(([project, workspaces, datasets, application, persistence, identity, deployment, distributed, artifacts, observability, connectors, primitives, branching, applicationRuntime, pipeline, mlops, automation]) => {
        if (!controller.signal.aborted) setContext({
          project,
          workspaces,
          datasets: datasets.items,
          application,
          persistence,
          identity,
          deployment,
          distributed,
          artifacts,
          observability,
          connectors,
          primitives,
          branching,
          applicationRuntime,
          pipeline,
          mlops,
          automation,
        });
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          reason instanceof ApiError
            ? `${reason.code}: ${reason.message}`
            : reason instanceof Error
              ? reason.message
              : "The V4 application context could not be loaded.",
        );
      });
    return () => controller.abort();
  }, [projectId, user]);

  function selectSurface(next: CommercialSurfaceId) {
    setSurface(next);
    if (preferenceKey) writeApplicationPreference(preferenceKey, {
      schemaVersion: 1,
      surface: next,
      compactNavigation,
    });
    const path = new URL(blueprintV4ProjectPath(projectId), window.location.origin);
    path.searchParams.set("surface", next);
    navigate(`${path.pathname}${path.search}`, { replace: true });
  }

  function toggleNavigation() {
    const next = !compactNavigation;
    setCompactNavigation(next);
    if (preferenceKey) writeApplicationPreference(preferenceKey, {
      schemaVersion: 1,
      surface,
      compactNavigation: next,
    });
  }

  async function operateJob(jobId: string, action: "cancel" | "replay") {
    setOperationMessage("");
    try {
      await operateDistributedJob(
        projectId,
        jobId,
        action,
        action === "cancel" ? "Cancelled from the Commercial V4 operator surface" : "Replayed from the Commercial V4 operator surface",
      );
      const distributed = await getDistributedRuntime(projectId);
      setContext((current) => current ? { ...current, distributed } : current);
      setOperationMessage(`Job ${action} completed.`);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : `Job ${action} failed.`);
    }
  }

  async function refreshArtifacts() {
    const artifacts = await getArtifactGovernance(projectId);
    setContext((current) => current ? { ...current, artifacts } : current);
  }

  async function operateArtifact(artifactId: string, action: "verify" | "download") {
    setOperationMessage("");
    try {
      if (action === "verify") {
        await verifyArtifact(projectId, artifactId);
        await refreshArtifacts();
        setOperationMessage("Artifact checksum verification completed.");
      } else {
        const signed = await signArtifactDownload(projectId, artifactId);
        window.location.assign(signed.url);
      }
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : `Artifact ${action} failed.`);
    }
  }

  async function runArtifactReconciliation() {
    setOperationMessage("");
    try {
      const report = await reconcileArtifacts(projectId, false);
      setContext((current) => current?.artifacts ? {
        ...current,
        artifacts: { ...current.artifacts, last_reconciliation: report },
      } : current);
      setOperationMessage(
        `Reconciliation preview: ${report.missing.length} missing, ${report.checksum_mismatch.length} mismatched, ${report.orphan_keys.length} orphaned.`,
      );
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Artifact reconciliation failed.");
    }
  }

  async function executeConnector(connectorId: string) {
    setOperationMessage("");
    try {
      const queued = await runConnector(projectId, connectorId);
      setOperationMessage(`Connector ingestion queued as ${queued.job_id}.`);
      const connectors = await getConnectorSnapshot(projectId);
      setContext((current) => current ? { ...current, connectors } : current);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Connector ingestion failed.");
    }
  }

  async function previewAction() {
    setOperationMessage("");
    try {
      const preview = await previewGovernedAction(projectId);
      setOperationMessage(
        preview.valid
          ? `Action preview valid for ${preview.target_count} assets · approval required: ${preview.approval_required}.`
          : `Action preview blocked: ${preview.validation_errors.join(", ")}`,
      );
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Action preview failed.");
    }
  }

  async function executeFunction() {
    setOperationMessage("");
    try {
      const execution = await executeRiskFunction(projectId);
      setOperationMessage(`Function ${execution.state}: risk ${execution.output.risk_score} (${execution.output.band}).`);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Function execution failed.");
    }
  }

  async function createReviewBranch() {
    setOperationMessage("");
    try {
      const result = await createBranchPreview(projectId);
      setOperationMessage(`Branch ${result.branch.name} created at revision ${result.branch.head_revision} · mergeable: ${result.mergeable}.`);
      const branching = await getBranchingLineage(projectId);
      setContext((current) => current ? { ...current, branching } : current);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Branch creation failed.");
    }
  }

  async function checkMarkingPolicy() {
    setOperationMessage("");
    try {
      const result = await checkRestrictedDatasetPolicy(projectId);
      setOperationMessage(`Policy ${result.decision}: ${result.reason_code} · masked: ${result.masked}.`);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Policy check failed.");
    }
  }

  async function searchObjects() {
    setOperationMessage("");
    try {
      const result = await globalObjectSearch(projectId, searchQuery);
      setSearchResults(result.items);
      setOperationMessage(`${result.items.length} governed search results.`);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Global search failed.");
    }
  }

  async function simulateAutomation() {
    setOperationMessage("");
    try {
      const result = await simulateHighRiskAutomation(projectId);
      setOperationMessage(`Automation ${String(result.state)} · approval required: ${String(result.approval_required)} · side effects: ${String(result.external_side_effects_executed)}.`);
    } catch (reason) {
      setOperationMessage(reason instanceof Error ? reason.message : "Automation simulation failed.");
    }
  }

  if (error) {
    return (
      <main className="commercial-v4 commercial-v4-state" data-application-version="v4">
        <CircleAlert aria-hidden="true" />
        <p className="commercial-v4-eyebrow">COMMERCIAL V4 · DEGRADED</p>
        <h1>Project context is unavailable</h1>
        <p>{error}</p>
        <button type="button" onClick={() => window.location.reload()}>Retry context load</button>
      </main>
    );
  }

  if (!context || !workspace || !user) {
    return (
      <main className="commercial-v4 commercial-v4-state" data-application-version="v4" aria-busy="true">
        <span className="commercial-v4-loader" aria-hidden="true" />
        <p className="commercial-v4-eyebrow">COMMERCIAL V4 · LOADING</p>
        <h1>Resolving version-scoped application context</h1>
        <p>Project, Dataset Version, role and permission metadata are loading.</p>
      </main>
    );
  }

  const selected = surfaces.find((item) => item.id === surface) ?? surfaces[0];
  const surfaceSnapshotUnavailable =
    (selected.id === "artifacts" && !context.artifacts)
    || (selected.id === "operations" && !context.observability)
    || (selected.id === "ingestion" && !context.connectors)
    || (selected.id === "models" && !context.mlops)
    || (selected.id === "lineage" && !context.branching);
  const artifacts = context.artifacts!;
  const observability = context.observability!;
  const connectors = context.connectors!;
  const mlops = context.mlops!;
  const branching = context.branching!;
  const activeDatasets = context.datasets.filter((item) => item.status === "active");
  const publishedRecords = activeDatasets.reduce((total, item) => total + item.record_count, 0);
  const readyFeatures = surfaces.filter((item) => item.state === "ready" && item.accessible).length;
  const plannedFeatures = surfaces.filter((item) => item.state === "planned").length;
  const domainPack = context.application.domain_pack;

  return (
    <main
      className={`commercial-v4 ${compactNavigation ? "is-navigation-compact" : ""}`}
      data-application-id={COMMERCIAL_V4_APPLICATION.id}
      data-application-version="v4"
    >
      <header className="commercial-v4-topbar">
        <div className="commercial-v4-brand">
          <span className="commercial-v4-mark" aria-hidden="true">O4</span>
          <div>
            <p className="commercial-v4-eyebrow">ONTOLOGY PLATFORM</p>
            <strong>Commercial V4</strong>
          </div>
        </div>
        <div className="commercial-v4-context-line" aria-label="Application context">
          <span>{context.project.display_name}</span>
          <ChevronRight aria-hidden="true" />
          <span>{workspace.display_name}</span>
          <ChevronRight aria-hidden="true" />
          <span>{user.active_project_roles.join(", ") || user.roles.join(", ")}</span>
        </div>
        <div className="commercial-v4-release">
          <span className="commercial-v4-state-badge is-ready">Separate application</span>
          <small>Not the default route</small>
        </div>
      </header>

      <div className="commercial-v4-layout">
        <aside className="commercial-v4-nav" aria-label="Commercial V4 navigation">
          <button className="commercial-v4-nav-toggle" type="button" onClick={toggleNavigation} aria-label="Toggle compact navigation">
            <Settings2 aria-hidden="true" />
            <span>Application surfaces</span>
          </button>
          <nav>
            {surfaces.map((item) => {
              const Icon = ICONS[item.id];
              return (
                <button
                  key={item.id}
                  type="button"
                  className={item.id === selected.id ? "is-active" : ""}
                  onClick={() => selectSurface(item.id)}
                  aria-current={item.id === selected.id ? "page" : undefined}
                >
                  <Icon aria-hidden="true" />
                  <span>{item.label}</span>
                  <i className={`commercial-v4-state-dot is-${item.state}`} title={stateLabel(item.state)} />
                </button>
              );
            })}
          </nav>
          <div className="commercial-v4-version-policy">
            <GitBranch aria-hidden="true" />
            <div>
              <strong>V1–V3 preserved</strong>
              <span>V4 promotion requires explicit approval.</span>
            </div>
          </div>
        </aside>

        <section className="commercial-v4-content">
          <div className="commercial-v4-resource-header">
            <div>
              <p className="commercial-v4-eyebrow">{COMMERCIAL_V4_APPLICATION.applicationIdentity}</p>
              <h1>{selected.label}</h1>
              <p>{selected.description}</p>
            </div>
            <div className="commercial-v4-header-actions">
              <span className={`commercial-v4-state-badge is-${selected.state}`}>{stateLabel(selected.state)} · Phase {selected.phase}</span>
              {selected.launchPath && selected.accessible ? (
                <button type="button" onClick={() => navigate(selected.launchPath!({ projectId, workspaceId: workspace.id }))}>
                  Open shared workbench <ChevronRight aria-hidden="true" />
                </button>
              ) : null}
            </div>
          </div>

          {!selected.accessible ? (
            <section className="commercial-v4-panel commercial-v4-feature-state is-blocked">
              <LockKeyhole aria-hidden="true" />
              <p className="commercial-v4-eyebrow">PERMISSION DENIED</p>
              <h2>Your active role cannot open this surface.</h2>
              <p>Required permission: {selected.permission}</p>
            </section>
          ) : surfaceSnapshotUnavailable ? (
            <section className="commercial-v4-panel commercial-v4-feature-state is-blocked">
              <CircleAlert aria-hidden="true" />
              <p className="commercial-v4-eyebrow">SURFACE DEGRADED</p>
              <h2>This surface could not load its operational snapshot.</h2>
              <p>The rest of Commercial V4 remains available. Reload this page after checking the corresponding service.</p>
            </section>
          ) : selected.id === "overview" ? (
            <>
              <section className="commercial-v4-metrics" aria-label="Commercial readiness metrics">
                <article><span>Ready surfaces</span><strong>{readyFeatures}</strong><small>permission-aware</small></article>
                <article><span>Planned surfaces</span><strong>{plannedFeatures}</strong><small>no fake success UI</small></article>
                <article><span>Active datasets</span><strong>{activeDatasets.length}</strong><small>{publishedRecords.toLocaleString()} governed rows</small></article>
                <article><span>Application scope</span><strong>V4</strong><small>isolated state and cache identity</small></article>
              </section>

              <div className="commercial-v4-grid">
                <section className="commercial-v4-panel commercial-v4-project-card">
                  <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Project & Dataset context</span></div>
                  <dl>
                    <div><dt>Project</dt><dd>{context.project.display_name}</dd></div>
                    <div><dt>Domain pack</dt><dd>{context.project.domain_pack_code}</dd></div>
                    <div><dt>Canonical pack</dt><dd>{domainPack.code} · {domainPack.version}</dd></div>
                    <div><dt>Workspace</dt><dd>{workspace.display_name}</dd></div>
                    <div><dt>Organization</dt><dd>{context.project.organization_id}</dd></div>
                  </dl>
                  <div className="commercial-v4-dataset-list">
                    {context.datasets.length ? context.datasets.slice(0, 4).map((dataset) => (
                      <article key={dataset.id}>
                        <span><strong>{dataset.display_name}</strong><small>{dataset.latest_version_label ?? "No published version"}</small></span>
                        <em>{dataset.record_count.toLocaleString()} rows</em>
                      </article>
                    )) : <p className="commercial-v4-empty">No Dataset is registered for this Project.</p>}
                  </div>
                </section>

                <section className="commercial-v4-panel">
                  <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Role & permission boundary</span></div>
                  <dl>
                    <div><dt>Signed in as</dt><dd>{user.display_name}</dd></div>
                    <div><dt>Project roles</dt><dd>{user.active_project_roles.join(", ") || "No active role"}</dd></div>
                    <div><dt>Workspace scope</dt><dd>{user.workspace_scopes.includes(workspace.id) || user.is_admin ? "Allowed" : "Denied"}</dd></div>
                    <div><dt>Permissions</dt><dd>{user.permissions.length}</dd></div>
                  </dl>
                  <div className="commercial-v4-capability-list">
                    {surfaces.map((item) => (
                      <div key={item.id}>
                        <span>{item.label}</span>
                        <strong className={`is-${item.accessible ? item.state : "blocked"}`}>
                          {item.accessible ? stateLabel(item.state) : "Permission denied"}
                        </strong>
                      </div>
                    ))}
                  </div>
                </section>
                <section className="commercial-v4-panel commercial-v4-domain-contexts">
                  <div className="commercial-v4-panel-title"><Boxes aria-hidden="true" /><span>Bounded contexts</span></div>
                  <p className="commercial-v4-policy-copy">{domainPack.description}</p>
                  <div className="commercial-v4-context-list">
                    {domainPack.bounded_contexts.map((boundedContext) => (
                      <article key={boundedContext.id}>
                        <span>
                          <strong>{boundedContext.display_name}</strong>
                          <small>{boundedContext.id} · {boundedContext.kind}</small>
                        </span>
                        <em>{boundedContext.owns.length} owned types</em>
                      </article>
                    ))}
                  </div>
                </section>
                <section className="commercial-v4-panel">
                  <div className="commercial-v4-panel-title"><GitBranch aria-hidden="true" /><span>Namespace boundary</span></div>
                  <dl>
                    <div><dt>Platform</dt><dd>{context.application.platform_namespace}</dd></div>
                    <div><dt>Domain pack</dt><dd>{domainPack.namespace}</dd></div>
                    <div><dt>Source</dt><dd>{context.application.configuration_source}</dd></div>
                    <div><dt>Legacy aliases</dt><dd>{context.application.compatibility_namespaces.length}</dd></div>
                  </dl>
                </section>
              </div>
            </>
          ) : selected.id === "identity" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Users aria-hidden="true" /><span>Provider status</span></div>
                <div className="commercial-v4-identity-providers">
                  {context.identity.providers.map((provider) => (
                    <article key={provider.provider}>
                      <span>
                        <strong>{provider.provider === "oidc" ? "Enterprise OIDC" : "Local development"}</strong>
                        <small>{provider.issuer ?? "Built-in credential provider"}</small>
                      </span>
                      <em className={`is-${provider.state}`}>{provider.state.replace("_", " ")}</em>
                    </article>
                  ))}
                </div>
                {context.identity.providers.flatMap((provider) => provider.blockers).map((blocker) => (
                  <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>
                ))}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Access lifecycle contract</span></div>
                <dl>
                  <div><dt>Canonical context</dt><dd>{context.identity.canonical_context}</dd></div>
                  <div><dt>Group mapping</dt><dd>{context.identity.group_mapping}</dd></div>
                  <div><dt>SCIM</dt><dd>{String(context.identity.scim.state)}</dd></div>
                  <div><dt>Break glass</dt><dd>{String(context.identity.break_glass.state)}</dd></div>
                </dl>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Settings2 aria-hidden="true" /><span>MFA & step-up</span></div>
                <p className="commercial-v4-policy-copy">High-impact operations require IdP MFA claims or phishing-resistant assurance. Local admin enrollment remains not configured rather than bypassed.</p>
                <div className="commercial-v4-chip-list">
                  {(context.identity.mfa.step_up_operations as string[]).map((operation) => <span key={operation}>{operation}</span>)}
                </div>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>Service & session identity</span></div>
                <dl>
                  <div><dt>Interactive cookie</dt><dd>{String(context.identity.service_identity.interactive_cookie)}</dd></div>
                  <div><dt>Scoped credentials</dt><dd>{String(context.identity.service_identity.scoped)}</dd></div>
                  <div><dt>Session rotation</dt><dd>{String(context.identity.session.rotation)}</dd></div>
                  <div><dt>Cross-instance revoke</dt><dd>{String(context.identity.session.cross_instance)}</dd></div>
                </dl>
              </section>
            </div>
          ) : selected.id === "deployment" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Container aria-hidden="true" /><span>Production topology</span></div>
                <div className="commercial-v4-chip-list">
                  {context.deployment.topology.map((service) => <span key={service}>{service}</span>)}
                </div>
                <p className="commercial-v4-policy-copy">{context.deployment.release_strategy}</p>
                <span className={`commercial-v4-state-badge is-${context.deployment.state}`}>{context.deployment.state}</span>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Activity aria-hidden="true" /><span>Probe contract</span></div>
                <dl>
                  {Object.entries(context.deployment.probes).map(([name, path]) => (
                    <div key={name}><dt>{name}</dt><dd>{path}</dd></div>
                  ))}
                </dl>
              </section>
              <section className="commercial-v4-panel commercial-v4-route-contract">
                <div className="commercial-v4-panel-title"><GitBranch aria-hidden="true" /><span>Versioned deep links</span></div>
                {context.deployment.routes.map((route) => <code key={route}>{route}</code>)}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Environment blockers</span></div>
                {context.deployment.blockers.length ? context.deployment.blockers.map((blocker) => (
                  <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>
                )) : <p className="commercial-v4-policy-copy">No deployment blockers reported.</p>}
              </section>
            </div>
          ) : selected.id === "runtime" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><ServerCog aria-hidden="true" /><span>Queue & coordination</span></div>
                <dl>
                  <div><dt>Queue backend</dt><dd>{context.distributed.readiness.queue_backend}</dd></div>
                  <div><dt>Redis</dt><dd>{context.distributed.readiness.redis_state.replace("_", " ")}</dd></div>
                  <div><dt>Delivery</dt><dd>{context.distributed.readiness.queue_delivery}</dd></div>
                  <div><dt>Worker types</dt><dd>{context.distributed.readiness.worker_types.length}</dd></div>
                </dl>
                <span className={`commercial-v4-state-badge is-${context.distributed.readiness.state}`}>{context.distributed.readiness.state}</span>
                {context.distributed.readiness.blockers.map((blocker) => <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>)}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Activity aria-hidden="true" /><span>Queue metrics</span></div>
                <div className="commercial-v4-runtime-metrics">
                  {Object.entries(context.distributed.readiness.metrics).map(([name, value]) => (
                    <article key={name}><span>{name.replaceAll("_", " ")}</span><strong>{Number(value).toLocaleString()}</strong></article>
                  ))}
                </div>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Distributed rate-limit policy</span></div>
                <div className="commercial-v4-runtime-policy">
                  {Object.entries(context.distributed.readiness.rate_limit_policies).map(([name, policy]) => (
                    <article key={name}>
                      <span><strong>{name}</strong><small>{policy.key_dimensions.join(" + ")}</small></span>
                      <em className={`is-${policy.fail_mode}`}>{policy.limit}/{policy.window_seconds}s · fail {policy.fail_mode}</em>
                    </article>
                  ))}
                </div>
              </section>
              <section className="commercial-v4-panel commercial-v4-runtime-jobs">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>Recent durable jobs</span></div>
                {operationMessage ? <p className="commercial-v4-policy-copy" role="status">{operationMessage}</p> : null}
                {context.distributed.jobs.length ? context.distributed.jobs.map((job) => (
                  <article key={job.id}>
                    <span><strong>{job.job_type}</strong><small>{job.id} · attempt {job.attempt_count}/{job.max_attempts}</small></span>
                    <em className={`is-${job.state}`}>{job.state.replace("_", " ")}</em>
                    {user.permissions.includes("governance.projection.retry") && ["queued", "retry", "running", "cancel_requested"].includes(job.state) ? (
                      <button type="button" onClick={() => void operateJob(job.id, "cancel")}>Cancel</button>
                    ) : null}
                    {user.permissions.includes("governance.projection.retry") && job.state === "dead_letter" ? (
                      <button type="button" onClick={() => void operateJob(job.id, "replay")}>Replay</button>
                    ) : null}
                  </article>
                )) : <p className="commercial-v4-empty">No durable jobs have been submitted for this Project.</p>}
              </section>
            </div>
          ) : selected.id === "artifacts" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Archive aria-hidden="true" /><span>Object-storage readiness</span></div>
                <dl>
                  <div><dt>Backend</dt><dd>{artifacts.readiness.backend}</dd></div>
                  <div><dt>Bucket</dt><dd>{artifacts.readiness.bucket ?? "Local emulator"}</dd></div>
                  <div><dt>Encryption</dt><dd>{artifacts.readiness.encryption}</dd></div>
                  <div><dt>Checksums</dt><dd>{artifacts.readiness.checksum}</dd></div>
                </dl>
                <span className={`commercial-v4-state-badge is-${artifacts.readiness.state}`}>{artifacts.readiness.state.replace("_", " ")}</span>
                {artifacts.readiness.blockers.map((blocker) => <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>)}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><GitBranch aria-hidden="true" /><span>Governance contract</span></div>
                <p className="commercial-v4-policy-copy">{artifacts.readiness.deterministic_key_schema}</p>
                <p className="commercial-v4-policy-copy">{artifacts.readiness.signed_downloads}</p>
                <div className="commercial-v4-chip-list">
                  {artifacts.readiness.retention_classes.map((retentionClass) => <span key={retentionClass}>{retentionClass}</span>)}
                </div>
              </section>
              <section className="commercial-v4-panel commercial-v4-artifact-catalog">
                <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Governed artifact catalog</span></div>
                {operationMessage ? <p className="commercial-v4-policy-copy" role="status">{operationMessage}</p> : null}
                {artifacts.artifacts.length ? artifacts.artifacts.map((artifact) => (
                  <article key={artifact.id}>
                    <span>
                      <strong>{artifact.resource_type} · {artifact.resource_id}</strong>
                      <small>{artifact.resource_version} · {artifact.checksum_sha256.slice(0, 12)}… · {artifact.size_bytes.toLocaleString()} B</small>
                    </span>
                    <em className={`is-${artifact.state}`}>{artifact.state.replace("_", " ")}</em>
                    <button type="button" onClick={() => void operateArtifact(artifact.id, "verify")}>Verify</button>
                    {artifact.state === "available" ? <button type="button" onClick={() => void operateArtifact(artifact.id, "download")}>Download</button> : null}
                  </article>
                )) : <p className="commercial-v4-empty">No governed artifact has been registered for this Project.</p>}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Retention & reconciliation</span></div>
                <dl>
                  <div><dt>Catalog objects</dt><dd>{artifacts.artifacts.length}</dd></div>
                  <div><dt>Delete candidates</dt><dd>{artifacts.retention_preview.filter((item) => item.action === "delete").length}</dd></div>
                  <div><dt>Legal holds</dt><dd>{artifacts.retention_preview.filter((item) => item.action === "skip_legal_hold").length}</dd></div>
                  <div><dt>Last preview</dt><dd>{artifacts.last_reconciliation?.completed_at ?? "Not run"}</dd></div>
                </dl>
                {user.permissions.includes("governance.projection.retry") ? (
                  <button type="button" onClick={() => void runArtifactReconciliation()}>Run reconciliation preview</button>
                ) : null}
              </section>
            </div>
          ) : selected.id === "operations" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Activity aria-hidden="true" /><span>Telemetry readiness</span></div>
                <dl>
                  <div><dt>Structured logs</dt><dd>{observability.structured_logging}</dd></div>
                  <div><dt>Tracing</dt><dd>{String(observability.tracing.state)}</dd></div>
                  <div><dt>Metrics endpoint</dt><dd>{String(observability.metrics.endpoint)}</dd></div>
                  <div><dt>Metric series</dt><dd>{Number(observability.metrics.counter_series ?? 0) + Number(observability.metrics.histogram_series ?? 0)}</dd></div>
                </dl>
                <span className={`commercial-v4-state-badge is-${observability.state}`}>{observability.state.replace("_", " ")}</span>
                {observability.blockers.map((blocker) => <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>)}
              </section>
              <section className="commercial-v4-panel commercial-v4-slo-list">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>Service level objectives</span></div>
                {observability.slos.map((slo) => {
                  const budget = observability.error_budgets.find((item) => item.slo_id === slo.id);
                  return (
                    <article key={slo.id}>
                      <span><strong>{slo.name}</strong><small>{slo.sli} · {slo.window_days}d</small></span>
                      <em>{(slo.objective * 100).toFixed(2)}%</em>
                      <b className={`is-${budget?.state ?? "healthy"}`}>{((budget?.remaining_fraction ?? 1) * 100).toFixed(1)}% budget</b>
                    </article>
                  );
                })}
              </section>
              <section className="commercial-v4-panel commercial-v4-alert-list">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Alert policy</span></div>
                {observability.alerts.map((alert) => (
                  <article key={alert.id}>
                    <span><strong>{alert.id}</strong><small>{alert.expression}</small></span>
                    <em className={`is-${alert.severity}`}>{alert.severity} · {alert.duration}</em>
                  </article>
                ))}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Operations dashboards</span></div>
                <div className="commercial-v4-chip-list">
                  {observability.dashboards.map((dashboard) => <span key={dashboard}>{dashboard}</span>)}
                </div>
                <p className="commercial-v4-policy-copy">{observability.log_redaction}</p>
              </section>
            </div>
          ) : selected.id === "ingestion" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Connector readiness</span></div>
                <dl>
                  <div><dt>Checkpoint</dt><dd>{connectors.readiness.checkpoint}</dd></div>
                  <div><dt>Schema drift</dt><dd>{connectors.readiness.schema_drift}</dd></div>
                  <div><dt>Quarantine</dt><dd>{connectors.quarantine_count}</dd></div>
                  <div><dt>Backpressure</dt><dd>{connectors.readiness.backpressure}</dd></div>
                </dl>
                <span className={`commercial-v4-state-badge is-${connectors.readiness.state}`}>{connectors.readiness.state}</span>
                {connectors.readiness.blockers.slice(0, 3).map((blocker) => <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>)}
              </section>
              <section className="commercial-v4-panel commercial-v4-connector-list">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>Configured connectors</span></div>
                {operationMessage ? <p className="commercial-v4-policy-copy" role="status">{operationMessage}</p> : null}
                {connectors.connectors.map((connector) => (
                  <article key={connector.id}>
                    <span><strong>{connector.name}</strong><small>{connector.connector_type} · {connector.max_batch_records.toLocaleString()} records/batch</small></span>
                    <em className={`is-${connector.status}`}>{connector.status}</em>
                    {user.permissions.includes("governance.projection.retry") ? <button type="button" onClick={() => void executeConnector(connector.id)}>Run ingestion</button> : null}
                  </article>
                ))}
              </section>
              <section className="commercial-v4-panel commercial-v4-connector-list">
                <div className="commercial-v4-panel-title"><Activity aria-hidden="true" /><span>Ingestion history</span></div>
                {connectors.runs.length ? connectors.runs.map((run) => (
                  <article key={run.id}>
                    <span><strong>{run.state}</strong><small>{run.records_committed} committed · {run.records_quarantined} quarantined · {run.bytes_read.toLocaleString()} B</small></span>
                    <em className={run.schema_drift.breaking ? "is-error" : "is-ready"}>{run.schema_drift.breaking ? "breaking drift" : "contract compatible"}</em>
                  </article>
                )) : <p className="commercial-v4-empty">No connector ingestion run has completed for this Project.</p>}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Provider configuration</span></div>
                <div className="commercial-v4-runtime-policy">
                  {Object.entries(connectors.readiness.providers).map(([provider, status]) => (
                    <article key={provider}><span><strong>{provider}</strong><small>{status.credential_reference ? "secret reference configured" : "no credential reference"}</small></span><em className={`is-${status.state}`}>{status.state.replace("_", " ")}</em></article>
                  ))}
                </div>
              </section>
            </div>
          ) : selected.id === "automation" ? (
            <div className="commercial-v4-grid">
              {(["definition", "simulation", "approval", "recovery", "integrations"] as const).map((section) => (
                <section key={section} className="commercial-v4-panel">
                  <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>{section}</span></div>
                  {Object.entries(context.automation[section]).map(([name, value]) => <p key={name} className="commercial-v4-policy-copy"><strong>{name}</strong>: {Array.isArray(value) ? value.join(", ") : String(value)}</p>)}
                </section>
              ))}
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Dry run & approval</span></div>
                {user.permissions.includes("ontology.actions.execute") ? <button type="button" onClick={() => void simulateAutomation()}>Simulate automation</button> : null}
                {operationMessage ? <p role="status" className="commercial-v4-policy-copy">{operationMessage}</p> : null}
                {context.automation.guarantees.map((item) => <p key={item} className="commercial-v4-policy-copy">{item}</p>)}
              </section>
            </div>
          ) : selected.id === "models" ? (
            <div className="commercial-v4-grid">
              {(["feature_view", "deployment", "drift", "retraining", "rollback", "explanation"] as const).map((section) => (
                <section key={section} className="commercial-v4-panel">
                  <div className="commercial-v4-panel-title"><BrainCircuit aria-hidden="true" /><span>{section.replace("_", " ")}</span></div>
                  {Object.entries(mlops[section]).map(([name, value]) => <p key={name} className="commercial-v4-policy-copy"><strong>{name}</strong>: {Array.isArray(value) ? value.join(", ") : String(value)}</p>)}
                </section>
              ))}
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Model limitations</span></div>
                {mlops.limitations.map((item) => <p key={item} className="commercial-v4-policy-copy">{item}</p>)}
              </section>
            </div>
          ) : selected.id === "analysis" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>Visual Pipeline Builder</span></div>
                <div className="commercial-v4-pipeline-nodes">{context.pipeline.nodes.map((node) => <article key={node.id}><strong>{node.id}</strong><small>{node.type}</small><em className={`is-${node.state}`}>{node.state}</em></article>)}</div>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Pushdown query plan</span></div>
                <code className="commercial-v4-code">{context.pipeline.sql_preview}</code>
                <dl><div><dt>Provider</dt><dd>{context.pipeline.pushdown_provider}</dd></div><div><dt>Estimated rows</dt><dd>{context.pipeline.estimated_rows.toLocaleString()}</dd></div><div><dt>Estimated bytes</dt><dd>{context.pipeline.estimated_bytes.toLocaleString()}</dd></div></dl>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Activity aria-hidden="true" /><span>Scalable execution</span></div>
                <p className="commercial-v4-policy-copy">{context.pipeline.keyset_pagination}</p>
                <p className="commercial-v4-policy-copy">{context.pipeline.cancellation}</p>
                {context.pipeline.issues.map((issue) => <p key={issue} className="commercial-v4-policy-copy">{issue}</p>)}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Archive aria-hidden="true" /><span>Materialization contract</span></div>
                {Object.entries(context.pipeline.materialization).map(([name, value]) => <p key={name} className="commercial-v4-policy-copy"><strong>{name}</strong>: {String(value)}</p>)}
              </section>
            </div>
          ) : selected.id === "objects" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Boxes aria-hidden="true" /><span>Standard Object Views</span></div>
                {context.applicationRuntime.object_views.map((view) => (
                  <article key={view.id} className="commercial-v4-primitive-card">
                    <strong>{view.object_type_id} · {view.form_factor}</strong>
                    <small>{view.definition.sections.join(" · ")}</small>
                    <div>{view.definition.property_order.map((property) => <span key={property}>{property}</span>)}</div>
                  </article>
                ))}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>Metadata application runtime</span></div>
                {context.applicationRuntime.application.pages.map((page) => (
                  <article key={page.id} className="commercial-v4-primitive-card">
                    <strong>{page.id} · {page.layout}</strong>
                    <small>{page.components.map((component) => component.type).join(" · ")}</small>
                  </article>
                ))}
                {Object.entries(context.applicationRuntime.safety).map(([name, value]) => <p key={name} className="commercial-v4-policy-copy"><strong>{name}</strong>: {value}</p>)}
              </section>
              <section className="commercial-v4-panel commercial-v4-search-panel">
                <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Global search</span></div>
                <label htmlFor="commercial-v4-global-search">Search Objects, Datasets, Actions and Functions</label>
                <div><input id="commercial-v4-global-search" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /><button type="button" onClick={() => void searchObjects()}>Search</button></div>
                {operationMessage ? <p role="status" className="commercial-v4-policy-copy">{operationMessage}</p> : null}
                {searchResults.map((result) => <article key={`${result.type}:${result.id}`}><strong>{result.title}</strong><small>{result.type} · {result.subtitle} · score {result.score}</small></article>)}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Settings2 aria-hidden="true" /><span>Renderer registry</span></div>
                <div className="commercial-v4-chip-list">{Object.entries(context.applicationRuntime.renderer_registry).map(([type, renderer]) => <span key={type}>{type}: {renderer}</span>)}</div>
              </section>
            </div>
          ) : selected.id === "lineage" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><GitBranch aria-hidden="true" /><span>Global branches</span></div>
                {branching.branches.map((branch) => (
                  <article key={branch.id} className="commercial-v4-primitive-card">
                    <strong>{branch.name}</strong>
                    <small>{branch.status} · revision {branch.head_revision} · base {branch.base_branch_id ?? "none"}</small>
                  </article>
                ))}
                <button type="button" onClick={() => void createReviewBranch()}>Create review branch</button>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Workflow aria-hidden="true" /><span>End-to-end lineage</span></div>
                <div className="commercial-v4-lineage-list">
                  {branching.lineage_edges.map((edge) => (
                    <article key={edge.id}><span>{edge.source_type}:{edge.source_id}</span><em>{edge.relation}</em><span>{edge.target_type}:{edge.target_id}</span></article>
                  ))}
                </div>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Markings & ABAC</span></div>
                {branching.markings.map((marking) => (
                  <p key={`${marking.marking}:${marking.field_name ?? "resource"}`} className="commercial-v4-policy-copy"><strong>{marking.marking}</strong> · {marking.resource_type}:{marking.resource_id}{marking.field_name ? ` · ${marking.field_name}` : ""}</p>
                ))}
                <button type="button" onClick={() => void checkMarkingPolicy()}>Check export policy</button>
                {operationMessage ? <p role="status" className="commercial-v4-policy-copy">{operationMessage}</p> : null}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Merge semantics</span></div>
                {Object.entries(branching.merge_semantics).map(([name, value]) => <p key={name} className="commercial-v4-policy-copy"><strong>{name}</strong>: {value}</p>)}
              </section>
            </div>
          ) : selected.id === "actions" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><GitBranch aria-hidden="true" /><span>Ontology Interfaces</span></div>
                {context.primitives.interfaces.map((item) => (
                  <article key={`${item.id}:${item.version}`} className="commercial-v4-primitive-card">
                    <strong>{item.display_name} · v{item.version}</strong>
                    <small>{Object.keys(item.property_contract).join(" · ")}</small>
                    <div>{item.implementations.map((implementation) => <span key={implementation.object_type_id}>{implementation.object_type_id}</span>)}</div>
                  </article>
                ))}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Generated Action</span></div>
                {context.primitives.actions.map((action) => (
                  <article key={`${action.id}:${action.version}`} className="commercial-v4-primitive-card">
                    <strong>{action.display_name}</strong>
                    <small>{action.execution_mode} · {action.approval_required ? "approval required" : "direct"}</small>
                    {user.permissions.includes("ontology.actions.execute") ? <button type="button" onClick={() => void previewAction()}>Preview action</button> : null}
                  </article>
                ))}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><BrainCircuit aria-hidden="true" /><span>Governed Functions</span></div>
                {context.primitives.functions.map((fn) => (
                  <article key={`${fn.id}:${fn.version}`} className="commercial-v4-primitive-card">
                    <strong>{fn.display_name}</strong>
                    <small>{fn.network_policy} · timeout {fn.timeout_ms} ms</small>
                    <button type="button" onClick={() => void executeFunction()}>Run function</button>
                  </article>
                ))}
                {operationMessage ? <p role="status" className="commercial-v4-policy-copy">{operationMessage}</p> : null}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><CircleAlert aria-hidden="true" /><span>Runtime guarantees</span></div>
                {Object.entries(context.primitives.guarantees).map(([name, value]) => <p key={name} className="commercial-v4-policy-copy"><strong>{name}</strong>: {value}</p>)}
              </section>
            </div>
          ) : selected.id === "settings" ? (
            <div className="commercial-v4-grid">
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Settings2 aria-hidden="true" /><span>Version-scoped runtime</span></div>
                <dl>
                  <div><dt>Application ID</dt><dd>{COMMERCIAL_V4_APPLICATION.id}</dd></div>
                  <div><dt>Storage namespace</dt><dd>{COMMERCIAL_V4_APPLICATION.storageNamespace}</dd></div>
                  <div><dt>Query namespace</dt><dd>{COMMERCIAL_V4_APPLICATION.queryNamespace}</dd></div>
                  <div><dt>Collaboration channel</dt><dd>{COMMERCIAL_V4_APPLICATION.collaborationNamespace}</dd></div>
                </dl>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><GitBranch aria-hidden="true" /><span>Release policy</span></div>
                <p className="commercial-v4-policy-copy">V4 does not replace the Original, Blueprint V1 or Blueprint V2 applications. Default-route promotion is a separate release decision after cross-version regression evidence.</p>
                <button type="button" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Open Original application</button>
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><Database aria-hidden="true" /><span>Tenant persistence readiness</span></div>
                <dl>
                  <div><dt>Production DB</dt><dd>{context.persistence.canonical_database}</dd></div>
                  <div><dt>Active runtime</dt><dd>{context.persistence.active_database}</dd></div>
                  <div><dt>Identity repository</dt><dd>{context.persistence.identity_repository}</dd></div>
                  <div><dt>RLS groups</dt><dd>{context.persistence.rls_coverage.length}</dd></div>
                  <div><dt>Pool</dt><dd>{context.persistence.pool.min_size}–{context.persistence.pool.max_size}</dd></div>
                </dl>
                <span className={`commercial-v4-state-badge is-${context.persistence.state}`}>
                  {context.persistence.state === "ready" ? "Production ready" : "Production PostgreSQL required"}
                </span>
                {context.persistence.blockers.map((blocker) => <p key={blocker} className="commercial-v4-policy-copy">{blocker}</p>)}
              </section>
              <section className="commercial-v4-panel">
                <div className="commercial-v4-panel-title"><LockKeyhole aria-hidden="true" /><span>Transaction & recovery contract</span></div>
                <ol className="commercial-v4-contract-list">
                  {context.persistence.transaction_boundary.map((step) => <li key={step}>{step}</li>)}
                </ol>
                <p className="commercial-v4-policy-copy">Recovery: {context.persistence.action_recovery_states.join(" · ")}</p>
              </section>
            </div>
          ) : (
            <section className={`commercial-v4-panel commercial-v4-feature-state is-${selected.accessible ? selected.state : "blocked"}`}>
              {selected.accessible ? <Database aria-hidden="true" /> : <LockKeyhole aria-hidden="true" />}
              <p className="commercial-v4-eyebrow">{selected.accessible ? stateLabel(selected.state) : "PERMISSION DENIED"}</p>
              <h2>{selected.accessible ? selected.description : "Your active role cannot open this surface."}</h2>
              {selected.launchPath && selected.accessible ? (
                <button type="button" onClick={() => navigate(selected.launchPath!({ projectId, workspaceId: workspace.id }))}>Open the existing governed workbench</button>
              ) : (
                <p>{selected.accessible ? `Implementation is assigned to Phase ${selected.phase}; V4 does not present a simulated success state.` : `Required permission: ${selected.permission}`}</p>
              )}
            </section>
          )}
        </section>

        <aside className="commercial-v4-inspector" aria-label="Application definition inspector">
          <p className="commercial-v4-eyebrow">APPLICATION DEFINITION</p>
          <h2>{selected.label}</h2>
          <dl>
            <div><dt>Surface ID</dt><dd>{selected.id}</dd></div>
            <div><dt>State</dt><dd>{selected.accessible ? stateLabel(selected.state) : "Permission denied"}</dd></div>
            <div><dt>Owning phase</dt><dd>{selected.phase}</dd></div>
            <div><dt>Permission</dt><dd>{selected.permission ?? "Project membership"}</dd></div>
          </dl>
          <hr />
          <p>This inspector is generated from the V4 application manifest. Future phases extend the manifest instead of adding pathname conditionals to unrelated components.</p>
        </aside>
      </div>
    </main>
  );
}

export function CommercialV4App({ projectId }: { projectId: string }) {
  return (
    <CommercialV4ErrorBoundary>
      <CommercialV4Runtime projectId={projectId} />
    </CommercialV4ErrorBoundary>
  );
}
