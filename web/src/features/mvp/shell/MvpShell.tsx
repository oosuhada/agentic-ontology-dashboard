import {
  Boxes,
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  Menu,
  RefreshCw,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import type { MvpContextModel, MvpRoleLens, MvpView } from "../api/mvpContracts";
import { MvpFreshness } from "../components/MvpUi";

const NAV_ITEMS: Array<{ id: MvpView; label: string; description: string; icon: typeof LayoutDashboard }> = [
  { id: "overview", label: "Overview", description: "위험 현황과 우선순위", icon: LayoutDashboard },
  { id: "objects", label: "Objects", description: "설비 목록과 근거", icon: Boxes },
  { id: "operations", label: "Operations", description: "점검·판단 업무", icon: ClipboardCheck },
  { id: "executive-report", label: "Executive Report", description: "임원 보고와 출력", icon: FileText },
];

export function MvpShell({
  context,
  activeView,
  role,
  onNavigate,
  onRoleChange,
  onRefresh,
  refreshing,
  children,
}: {
  context: MvpContextModel;
  activeView: MvpView;
  role: MvpRoleLens;
  onNavigate: (view: MvpView) => void;
  onRoleChange: (role: MvpRoleLens) => void;
  onRefresh: () => void;
  refreshing: boolean;
  children: ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const active = NAV_ITEMS.find((item) => item.id === activeView) ?? NAV_ITEMS[0];
  return (
    <main className="mvp-app">
      <header className="mvp-global-header">
        <div className="mvp-brand">
          <span className="mvp-brand-mark"><LayoutDashboard size={19} /></span>
          <div><span>Ontology Dashboard</span><strong>Predictive Maintenance MVP</strong></div>
        </div>
        <div className="mvp-header-context" aria-label="현재 MVP 문맥">
          <div><span>Project</span><strong>{context.projectName}</strong></div>
          <div><span>Workspace</span><strong>{context.workspaceName}</strong></div>
          <div className="is-dataset"><span>Dataset</span><strong title={context.datasetLabel}>Canonical V3.1 · {context.datasetVersionId}</strong></div>
        </div>
        <div className="mvp-header-actions">
          <label><span>역할</span><select value={role} onChange={(event) => onRoleChange(event.target.value as MvpRoleLens)}><option value="process_manager">생산 관리자</option><option value="field_operator">현장 담당자</option></select></label>
          <button type="button" className="mvp-icon-button" onClick={onRefresh} aria-label="데이터 새로고침" disabled={refreshing}><RefreshCw size={17} className={refreshing ? "is-spinning" : ""} /></button>
          <button type="button" className="mvp-icon-button mvp-mobile-menu" onClick={() => setMobileOpen((current) => !current)} aria-label="메뉴 열기">{mobileOpen ? <X size={19} /> : <Menu size={19} />}</button>
        </div>
      </header>

      <div className="mvp-context-line">
        <div><span className={`mvp-source-mode source-${context.sourceMode}`}>{context.sourceMode === "canonical-runtime" ? "실제 Result Artifact" : "계약형 Fallback"}</span><strong>{context.sourceStatus}</strong></div>
        <MvpFreshness observedAt={context.observedAt} stale={context.stale} />
      </div>

      {context.warnings.length ? (
        <details className="mvp-source-warning">
          <summary>부분 연결 경고 {context.warnings.length}건</summary>
          <ul>{context.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </details>
      ) : null}

      <div className="mvp-workspace">
        <aside className={`mvp-navigation ${mobileOpen ? "is-open" : ""}`} aria-label="MVP 화면">
          <div className="mvp-nav-intro"><span>MENTORING SCOPE</span><strong>4-screen flow</strong><p>Analysis 없이 운영 판단부터 보고까지 연결합니다.</p></div>
          <nav>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return <button type="button" key={item.id} className={activeView === item.id ? "is-active" : ""} onClick={() => { onNavigate(item.id); setMobileOpen(false); }}><Icon size={17} /><div><strong>{item.label}</strong><span>{item.description}</span></div></button>;
            })}
          </nav>
          <div className="mvp-nav-footnote"><strong>Analysis 제외</strong><span>모델 탐색·Canvas·관리자 Surface는 이번 MVP 범위가 아닙니다.</span></div>
        </aside>
        <section className="mvp-main">
          <header className="mvp-page-heading"><span>{active.label}</span><h1>{active.description}</h1><p>{role === "process_manager" ? "생산 관리자가 위험·영향·대응을 빠르게 판단하는 관점입니다." : "현장 담당자가 설비 근거와 수행 업무를 확인하는 관점입니다."}</p></header>
          {children}
        </section>
      </div>
    </main>
  );
}
