import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import {
  matchAgentPath,
  matchAnalysisPath,
  matchBlueprintComparisonPath,
  matchBlueprintProjectPath,
  matchBlueprintV2ProjectPath,
  matchBlueprintV4ProjectPath,
  matchDatasetCatalogPath,
  matchGovernancePath,
  matchModelingPath,
  matchOperationsProjectPath,
  matchOntologyPath,
  matchProjectDashboardPath,
  matchProjectHomePath,
  operationsProjectPath,
  navigate,
  loginPath,
  week2OperationsRedirectPath,
  usePathname,
} from "./routing";
import { ApiError, getProject, getProjectWorkspaces } from "./api";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { DisplayPreferencesProvider } from "./ui/foundry/displayPreferences";
import { I18nProvider } from "./ui/i18n/I18nProvider";
import { WorkbenchState } from "./ui/foundry/WorkbenchState";
import { HanbitLogo } from "./ui/foundry/HanbitLogo";
import { featureFlags } from "./featureFlags";
import {
  isReliabilityPreviewLocation,
  ReliabilityRoutePlaceholder,
} from "./features/predictive-maintenance/ReliabilityRoutePlaceholder";

const AdminApp = lazy(() =>
  import("./features/admin/AdminApp").then((module) => ({ default: module.AdminApp })),
);
const LoginPage = lazy(() =>
  import("./features/auth/LoginPage").then((module) => ({ default: module.LoginPage })),
);
const PendingPage = lazy(() =>
  import("./features/auth/PendingPage").then((module) => ({ default: module.PendingPage })),
);
const RegisterPage = lazy(() =>
  import("./features/auth/RegisterPage").then((module) => ({ default: module.RegisterPage })),
);
const ManufacturingApp = lazy(() =>
  import("./features/manufacturing/ManufacturingApp").then((module) => ({ default: module.ManufacturingApp })),
);
const BlueprintManufacturingApp = lazy(() =>
  import("./features/blueprint/BlueprintManufacturingApp").then((module) => ({ default: module.BlueprintManufacturingApp })),
);
const BlueprintManufacturingV2App = lazy(() =>
  import("./features/blueprint-v2/BlueprintManufacturingV2App").then((module) => ({ default: module.BlueprintManufacturingV2App })),
);
const BlueprintComparisonPage = lazy(() =>
  import("./features/blueprint-compare/BlueprintComparisonPage").then((module) => ({ default: module.BlueprintComparisonPage })),
);
const CommercialV4App = lazy(() =>
  import("./features/commercial-v4/CommercialV4App").then((module) => ({ default: module.CommercialV4App })),
);
const OperationsApplication = lazy(() => import("./features/operations/OperationsApplication"));
const FoundryAppShell = lazy(() =>
  import("./ui/foundry/FoundryAppShell").then((module) => ({ default: module.FoundryAppShell })),
);
const ProjectHomePage = lazy(() =>
  import("./features/projects/ProjectHomePage").then((module) => ({ default: module.ProjectHomePage })),
);
const ProjectTombstonePage = lazy(() =>
  import("./features/projects/ProjectTombstonePage").then((module) => ({ default: module.ProjectTombstonePage })),
);
const AgentWorkbenchPage = lazy(() =>
  import("./features/agent/AgentWorkbenchPage").then((module) => ({ default: module.AgentWorkbenchPage })),
);
const OntologyPreviewPage = lazy(() =>
  import("./features/ontology/OntologyPreviewPage").then((module) => ({ default: module.OntologyPreviewPage })),
);
const DatasetCatalogPage = lazy(() =>
  import("./features/datasets/DatasetCatalogPage").then((module) => ({ default: module.DatasetCatalogPage })),
);
const GovernanceWorkbenchPage = lazy(() =>
  import("./features/governance/GovernanceWorkbenchPage").then((module) => ({ default: module.GovernanceWorkbenchPage })),
);
const MLValidatorWorkbench = lazy(() =>
  import("./features/modeling/MLValidatorWorkbench").then((module) => ({ default: module.MLValidatorWorkbench })),
);
const ReferenceGallery = lazy(() =>
  import("./features/reference/ReferenceGallery").then((module) => ({ default: module.ReferenceGallery })),
);
const TeamShareStory = lazy(() =>
  import("./features/teamshare/TeamShareStory").then((module) => ({ default: module.TeamShareStory })),
);
const AdaptiveTeamShareStory = lazy(() =>
  import("./features/teamshare/AdaptiveTeamShareStory").then((module) => ({ default: module.AdaptiveTeamShareStory })),
);
const EChartsComparisonEmbed = lazy(() =>
  import("./features/visualization/EChartsComparisonEmbed").then((module) => ({ default: module.EChartsComparisonEmbed })),
);

