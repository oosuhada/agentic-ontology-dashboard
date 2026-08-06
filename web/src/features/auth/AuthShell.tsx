import { navigate } from "../../routing";
import { Boxes, Database, GitBranch, LockKeyhole, Network, ShieldCheck } from "lucide-react";
import { DisplayMenu } from "../../ui/foundry/DisplayMenu";

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
        <button className="auth-brand" onClick={() => navigate("/login")}><span className="brand-mark">OD</span><span><strong>Ontology Dashboard</strong><small>Foundry-style operational platform</small></span></button>
        <div><DisplayMenu className="auth-display-menu" /><span><ShieldCheck size={12} /> Governed environment</span><span>Asia/Seoul</span><span>v0.7</span></div>
      </header>
      <div className="auth-control-plane">
        <aside className="auth-resource-context">
          <header><span><Boxes size={16} /></span><div><small>APPLICATION</small><strong>Ontology Dashboard</strong></div></header>
          <section><span className="section-label">PLATFORM RESOURCES</span><div><Database size={13} /><span><strong>Dataset Catalog</strong><small>Immutable versions and lineage</small></span></div><div><Network size={13} /><span><strong>Object Explorer</strong><small>Objects, links and actions</small></span></div><div><GitBranch size={13} /><span><strong>Analysis</strong><small>Typed transformation paths</small></span></div></section>
          <section><span className="section-label">SECURITY BOUNDARY</span><div><LockKeyhole size={13} /><span><strong>Scoped authentication</strong><small>Organization → Project → Workspace → Role</small></span></div><p>계정 상태, 역할, Project scope와 object permission을 확인한 뒤 업무 화면을 엽니다.</p></section>
          <footer><span>ENVIRONMENT</span><strong>Local governed runtime</strong><small>PostgreSQL · Redis-ready · Project 3 boundary</small></footer>
        </aside>
        <section className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-heading"><span><LockKeyhole size={15} /></span><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>
            <p className="auth-description">{description}</p>
            {children}
            <footer><ShieldCheck size={12} /><span>Credentials are validated inside the configured tenant boundary.</span></footer>
          </div>
        </section>
      </div>
    </main>
  );
}
