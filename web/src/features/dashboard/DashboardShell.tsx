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
  SlidersHorizontal,
  Share2,
  ShieldCheck,
  Sparkles,
  Sun,
  Workflow,
  X,
} from "lucide-react";
import { featureFlags } from "../../featureFlags";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchHeader, WorkbenchToolbar } from "../../ui/foundry/WorkbenchChrome";
import { DisplayMenu } from "../../ui/foundry/DisplayMenu";
import { useDisplayPreferences } from "../../ui/foundry/displayPreferences";
import { FoundryProductNavigation } from "../../ui/foundry/FoundryProductNavigation";
import { FoundryDrawer } from "../../ui/foundry/FoundryDrawer";
import { useMediaQuery } from "../../ui/foundry/useMediaQuery";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { FoundryDialog } from "../../ui/foundry/FoundryDialog";
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
  const [commandOpen, setCommandOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mobileScopeOpen, setMobileScopeOpen] = useState(false);
  const [mobileContextOpen, setMobileContextOpen] = useState(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">(initialTheme);
  const isCompactWorkbench = useMediaQuery("(max-width: 980px)");
  const { t } = useI18n();
  const { preferences, setDensity } = useDisplayPreferences();

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
        if (mode === "edit") onModeChange("view");
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [canRedo, canUndo, dirty, mode, onModeChange, onRedo, onSave, onUndo, saving]);

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
    <div className={`ontology-dashboard-shell od-product-shell mode-${mode} role-${user.landing_key} density-${preferences.density} workspace-${workspaceView} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
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
        onCloseMobile={() => setMobileNavOpen(false)}
        onAdmin={onAdmin}
        onLogout={onLogout}
      />

      <div className="od-shell-main">
        <header className="od-global-topbar">
          <button type="button" className="od-mobile-menu" aria-label={t("nav.open")} onClick={() => setMobileNavOpen((current) => !current)}><Menu size={17} /></button>
          <div className="od-breadcrumbs">
            <span>{selectedProject?.display_name ?? "Project"}</span><ChevronRight size={12} />
            <span>{selectedWorkspace?.display_name ?? "Workspace"}</span><ChevronRight size={12} />
            <strong>{workspaceView === "dashboard" ? activeTab?.title ?? "Dashboard" : "Analysis Path"}</strong>
          </div>
          <button type="button" className="od-global-search" onClick={() => setCommandOpen(true)}><Search size={14} /><span>{t("nav.search")}</span><kbd>⌘K</kbd></button>
          <div className="od-topbar-actions">
            <DisplayMenu />
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
              trailing={<div className="fd-entity-title__trailing"><span className="od-domain-pack-name">{domainPack?.display_name ?? "Manufacturing Operations"}</span><StatusPill intent={dirty ? "warning" : "success"}>{dirty ? t("common.unsaved") : t("common.saved")}</StatusPill></div>}
            />
          </div>}
          actions={<div className={`dashboard-scope-actions ${mobileScopeOpen ? "mobile-open" : ""}`}>
            <button type="button" className="dashboard-mobile-scope-toggle" aria-expanded={mobileScopeOpen} aria-controls="dashboard-scope-controls" onClick={() => setMobileScopeOpen((current) => !current)}><Settings size={13} /> {t("dashboard.scope")}</button>
            <div className="od-context-controls" id="dashboard-scope-controls">
              <label>{t("common.project")}<select aria-label={t("common.project")} value={selectedProjectId} onChange={(event) => onProjectChange(event.target.value)}>{projects.map((project) => <option key={project.id} value={project.id}>{project.display_name}</option>)}</select></label>
              <label>{t("common.workspace")}<select aria-label={t("common.workspace")} value={selectedWorkspaceId} onChange={(event) => onWorkspaceChange(event.target.value)}>{workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.display_name}</option>)}</select></label>
              <label>{t("common.role")}<select aria-label={t("common.role")} value={activeRole} onChange={(event) => onActiveRoleChange(event.target.value as AppRole)}>{availableRoles.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}</select></label>
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
            label={t("dashboard.tabsActions")}
            start={<nav className="dashboard-tabs" aria-label={t("dashboard.tabsActions")}>
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
                  {tab.title}{tab.custom ? <small>{t("dashboard.personal").toUpperCase()}</small> : null}
                </button>
              ))}
              {mode === "edit" ? <button type="button" className="add-tab-button" onClick={onAddTab}><Plus size={13} /> Tab</button> : null}
            </nav>}
            end={<div className="dashboard-edit-toolbar">
              <div className="view-edit-switch" role="group" aria-label={t("dashboard.mode")}>
                <button type="button" className={mode === "view" ? "active" : ""} onClick={() => onModeChange("view")}><Eye size={12} /> {mode === "edit" ? t("common.done") : t("common.view")}</button>
                <button type="button" className={mode === "edit" ? "active" : ""} title={t("common.edit")} onClick={() => onModeChange("edit")}><Blocks size={12} /> {t("common.edit")}</button>
              </div>
              {mode === "edit" ? <>
                <button type="button" className="icon-button" aria-label="Undo dashboard edit" title="실행 취소 (⌘Z)" disabled={!canUndo} onClick={onUndo}><Undo2 size={13} /></button>
                <button type="button" className="icon-button" aria-label="Redo dashboard edit" title="다시 실행 (⌘⇧Z)" disabled={!canRedo} onClick={onRedo}><Redo2 size={13} /></button>
                <button type="button" className="secondary" aria-label={t("dialog.boardCatalog")} onClick={onOpenCatalog}><Plus size={12} /> {t("dashboard.addBoard")}</button>
              </> : null}
              <button type="button" className="secondary" aria-label={t("dashboard.saveView")} onClick={onSaveView}><Sparkles size={12} /> {t("dashboard.saveView")}</button>
              <button type="button" className="secondary" aria-label={t("common.share")} onClick={onShare}><Share2 size={12} /> {t("common.share")}</button>
              <div className="dashboard-export-control"><select aria-label={t("dashboard.exportFormat")} value={exportFormat} onChange={(event) => setExportFormat(event.target.value as "json" | "csv" | "pdf")}><option value="pdf">PDF</option><option value="csv">CSV</option><option value="json">JSON</option></select><button type="button" className="secondary" disabled={exporting} onClick={() => onExport(exportFormat)}><Download size={12} />{exporting ? t("common.exporting") : t("common.export")}</button></div>
              <button type="button" className="icon-button" title={t("dashboard.restore")} onClick={onRestore}><RotateCcw size={13} /></button>
              <button type="button" className="primary" aria-label={saving ? t("common.saving") : dirty ? t("dashboard.saveLayout") : t("common.saved")} disabled={!dirty || saving} onClick={onSave}><Save size={13} />{saving ? t("common.saving") : dirty ? t("dashboard.saveLayout") : t("common.saved")}</button>
            </div>}
          />
        ) : null}

        {workspaceView === "dashboard" && canManageTemplates && mode === "edit" ? (
          <section className="template-publish-bar"><div><strong>Governed Template Editor</strong><span>현재 canvas를 선택 역할의 새 template version으로 게시합니다.</span></div><select value={targetTemplateRole} onChange={(event) => onTargetTemplateRoleChange(event.target.value as AppRole)}>{TEMPLATE_ROLES.map((role) => <option key={role} value={role}>{role}</option>)}</select><button type="button" className="secondary" onClick={onPublishTemplate}>{templateActionLabel}</button></section>
        ) : null}

        {workspaceView === "dashboard" && mode === "edit" ? (
          <nav className="dashboard-editor-lanes" aria-label="Dashboard editor regions">
            <span><b>1</b><strong>Resources</strong><small>Context and filters</small></span>
            <span><b>2</b><strong>Canvas</strong><small>12-column governed layout</small></span>
            <span><b>3</b><strong>Inspector</strong><small>Board contract and settings</small></span>
          </nav>
        ) : null}

        {notice ? <div className="notice dashboard-notice" role="status"><span>{notice}</span><button onClick={onDismissNotice}>{t("common.close")}</button></div> : null}
        {error ? <div className="error-panel dashboard-error" role="alert"><strong>{t("dashboard.error")}</strong><p>{error}</p><button onClick={onRetry}>{t("common.retry")}</button></div> : null}

        <main className="od-workbench-main">
          {workspaceView === "dashboard" ? (
            <div className={`dashboard-workspace-layout ${mode === "edit" ? "with-inspector" : ""}`}>
              <aside className="dashboard-context-rail">
                {isCompactWorkbench
                  ? <div className="dashboard-mobile-context-bar"><button type="button" aria-expanded={mobileContextOpen} onClick={() => setMobileContextOpen(true)}><SlidersHorizontal size={14} /> {t("dashboard.context")}</button></div>
                  : contextPanel}
              </aside>
              <section className="dashboard-canvas-region">{boardCanvas}</section>
              {mode === "edit" ? (
                isCompactWorkbench
                  ? <button type="button" className="dashboard-mobile-inspector-trigger" aria-expanded={mobileInspectorOpen} onClick={() => setMobileInspectorOpen(true)}><Settings size={14} /> {t("dashboard.inspector")}</button>
                  : inspector
              ) : null}
            </div>
          ) : <div className="analysis-workspace-region">{analysisWorkbench}</div>}
        </main>

        {isCompactWorkbench && mobileContextOpen ? (
          <FoundryDrawer ariaLabel={t("drawer.context")} title={t("drawer.context")} position="bottom" onClose={() => setMobileContextOpen(false)} className="dashboard-context-drawer">
            {contextPanel}
          </FoundryDrawer>
        ) : null}
        {isCompactWorkbench && mode === "edit" && mobileInspectorOpen ? (
          <FoundryDrawer ariaLabel={t("drawer.inspector")} title={t("drawer.inspector")} position="bottom" onClose={() => setMobileInspectorOpen(false)} className="dashboard-inspector-drawer">
            {inspector}
          </FoundryDrawer>
        ) : null}

        <footer className="footer-note">Ontology Dashboard · Organization → Project → Workspace → Role Dashboard · Object permissions and scope remain enforced.</footer>
        {workspaceView === "dashboard" ? catalog : null}
      </div>

      {mobileNavOpen ? <button type="button" className="od-mobile-backdrop" aria-label={t("nav.close")} onClick={() => setMobileNavOpen(false)} /> : null}

      {commandOpen ? (
        <FoundryDialog ariaLabel={t("dialog.commandPalette")} overlayClassName="command-palette-overlay" dialogClassName="command-palette" onClose={() => setCommandOpen(false)}>
            <header><div><span className="section-label">COMMAND PALETTE</span><strong>{t("dashboard.commandTitle")}</strong></div><kbd>ESC</kbd></header>
            <div className="command-search"><Search size={15} /><input data-dialog-initial-focus placeholder={t("dashboard.command")} /></div>
            <div className="command-group"><span>Workspace</span>
              <button type="button" onClick={() => runCommand(() => openWorkspace("dashboard"))}><b><LayoutDashboard size={14} /></b><div><strong>{t("dashboard.openDashboard")}</strong><small>역할별 운영 canvas</small></div><kbd>1</kbd></button>
              <button type="button" onClick={() => runCommand(() => openWorkspace("analysis"))}><b><Workflow size={14} /></b><div><strong>{t("dashboard.openAnalysis")}</strong><small>변형·검증·dataset snapshot</small></div><kbd>2</kbd></button>
            </div>
            <div className="command-group"><span>Dashboard actions</span>
              <button type="button" onClick={() => runCommand(() => { openWorkspace("dashboard"); onModeChange("edit"); })}><b><Blocks size={14} /></b><div><strong>{t("dashboard.editCanvas")}</strong><small>Board 이동, 복제, 크기 조정</small></div></button>
              <button type="button" onClick={() => runCommand(() => { openWorkspace("dashboard"); onOpenCatalog(); })}><b><Plus size={14} /></b><div><strong>{t("dashboard.addBoard")}</strong><small>Board Catalog</small></div></button>
              <button type="button" disabled={!canUndo} onClick={() => runCommand(onUndo)}><b><Undo2 size={14} /></b><div><strong>Undo edit</strong><small>이전 Dashboard draft 복원</small></div><kbd>⌘Z</kbd></button>
              <button type="button" disabled={!canRedo} onClick={() => runCommand(onRedo)}><b><Redo2 size={14} /></b><div><strong>Redo edit</strong><small>취소한 Dashboard draft 재적용</small></div><kbd>⌘⇧Z</kbd></button>
              <button type="button" disabled={!dirty || saving} onClick={() => runCommand(onSave)}><b><Save size={14} /></b><div><strong>Save preferences</strong><small>현재 개인 revision 저장</small></div><kbd>⌘S</kbd></button>
              <button type="button" onClick={() => runCommand(onShare)}><b><Share2 size={14} /></b><div><strong>Create shared view</strong><small>Scope를 유지한 링크 생성</small></div></button>
              <button type="button" onClick={() => runCommand(() => setDensity(preferences.density === "compact" ? "standard" : preferences.density === "standard" ? "comfortable" : "compact"))}><b><Settings size={14} /></b><div><strong>Cycle density</strong><small>{preferences.density} → {preferences.density === "compact" ? "standard" : preferences.density === "standard" ? "comfortable" : "compact"}</small></div></button>
              <button type="button" onClick={() => runCommand(() => setTheme((current) => current === "light" ? "dark" : "light"))}><b>{theme === "light" ? <Moon size={14} /> : <Sun size={14} />}</b><div><strong>Toggle theme</strong><small>{theme === "light" ? "Switch to dark" : "Switch to light"}</small></div></button>
            </div>
        </FoundryDialog>
      ) : null}
    </div>
  );
}
