import { Activity, Factory, LockKeyhole, ShieldCheck, Wrench } from "lucide-react";
import { navigate } from "../../routing";

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <main className="auth-page">
      <header className="auth-platform-bar">
        <button className="auth-brand" onClick={() => navigate("/login")}>
          <span className="brand-mark">OD</span>
          <span><strong>Ontology Dashboard</strong><small>Predictive Maintenance MVP</small></span>
        </button>
        <div><span><ShieldCheck size={12} /> Governed demo</span><span>Asia/Seoul</span></div>
      </header>
      <div className="auth-control-plane">
        <aside className="auth-resource-context">
          <header><span><Factory size={16} /></span><div><small>CURRENT PRODUCT</small><strong>Manufacturing MVP</strong></div></header>
          <section>
            <span className="section-label">FOUR-SCREEN FLOW</span>
            <div><Activity size={13} /><span><strong>Overview</strong><small>위험 현황과 우선순위</small></span></div>
            <div><Wrench size={13} /><span><strong>Objects · Operations</strong><small>근거 확인과 판단 기록</small></span></div>
            <div><ShieldCheck size={13} /><span><strong>Executive Report</strong><small>검증된 의사결정 보고</small></span></div>
          </section>
          <section><span className="section-label">ACCESS MODEL</span><div><LockKeyhole size={13} /><span><strong>두 역할</strong><small>관리자·임원 / 실무 엔지니어</small></span></div><p>Project와 Workspace 범위, 역할별 Action 권한을 확인한 뒤 업무 화면을 엽니다.</p></section>
          <footer><span>DATA SOURCE</span><strong>Canonical V3.1 Result Artifact</strong><small>Gold Fixture fallback 포함</small></footer>
        </aside>
        <section className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-heading"><span><LockKeyhole size={15} /></span><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>
            <p className="auth-description">{description}</p>
            {children}
            <footer><ShieldCheck size={12} /><span>승인된 Project 범위와 역할 권한으로 세션을 생성합니다.</span></footer>
          </div>
        </section>
      </div>
    </main>
  );
}
