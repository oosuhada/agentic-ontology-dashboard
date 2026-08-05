import {
  ArrowRight,
  BarChart3,
  Boxes,
  CheckCircle2,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  LayoutDashboard,
  Maximize2,
  Network,
  Settings2,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

import signupRoleRequest from "../../../../docs/00-team-onboarding/assets/screenshots/01-signup-role-request.png";
import adminConfirmation from "../../../../docs/00-team-onboarding/assets/screenshots/04-admin-role-permission-confirmation.png";
import managerReport from "../../../../docs/00-team-onboarding/assets/screenshots/05-manager-report-home.png";
import engineerDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/07-engineer-dashboard-home.png";
import personalizedDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/09-personalized-dashboard-display-settings.png";
import factoryDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/10-factory-adaptive-dashboard.png";
import fleetDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/11-fleet-adaptive-dashboard.png";
import compressorDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/12-compressor-adaptive-dashboard.png";
import analysisCanvas from "../../../../docs/00-team-onboarding/assets/screenshots/13-analysis-canvas.png";
import analysisGraph from "../../../../docs/00-team-onboarding/assets/screenshots/14-analysis-dependency-graph.png";
import ontologySelection from "../../../../docs/00-team-onboarding/assets/screenshots/15-ontology-objectset-selection.png";

const CAPTURE_ROOT = "/team-share-adaptive-assets";
const VERIFIED_TAG = "team-share-adaptive-complete-integrity-20260805";
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

const foundationCaptures: Capture[] = [
  {
    id: "signup",
    eyebrow: "GOVERNED ONBOARDING",
    title: "구성원이 희망 역할을 요청하고 승인 대기 상태로 등록됩니다",
    description: "조직·업무 이메일·희망 역할을 입력해도 계정은 즉시 활성화되지 않습니다. Tenant Admin이 역할과 scope를 확정하기 전까지 로그인은 차단됩니다.",
    image: signupRoleRequest,
    alt: "역할을 선택하는 회원가입 화면",
    status: "pending approval · tenant admin self-request blocked",
  },
  {
    id: "admin",
    eyebrow: "IDENTITY · RBAC · SCOPE",
    title: "관리자가 역할, Project·Workspace와 개별 권한을 확정합니다",
    description: "역할 기본 권한에 더해 사용자별 allow·deny override를 적용하고, 승인 변경은 감사 가능한 기록으로 남깁니다.",
    image: adminConfirmation,
    alt: "관리자 역할과 권한 승인 화면",
    status: "organization → project → workspace isolation",
  },
  {
    id: "manager",
    eyebrow: "REPORT-FIRST DECISION FLOW",
    title: "운영 매니저와 임원은 근거가 연결된 보고서에서 시작합니다",
    description: "임원 요약, 위험·영향·조치, Evidence field, 차트와 A4 출력 레이아웃을 먼저 읽고 필요할 때 상세 Dashboard로 내려갑니다.",
    image: managerReport,
    alt: "운영 매니저 보고서 첫 화면",
    status: "report → evidence → dashboard → decision",
  },
  {
    id: "engineer",
    eyebrow: "DASHBOARD-FIRST OPERATIONS",
    title: "엔지니어와 실무자는 운영 Dashboard에서 분석을 시작합니다",
    description: "위험 설비, 원인 기여, 이벤트와 권장 조치를 확인하고 Ontology·Analysis·Report로 근거를 확장합니다.",
    image: engineerDashboard,
    alt: "엔지니어 역할 Dashboard",
    status: "dashboard → ontology → analysis → report",
  },
];

const adaptiveCaptures: Capture[] = [
  {
    id: "personalization",
    eyebrow: "PERSONAL WORKSPACE",
    title: "같은 역할에서도 사용자별 Layout·Filter·Display를 복원합니다",
    description: "Board 위치와 크기, 즐겨찾기, 필터, 시각화, 글자 크기와 density를 사용자·Workspace·Template 단위로 저장합니다.",
    image: personalizedDashboard,
    alt: "개인 Dashboard와 Display 설정",
    status: "role default + isolated personal preference",
  },
  {
    id: "factory",
    eyebrow: "FACTORY RELIABILITY",
    title: "제조 Dataset은 설비 위험과 생산 영향 중심 화면을 만듭니다",
    description: "Operations KPI, Risk Trend, Factor Contribution, Priority List, Event Grid와 관계·조치 Board를 조합합니다.",
    image: factoryDashboard,
    alt: "Factory Reliability 적응형 Dashboard",
    status: "schema signal → board catalog → role layout",
  },
  {
    id: "fleet",
    eyebrow: "FLEET MAINTENANCE",
    title: "차량 Dataset은 정비 우선순위와 운행 영향 중심으로 바뀝니다",
    description: "같은 템플릿에 데이터만 교체하지 않고 Impact Summary, Maintenance Priority, Activity Stream과 Route·Service 흐름을 선택합니다.",
    image: fleetDashboard,
    alt: "Fleet Maintenance 적응형 Dashboard",
    status: "different dataset · different board definitions",
  },
  {
    id: "compressor",
    eyebrow: "COMPRESSOR TELEMETRY",
    title: "연속 센서 Dataset은 대형 시계열과 이상 구간 중심으로 구성됩니다",
    description: "Sensor Line Chart, Anomaly Timeline, Model Details, Evidence Table, Data Quality Warning과 Preventive Action을 배치합니다.",
    image: compressorDashboard,
    alt: "Compressor Monitoring 적응형 Dashboard",
    status: "telemetry-first composition",
  },
];

const workbenchCaptures: Capture[] = [
  {
    id: "analysis-canvas",
    eyebrow: "ANALYSIS AUTHORING",
    title: "계산 정의와 표현 배치를 분리한 자유 Canvas를 제공합니다",
    description: "Typed DataPill, compatible next action, multiple canvas, 카드 이동·크기 조절과 숨겨진 계산 노드를 지원합니다.",
    image: analysisCanvas,
    alt: "Analysis 자유 Canvas",
    status: "typed nodes · reusable analysis definition",
  },
  {
    id: "analysis-graph",
    eyebrow: "LINEAGE · DEPENDENCY",
    title: "같은 Analysis를 Dependency Graph로 추적합니다",
    description: "동일한 서버 nodes·edges를 Path, Canvas와 Graph로 투영해 upstream·downstream과 focus chain을 확인합니다.",
    image: analysisGraph,
    alt: "Analysis Dependency Graph",
    status: "one graph contract · multiple projections",
  },
  {
    id: "ontology",
    eyebrow: "ONTOLOGY OBJECTSET",
    title: "객체 집합을 조합하고 연결 관계를 탐색합니다",
    description: "Replace·Union·Intersection·Difference로 ObjectSet을 만들고 여러 root의 linked traversal 결과를 병합합니다.",
    image: ontologySelection,
    alt: "Ontology ObjectSet 선택 화면",
    status: "object · link · action context",
  },
];

const upgradeCaptures: Capture[] = [
  {
    id: "runtime",
    eyebrow: "CANONICAL V3.1 RUNTIME",
    title: "Dataset Version과 Result Artifact가 운영 Dashboard에 연결됩니다",
    description: "V2/V3.1 버전 선택, provenance, release evidence, 최신 위험 자산과 PostgreSQL 기반 replay를 한 화면에서 확인합니다.",
    image: `${CAPTURE_ROOT}/01-v3-runtime-dashboard.png`,
    alt: "Predictive Maintenance V3.1 운영 Dashboard",
    status: "65/65 canonical release checks",
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
    status: "request → approve → activate → rollback",
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
  "가입 승인·세션·RBAC·Project/Workspace scope",
  "역할별 Report-first·Dashboard-first landing",
  "Dataset 적응형 Board Catalog와 사용자 개인화",
  "Analysis Canvas·Dependency Graph·Ontology ObjectSet",
  "Canonical V3.1 package·Dataset Version·Result Artifact",
  "CSV·TSV·XLSX governed intake와 immutable Dataset Version",
  "Ontology Mapping·Feature Recipe·Feature Dataset lineage",
  "Chronological experiment와 validation-only selection",
  "Model Registry·release approval·atomic activation·rollback",
  "Prediction Result와 non-causal Explanation Artifact",
  "PostgreSQL JSONB·RLS·tenant/project/workspace isolation",
  "Desktop·tablet·mobile visual regression",
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
        <a className="adaptive-share-brand" href="#overview"><span>OD</span><div><strong>Ontology Dashboard</strong><small>Complete project + V3.1/Adaptive Modeling</small></div></a>
        <nav aria-label="Complete team share sections">
          <a href="#foundation">Foundation</a><a href="#adaptive">Adaptive UI</a><a href="#workbenches">Workbenches</a><a href="#runtime">V3.1</a><a href="#modeling">Modeling</a><a href="#status">Status</a>
        </nav>
        <div><a href="/team-share">2026-08-04 기록</a><a className="primary" href={APP_ROUTE}>앱 열기 <ArrowRight size={13} /></a></div>
      </header>

      <section className="adaptive-share-hero" id="overview">
        <div>
          <span className="adaptive-share-kicker"><Sparkles size={14} /> COMPLETE PROJECT STORY · VERIFIED 2026-08-05</span>
          <h1>가입과 역할별 업무부터<br />V3.1 모델 승인까지 한 페이지에서</h1>
          <p>Ontology Dashboard의 기존 선행 프로토타입과 이후 추가된 Predictive Maintenance V3.1·Adaptive Modeling을 하나의 제품 흐름으로 통합했습니다. 이 페이지 하나만 읽어도 프로젝트 목적, 사용자 경험, 데이터·온톨로지·분석·시각화·모델 governance와 현재 한계를 파악할 수 있습니다.</p>
          <div className="adaptive-share-actions"><a className="primary" href="#foundation">전체 프로젝트 보기 <ArrowRight size={14} /></a><a href="/team-share-adaptive.html">독립 HTML 열기 <ExternalLink size={13} /></a></div>
          <div className="adaptive-share-integrity"><ShieldCheck size={14} /><strong>{VERIFIED_TAG}</strong><span>16 verified feature captures</span><span>loader-free screenshots</span></div>
        </div>
        <div className="adaptive-share-product-map" aria-label="Ontology Dashboard complete product flow">
          <article><Users /><strong>Identity & Role</strong><small>approval · RBAC · scope</small></article><ArrowRight />
          <article><Database /><strong>Dataset Version</strong><small>schema · quality · provenance</small></article><ArrowRight />
          <article><Boxes /><strong>Ontology</strong><small>object · link · action</small></article><ArrowRight />
          <article><GitBranch /><strong>Analysis & Model</strong><small>lineage · experiment</small></article><ArrowRight />
          <article><LayoutDashboard /><strong>Dashboard & Report</strong><small>role · dataset · user</small></article><ArrowRight />
          <article><UserCheck /><strong>Governed Action</strong><small>approval · audit · rollback</small></article>
        </div>
        <div className="adaptive-share-metrics">
          <span><strong>8</strong><small>업무 역할</small></span>
          <span><strong>3</strong><small>Dataset 적응형 사례</small></span>
          <span><strong>16</strong><small>통합 기능 캡처</small></span>
          <span><strong>65/65</strong><small>Canonical V3.1 verifier</small></span>
        </div>
      </section>

      <section className="adaptive-share-section" id="foundation">
        <header><span>01 · PRODUCT FOUNDATION</span><h2>조직 가입부터 역할별 첫 업무까지 서버 계약으로 연결합니다</h2><p>역할은 메뉴 표시 여부만 바꾸지 않습니다. 승인 방식, 첫 화면, 정보 우선순위, 편집 가능 범위와 Project·Workspace scope를 결정합니다.</p></header>
        <div className="adaptive-share-feature-grid two-by-two">
          {foundationCaptures.map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
        <div className="adaptive-share-role-map" aria-label="Role experience summary">
          <article><ShieldCheck /><div><strong>Tenant Admin</strong><span>Control Plane · identity · scope · audit</span></div></article>
          <article><FileText /><div><strong>Manager · Executive · Auditor</strong><span>Report-first · evidence review · decision</span></div></article>
          <article><LayoutDashboard /><div><strong>Engineer · Technician · FDE</strong><span>Dashboard-first · ontology · analysis · report</span></div></article>
          <article><BarChart3 /><div><strong>ML Validator</strong><span>Experiment evaluation · release request</span></div></article>
        </div>
      </section>

      <section className="adaptive-share-section alt" id="adaptive">
        <header><span>02 · DATASET-ADAPTIVE EXPERIENCE</span><h2>Dataset와 사용자가 바뀌면 화면 종류와 배치도 바뀝니다</h2><p>고정 Dashboard 템플릿에 값만 바꾸는 방식이 아니라 schema·시간·수치·범주·관계·품질 신호로 Board Catalog를 조합하고, 이후 사용자 개인 설정을 격리해 저장합니다.</p></header>
        <div className="adaptive-share-feature-grid two-by-two">
          {adaptiveCaptures.map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
        <div className="adaptive-share-chain"><span>Dataset schema</span><ArrowRight /><span>Semantic signals</span><ArrowRight /><span>Board selection</span><ArrowRight /><span>Role layout</span><ArrowRight /><span>Personal preference</span></div>
      </section>

      <section className="adaptive-share-section" id="workbenches">
        <header><span>03 · ANALYSIS & ONTOLOGY WORKBENCHES</span><h2>결과 화면이 어디서 왔는지 구성하고 추적합니다</h2><p>Dashboard와 Report는 최종 표현입니다. Analysis는 계산과 lineage를 정의하고 Ontology는 업무 객체와 관계, Action context를 제공합니다.</p></header>
        <div className="adaptive-share-feature-grid three">
          {workbenchCaptures.map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
      </section>

      <section className="adaptive-share-section alt" id="runtime">
        <header><span>04 · PREDICTIVE MAINTENANCE V3.1</span><h2>운영 Dashboard와 replay가 같은 immutable Dataset Version을 가리킵니다</h2><p>버전, checksum, model, task, Result Artifact schema와 graph readiness를 분리해 표시하며, 현재 결과와 과거 replay를 혼동하지 않습니다.</p></header>
        <div className="adaptive-share-feature-grid">
          {upgradeCaptures.slice(0, 2).map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
      </section>

      <section className="adaptive-share-section" id="modeling">
        <header><span>05 · GOVERNED ADAPTIVE MODELING</span><h2>모델 성능보다 먼저 lineage와 승인 가능성을 검증합니다</h2><p>실험 결과가 좋아도 Dataset·Mapping·Recipe·Feature Dataset·artifact checksum이 맞지 않으면 release를 요청할 수 없습니다. 선택자와 승인자도 분리합니다.</p></header>
        <div className="adaptive-share-feature-grid three">
          {upgradeCaptures.slice(2).map((capture) => <CaptureCard key={capture.id} capture={capture} onOpen={setSelected} />)}
        </div>
        <div className="adaptive-share-evidence">
          <article><span>DATA</span><strong>360 → 360</strong><p>Source rows와 accepted rows. quarantine 0, equipment 3, derived features 4.</p></article>
          <article><span>MODEL SELECTION</span><strong>AP 0.5882</strong><p>Logistic Regression validation AP. Dummy baseline AP 0.2917.</p></article>
          <article><span>HELD-OUT TEST</span><strong>AP 0.5003</strong><p>선택된 후보 한 건에만 test를 사용했으며 selection에는 사용하지 않았습니다.</p></article>
          <article><span>THRESHOLD</span><strong>0.33</strong><p>Validation recall 0.9524. FN cost 10, FP cost 1 정책 근거.</p></article>
        </div>
        <div className="adaptive-share-chain"><span>Intake</span><ArrowRight /><span>Manifest</span><ArrowRight /><span>Mapping</span><ArrowRight /><span>Feature</span><ArrowRight /><span>Experiment</span><ArrowRight /><span>Registry</span><ArrowRight /><span>Prediction</span><ArrowRight /><span>Explanation</span></div>
      </section>

      <section className="adaptive-share-section alt" id="status">
        <header><span>06 · DELIVERY STATUS</span><h2>완료, 검토, 추가 작업을 같은 수준으로 표시하지 않습니다</h2><p>동작하는 prototype·local release와 strict production readiness를 명확히 구분합니다.</p></header>
        <div className="adaptive-share-status-grid">
          <StatusColumn title="완료" tone="complete" items={completed} />
          <StatusColumn title="검토 필요" tone="review" items={needsReview} />
          <StatusColumn title="추가 작업" tone="next" items={nextWork} />
        </div>
        <div className="adaptive-share-production"><Network size={20} /><div><strong>Strict production release는 외부 인프라로 blocked</strong><p>Production PostgreSQL, Redis, Neo4j, Project 3, OIDC, object storage, OTLP와 optional LightGBM·XGBoost·SHAP 구성이 필요합니다.</p></div></div>
      </section>

      <footer className="adaptive-share-footer"><div><Settings2 size={16} /><strong>Ontology Dashboard · Complete Project Story</strong></div><span>{VERIFIED_TAG}</span><a href="/team-share">2026-08-04 기록 보기</a></footer>

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
