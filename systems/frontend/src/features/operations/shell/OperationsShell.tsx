import {
  Boxes,
  ClipboardCheck,
  Factory,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  RefreshCw,
  TerminalSquare,
  Wrench,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import type { OperationsContextModel, OperationsDashboardMode, OperationsRoleLens, OperationsView } from "../api/operationsContracts";
import { OperationsFreshness } from "../components/OperationsUi";
import { HanbitLogo } from "../../../ui/foundry/HanbitLogo";
import { displayDataSource } from "../displayLabels";

const VIEW_LABELS: Record<OperationsView, { label: string; description: string }> = {
  overview: { label: "Overview", description: "운영 상황판" },
  objects: { label: "Assets", description: "설비 상태와 근거" },
  operations: { label: "작업요청", description: "처리할 작업" },
  reports: { label: "Reports", description: "보고서 출력" },
  system: { label: "시스템 관리자", description: "AI 요약 처리 로그" },
};

const NAV_ITEMS: Array<{ id: OperationsView; label: string; description: string; icon: typeof LayoutDashboard }> = [
  { id: "overview", label: "Overview", description: "운영 상황판", icon: LayoutDashboard },
  { id: "objects", label: "Assets", description: "설비 상태와 근거", icon: Boxes },
  { id: "operations", label: "작업요청", description: "처리할 작업", icon: ClipboardCheck },
  { id: "reports", label: "Reports", description: "보고서 출력", icon: FileText },
  { id: "system", label: "시스템 관리자", description: "AI 요약 처리 로그", icon: TerminalSquare },
];

const ROLE_LABELS: Record<OperationsRoleLens, { label: string; description: string; icon: typeof LayoutDashboard }> = {
  field_operator: { label: "현장 관리자", description: "점검 요청 · 의심 부품 · 처리 작업", icon: Wrench },
  process_manager: { label: "생산 관리자", description: "공정 리스크 · 계획 영향 · 진행 현황", icon: Factory },
};

const ROLE_SCREENS: Array<{ id: OperationsRoleLens; label: string; description: string; icon: typeof LayoutDashboard }> = [
  { id: "field_operator", label: "현장 관리자", description: "점검 요청 · 의심 부품 · 처리 작업", icon: Wrench },
  { id: "process_manager", label: "생산 관리자", description: "공정 리스크 · 계획 영향 · 진행 현황", icon: Factory },
];

const WORKFLOW_SYSTEM_ITEM = {
  id: "system" as const,
  label: "시스템 관리자",
  description: "AI 요약 처리 로그",
  icon: TerminalSquare,
};

export function operationsNavigationItems(dashboard: OperationsDashboardMode) {
  return dashboard === "workflow"
    ? [...ROLE_SCREENS, WORKFLOW_SYSTEM_ITEM]
    : NAV_ITEMS;
}

export function OperationsShell({
  context,
  activeView,
  dashboard,
  role,
  onNavigate,
  onRoleChange,
  onRefresh,
  refreshing,
  refreshIntervalSeconds,
  canReadSystemLogs: _canReadSystemLogs,
  onLogout,
  children,
}: {
  context: OperationsContextModel;
  activeView: OperationsView;
  dashboard: OperationsDashboardMode;
  role: OperationsRoleLens;
  onNavigate: (view: OperationsView) => void;
  onRoleChange: (role: OperationsRoleLens) => void;
  onRefresh: () => void;
  refreshing: boolean;
  refreshIntervalSeconds: number;
  canReadSystemLogs: boolean;
  onLogout: () => void | Promise<void>;
  children: ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const workflowMode = dashboard === "workflow";
  const navItems = operationsNavigationItems(dashboard);
  const roleMeta = ROLE_LABELS[role];
  const active = workflowMode && activeView === "overview" ? roleMeta : VIEW_LABELS[activeView];
  const headingDetail = workflowMode && activeView === "overview"
    ? "하나의 업무판에서 상황, 설비 근거, 작업요청을 역할별로 바로 이어갑니다."
    : activeView === "system"
    ? "자동 감시 생성, 운영자 요청, 대체 요약, 검증 상태를 한 화면에서 조회하는 시스템 관리자 로그입니다."
    : activeView === "reports"
    ? "map-report UI prototype의 보고서 화면과 선택 Event 브리핑을 하나의 사이드탭에서 전환합니다."
    : activeView !== "overview"
      ? role === "process_manager"
        ? "생산 관리자가 위험·영향·대응을 빠르게 판단하는 관점입니다."
        : "현장 담당자가 설비 근거와 수행 업무를 확인하는 관점입니다."
    : role === "process_manager"
      ? "생산 관리자가 위험·영향·대응을 빠르게 판단하는 관점입니다."
      : "현장 담당자가 설비 근거와 수행 업무를 확인하는 관점입니다.";
  return (
    <main className="operations-app">
      <header className="operations-global-header">
        <div className="operations-brand">
          <span className="operations-brand-mark hanbit-brand-mark"><HanbitLogo /></span>
          <div><span>Ontology Dashboard</span><strong>Predictive Maintenance</strong></div>
        </div>
        <div className="operations-header-context" aria-label="현재 운영 문맥">
          <div><span>Project</span><strong>{context.projectName}</strong></div>
          <div><span>Workspace</span><strong>{context.workspaceName}</strong></div>
          <div className="is-dataset"><span>데이터 기준</span><strong>{displayDataSource(context.sourceVersion)}</strong></div>
        </div>
        <div className="operations-header-actions">
          {!workflowMode ? (
            <label>
              <span>역할</span>
              <select value={role} onChange={(event) => onRoleChange(event.target.value as OperationsRoleLens)}>
                <option value="process_manager">생산 관리자</option>
                <option value="field_operator">현장 담당자</option>
              </select>
            </label>
          ) : null}
          <button type="button" className="operations-icon-button" onClick={onRefresh} aria-label="데이터 새로고침" disabled={refreshing}><RefreshCw size={17} className={refreshing ? "is-spinning" : ""} /></button>
          <button type="button" className="operations-icon-button" onClick={() => void onLogout()} aria-label="로그아웃" title="로그아웃"><LogOut size={17} /></button>
          <button type="button" className="operations-icon-button operations-mobile-menu" onClick={() => setMobileOpen((current) => !current)} aria-label="메뉴 열기">{mobileOpen ? <X size={19} /> : <Menu size={19} />}</button>
        </div>
      </header>

      <div className="operations-context-line">
        <div><span className={`operations-source-mode source-${context.sourceMode}`}>{context.sourceMode === "canonical-runtime" ? "운영 데이터 연결" : "보조 데이터 표시"}</span><strong>{context.sourceStatus}</strong></div>
        <div className="operations-refresh-status" aria-label="데이터 갱신 상태">
          <span className="operations-refresh-cadence"><RefreshCw size={13} className={refreshing ? "is-spinning" : ""} />자동 확인 · {refreshIntervalSeconds}초마다 갱신</span>
          <OperationsFreshness observedAt={context.observedAt} stale={context.stale} />
        </div>
      </div>

      {context.warnings.length ? (
        <details className="operations-source-warning">
          <summary>부분 연결 경고 {context.warnings.length}건</summary>
          <ul>{context.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      ) : null}

      <div className="operations-workspace">
        <aside className={`operations-navigation ${mobileOpen ? "is-open" : ""}`} aria-label="예지보전 화면">
          <div className="operations-nav-intro">
            <span>{workflowMode ? "WORKFLOW DASHBOARD" : "MENTORING SCOPE"}</span>
            <strong>{workflowMode ? "역할 → 업무판" : "Dashboard side tabs"}</strong>
            <p>{workflowMode ? "역할별 화면 안에서 Overview, Assets, 작업요청 흐름을 한 번에 처리합니다." : "Analysis 없이 운영 판단부터 점검 보고까지 연결합니다."}</p>
          </div>
          <nav>
            {navItems.map((item) => {
              const Icon = item.icon;
              const activeItem = workflowMode && item.id !== "system"
                ? activeView === "overview" && role === item.id
                : activeView === item.id;
              return (
                <button
                  type="button"
                  key={item.id}
                  className={activeItem ? "is-active" : ""}
                  aria-current={activeItem ? "page" : undefined}
                  onClick={() => {
                    if (workflowMode && item.id !== "system") {
                      onRoleChange(item.id as OperationsRoleLens);
                    } else {
                      onNavigate(item.id as OperationsView);
                    }
                    setMobileOpen(false);
                  }}
                >
                  <Icon size={17} />
                  <div><strong>{item.label}</strong><span>{item.description}</span></div>
                </button>
              );
            })}
          </nav>
          <div className="operations-nav-footnote"><strong>{workflowMode ? "업무 흐름" : "Analysis 제외"}</strong><span>{workflowMode ? "역할별 업무판은 하나의 화면에서 설비, 근거, 작업요청을 연결합니다." : "모델 탐색·Canvas·관리자 Surface는 현재 운영 화면 범위가 아닙니다."}</span></div>
        </aside>
        <section className="operations-main">
          <header className="operations-page-heading"><span>{active.label}</span><h1>{active.description}</h1><p>{headingDetail}</p></header>
          {children}
        </section>
      </div>
    </main>
  );
}
