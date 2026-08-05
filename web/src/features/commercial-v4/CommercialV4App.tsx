import { Component, useEffect, useMemo, useState, type ErrorInfo, type ReactNode } from "react";
import {
  Activity,
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
    const controller = new AbortController();
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
    ])
      .then(([project, workspaces, datasets, application, persistence, identity, deployment]) => {
        if (!controller.signal.aborted) setContext({
          project,
          workspaces,
          datasets: datasets.items,
          application,
          persistence,
          identity,
          deployment,
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
  }, [projectId]);

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

          {selected.id === "overview" ? (
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
