import { useEffect } from "react";
import { matchAnalysisPath, navigate, usePathname } from "./routing";
import { AdminApp } from "./features/admin/AdminApp";
import { AuthProvider, useAuth } from "./features/auth/AuthContext";
import { LoginPage } from "./features/auth/LoginPage";
import { PendingPage } from "./features/auth/PendingPage";
import { RegisterPage } from "./features/auth/RegisterPage";
import { ManufacturingApp } from "./features/manufacturing/ManufacturingApp";

function Redirect({ to }: { to: string }) {
  useEffect(() => navigate(to, { replace: true }), [to]);
  return <div className="route-loading">화면을 이동하고 있습니다.</div>;
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
  if (pathname === "/app" || pathname.startsWith("/app/")) return <ManufacturingApp />;
  if (pathname === "/login" || pathname === "/register" || pathname === "/pending" || pathname === "/") {
    return <Redirect to={user.default_path} />;
  }
  return <Redirect to={user.default_path} />;
}

export default function App() {
  return <AuthProvider><AppRouter /></AuthProvider>;
}
