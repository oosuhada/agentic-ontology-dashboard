import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { ApiError, getProject, getProjectWorkspaces } from "./api";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { LoginPage } from "./features/auth/LoginPage";
import { loginPath, matchMvpProjectPath, mvpProjectPath, navigate, usePathname } from "./routing";

const MvpApplication = lazy(() => import("./features/mvp/MvpApplication"));
const DEFAULT_PROJECT_ID = "manufacturing-demo-project";

function RouteLoading({ label }: { label: string }) {
  return <main className="route-loading" aria-live="polite"><span className="route-spinner" />{label}</main>;
}

function Redirect({ to }: { to: string }) {
  useEffect(() => navigate(to, { replace: true }), [to]);
  return <RouteLoading label="화면을 여는 중…" />;
}

function ProjectBoundary({ projectId, children }: { projectId: string; children: ReactNode }) {
  const { user } = useAuth();
  const [state, setState] = useState<"checking" | "allowed" | "denied">("checking");

  useEffect(() => {
    let cancelled = false;
    if (!user || (!user.is_admin && !user.project_scopes.includes(projectId))) {
      setState("denied");
      return;
    }
    setState("checking");
    Promise.all([getProject(projectId), getProjectWorkspaces(projectId)])
      .then(([, workspaces]) => {
        if (!cancelled) setState(workspaces.length ? "allowed" : "denied");
      })
      .catch(() => !cancelled && setState("denied"));
    return () => { cancelled = true; };
  }, [projectId, user]);

  if (state === "checking") return <RouteLoading label="Project 권한을 확인하는 중…" />;
  if (state === "denied") return <Redirect to={mvpProjectPath(user?.active_project_id ?? DEFAULT_PROJECT_ID)} />;
  return <>{children}</>;
}

function AppRouter() {
  const pathname = usePathname();
  const { user, loading } = useAuth();

  if (loading) return <RouteLoading label="로그인 상태를 확인하는 중…" />;
  if (!user) {
    if (pathname !== "/login" && pathname !== "/") {
      return <Redirect to={loginPath(`${pathname}${window.location.search}`)} />;
    }
    return <LoginPage />;
  }

  const mvpRoute = matchMvpProjectPath(pathname);
  if (mvpRoute) {
    return (
      <ProjectBoundary projectId={mvpRoute.projectId}>
        <Suspense fallback={<RouteLoading label="MVP 업무 화면을 불러오는 중…" />}>
          <MvpApplication projectId={mvpRoute.projectId} />
        </Suspense>
      </ProjectBoundary>
    );
  }

  return <Redirect to={mvpProjectPath(user.active_project_id ?? DEFAULT_PROJECT_ID)} />;
}

export default function App() {
  return <AuthProvider><AppRouter /></AuthProvider>;
}
