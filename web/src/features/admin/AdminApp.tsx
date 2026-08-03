import { useEffect, useMemo, useState } from "react";
import {
  getAdminAudit,
  getAdminOverview,
  getAdminRoles,
  getAdminUsers,
  getAdminWorkspaces,
  updateAdminUser,
  type AdminOverview,
} from "../../api";
import { navigate } from "../../routing";
import type { AdminAuditEntry, AdminUser, AppRole, RoleDefinition, UserStatus, Workspace } from "../../types";
import { useAuth } from "../auth/AuthContext";

type AdminTab = "overview" | "users" | "roles" | "audit";

function UserAccessRow({
  user,
  roles,
  workspaces,
  currentUserId,
  onSaved,
}: {
  user: AdminUser;
  roles: RoleDefinition[];
  workspaces: Workspace[];
  currentUserId: string;
  onSaved: () => Promise<void>;
}) {
  const [status, setStatus] = useState<UserStatus>(user.status);
  const [role, setRole] = useState<AppRole | "">(user.roles[0] ?? "");
  const [scope, setScope] = useState(user.workspace_scopes[0] ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setStatus(user.status);
    setRole(user.roles[0] ?? "");
    setScope(user.workspace_scopes[0] ?? "");
  }, [user]);

  async function save(nextStatus = status) {
    setSaving(true);
    setMessage("");
    try {
      await updateAdminUser(user.id, {
        status: nextStatus,
        roles: role ? [role] : [],
        workspace_scopes: scope ? [scope] : [],
      });
      setStatus(nextStatus);
      setMessage("저장됨");
      await onSaved();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr>
      <td>
        <strong>{user.display_name}</strong>
        <small>{user.email}</small>
        {user.requested_organization_name ? <small>요청 조직 · {user.requested_organization_name}</small> : null}
      </td>
      <td><span className={`account-status status-${user.status}`}>{user.status}</span></td>
      <td>
        <select aria-label={`${user.email} 역할`} value={role} onChange={(event) => setRole(event.target.value as AppRole)} disabled={user.id === currentUserId}>
          <option value="">역할 없음</option>
          {roles.map((item) => <option key={item.code} value={item.code}>{item.display_name}</option>)}
        </select>
      </td>
      <td>
        <select aria-label={`${user.email} workspace`} value={scope} onChange={(event) => setScope(event.target.value)}>
          <option value="">scope 없음</option>
          {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.display_name}</option>)}
        </select>
      </td>
      <td className="admin-actions-cell">
        {user.status === "pending_approval" ? (
          <button className="primary compact-button" disabled={saving || !role || !scope} onClick={() => save("active")}>승인</button>
        ) : null}
        {user.status === "active" && user.id !== currentUserId ? (
          <button className="secondary compact-button" disabled={saving} onClick={() => save("disabled")}>비활성화</button>
        ) : null}
        {user.status === "disabled" ? (
          <button className="secondary compact-button" disabled={saving || !role || !scope} onClick={() => save("active")}>재활성화</button>
        ) : null}
        <button className="secondary compact-button" disabled={saving} onClick={() => save()}>저장</button>
        {message ? <small className={message === "저장됨" ? "save-success" : "save-error"}>{message}</small> : null}
      </td>
    </tr>
  );
}

