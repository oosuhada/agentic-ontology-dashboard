import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import {
  matchAgentPath,
  matchAnalysisPath,
  matchDatasetCatalogPath,
  matchGovernancePath,
  matchModelingPath,
  matchOntologyPath,
  matchProjectDashboardPath,
  matchProjectHomePath,
  navigate,
  usePathname,
} from "./routing";
import { ApiError, getProject, getProjectWorkspaces } from "./api";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { LoginPage } from "./features/auth/LoginPage";
import { PendingPage } from "./features/auth/PendingPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { DisplayPreferencesProvider } from "./ui/foundry/displayPreferences";
import { I18nProvider } from "./ui/i18n/I18nProvider";
import { FoundryAppShell } from "./ui/foundry/FoundryAppShell";
import { WorkbenchState } from "./ui/foundry/WorkbenchState";

const AdminApp = lazy(() =>
  import("./features/admin/AdminApp").then((module) => ({ default: module.AdminApp })),
);
const ManufacturingApp = lazy(() =>
  import("./features/manufacturing/ManufacturingApp").then((module) => ({ default: module.ManufacturingApp })),
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

const LAST_VALID_PROJECT_KEY = "ontology-dashboard:last-valid-project";
const IS_PUBLIC_STORY = import.meta.env.VITE_PUBLIC_STORY === "1";

function RouteLoading({ operation, detail }: { operation: string; detail?: string }) {
  return (
    <div className="route-loading">
      <WorkbenchState kind="loading" title={operation} detail={detail} />
    </div>
  );
}

function Redirect({ to }: { to: string }) {
  useEffect(() => navigate(to, { replace: true }), [to]);
  return <RouteLoading operation="Opening governed workspace" />;
}

function ProjectRouteBoundary({
  projectId,
  workspaceId,
  requiredPermission,
  children,
}: {
  projectId: string;
  workspaceId?: string;
  requiredPermission?: string;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const [state, setState] = useState<"allowed" | "denied" | "tombstone" | null>(null);
  const lastValidProjectId = window.sessionStorage.getItem(LAST_VALID_PROJECT_KEY);
  const fallbackProjectId = lastValidProjectId && user?.project_scopes.includes(lastValidProjectId)
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
        if (reason instanceof ApiError && reason.code === "project_not_found") setState("tombstone");
        else setState("denied");
      });
    return () => { cancelled = true; };
  }, [projectId, requiredPermission, user, workspaceId]);

  if (state === null) {
    return <RouteLoading operation="Validating Project scope" detail="Checking workspace membership and permissions." />;
  }
  if (state === "tombstone") return <ProjectTombstonePage projectId={projectId} />;
  if (state === "denied") return <Redirect to={fallback} />;
  return <>{children}</>;
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

  if (loading) {
    return <RouteLoading operation="Checking session" detail="Resolving identity and governed scope." />;
  }

  if (!user) {
    if (pathname === "/register") return <RegisterPage />;
    if (pathname === "/pending") return <PendingPage />;
    if (pathname !== "/login" && pathname !== "/") return <Redirect to="/login" />;
    return <LoginPage />;
  }

  if (pathname === "/admin") return user.is_admin ? <AdminApp /> : <ForbiddenPage />;

  const analysisId = matchAnalysisPath(pathname);
  if (analysisId) return <ManufacturingApp initialWorkspaceView="analysis" analysisId={analysisId} />;

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
        <Suspense fallback={<RouteLoading operation="Loading Dataset Catalog" detail="Resolving immutable versions and lineage." />}>
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
        <Suspense fallback={<RouteLoading operation="Loading ML Validator Workbench" detail="Resolving experiment, registry, and release artifacts." />}>
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
        <Suspense fallback={<RouteLoading operation="Loading Ontology Object Explorer" detail="Resolving governed objects and links." />}>
          <FoundryAppShell projectId={ontologyRoute.projectId} workspaceId={ontologyRoute.workspaceId} activeRoute="ontology" title="Ontology Object Explorer">
            <OntologyPreviewPage projectId={ontologyRoute.projectId} workspaceId={ontologyRoute.workspaceId} />
          </FoundryAppShell>
        </Suspense>
      </ProjectRouteBoundary>
    );
  }

  const projectDashboardRoute = matchProjectDashboardPath(pathname);
  if (projectDashboardRoute) {
    return (
      <ProjectRouteBoundary projectId={projectDashboardRoute.projectId}>
        <ManufacturingApp />
      </ProjectRouteBoundary>
    );
  }

  if (pathname === "/app" || pathname.startsWith("/app/")) return <ManufacturingApp />;
  if (pathname === "/login" || pathname === "/register" || pathname === "/pending" || pathname === "/") {
    return <Redirect to={user.default_path} />;
  }
  return <Redirect to={user.default_path} />;
}

export default function App() {
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
