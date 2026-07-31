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
      <section className="auth-story">
        <button className="auth-brand" onClick={() => navigate("/login")}>
          <span className="brand-mark">OD</span>
          <span><strong>Ontology Dashboard</strong><small>Ontology-aware operational application</small></span>
        </button>
        <div className="auth-story-copy">
          <span className="eyebrow">MANUFACTURING PREDICTIVE MAINTENANCE PACK</span>
          <h1>같은 Ontology를<br />역할에 맞는 업무 화면으로.</h1>
          <p>객체, 관계, 근거와 행동을 하나의 권한 경계 안에서 연결합니다.</p>
        </div>
        <div className="auth-principles">
          <span>Object & Link</span>
          <span>Evidence</span>
          <span>Action</span>
          <span>Role Default</span>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
          <p className="auth-description">{description}</p>
          {children}
        </div>
      </section>
    </main>
  );
}