export function AdminApp() {
  const { user, logout } = useAuth();
  if (!user) throw new Error("AdminApp requires an authenticated user");

  const [tab, setTab] = useState<AdminTab>("overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [audit, setAudit] = useState<AdminAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextUsers, nextRoles, nextWorkspaces, nextAudit] = await Promise.all([
        getAdminOverview(),
        getAdminUsers(),
        getAdminRoles(),
        getAdminWorkspaces(),
        getAdminAudit(),
      ]);
      setOverview(nextOverview);
      setUsers(nextUsers);
      setRoles(nextRoles);
      setWorkspaces(nextWorkspaces);
      setAudit(nextAudit);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "관리자 데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const roleCounts = useMemo(() => roles.map((role) => ({
    ...role,
    count: users.filter((item) => item.roles.includes(role.code)).length,
  })), [roles, users]);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="brand admin-brand">
          <span className="brand-mark">OD</span>
          <div><strong>Ontology Dashboard</strong><small>Administrator control plane</small></div>
        </div>
        <nav className="admin-nav" aria-label="관리자 메뉴">
          <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>Overview</button>
          <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>Users</button>
          <button className={tab === "roles" ? "active" : ""} onClick={() => setTab("roles")}>Roles & Permissions</button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>Audit Logs</button>
        </nav>
        <div className="admin-boundary-note">
          <strong>FDE ≠ Tenant Admin</strong>
          <p>FDE는 ontology와 template을 구축하지만 사용자 계정과 보안 정책을 임의로 관리할 수 없습니다.</p>
        </div>
        <div className="sidebar-user">
          <div><strong>{user.display_name}</strong><small>{user.email}</small></div>
          <button onClick={() => navigate("/app")}>사용자 앱</button>
          <button onClick={handleLogout}>로그아웃</button>
        </div>
      </aside>

      <main className="admin-main">
        <header className="admin-topbar">
          <div><span className="eyebrow">TENANT ADMIN</span><h1>{tab === "overview" ? "관리자 Overview" : tab === "users" ? "사용자 승인과 접근 범위" : tab === "roles" ? "역할과 권한 경계" : "관리자 변경 감사"}</h1></div>
          <button className="secondary" onClick={load}>새로고침</button>
        </header>

        {error ? <div className="error-panel" role="alert"><strong>관리자 API 오류</strong><p>{error}</p></div> : null}
        {loading ? <div className="loading-panel"><div className="spinner" /><p>관리자 데이터를 불러오고 있습니다.</p></div> : null}

        {!loading && tab === "overview" && overview ? (
          <>
            <section className="admin-metrics">
              <article><span>활성 사용자</span><strong>{overview.active_users}</strong></article>
              <article><span>승인 대기</span><strong>{overview.pending_users}</strong></article>
              <article><span>비활성 사용자</span><strong>{overview.disabled_users}</strong></article>
              <article><span>Workspace</span><strong>{overview.workspace_count}</strong></article>
            </section>
            <section className="admin-card">
              <div className="admin-card-header"><div><span className="eyebrow">RECENT CHANGES</span><h2>최근 관리자 변경</h2></div><button className="link-button" onClick={() => setTab("audit")}>전체 보기</button></div>
              {overview.recent_admin_changes.length ? (
                <div className="audit-list">{overview.recent_admin_changes.map((entry) => <div key={entry.id}><strong>{entry.action}</strong><span>{entry.actor_email} → {entry.target_email ?? "system"}</span><time>{new Date(entry.created_at).toLocaleString()}</time></div>)}</div>
              ) : <p className="empty-state">아직 관리자 변경 기록이 없습니다.</p>}
            </section>
          </>
        ) : null}

        {!loading && tab === "users" ? (
          <section className="admin-card admin-table-card">
            <div className="admin-card-header"><div><span className="eyebrow">IDENTITY & SCOPE</span><h2>가입 승인·역할·Workspace scope</h2></div><span>{users.length} accounts</span></div>
            <div className="table-scroll"><table className="admin-user-table"><thead><tr><th>사용자</th><th>상태</th><th>역할</th><th>Workspace scope</th><th>작업</th></tr></thead><tbody>
              {users.map((item) => <UserAccessRow key={item.id} user={item} roles={roles} workspaces={workspaces} currentUserId={user.user_id} onSaved={load} />)}
            </tbody></table></div>
          </section>
        ) : null}

        {!loading && tab === "roles" ? (
          <section className="role-registry-grid">
            {roleCounts.map((role) => (
              <article className={`admin-card role-registry-card ${role.code === "tenant_admin" ? "admin-role" : role.code === "fde" ? "fde-role" : ""}`} key={role.code}>
                <span className="eyebrow">{role.code}</span><h2>{role.display_name}</h2><p>{role.description}</p><strong>{role.count}명</strong>
                {role.code === "fde" ? <small>사용자·비밀번호·보안 정책 관리 권한 없음</small> : null}
                {role.code === "tenant_admin" ? <small>가입 승인·역할·scope와 관리자 감사 권한</small> : null}
              </article>
            ))}
          </section>
        ) : null}

        {!loading && tab === "audit" ? (
          <section className="admin-card admin-table-card">
            <div className="admin-card-header"><div><span className="eyebrow">IMMUTABLE ADMIN HISTORY</span><h2>역할·상태·Scope 변경</h2></div><span>{audit.length} records</span></div>
            <div className="table-scroll"><table><thead><tr><th>시각</th><th>행동</th><th>관리자</th><th>대상</th><th>변경 후</th></tr></thead><tbody>
              {audit.map((entry) => <tr key={entry.id}><td>{new Date(entry.created_at).toLocaleString()}</td><td>{entry.action}</td><td>{entry.actor_email}</td><td>{entry.target_email ?? "—"}</td><td><code>{JSON.stringify(entry.after)}</code></td></tr>)}
            </tbody></table></div>
          </section>
        ) : null}
      </main>
    </div>
  );
}
