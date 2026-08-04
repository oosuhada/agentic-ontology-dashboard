import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import {
  matchAgentPath,
  matchAnalysisPath,
  matchDatasetCatalogPath,
  matchGovernancePath,
  matchOntologyPath,
  navigate,
  usePathname,
} from "./routing";
import { getProjectWorkspaces } from "./api";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { LoginPage } from "./features/auth/LoginPage";
import { PendingPage } from "./features/auth/PendingPage";
import { RegisterPage } from "./features/auth/RegisterPage";

const AdminApp = lazy(() =>
  import("./features/admin/AdminApp").then((module) => ({ default: module.AdminApp })),
);
const ManufacturingApp = lazy(() =>
  import("./features/manufacturing/ManufacturingApp").then((module) => ({ default: module.ManufacturingApp })),
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

function Redirect({ to }: { to: string }) {
  useEffect(() => navigate(to, { replace: true }), [to]);
  return <div className="route-loading">화면을 이동하고 있습니다.</div>;
}

function ScopedWorkbenchRoute({
  projectId,
  workspaceId,
  requiredPermission,
  children,
}: {
  projectId: string;
  workspaceId: string;
  requiredPermission: string;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const fallback = `/app/projects/${encodeURIComponent(user?.active_project_id ?? user?.project_scopes[0] ?? "")}`;

  useEffect(() => {
    let cancelled = false;
    if (!user || !user.project_scopes.includes(projectId) || !user.workspace_scopes.includes(workspaceId) || !user.permissions.includes(requiredPermission)) {
      setAllowed(false);
      return () => { cancelled = true; };
    }
    setAllowed(null);
    getProjectWorkspaces(projectId)
      .then((items) => {
        if (!cancelled) setAllowed(items.some((item) => item.id === workspaceId));
      })
      .catch(() => {
        if (!cancelled) setAllowed(false);
      });
    return () => { cancelled = true; };
  }, [projectId, requiredPermission, user, workspaceId]);

  if (allowed === null) return <div className="route-loading"><div className="spinner" /><p>Project scope를 검증하고 있습니다.</p></div>;
  if (!allowed) return <Redirect to={fallback} />;
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

  if (loading) {
    return <div className="route-loading"><div className="spinner" /><p>세션을 확인하고 있습니다.</p></div>;
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
  const datasetRoute = matchDatasetCatalogPath(pathname);
  if (datasetRoute) {
    if (!user.project_scopes.includes(datasetRoute.projectId) || !user.permissions.includes("datasets.read")) {
      return <Redirect to={`/app/projects/${encodeURIComponent(user.active_project_id ?? user.project_scopes[0] ?? "")}`} />;
    }
    return (
      <Suspense fallback={<div className="route-loading"><div className="spinner" /><p>Dataset Catalog를 불러오고 있습니다.</p></div>}>
        <DatasetCatalogPage projectId={datasetRoute.projectId} />
      </Suspense>
    );
  }
  const agentRoute = matchAgentPath(pathname);
  if (agentRoute) {
    return (
      <ScopedWorkbenchRoute
        projectId={agentRoute.projectId}
        workspaceId={agentRoute.workspaceId}
        requiredPermission="planner.object_query"
      >
        <Suspense fallback={<div className="route-loading"><div className="spinner" /><p>Agent Evidence Workbench를 불러오고 있습니다.</p></div>}>
          <AgentWorkbenchPage projectId={agentRoute.projectId} workspaceId={agentRoute.workspaceId} />
        </Suspense>
      </ScopedWorkbenchRoute>
    );
  }
  const governanceRoute = matchGovernancePath(pathname);
  if (governanceRoute) {
    return (
      <ScopedWorkbenchRoute
        projectId={governanceRoute.projectId}
        workspaceId={governanceRoute.workspaceId}
        requiredPermission="governance.read"
      >
        <Suspense fallback={<div className="route-loading"><div className="spinner" /><p>Governance Workbench를 불러오고 있습니다.</p></div>}>
          <GovernanceWorkbenchPage projectId={governanceRoute.projectId} workspaceId={governanceRoute.workspaceId} />
        </Suspense>
      </ScopedWorkbenchRoute>
    );
  }
  const ontologyRoute = matchOntologyPath(pathname);
  if (ontologyRoute) {
    return (
      <ScopedWorkbenchRoute
        projectId={ontologyRoute.projectId}
        workspaceId={ontologyRoute.workspaceId}
        requiredPermission="ontology.objects.read"
      >
        <Suspense fallback={<div className="route-loading"><div className="spinner" /><p>Ontology Workbench를 불러오고 있습니다.</p></div>}>
          <OntologyPreviewPage projectId={ontologyRoute.projectId} workspaceId={ontologyRoute.workspaceId} />
        </Suspense>
      </ScopedWorkbenchRoute>
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
    <AuthProvider>
      <Suspense fallback={<div className="route-loading"><div className="spinner" /><p>애플리케이션 화면을 불러오고 있습니다.</p></div>}>
        <AppRouter />
      </Suspense>
    </AuthProvider>
  );
}
