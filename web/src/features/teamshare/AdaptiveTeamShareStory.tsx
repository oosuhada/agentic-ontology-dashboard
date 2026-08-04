import {
  ArrowRight,
  Boxes,
  CheckCircle2,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  LayoutDashboard,
  Maximize2,
  Network,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

const CAPTURE_ROOT = "/team-share-adaptive-assets";
const VERIFIED_TAG = "team-share-adaptive-capture-integrity-20260805";
const APP_ROUTE = "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling";

interface Capture {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  image: string;
  alt: string;
  status: string;
}

const captures: Capture[] = [
  {
    id: "runtime",
    eyebrow: "CANONICAL V3.1 RUNTIME",
    title: "Dataset Version과 Result Artifact가 운영 Dashboard에 연결됩니다",
    description: "V2/V3.1 버전 선택, provenance, release evidence, 최신 위험 자산과 PostgreSQL 기반 replay를 한 화면에서 확인합니다.",
    image: `${CAPTURE_ROOT}/01-v3-runtime-dashboard.png`,
    alt: "Predictive Maintenance V3.1 운영 Dashboard",
    status: "65/65 release checks",
  },
  {
    id: "replay",
    eyebrow: "RESULT ARTIFACT REPLAY",
    title: "과거 센서와 precomputed prediction timeline을 재생합니다",
    description: "Replay는 새 값을 생성하거나 모델을 재학습하지 않습니다. 저장된 관측과 prediction timeline만 시간 순서대로 재현합니다.",
    image: `${CAPTURE_ROOT}/02-v3-result-replay.png`,
    alt: "Predictive Maintenance Result Artifact replay controls",
    status: "truth hidden · source immutable",
  },
  {
    id: "validator",
    eyebrow: "ML VALIDATOR WORKBENCH",
    title: "모델 비교와 threshold 선택 근거를 실제 artifact로 검토합니다",
    description: "Dummy baseline, Logistic Regression, optional model capability, PR/ROC, calibration, slice metrics와 lineage를 검증합니다.",
    image: `${CAPTURE_ROOT}/03-ml-validator-desktop.png`,
    alt: "ML Validator Workbench desktop",
    status: "validation-only selection",
  },
  {
    id: "governance",
    eyebrow: "MODEL RELEASE GOVERNANCE",
    title: "검증자와 승인자의 책임을 분리합니다",
    description: "ML Validator는 release를 요청하고 Tenant Admin은 승인·활성화·rollback을 수행합니다. 한 사용자가 스스로 승인할 수 없습니다.",
    image: `${CAPTURE_ROOT}/04-model-release-governance.png`,
    alt: "Model Registry release governance",
    status: "request → approve → activate",
  },
  {
    id: "mobile",
    eyebrow: "RESPONSIVE VALIDATION",
    title: "모바일에서도 lineage와 release 상태를 잃지 않습니다",
    description: "390px viewport에서도 가로 overflow 없이 실험, 모델, threshold와 governance 상태가 단일 column으로 정리됩니다.",
    image: `${CAPTURE_ROOT}/05-ml-validator-mobile.png`,
    alt: "ML Validator Workbench mobile",
    status: "desktop · tablet · mobile",
  },
];

const completed = [
  "Canonical V3.1 package·Dataset Version·Result Artifact",
  "CSV·TSV·XLSX governed intake와 immutable Dataset Version",
  "Ontology Mapping·Feature Recipe·Feature Dataset lineage",
  "Chronological experiment와 validation-only selection",
  "Model Registry·release approval·atomic activation·rollback",
  "Prediction Result와 non-causal Explanation Artifact",
  "PostgreSQL JSONB·RLS·tenant/project/workspace isolation",
  "ML Validator role flow와 desktop/tablet/mobile visual baseline",
];

const needsReview = [
  "실제 공정 기준 Recall·FN/FP 비용·prediction horizon",
  "Feature Recipe의 설비 물리 의미와 현장 유효성",
  "Synthetic controlled E2E metric의 발표 표현 범위",
  "Cloudflare 개발 터널과 production reverse proxy 경계",
];

const nextWork = [
  "Live demo Dataset·Mapping·Recipe·Experiment seed",
  "통합 Modeling authoring UI",
  "Daemon worker·heartbeat·queue consumer",
  "S3/GCS artifact store와 backup/restore exercise",
  "Calibration·confidence·drift·outcome artifact",
];

export function AdaptiveTeamShareStory() {
  const [selected, setSelected] = useState<Capture | null>(null);

  useEffect(() => {
    if (!selected) return undefined;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", close);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", close);
    };
  }, [selected]);

  return (
    <main className="adaptive-share-page">
      <header className="adaptive-share-header">
        <a className="adaptive-share-brand" href="#overview"><span>OD</span><div><strong>Ontology Dashboard</strong><small>V3.1 + Adaptive Modeling release story</small></div></a>
        <nav aria-label="Adaptive team share sections">
          <a href="#runtime">Runtime</a><a href="#modeling">Modeling</a><a href="#evidence">Evidence</a><a href="#status">Status</a>
        </nav>
        <div><a href="/team-share">이전 Team Share</a><a className="primary" href={APP_ROUTE}>앱 열기 <ArrowRight size={13} /></a></div>
      </header>

      <section className="adaptive-share-hero" id="overview">
        <div>
          <span className="adaptive-share-kicker"><Sparkles size={14} /> VERIFIED UPDATE · 2026-08-05</span>
          <h1>Canonical V3.1의 데이터 계약에서<br />Adaptive Modeling의 모델 승인까지</h1>
          <p>기존 `/team-share`를 보존한 채, 최신 Predictive Maintenance V3.1과 Adaptive Modeling Phase 09~16을 별도 비교 자료로 구성했습니다.</p>
          <div className="adaptive-share-actions"><a className="primary" href="#runtime">업데이트 화면 보기 <ArrowRight size={14} /></a><a href="/team-share-adaptive.html">독립 HTML 열기 <ExternalLink size={13} /></a></div>
          <div className="adaptive-share-integrity"><ShieldCheck size={14} /><strong>{VERIFIED_TAG}</strong><span>loader-free captures</span><span>controlled release evidence</span></div>
        </div>
        <div className="adaptive-share-release-map" aria-label="Adaptive modeling release map">
          <article><Database /><strong>Dataset Version</strong><small>immutable source identity</small></article>
          <ArrowRight />
          <article><Boxes /><strong>Ontology Mapping</strong><small>registry-bound approval</small></article>
          <ArrowRight />
          <article><GitBranch /><strong>Feature + Experiment</strong><small>chronological validation</small></article>
          <ArrowRight />
          <article><ShieldCheck /><strong>Model Release</strong><small>approval and rollback</small></article>
        </div>
        <div className="adaptive-share-metrics">
          <span><strong>65/65</strong><small>Canonical V3.1 verifier</small></span>
          <span><strong>53</strong><small>Adaptive targeted tests</small></span>
          <span><strong>255</strong><small>Project 2 backend tests</small></span>
          <span><strong>13/13</strong><small>General release gate</small></span>
        </div>
      </section>

      <section className="adaptive-share-section" id="runtime">
        <header><span>01 · PREDICTIVE MAINTENANCE V3.1</span><h2>운영 Dashboard와 replay가 같은 Dataset Version을 가리킵니다</h2><p>버전, checksum, model, task, Result Artifact schema와 graph readiness를 화면에서 분리해 확인합니다.</p></header>
        <div className="adaptive-share-feature-grid">
          {captures.slice(0, 2).map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
      </section>

      <section className="adaptive-share-section alt" id="modeling">
        <header><span>02 · ADAPTIVE MODELING</span><h2>모델 성능보다 먼저 lineage와 승인 가능성을 검증합니다</h2><p>실험 결과가 좋아도 Dataset·Mapping·Recipe·Feature Dataset·artifact checksum이 맞지 않으면 release를 요청할 수 없습니다.</p></header>
        <div className="adaptive-share-feature-grid three">
          {captures.slice(2).map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
      </section>

      <section className="adaptive-share-section" id="evidence">
        <header><span>03 · CONTROLLED EVIDENCE</span><h2>Source-to-serving 전체 체인을 한 번에 재현했습니다</h2><p>Synthetic controlled data는 제품 계약과 governance를 검증하는 증거이며 production predictive quality를 대신하지 않습니다.</p></header>
        <div className="adaptive-share-evidence">
          <article><span>DATA</span><strong>360 → 360</strong><p>Source rows와 accepted rows. quarantine 0, equipment 3, derived features 4.</p></article>
          <article><span>MODEL SELECTION</span><strong>AP 0.5882</strong><p>Logistic Regression validation AP. Dummy baseline AP 0.2917.</p></article>
          <article><span>HELD-OUT TEST</span><strong>AP 0.5003</strong><p>선택된 후보 한 건에만 test를 사용했으며 selection에는 사용하지 않았습니다.</p></article>
          <article><span>THRESHOLD</span><strong>0.33</strong><p>Validation recall 0.9524. FN cost 10, FP cost 1 정책 근거.</p></article>
        </div>
        <div className="adaptive-share-chain"><span>Intake</span><ArrowRight /><span>Manifest</span><ArrowRight /><span>Mapping</span><ArrowRight /><span>Feature</span><ArrowRight /><span>Experiment</span><ArrowRight /><span>Registry</span><ArrowRight /><span>Prediction</span><ArrowRight /><span>Explanation</span></div>
      </section>

      <section className="adaptive-share-section alt" id="status">
        <header><span>04 · DELIVERY STATUS</span><h2>완료, 검토, 추가 작업을 같은 수준으로 표시하지 않습니다</h2><p>Local release와 strict production release를 명확히 구분합니다.</p></header>
        <div className="adaptive-share-status-grid">
          <StatusColumn title="완료" tone="complete" items={completed} />
          <StatusColumn title="검토 필요" tone="review" items={needsReview} />
          <StatusColumn title="추가 작업" tone="next" items={nextWork} />
        </div>
        <div className="adaptive-share-production"><Network size={20} /><div><strong>Strict production release는 외부 인프라로 blocked</strong><p>Production PostgreSQL, Redis, Neo4j, Project 3, OIDC, object storage, OTLP와 optional LightGBM·XGBoost·SHAP 구성이 필요합니다.</p></div></div>
      </section>

      <footer className="adaptive-share-footer"><div><LayoutDashboard size={16} /><strong>Ontology Dashboard · Predictive Maintenance V3.1 + Adaptive Modeling</strong></div><span>{VERIFIED_TAG}</span><a href="/team-share">이전 자료와 비교</a></footer>

      {selected ? (
        <div className="adaptive-share-lightbox" role="dialog" aria-modal="true" aria-label={`${selected.title} 확대 보기`}>
          <button aria-label="확대 화면 닫기" className="adaptive-share-lightbox-backdrop" onClick={() => setSelected(null)} />
          <section><header><div><span>{selected.eyebrow}</span><strong>{selected.title}</strong></div><button aria-label="확대 화면 닫기" onClick={() => setSelected(null)}><X size={18} /></button></header><img src={selected.image} alt={selected.alt} /></section>
        </div>
      ) : null}
    </main>
  );
}

function CaptureCard({ capture, onOpen }: { capture: Capture; onOpen: (capture: Capture) => void }) {
  return <article className="adaptive-share-capture-card"><figure><button type="button" onClick={() => onOpen(capture)} aria-label={`${capture.title} 확대 보기`}><img src={capture.image} alt={capture.alt} /><span><Maximize2 size={13} /> 원본 보기</span></button></figure><div><span>{capture.eyebrow}</span><h3>{capture.title}</h3><p>{capture.description}</p><small><CheckCircle2 size={12} />{capture.status}</small></div></article>;
}

function StatusColumn({ title, tone, items }: { title: string; tone: string; items: string[] }) {
  return <article className={`adaptive-share-status ${tone}`}><header><span>{title}</span><strong>{items.length}</strong></header><ul>{items.map((item) => <li key={item}><CheckCircle2 size={13} />{item}</li>)}</ul></article>;
}
