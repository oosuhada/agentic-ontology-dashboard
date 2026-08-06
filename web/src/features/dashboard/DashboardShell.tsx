import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bell,
  Bot,
  Blocks,
  ChevronRight,
  Command,
  Database,
  Download,
  Eye,
  Home,
  LayoutDashboard,
  Maximize2,
  Menu,
  Moon,
  Network,
  Plus,
  Redo2,
  RotateCcw,
  Undo2,
  Save,
  Search,
  Settings,
  Share2,
  ShieldCheck,
  Sparkles,
  Sun,
  Workflow,
} from "lucide-react";
import { featureFlags } from "../../featureFlags";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchHeader, WorkbenchToolbar } from "../../ui/foundry/WorkbenchChrome";
import { FoundryProductNavigation } from "../../ui/foundry/FoundryProductNavigation";
import { agentPath, datasetCatalogPath, governancePath, navigate, ontologyPath, projectHomePath } from "../../routing";
import type { AppRole, AuthUser, DomainPack, Project, Workspace } from "../../types";
import type { DashboardMode, DashboardTab } from "./types";

export type WorkspaceView = "dashboard" | "analysis";

interface DashboardShellProps {
  user: AuthUser;
  roleLabel: string;
  roleEyebrow: string;
  roleDescription: string;
  roleFocus: string[];
  projects: Project[];
  selectedProjectId: string;
  workspaces: Workspace[];
  selectedWorkspaceId: string;
  domainPack: DomainPack | undefined;
  tabs: DashboardTab[];
  activeTabId: string;
  templateVersion: number;
  preferenceRevision: number;
  layoutMode: string | null;
  mode: DashboardMode;
  dirty: boolean;
  saving: boolean;
  exporting: boolean;
  notice: string;
  error: string;
  canManageTemplates: boolean;
  templateActionLabel: string;
  targetTemplateRole: AppRole;
  availableRoles: AppRole[];
  activeRole: AppRole;
  contextPanel: ReactNode;
  boardCanvas: ReactNode;
  inspector: ReactNode;
  catalog: ReactNode;
  analysisWorkbench: ReactNode;
  draftRecovery?: ReactNode;
  canUndo: boolean;
  canRedo: boolean;
  initialWorkspaceView?: WorkspaceView;
  onWorkspaceViewChange?: (view: WorkspaceView) => void;
  onProjectChange: (projectId: string) => void;
  onWorkspaceChange: (workspaceId: string) => void;
  onActiveTabChange: (tabId: string) => void;
  onReorderTabs: (sourceId: string, targetId: string) => void;
  onModeChange: (mode: DashboardMode) => void;
  onUndo: () => void;
  onRedo: () => void;
  onOpenCatalog: () => void;
  onAddTab: () => void;
  onSave: () => void;
  onRestore: () => void;
  onSaveView: () => void;
  onShare: () => void;
  onExport: (format: "json" | "csv" | "pdf") => void;
  onPublishTemplate: () => void;
  onTargetTemplateRoleChange: (role: AppRole) => void;
  onActiveRoleChange: (role: AppRole) => void;
  onDismissNotice: () => void;
  onRetry: () => void;
  onAdmin: () => void;
  onLogout: () => void;
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

const TEMPLATE_ROLES: AppRole[] = [
  "tenant_admin",
  "executive_viewer",
  "process_manager",
  "process_engineer",
  "maintenance_technician",
  "quality_auditor",
  "ml_validator",
  "fde",
];

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

export function DashboardShell({
  user,
  roleLabel,
  roleEyebrow,
  roleFocus,
  projects,
  selectedProjectId,
  workspaces,
  selectedWorkspaceId,
  domainPack,
  tabs,
  activeTabId,
  templateVersion,
  preferenceRevision,
  layoutMode,
  mode,
  dirty,
  saving,
  exporting,
  notice,
  error,
  canManageTemplates,
  templateActionLabel,
  targetTemplateRole,
  availableRoles,
  activeRole,
  contextPanel,
  boardCanvas,
  inspector,
  catalog,
  analysisWorkbench,
  draftRecovery,
  canUndo,
  canRedo,
  initialWorkspaceView = "dashboard",
  onWorkspaceViewChange,
  onProjectChange,
  onWorkspaceChange,
  onActiveTabChange,
  onReorderTabs,
  onModeChange,
  onUndo,
  onRedo,
  onOpenCatalog,
  onAddTab,
  onSave,
  onRestore,
  onSaveView,
  onShare,
  onExport,
  onPublishTemplate,
  onTargetTemplateRoleChange,
  onActiveRoleChange,
  onDismissNotice,
  onRetry,
  onAdmin,
  onLogout,
}: DashboardShellProps) {
  const [draggingTabId, setDraggingTabId] = useState<string | null>(null);
  const [exportFormat, setExportFormat] = useState<"json" | "csv" | "pdf">("pdf");
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>(initialWorkspaceView);
  const [density, setDensity] = useState<"compact" | "comfortable">("compact");
  const [commandOpen, setCommandOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(initialTheme);

  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedProjectId), [projects, selectedProjectId]);
  const selectedWorkspace = useMemo(() => workspaces.find((workspace) => workspace.id === selectedWorkspaceId), [selectedWorkspaceId, workspaces]);
  const activeTab = useMemo(() => tabs.find((tab) => tab.id === activeTabId), [activeTabId, tabs]);

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
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (dirty && !saving) onSave();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) {
          if (canRedo) onRedo();
        } else if (canUndo) onUndo();
      }
      if (event.key === "Escape") {
        setCommandOpen(false);
        setMobileNavOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [canRedo, canUndo, dirty, onRedo, onSave, onUndo, saving]);

  function runCommand(action: () => void) {
    action();
    setCommandOpen(false);
  }

  function openWorkspace(next: WorkspaceView) {
    setWorkspaceView(next);
    setMobileNavOpen(false);
    onWorkspaceViewChange?.(next);
  }

  function openProductView(itemId: (typeof NAV_ITEMS)[number]["id"]) {
    if (itemId === "home") {
      navigate(projectHomePath(selectedProjectId));
      return;
    }
    if (itemId === "dashboard" || itemId === "analysis") {
      openWorkspace(itemId);
      return;
    }
    setMobileNavOpen(false);
    if (itemId === "agent") {
      navigate(agentPath(selectedProjectId, selectedWorkspaceId));
      return;
    }
    if (itemId === "ontology") {
      navigate(ontologyPath(selectedProjectId, selectedWorkspaceId));
      return;
    }
    if (itemId === "datasets") {
      navigate(datasetCatalogPath(selectedProjectId));
      return;
    }
    if (itemId === "governance") {
      navigate(governancePath(selectedProjectId, selectedWorkspaceId));
    }
  }

  return (
    <div className={`ontology-dashboard-shell od-product-shell mode-${mode} role-${user.landing_key} density-${density} workspace-${workspaceView} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <FoundryProductNavigation
        items={NAV_ITEMS}
        activeId={workspaceView}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileNavOpen}
        projectName={selectedProject?.display_name ?? "Project"}
        workspaceName={selectedWorkspace?.display_name ?? "Workspace"}
        userName={user.display_name}
        roleLabel={roleLabel}
        isAdmin={user.is_admin}
        onNavigate={(id) => openProductView(id as (typeof NAV_ITEMS)[number]["id"])}
        onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        onAdmin={onAdmin}
        onLogout={onLogout}
      />

      <div className="od-shell-main">
        <header className="od-global-topbar">
          <button type="button" className="od-mobile-menu" aria-label="Product navigation 열기" onClick={() => setMobileNavOpen((current) => !current)}><Menu size={17} /></button>
          <div className="od-breadcrumbs">
            <span>{selectedProject?.display_name ?? "Project"}</span><ChevronRight size={12} />
            <span>{selectedWorkspace?.display_name ?? "Workspace"}</span><ChevronRight size={12} />
            <strong>{workspaceView === "dashboard" ? activeTab?.title ?? "Dashboard" : "Analysis Path"}</strong>
          </div>
          <button type="button" className="od-global-search" onClick={() => setCommandOpen(true)}><Search size={14} /><span>Search objects, boards, actions…</span><kbd>⌘K</kbd></button>
          <div className="od-topbar-actions">
            <button type="button" title="테마 전환" onClick={() => setTheme((current) => current === "light" ? "dark" : "light")}>{theme === "light" ? <Moon size={15} /> : <Sun size={15} />}</button>
            <button type="button" title="알림"><Bell size={15} /><i /></button>
            <div className="od-user-identity"><span>{user.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.display_name}</strong><small>{roleLabel}</small></div></div>
          </div>
        </header>

        <WorkbenchHeader
          className="od-context-header fd-dashboard-resource-header"
          title={<div className="od-context-title">
            <EntityTitle
              icon={workspaceView === "dashboard" ? LayoutDashboard : Workflow}
              eyebrow={workspaceView === "dashboard" ? `DASHBOARD · ${roleEyebrow}` : "ANALYSIS · GOVERNED PATH"}
              title={workspaceView === "dashboard" ? activeTab?.title ?? `${roleLabel} Operations` : "Risk Event Analysis Path"}
              subtitle={workspaceView === "dashboard"
                ? `${selectedProject?.display_name ?? "Project"} / ${selectedWorkspace?.display_name ?? "Workspace"} · ${roleLabel}`
                : `${selectedWorkspace?.display_name ?? "Workspace"} · Object set → transform → validate → publish`}
              trailing={<div className="fd-entity-title__trailing"><span className="od-domain-pack-name">{domainPack?.display_name ?? "Manufacturing Operations"}</span><StatusPill intent={dirty ? "warning" : "success"}>{dirty ? "Unsaved changes" : "Saved"}</StatusPill></div>}
            />
          </div>}
          actions={<div className="od-context-controls">
            <label>Project<select aria-label="Project" value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)}>{projects.map((project) => <option key={project.id} value={project.id}>{project.display_name}</option>)}</select></label>
            <label>Workspace<select aria-label="Workspace" value={selectedWorkspaceId} onChange={(event) => onWorkspaceChange(event.target.value)}>{workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.display_name}</option>)}</select></label>
            <label>Role<select aria-label="Role" value={activeRole} onChange={(event) => onActiveRoleChange(event.target.value as AppRole)}>{availableRoles.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}</select></label>
            <div className="workbench-switcher" role="group" aria-label="Workbench mode">
              <button type="button" className={workspaceView === "dashboard" ? "active" : ""} onClick={() => openWorkspace("dashboard")}><LayoutDashboard size={13} /> Dashboard</button>
              <button type="button" className={workspaceView === "analysis" ? "active" : ""} onClick={() => openWorkspace("analysis")}><Workflow size={13} /> Analysis</button>
            </div>
          </div>}
        />

        {draftRecovery}

        <section className="od-status-strip">
          <div className="role-focus-list">{roleFocus.map((item) => <span key={item}>{item}</span>)}</div>
          <div className="od-runtime-meta"><span>Template v{templateVersion}</span><span>Revision {preferenceRevision}</span>{layoutMode ? <span className={`mode-badge ${layoutMode.includes("fallback") ? "fallback" : ""}`}>{layoutMode}</span> : null}</div>
        </section>

        {workspaceView === "dashboard" ? (
          <WorkbenchToolbar
            className="dashboard-tab-toolbar od-workbench-toolbar"
            label="Dashboard tabs and actions"
            start={<nav className="dashboard-tabs" aria-label="Dashboard tabs">
              {tabs.filter((tab) => mode === "edit" || !tab.hidden).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={tab.id === activeTabId ? "active" : ""}
                  draggable={mode === "edit"}
                  onDragStart={() => setDraggingTabId(tab.id)}
                  onDragEnd={() => setDraggingTabId(null)}
                  onDragOver={(event) => mode === "edit" && event.preventDefault()}
                  onDrop={(event) => {
                    if (mode !== "edit" || !draggingTabId) return;
                    event.preventDefault();
                    onReorderTabs(draggingTabId, tab.id);
                    setDraggingTabId(null);
                  }}
                  onClick={() => onActiveTabChange(tab.id)}
                >
                  {tab.title}{tab.custom ? <small>PERSONAL</small> : null}
                </button>
              ))}
              {mode === "edit" ? <button type="button" className="add-tab-button" onClick={onAddTab}><Plus size={13} /> Tab</button> : null}
            </nav>}
            end={<div className="dashboard-edit-toolbar">
              <div className="view-edit-switch" role="group" aria-label="Dashboard mode">
                <button type="button" className={mode === "view" ? "active" : ""} onClick={() => onModeChange("view")}><Eye size={12} /> View</button>
                <button type="button" className={mode === "edit" ? "active" : ""} onClick={() => onModeChange("edit")}><Blocks size={12} /> Edit</button>
              </div>
              {mode === "edit" ? <>
                <button type="button" className="icon-button" aria-label="Undo dashboard edit" title="실행 취소 (⌘Z)" disabled={!canUndo} onClick={onUndo}><Undo2 size={13} /></button>
                <button type="button" className="icon-button" aria-label="Redo dashboard edit" title="다시 실행 (⌘⇧Z)" disabled={!canRedo} onClick={onRedo}><Redo2 size={13} /></button>
                <button type="button" className="secondary" aria-label="Board Catalog" onClick={onOpenCatalog}><Plus size={12} /> Add board</button>
              </> : null}
              <button type="button" className="secondary" aria-label="View 저장" onClick={onSaveView}><Sparkles size={12} /> Save view</button>
              <button type="button" className="secondary" aria-label="공유" onClick={onShare}><Share2 size={12} /> Share</button>
              <div className="dashboard-export-control"><select aria-label="Export 형식" value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "json" | "csv" | "pdf")}><option value="pdf">PDF</option><option value="csv">CSV</option><option value="json">JSON</option></select><button type="button" className="secondary" disabled={exporting} onClick={() => onExport(exportFormat)}><Download size={12} />{exporting ? "Exporting" : "Export"}</button></div>
              <button type="button" className="icon-button" title="역할 기본값 복원" onClick={onRestore}><RotateCcw size={13} /></button>
              <button type="button" className="primary" aria-label={saving ? "저장 중" : dirty ? "개인 설정 저장" : "저장됨"} disabled={!dirty || saving} onClick={onSave}><Save size={13} />{saving ? "Saving" : dirty ? "Save" : "Saved"}</button>
            </div>}
          />
        ) : null}

        {workspaceView === "dashboard" && canManageTemplates && mode === "edit" ? (
          <section className="template-publish-bar"><div><strong>Governed Template Editor</strong><span>현재 canvas를 선택 역할의 새 template version으로 게시합니다.</span></div><select value={targetTemplateRole} onChange={(event) => onTargetTemplateRoleChange(event.target.value as AppRole)}>{TEMPLATE_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}</select><button type="button" className="secondary" onClick={onPublishTemplate}>{templateActionLabel}</button></section>
        ) : null}

        {notice ? <div className="notice dashboard-notice" role="status"><span>{notice}</span><button onClick={onDismissNotice}>닫기</button></div> : null}
        {error ? <div className="error-panel dashboard-error" role="alert"><strong>Dashboard 오류</strong><p>{error}</p><button onClick={onRetry}>다시 불러오기</button></div> : null}

        <main className="od-workbench-main">
          {workspaceView === "dashboard" ? (
            <div className={`dashboard-workspace-layout ${mode === "edit" ? "with-inspector" : ""}`}>
              {contextPanel}
              <section className="dashboard-canvas-region">{boardCanvas}</section>
              {mode === "edit" ? inspector : null}
            </div>
          ) : <div className="analysis-workspace-region">{analysisWorkbench}</div>}
        </main>

        <footer className="footer-note">Ontology Dashboard · Organization → Project → Workspace → Role Dashboard · Object permissions and scope remain enforced.</footer>
        {workspaceView === "dashboard" ? catalog : null}
      </div>

      {mobileNavOpen ? <button type="button" className="od-mobile-backdrop" aria-label="내비게이션 닫기" onClick={() => setMobileNavOpen(false)} /> : null}

      {commandOpen ? (
        <div className="command-palette-overlay" role="presentation" onMouseDown={() => setCommandOpen(false)}>
          <section className="command-palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><span className="section-label">COMMAND PALETTE</span><strong>Navigate and execute</strong></div><kbd>ESC</kbd></header>
            <div className="command-search"><Search size={15} /><input autoFocus placeholder="명령, Object 또는 Board 검색" /></div>
            <div className="command-group"><span>Workspace</span>
              <button type="button" onClick={() => runCommand(() => openWorkspace("dashboard"))}><b><LayoutDashboard size={14} /></b><div><strong>Open Dashboard</strong><small>역할별 운영 canvas</small></div><kbd>1</kbd></button>
              <button type="button" onClick={() => runCommand(() => openWorkspace("analysis"))}><b><Workflow size={14} /></b><div><strong>Open Analysis Path</strong><small>변형·검증·dataset snapshot</small></div><kbd>2</kbd></button>
            </div>
            <div className="command-group"><span>Dashboard actions</span>
              <button type="button" onClick={() => runCommand(() => { openWorkspace("dashboard"); onModeChange("edit"); })}><b><Blocks size={14} /></b><div><strong>Edit canvas</strong><small>Board 이동, 복제, 크기 조정</small></div></button>
              <button type="button" onClick={() => runCommand(() => { openWorkspace("dashboard"); onOpenCatalog(); })}><b><Plus size={14} /></b><div><strong>Add board</strong><small>Board Catalog 열기</small></div></button>
              <button type="button" disabled={!canUndo} onClick={() => runCommand(onUndo)}><b><Undo2 size={14} /></b><div><strong>Undo edit</strong><small>이전 Dashboard draft 복원</small></div><kbd>⌘Z</kbd></button>
              <button type="button" disabled={!canRedo} onClick={() => runCommand(onRedo)}><b><Redo2 size={14} /></b><div><strong>Redo edit</strong><small>취소한 Dashboard draft 재적용</small></div><kbd>⌘⇧Z</kbd></button>
              <button type="button" disabled={!dirty || saving} onClick={() => runCommand(onSave)}><b><Save size={14} /></b><div><strong>Save preferences</strong><small>현재 개인 revision 저장</small></div><kbd>⌘S</kbd></button>
              <button type="button" onClick={() => runCommand(onShare)}><b><Share2 size={14} /></b><div><strong>Create shared view</strong><small>Scope를 유지한 링크 생성</small></div></button>
              <button type="button" onClick={() => runCommand(() => setDensity((current) => current === "compact" ? "comfortable" : "compact"))}><b><Maximize2 size={14} /></b><div><strong>Toggle density</strong><small>{density === "compact" ? "Comfortable spacing" : "Compact spacing"}</small></div></button>
              <button type="button" onClick={() => runCommand(() => setTheme((current) => current === "light" ? "dark" : "light"))}><b>{theme === "light" ? <Moon size={14} /> : <Sun size={14} />}</b><div><strong>Toggle theme</strong><small>{theme === "light" ? "Switch to dark" : "Switch to light"}</small></div></button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