const LAST_VALID_PROJECT_KEY = "ontology-dashboard:last-valid-project";
const IS_PUBLIC_STORY = import.meta.env.VITE_PUBLIC_STORY === "1";

function RouteLoading({ operation }: { operation: string }) {
  const sessionBootstrap = operation === "Checking session" || operation === "Loading sign in";
  return (
    <div className="route-loading">
      <div className="route-loading__brand" aria-hidden="true">
        <span><HanbitLogo /></span>
        <div><strong>Hanbit Tech</strong><small>Reliability Operations</small></div>
      </div>
      <WorkbenchState
        kind="loading"
        title={operation}
        detail={sessionBootstrap ? "Preparing a secure, role-aware operations workspace" : "Preparing governed resources and operational context"}
        loaderVariant="page"
        loaderSteps={sessionBootstrap ? ["Session", "Scope", "Workspace"] : ["Data", "Logic", "Action"]}
      />
      <div className="route-loading__trust" aria-hidden="true">
        <span>Live signals</span><i /> <span>Traceable decisions</span><i /> <span>Closed loop</span>
      </div>
    </div>
  );
}

function Redirect({ to }: { to: string }) {
  useEffect(() => {
    // On an initial page load this child effect can run before usePathname's
    // parent popstate listener is registered. Deferring by one task guarantees
    // the listener exists before navigate() dispatches the synthetic event.
    const timer = window.setTimeout(() => navigate(to, { replace: true }), 0);
    return () => window.clearTimeout(timer);
  }, [to]);
  return <RouteLoading operation="Opening governed workspace" />;
}

