import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bell,
  Bot,
  ChevronRight,
  Database,
  Home,
  LayoutDashboard,
  Menu,
  Moon,
  Network,
  Search,
  ShieldCheck,
  Sun,
  Workflow,
} from "lucide-react";
import { getProject, getProjectWorkspaces } from "../../api";
import { featureFlags } from "../../featureFlags";
import {
  agentPath,
  analysisPath,
  datasetCatalogPath,
  governancePath,
  navigate,
  ontologyPath,
  projectDashboardPath,
  projectHomePath,
} from "../../routing";
import { useAuth } from "../../features/auth/AuthContext";
import type { AppRole, Project, Workspace } from "../../types";
import { DisplayMenu } from "./DisplayMenu";
import { FoundryDialog } from "./FoundryDialog";
import { FoundryProductNavigation } from "./FoundryProductNavigation";

export type FoundryRoute = "home" | "dashboard" | "analysis" | "agent" | "ontology" | "datasets" | "governance";

interface FoundryAppShellProps {
  projectId: string;
  workspaceId?: string;
  activeRoute: FoundryRoute;
  title: string;
  children: ReactNode;
}

const ROLE_LABELS: Record<AppRole, string> = {
  tenant_admin: "조직 관리자",
  executive_viewer: "임원 Viewer",
  process_manager: "운영 매니저",
  process_engineer: "도메인 엔지니어",
  maintenance_technician: "현장 작업자",
  quality_auditor: "품질·감사 Viewer",
  ml_validator: "데이터 사이언티스트",
  fde: "Forward Deployed Engineer",
};

const NAV_ITEMS = [
  { id: "home", label: "Project Home", icon: Home, enabled: true },
  { id: "dashboard", label: "Dashboards", icon: LayoutDashboard, enabled: true },
  { id: "analysis", label: "Analysis", icon: Workflow, enabled: true },
  { id: "agent", label: "Agent", icon: Bot, enabled: true },
  { id: "ontology", label: "Ontology", icon: Network, enabled: featureFlags.ontologyWorkbench },
  { id: "datasets", label: "Datasets", icon: Database, enabled: featureFlags.datasetCatalog },
  { id: "governance", label: "Governance", icon: ShieldCheck, enabled: featureFlags.governanceWorkbench },
] as const;

function initialTheme(): "light" | "dark" {
  const saved = window.localStorage.getItem("ontology-dashboard-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function FoundryAppShell({ projectId, workspaceId, activeRoute, title, children }: FoundryAppShellProps) {
  const { user, logout } = useAuth();
  if (!user) throw new Error("FoundryAppShell requires an authenticated user");

  const [project, setProject] = useState<Project | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(initialTheme);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getProject(projectId), getProjectWorkspaces(projectId)])
      .then(([nextProject, nextWorkspaces]) => {
        if (cancelled) return;
        setProject(nextProject);
        setWorkspaces(nextWorkspaces);
      })
      .catch(() => {
        if (cancelled) return;
        setProject(null);
        setWorkspaces([]);
      });
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("ontology-dashboard-theme", theme);
  }, [theme]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((current) => !current);
      }
      if (event.key === "Escape") {
        setCommandOpen(false);
        setMobileNavOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const selectedWorkspace = useMemo(
    () => workspaces.find((item) => item.id === workspaceId) ?? workspaces[0] ?? null,
    [workspaceId, workspaces],
  );
  const resolvedWorkspaceId = workspaceId ?? selectedWorkspace?.id ?? "";
  const activeRole = user.active_project_roles[0] as AppRole | undefined;
  const roleLabel = activeRole ? ROLE_LABELS[activeRole] : user.is_admin ? ROLE_LABELS.tenant_admin : "Project member";

  function routeFor(route: FoundryRoute) {
    if (route === "home") return projectHomePath(projectId);
    if (route === "dashboard") return projectDashboardPath(projectId);
    if (route === "analysis") return analysisPath("risk-event-portfolio");
    if (route === "datasets") return datasetCatalogPath(projectId);
    if (!resolvedWorkspaceId) return projectHomePath(projectId);
    if (route === "agent") return agentPath(projectId, resolvedWorkspaceId);
    if (route === "ontology") return ontologyPath(projectId, resolvedWorkspaceId);
    return governancePath(projectId, resolvedWorkspaceId);
  }

  function openRoute(route: FoundryRoute) {
    setMobileNavOpen(false);
    setCommandOpen(false);
    navigate(routeFor(route));
  }

  async function signOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className={`od-product-shell fd-route-shell route-${activeRoute} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <FoundryProductNavigation
        items={NAV_ITEMS.map((item) => ({
          ...item,
          enabled: item.enabled && (!(item.id === "agent" || item.id === "ontology" || item.id === "governance") || Boolean(resolvedWorkspaceId)),
        }))}
        activeId={activeRoute}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileNavOpen}
        projectName={project?.display_name ?? projectId}
        workspaceName={selectedWorkspace?.display_name ?? resolvedWorkspaceId ?? "Project scope"}
        userName={user.display_name}
        roleLabel={roleLabel}
        isAdmin={user.is_admin}
        onNavigate={(id) => openRoute(id as FoundryRoute)}
        onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        onAdmin={() => navigate("/admin")}
        onLogout={() => void signOut()}
      />

      <div className="od-shell-main fd-route-shell__main">
        <header className="od-global-topbar">
          <button type="button" className="od-mobile-menu" aria-label="Product navigation 열기" onClick={() => setMobileNavOpen((current) => !current)}><Menu size={17} /></button>
          <div className="od-breadcrumbs">
            <span>{project?.display_name ?? projectId}</span><ChevronRight size={12} />
            {selectedWorkspace ? <><span>{selectedWorkspace.display_name}</span><ChevronRight size={12} /></> : null}
            <strong>{title}</strong>
          </div>
          <button type="button" className="od-global-search" onClick={() => setCommandOpen(true)}><Search size={14} /><span>Search objects, datasets, actions…</span><kbd>⌘K</kbd></button>
          <div className="od-topbar-actions">
            <DisplayMenu />
            <button type="button" title="테마 전환" onClick={() => setTheme((current) => current === "light" ? "dark" : "light")}>{theme === "light" ? <Moon size={15} /> : <Sun size={15} />}</button>
            <button type="button" title="알림"><Bell size={15} /></button>
            <div className="od-user-identity"><span>{user.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.display_name}</strong><small>{roleLabel}</small></div></div>
          </div>
        </header>
        <div className="fd-route-shell__content">{children}</div>
      </div>

      {mobileNavOpen ? <button type="button" className="od-mobile-backdrop" aria-label="내비게이션 닫기" onClick={() => setMobileNavOpen(false)} /> : null}
      {commandOpen ? (
        <FoundryDialog ariaLabel="Command palette" overlayClassName="command-palette-overlay" dialogClassName="command-palette" onClose={() => setCommandOpen(false)}>
            <header><div><span className="section-label">COMMAND PALETTE</span><strong>Navigate workbenches</strong></div><kbd>ESC</kbd></header>
            <div className="command-search"><Search size={15} /><input data-dialog-initial-focus placeholder="Object, Dataset 또는 Workbench 검색" /></div>
            <div className="command-group"><span>Project resources</span>
              {NAV_ITEMS.filter((item) => item.enabled).map((item) => {
                const Icon = item.icon;
                return <button type="button" key={item.id} onClick={() => openRoute(item.id)}><b><Icon size={14} /></b><div><strong>{item.label}</strong><small>{routeFor(item.id)}</small></div></button>;
              })}
            </div>
        </FoundryDialog>
      ) : null}
    </div>
  );
}