function ProjectRouteBoundary({
  projectId,
  workspaceId,
  requiredPermission,
  pending,
  children,
}: {
  projectId: string;
  workspaceId?: string;
  requiredPermission?: string;
  pending?: ReactNode;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const [state, setState] = useState<"allowed" | "auth-required" | "denied" | "tombstone" | null>(null);
  const lastValidProjectId = window.sessionStorage.getItem(LAST_VALID_PROJECT_KEY);
  const fallbackProjectId = lastValidProjectId
    && lastValidProjectId !== projectId
    && user?.project_scopes.includes(lastValidProjectId)
    ? lastValidProjectId
    : user?.active_project_id !== projectId
      ? user?.active_project_id
      : user?.project_scopes.find((item) => item !== projectId);
  const fallback = fallbackProjectId
    ? `/app/projects/${encodeURIComponent(fallbackProjectId)}`
    : "/app";

  useEffect(() => {
    let cancelled = false;
    const lacksScope = !user || (!user.is_admin && !user.project_scopes.includes(projectId));
    const lacksPermission = Boolean(requiredPermission && !user?.permissions.includes(requiredPermission));
    const lacksWorkspaceScope = Boolean(
      workspaceId && !user?.is_admin && !user?.workspace_scopes.includes(workspaceId),
    );
    if (lacksScope || lacksPermission || lacksWorkspaceScope) {
      setState("denied");
      return () => { cancelled = true; };
    }

    setState(null);
    Promise.all([
      getProject(projectId),
      workspaceId ? getProjectWorkspaces(projectId) : Promise.resolve([]),
    ])
      .then(([, workspaces]) => {
        if (cancelled) return;
        if (workspaceId && !workspaces.some((item) => item.id === workspaceId)) {
          setState("denied");
          return;
        }
        window.sessionStorage.setItem(LAST_VALID_PROJECT_KEY, projectId);
        setState("allowed");
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        if (reason instanceof ApiError && reason.status === 401) setState("auth-required");
        else if (reason instanceof ApiError && reason.code === "project_not_found") setState("tombstone");
        else setState("denied");
      });
    return () => { cancelled = true; };
  }, [projectId, requiredPermission, user, workspaceId]);

  if (state === null) {
    return <>{pending ?? <RouteLoading operation="Validating Project scope" />}</>;
  }
  if (state === "auth-required") {
    return <Redirect to={loginPath(`${window.location.pathname}${window.location.search}`)} />;
  }
  if (state === "tombstone") return <ProjectTombstonePage projectId={projectId} />;
  if (state === "denied") return <Redirect to={fallback} />;
  return <>{children}</>;
}

function ProjectPreviewRoute({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) {
  const reliabilityPreview = isReliabilityPreviewLocation();
  const pending = reliabilityPreview
    ? <ReliabilityRoutePlaceholder />
    : <RouteLoading operation="Loading workbench" />;
  return (
    <ProjectRouteBoundary projectId={projectId} pending={pending}>
      <Suspense fallback={pending}>
        {children}
      </Suspense>
    </ProjectRouteBoundary>
  );
}

function ForbiddenPage() {
  const { user, logout } = useAuth();
  async function signOut() {
    await logout();
    navigate("/login", { replace: true });
  }
  return (
    <main className="forbidden-page">
      <div className="forbidden-card">
        <span className="eyebrow">403 · PERMISSION DENIED</span>
        <h1>관리자 권한이 없습니다</h1>
        <p>FDE와 일반 사용자 역할은 tenant administrator control plane에 접근할 수 없습니다.</p>
        <div className="button-row">
          <button className="primary" onClick={() => navigate("/app")}>사용자 앱으로</button>
          <button className="secondary" onClick={signOut}>로그아웃</button>
        </div>
        <small>{user?.email}</small>
      </div>
    </main>
  );
}

function AppRouter() {
  const pathname = usePathname();
  const { user, loading } = useAuth();

  if (pathname === "/reference") return <ReferenceGallery />;
  if (pathname === "/team-share") return <TeamShareStory />;
  if (pathname === "/team-share-adaptive") return <AdaptiveTeamShareStory />;
  if (pathname === "/visualization-compare/echarts") return <EChartsComparisonEmbed />;
  if (pathname === "/loader") return <RouteLoading operation="Checking session" />;

  if (loading) {
    return isReliabilityPreviewLocation()
      ? <ReliabilityRoutePlaceholder />
      : <RouteLoading operation="Checking session" />;
  }

  if (!user) {
    if (pathname === "/register") return <Suspense fallback={<RouteLoading operation="Loading registration" />}><RegisterPage /></Suspense>;
    if (pathname === "/pending") return <Suspense fallback={<RouteLoading operation="Loading account status" />}><PendingPage /></Suspense>;
    if (pathname !== "/login" && pathname !== "/") {
      return <Redirect to={loginPath(`${pathname}${window.location.search}`)} />;
    }
    return <Suspense fallback={<RouteLoading operation="Loading sign in" />}><LoginPage /></Suspense>;
  }

  if (pathname === "/admin") return user.is_admin ? <AdminApp /> : <ForbiddenPage />;

  if (pathname === "/backup") {
    const backupProjectId = user.active_project_id ?? user.project_scopes[0] ?? null;
    if (!backupProjectId) return <Redirect to={user.default_path} />;
    return (
      <ProjectPreviewRoute projectId={backupProjectId}>
        <OperationsApplication projectId={backupProjectId} backupMode />
      </ProjectPreviewRoute>
    );
  }

  const operationsProjectRoute = matchOperationsProjectPath(pathname);
  if (operationsProjectRoute) {
    return (
      <ProjectPreviewRoute projectId={operationsProjectRoute.projectId}>
        <OperationsApplication projectId={operationsProjectRoute.projectId} />
      </ProjectPreviewRoute>
    );
  }

  const defaultProjectId = user.active_project_id ?? user.project_scopes[0] ?? null;
  const defaultPath = featureFlags.week2OperationsOnly && defaultProjectId
    ? operationsProjectPath(defaultProjectId)
    : user.default_path;
  if (featureFlags.week2OperationsOnly) {
    const operationsRedirect = week2OperationsRedirectPath(pathname, defaultProjectId, window.location.search);
    if (operationsRedirect) return <Redirect to={operationsRedirect} />;
  }

  const analysisId = matchAnalysisPath(pathname);
  if (analysisId) return <ManufacturingApp initialWorkspaceView="analysis" analysisId={analysisId} />;

  const blueprintComparisonRoute = matchBlueprintComparisonPath(pathname);
  if (blueprintComparisonRoute) {
    return (
      <ProjectPreviewRoute projectId={blueprintComparisonRoute.projectId}>
        <BlueprintComparisonPage projectId={blueprintComparisonRoute.projectId} />
      </ProjectPreviewRoute>
    );
  }

  const blueprintProjectRoute = matchBlueprintProjectPath(pathname);
  if (blueprintProjectRoute) {
    return (
      <ProjectPreviewRoute projectId={blueprintProjectRoute.projectId}>
        <BlueprintManufacturingApp projectId={blueprintProjectRoute.projectId} />
      </ProjectPreviewRoute>
    );
  }

  const blueprintV2ProjectRoute = matchBlueprintV2ProjectPath(pathname);
  if (blueprintV2ProjectRoute) {
    return (
      <ProjectPreviewRoute projectId={blueprintV2ProjectRoute.projectId}>
        <BlueprintManufacturingV2App projectId={blueprintV2ProjectRoute.projectId} />
      </ProjectPreviewRoute>
    );
  }

  const blueprintV4ProjectRoute = matchBlueprintV4ProjectPath(pathname);
  if (blueprintV4ProjectRoute) {
    return (
      <ProjectPreviewRoute projectId={blueprintV4ProjectRoute.projectId}>
        <CommercialV4App projectId={blueprintV4ProjectRoute.projectId} />
      </ProjectPreviewRoute>
    );
  }

  const projectHomeRoute = matchProjectHomePath(pathname);
  if (projectHomeRoute) {
    return (
      <ProjectRouteBoundary projectId={projectHomeRoute.projectId}>
        <Suspense fallback={<RouteLoading operation="Loading Project Home" />}>
          <FoundryAppShell projectId={projectHomeRoute.projectId} activeRoute="home" title="Project Home">
            <ProjectHomePage projectId={projectHomeRoute.projectId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const datasetRoute = matchDatasetCatalogPath(pathname);
  if (datasetRoute) {
    return (
      <ProjectRouteBoundary projectId={datasetRoute.projectId} requiredPermission="datasets.read">
        <Suspense fallback={<RouteLoading operation="Loading Dataset Catalog" />}>
          <FoundryAppShell projectId={datasetRoute.projectId} activeRoute="datasets" title="Dataset Catalog">
            <DatasetCatalogPage projectId={datasetRoute.projectId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const agentRoute = matchAgentPath(pathname);
  if (agentRoute) {
    return (
      <ProjectRouteBoundary
        projectId={agentRoute.projectId}
        workspaceId={agentRoute.workspaceId}
        requiredPermission="planner.object_query"
      >
        <Suspense fallback={<RouteLoading operation="Loading Agent Evidence Workbench" />}>
          <FoundryAppShell projectId={agentRoute.projectId} workspaceId={agentRoute.workspaceId} activeRoute="agent" title="Agent Evidence Workbench">
            <AgentWorkbenchPage projectId={agentRoute.projectId} workspaceId={agentRoute.workspaceId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const governanceRoute = matchGovernancePath(pathname);
  if (governanceRoute) {
    return (
      <ProjectRouteBoundary
        projectId={governanceRoute.projectId}
        workspaceId={governanceRoute.workspaceId}
        requiredPermission="governance.read"
      >
        <Suspense fallback={<RouteLoading operation="Loading Governance Workbench" />}>
          <FoundryAppShell projectId={governanceRoute.projectId} workspaceId={governanceRoute.workspaceId} activeRoute="governance" title="Governance Workbench">
            <GovernanceWorkbenchPage projectId={governanceRoute.projectId} workspaceId={governanceRoute.workspaceId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const modelingRoute = matchModelingPath(pathname);
  if (modelingRoute) {
    return (
      <ProjectRouteBoundary
        projectId={modelingRoute.projectId}
        workspaceId={modelingRoute.workspaceId}
        requiredPermission="ml.console.read"
      >
        <Suspense fallback={<RouteLoading operation="Loading ML Validator Workbench" />}>
          <FoundryAppShell projectId={modelingRoute.projectId} workspaceId={modelingRoute.workspaceId} activeRoute="modeling" title="ML Validator Workbench">
            <MLValidatorWorkbench projectId={modelingRoute.projectId} workspaceId={modelingRoute.workspaceId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const ontologyRoute = matchOntologyPath(pathname);
  if (ontologyRoute) {
    return (
      <ProjectRouteBoundary
        projectId={ontologyRoute.projectId}
        workspaceId={ontologyRoute.workspaceId}
        requiredPermission="ontology.objects.read"
      >
        <Suspense fallback={<RouteLoading operation="Loading Ontology Object Explorer" />}>
          <FoundryAppShell projectId={ontologyRoute.projectId} workspaceId={ontologyRoute.workspaceId} activeRoute="ontology" title="Ontology Object Explorer">
            <OntologyPreviewPage projectId={ontologyRoute.projectId} workspaceId={ontologyRoute.workspaceId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const projectDashboardRoute = matchProjectDashboardPath(pathname);
  if (projectDashboardRoute) {
    const requestedView = new URLSearchParams(window.location.search).get("view");
    const initialWorkspaceView = requestedView === "report" || requestedView === "dashboard" || requestedView === "analysis"
      ? requestedView
      : undefined;
    return (
      <ProjectRouteBoundary projectId={projectDashboardRoute.projectId}>
        <ManufacturingApp initialWorkspaceView={initialWorkspaceView} />
      </ProjectRouteBoundary>
    );
  }

  if (pathname === "/app" || pathname.startsWith("/app/")) return <ManufacturingApp />;
  return <Redirect to={defaultPath} />;
}

export default function App() {
  if (window.location.pathname === "/visualization-compare/echarts") {
    return (
      <I18nProvider>
        <Suspense fallback={<RouteLoading operation="Loading ECharts comparison" />}>
          <EChartsComparisonEmbed />
        </Suspense>
      </I18nProvider>
    );
  }
  return (
    <I18nProvider>
      {IS_PUBLIC_STORY ? (
        <Suspense fallback={<RouteLoading operation="Loading Team Share" />}>
          <TeamShareStory />
        </Suspense>
      ) : (
        <AuthProvider>
          <DisplayScopedRouter />
        </AuthProvider>
      )}
    </I18nProvider>
  );
}

function DisplayScopedRouter() {
  const { user } = useAuth();
  const scope = user?.user_id ?? "guest";
  return (
    <DisplayPreferencesProvider key={scope} scope={scope}>
      <Suspense fallback={<RouteLoading operation="Loading Ontology Dashboard" />}>
        <AppRouter />
      </Suspense>
    </DisplayPreferencesProvider>
  );
}
