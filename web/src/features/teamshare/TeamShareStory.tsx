import {
  ArrowDown,
  ArrowRight,
  BarChart3,
  Boxes,
  CheckCircle2,
  Database,
  FileText,
  GitBranch,
  LayoutDashboard,
  Network,
  Printer,
  Settings2,
  ShieldCheck,
  Sparkles,
  UserCheck,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { navigate } from "../../routing";

import signupRoleRequest from "../../../../docs/00-team-onboarding/assets/screenshots/01-signup-role-request.png";
import pendingApproval from "../../../../docs/00-team-onboarding/assets/screenshots/02-pending-approval.png";
import adminNotification from "../../../../docs/00-team-onboarding/assets/screenshots/03-admin-signup-notification.png";
import adminConfirmation from "../../../../docs/00-team-onboarding/assets/screenshots/04-admin-role-permission-confirmation.png";
import managerReport from "../../../../docs/00-team-onboarding/assets/screenshots/05-manager-report-home.png";
import managerDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/06-manager-dashboard-drilldown.png";
import engineerDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/07-engineer-dashboard-home.png";
import engineerReport from "../../../../docs/00-team-onboarding/assets/screenshots/08-engineer-report-editor.png";
import personalizedDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/09-personalized-dashboard-display-settings.png";
import factoryDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/10-factory-adaptive-dashboard.png";
import fleetDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/11-fleet-adaptive-dashboard.png";
import compressorDashboard from "../../../../docs/00-team-onboarding/assets/screenshots/12-compressor-adaptive-dashboard.png";
import analysisCanvas from "../../../../docs/00-team-onboarding/assets/screenshots/13-analysis-canvas.png";
import analysisGraph from "../../../../docs/00-team-onboarding/assets/screenshots/14-analysis-dependency-graph.png";
import ontologySelection from "../../../../docs/00-team-onboarding/assets/screenshots/15-ontology-objectset-selection.png";

type FlowId = "signup" | "approval" | "role-home" | "report" | "adaptive" | "personal";
type RoleId = "admin" | "manager" | "engineer";
type DatasetId = "factory" | "fleet" | "compressor";

const flowSteps: Array<{
  id: FlowId;
  number: string;
  title: string;
  actor: string;
  description: string;
  implementation: string[];
  image: string;
  imageAlt: string;
}> = [
  {
    id: "signup",
    number: "01",
    title: "회사 구성원이 가입하고 희망 역할을 요청합니다",
    actor: "신규 사용자",
    description: "조직명과 업무 이메일, 희망 역할을 입력하면 계정은 즉시 활성화되지 않고 승인 대기 상태로 저장됩니다.",
    implementation: ["requested_role_code 저장", "pending_approval 상태", "승인 전 로그인 차단"],
    image: signupRoleRequest,
    imageAlt: "희망 역할을 선택하는 회원가입 화면",
  },
  {
    id: "approval",
    number: "02",
    title: "관리자가 알림을 받고 역할·범위·권한을 확정합니다",
    actor: "조직 관리자",
    description: "신규 가입 알림에서 요청 역할을 확인한 뒤 실제 역할, Project·Workspace 범위와 사용자별 권한 허용·차단을 결정합니다.",
    implementation: ["영속 관리자 알림", "역할 변경", "permission override", "승인 감사 기록"],
    image: adminConfirmation,
    imageAlt: "관리자가 역할과 권한을 확정하는 화면",
  },
  {
    id: "role-home",
    number: "03",
    title: "역할에 따라 로그인 첫 화면이 달라집니다",
    actor: "전체 사용자",
    description: "운영 매니저·임원은 보고서에서 시작하고, 엔지니어·실무자는 Dashboard에서 시작합니다. 마지막 방문 화면보다 역할별 landing 정책이 우선합니다.",
    implementation: ["manager → Reports", "engineer → Dashboards", "admin → Control Plane"],
    image: managerReport,
    imageAlt: "운영 매니저의 보고서 메인 화면",
  },
  {
    id: "report",
    number: "04",
    title: "실무자가 근거 기반 보고서를 작성하고 관리자가 검토합니다",
    actor: "엔지니어 → 매니저",
    description: "실무자는 Dashboard와 Ontology에서 근거를 확인하고 보고서의 제목·요약·섹션을 수정합니다. 매니저는 같은 공용 revision과 연결된 차트를 읽은 뒤 상세 Dashboard로 내려갑니다.",
    implementation: ["공유 report revision", "evidence field citation", "시계열·기여 요인 연동", "Dashboard drill-down"],
    image: engineerReport,
    imageAlt: "엔지니어가 보고서를 편집하는 화면",
  },
  {
    id: "adaptive",
    number: "05",
    title: "Dataset schema가 화면 종류와 배치를 바꿉니다",
    actor: "Adaptive composition engine",
    description: "시간·수치·범주·관계·문서·품질 신호를 분석해 검증된 Board Catalog에서 필요한 화면을 선택합니다. 데이터만 바꾸는 고정 Template이 아닙니다.",
    implementation: ["schema signal 추론", "Board definition 교체", "Tab·배치 생성", "개인화 이후 덮어쓰기 방지"],
    image: compressorDashboard,
    imageAlt: "센서 시계열 중심의 Compressor 적응형 Dashboard",
  },
  {
    id: "personal",
    number: "06",
    title: "각 사용자의 화면 설정은 다음 로그인에도 복원됩니다",
    actor: "개별 사용자",
    description: "같은 역할이라도 Board 위치·크기·즐겨찾기·필터·차트와 Display 설정을 사용자 계정 단위로 저장합니다.",
    implementation: ["user + workspace + template 저장", "자동 저장", "동일 역할 사용자 격리", "다른 기기 Display 복원"],
    image: personalizedDashboard,
    imageAlt: "개인 Dashboard와 Display 설정 화면",
  },
];

const roles: Record<RoleId, {
  label: string;
  eyebrow: string;
  headline: string;
  description: string;
  firstView: string;
  capabilities: string[];
  image: string;
}> = {
  admin: {
    label: "조직 관리자",
    eyebrow: "GOVERNED ONBOARDING",
    headline: "가입 요청과 접근 범위를 통제합니다",
    description: "일반 업무 화면과 분리된 Control Plane에서 사용자 상태, 역할, Workspace scope와 permission override를 관리합니다.",
    firstView: "Admin Control Plane",
    capabilities: ["가입 알림", "역할·Scope 승인", "개별 권한 허용·차단", "감사 기록"],
    image: adminNotification,
  },
  manager: {
    label: "운영 매니저·임원",
    eyebrow: "REPORT-FIRST DECISION FLOW",
    headline: "설명과 근거를 먼저 읽고 세부 Dashboard로 이동합니다",
    description: "실무자가 원래 작성해야 했던 운영 보고서를 메인 화면으로 제공하고, 텍스트와 시각화가 같은 Evidence를 참조합니다.",
    firstView: "Operational Reports",
    capabilities: ["보고서 검토", "근거 차트", "위험·영향 요약", "상세 Dashboard drill-down"],
    image: managerReport,
  },
  engineer: {
    label: "엔지니어·실무자",
    eyebrow: "DASHBOARD-FIRST WORKFLOW",
    headline: "전체 운영 Dashboard에서 분석하고 보고서를 작성합니다",
    description: "Dataset과 Ontology Object를 탐색하고 Analysis를 구성한 뒤, 검토한 근거를 공용 Report revision으로 저장합니다.",
    firstView: "Adaptive Dashboard",
    capabilities: ["Dashboard 분석", "Ontology 탐색", "Analysis 작성", "보고서 편집"],
    image: engineerDashboard,
  },
};

const datasets: Record<DatasetId, {
  label: string;
  entity: string;
  focus: string;
  boards: string[];
  composition: string;
  image: string;
}> = {
  factory: {
    label: "Factory Reliability",
    entity: "Equipment · Production line",
    focus: "고장 위험과 생산 영향",
    boards: ["Operations KPI", "Risk Trend", "Factor Contribution", "Priority List", "Ontology Relationship"],
    composition: "7:5 위험·원인 중심 구성",
    image: factoryDashboard,
  },
  fleet: {
    label: "Fleet Maintenance",
    entity: "Vehicle · Service · Route",
    focus: "정비 우선순위와 운행 영향",
    boards: ["Impact Summary", "Maintenance Priority", "Fleet Event Grid", "Activity Stream", "Planner Assistant"],
    composition: "12-column 전사 요약 + 4:4:4 운영 카드",
    image: fleetDashboard,
  },
  compressor: {
    label: "Compressor Monitoring",
    entity: "Telemetry · Pressure · Anomaly",
    focus: "연속 센서와 이상 구간",
    boards: ["Sensor Line Chart", "Anomaly Timeline", "Model Details", "Evidence Table", "Data Quality Warning"],
    composition: "8:4 대형 시계열 + 이상 탐지 구성",
    image: compressorDashboard,
  },
};

const capabilityGroups = [
  {
    icon: ShieldCheck,
    title: "Identity & Governance",
    detail: "가입 승인, 세션, RBAC, Project·Workspace scope, 사용자별 권한 override",
    status: "API + DB",
  },
  {
    icon: FileText,
    title: "Role Reports",
    detail: "실무자 편집, 공용 revision, Evidence citation, 매니저 검토와 Dashboard drill-down",
    status: "API + DB",
  },
  {
    icon: LayoutDashboard,
    title: "Adaptive Dashboards",
    detail: "Dataset schema signal에 따른 Board 종류·Tab·배치·기본 시각화 자동 구성",
    status: "Runtime",
  },
  {
    icon: Settings2,
    title: "Personal Preferences",
    detail: "사용자별 Layout·Filter·Visualization·Display 설정 자동 저장과 복원",
    status: "API + DB",
  },
  {
    icon: GitBranch,
    title: "Analysis Workbench",
    detail: "Typed Path, 자유 Canvas, Dependency Graph, Forecast editor, Dataset materialization",
    status: "Mixed",
  },
  {
    icon: Network,
    title: "Ontology Workbench",
    detail: "ObjectSet 선택, 집합 연산, linked traversal, Graph와 Agent context 연결",
    status: "API + UI",
  },
];

function Screenshot({ src, alt, label }: { src: string; alt: string; label: string }) {
  return (
    <figure className="team-share-screenshot">
      <figcaption>{label}</figcaption>
      <a href={src} target="_blank" rel="noreferrer">
        <img src={src} alt={alt} />
      </a>
    </figure>
  );
}

export function TeamShareStory() {
  const [activeFlow, setActiveFlow] = useState<FlowId>("signup");
  const [activeRole, setActiveRole] = useState<RoleId>("manager");
  const [activeDataset, setActiveDataset] = useState<DatasetId>("factory");

  const flow = useMemo(() => flowSteps.find((item) => item.id === activeFlow) ?? flowSteps[0], [activeFlow]);
  const role = roles[activeRole];
  const dataset = datasets[activeDataset];

  return (
    <main className="team-share-story-page">
      <header className="team-share-story-header">
        <div className="team-share-brand"><span>OD</span><div><strong>Ontology Dashboard</strong><small>Team handoff story · verified prototype</small></div></div>
        <nav aria-label="Team handoff sections">
          <a href="#user-flow">User flow</a>
          <a href="#roles">Role experience</a>
          <a href="#adaptive">Adaptive UI</a>
          <a href="#capabilities">Implementation</a>
        </nav>
        <div className="team-share-header-actions">
          <button type="button" onClick={() => window.print()}><Printer size={13} /> Print</button>
          <button type="button" className="primary" onClick={() => navigate("/login")}>Open application <ArrowRight size={13} /></button>
        </div>
      </header>

      <section className="team-share-hero">
        <div className="team-share-hero-copy">
          <span className="team-share-kicker"><Sparkles size={13} /> PROJECT PREBUILD · TEAM REVIEW</span>
          <h1>데이터를 보여주는 Dashboard가 아니라,<br />업무 설명과 근거, 분석과 행동을 연결합니다.</h1>
          <p>프로젝트 시작 전에 사용자 흐름과 제품 경계를 실제 동작으로 검증한 선행 프로토타입입니다. 역할, Dataset, 개인 설정이 화면의 모양과 첫 업무를 결정합니다.</p>
          <div className="team-share-hero-actions">
            <a href="#user-flow">전체 사용자 흐름 보기 <ArrowDown size={13} /></a>
            <button type="button" onClick={() => navigate("/reference")}>Analysis UI reference</button>
          </div>
          <div className="team-share-metrics">
            <span><strong>8</strong><small>업무 역할</small></span>
            <span><strong>3</strong><small>적응형 Dataset 사례</small></span>
            <span><strong>15</strong><small>검증 캡처</small></span>
            <span><strong>34</strong><small>핵심 자동 테스트</small></span>
          </div>
        </div>
        <div className="team-share-product-loop" aria-label="Ontology Dashboard product loop">
          <div className="loop-center"><Boxes size={26} /><strong>Ontology</strong><small>Object · Link · Action</small></div>
          <div className="loop-node node-dataset"><Database size={17} /><span>Dataset</span></div>
          <div className="loop-node node-analysis"><GitBranch size={17} /><span>Analysis</span></div>
          <div className="loop-node node-dashboard"><LayoutDashboard size={17} /><span>Dashboard</span></div>
          <div className="loop-node node-report"><FileText size={17} /><span>Report</span></div>
          <div className="loop-node node-action"><UserCheck size={17} /><span>Action</span></div>
          <svg viewBox="0 0 520 400" aria-hidden="true"><ellipse cx="260" cy="200" rx="204" ry="142" /><path d="M156 68l18 5-12 14" /><path d="M445 185l-4 18-16-8" /><path d="M325 336l-18-4 10-15" /></svg>
        </div>
      </section>

      <section className="team-share-section" id="user-flow">
        <header className="team-share-section-heading">
          <div><span>01 · USER FLOW</span><h2>가입부터 개인화된 업무 화면까지</h2></div>
          <p>각 단계는 UI만 존재하는 것이 아니라 서버 저장과 권한 계약으로 연결됩니다.</p>
        </header>
        <div className="team-share-flow-switcher" role="tablist" aria-label="User flow stages">
          {flowSteps.map((step, index) => (
            <button type="button" key={step.id} className={activeFlow === step.id ? "active" : ""} onClick={() => setActiveFlow(step.id)} role="tab" aria-selected={activeFlow === step.id}>
              <b>{step.number}</b><span>{step.title}</span>{index < flowSteps.length - 1 ? <ArrowRight size={12} /> : null}
            </button>
          ))}
        </div>
        <article className="team-share-flow-detail">
          <div className="team-share-flow-copy">
            <span className="team-share-actor"><Users size={13} /> {flow.actor}</span>
            <h3>{flow.title}</h3>
            <p>{flow.description}</p>
            <div className="team-share-contract-list">
              {flow.implementation.map((item) => <span key={item}><CheckCircle2 size={12} />{item}</span>)}
            </div>
          </div>
          <Screenshot src={flow.image} alt={flow.imageAlt} label={`VERIFIED SCREEN · FLOW ${flow.number}`} />
        </article>
      </section>

      <section className="team-share-section alt" id="roles">
        <header className="team-share-section-heading">
          <div><span>02 · ROLE EXPERIENCE</span><h2>같은 데이터, 다른 첫 질문과 업무 화면</h2></div>
          <p>역할은 단순 메뉴 권한이 아니라 첫 화면, 정보 우선순위와 편집 가능 범위를 결정합니다.</p>
        </header>
        <div className="team-share-role-tabs" role="tablist" aria-label="Role experiences">
          {(Object.keys(roles) as RoleId[]).map((id) => <button type="button" role="tab" aria-selected={activeRole === id} className={activeRole === id ? "active" : ""} key={id} onClick={() => setActiveRole(id)}>{roles[id].label}</button>)}
        </div>
        <article className="team-share-role-detail">
          <Screenshot src={role.image} alt={`${role.label} 화면`} label={`${role.eyebrow} · ${role.firstView}`} />
          <div>
            <span className="team-share-kicker">{role.eyebrow}</span>
            <h3>{role.headline}</h3>
            <p>{role.description}</p>
            <dl>
              <div><dt>LOGIN LANDING</dt><dd>{role.firstView}</dd></div>
              <div><dt>PRIMARY WORK</dt><dd>{role.capabilities.join(" · ")}</dd></div>
            </dl>
            <div className="team-share-role-journey">
              {activeRole === "manager" ? <><span>Report</span><ArrowRight /><span>Evidence</span><ArrowRight /><span>Dashboard</span><ArrowRight /><span>Decision</span></> : null}
              {activeRole === "engineer" ? <><span>Dashboard</span><ArrowRight /><span>Ontology</span><ArrowRight /><span>Analysis</span><ArrowRight /><span>Report</span></> : null}
              {activeRole === "admin" ? <><span>Notification</span><ArrowRight /><span>Identity</span><ArrowRight /><span>Scope</span><ArrowRight /><span>Audit</span></> : null}
            </div>
          </div>
        </article>
      </section>

      <section className="team-share-section" id="adaptive">
        <header className="team-share-section-heading">
          <div><span>03 · DATASET-ADAPTIVE UI</span><h2>Dataset가 바뀌면 화면의 종류도 바뀝니다</h2></div>
          <p>Schema와 projection 신호로 검증된 Board Catalog를 조합합니다.</p>
        </header>
        <div className="team-share-dataset-tabs" role="tablist" aria-label="Adaptive dataset examples">
          {(Object.keys(datasets) as DatasetId[]).map((id) => <button type="button" role="tab" aria-selected={activeDataset === id} className={activeDataset === id ? "active" : ""} key={id} onClick={() => setActiveDataset(id)}><strong>{datasets[id].label}</strong><small>{datasets[id].focus}</small></button>)}
        </div>
        <article className="team-share-dataset-detail">
          <div className="team-share-dataset-copy">
            <span>{dataset.entity}</span>
            <h3>{dataset.label}</h3>
            <p>{dataset.composition}</p>
            <div className="team-share-board-pills">{dataset.boards.map((board) => <b key={board}>{board}</b>)}</div>
            <div className="team-share-schema-flow">
              <span>Dataset schema</span><ArrowRight /><span>Semantic signals</span><ArrowRight /><span>Board selection</span><ArrowRight /><span>Role layout</span>
            </div>
          </div>
          <Screenshot src={dataset.image} alt={`${dataset.label} 적응형 Dashboard`} label="DATASET-DRIVEN COMPOSITION" />
        </article>
      </section>

      <section className="team-share-section alt team-share-workbenches">
        <header className="team-share-section-heading">
          <div><span>04 · ANALYSIS & ONTOLOGY</span><h2>결과 화면을 넘어 분석과 관계 탐색까지</h2></div>
          <p>Dashboard에 표시할 결과가 어디서 왔는지 구성하고 추적하는 Workbench입니다.</p>
        </header>
        <div className="team-share-workbench-grid">
          <article><Screenshot src={analysisCanvas} alt="Analysis 자유 Canvas" label="ANALYSIS · FREE-FORM CANVAS" /><h3>계산 정의와 표현 배치를 분리</h3><p>Path·Canvas·Graph로 같은 nodes/edges를 다르게 보고, 여러 Canvas와 숨겨진 계산 노드를 관리합니다.</p></article>
          <article><Screenshot src={analysisGraph} alt="Analysis Dependency Graph" label="ANALYSIS · DEPENDENCY GRAPH" /><h3>결과의 upstream과 downstream 추적</h3><p>Typed metadata, compatible next actions, 계산 노드 접기와 Dependency panel을 제공합니다.</p></article>
          <article><Screenshot src={ontologySelection} alt="Ontology ObjectSet 선택" label="ONTOLOGY · OBJECTSET" /><h3>객체를 집합으로 만들고 관계를 탐색</h3><p>Replace·Union·Intersection·Difference로 대상을 구성하고 여러 root의 linked traversal을 병합합니다.</p></article>
        </div>
      </section>

      <section className="team-share-section" id="capabilities">
        <header className="team-share-section-heading">
          <div><span>05 · IMPLEMENTATION MAP</span><h2>화면 뒤에 연결된 실제 계약</h2></div>
          <p>모든 항목이 같은 완성 상태인 것처럼 보이지 않도록 연결 수준을 표시합니다.</p>
        </header>
        <div className="team-share-capability-grid">
          {capabilityGroups.map(({ icon: Icon, title, detail, status }) => (
            <article key={title}><div><Icon size={17} /><span>{status}</span></div><h3>{title}</h3><p>{detail}</p></article>
          ))}
        </div>
        <div className="team-share-architecture">
          <div><Database /><strong>Dataset Versions</strong><small>Schema · Quality · Projection</small></div><ArrowRight />
          <div><Boxes /><strong>Ontology</strong><small>Object · Link · Action</small></div><ArrowRight />
          <div><GitBranch /><strong>Analysis</strong><small>Typed nodes · lineage</small></div><ArrowRight />
          <div><LayoutDashboard /><strong>Dashboard</strong><small>Role + Dataset + User</small></div><ArrowRight />
          <div><FileText /><strong>Report</strong><small>Narrative + Evidence</small></div><ArrowRight />
          <div><UserCheck /><strong>Human action</strong><small>Decision · Audit</small></div>
        </div>
      </section>

      <section className="team-share-review">
        <div><span>TEAM REVIEW</span><h2>이 프로토타입에서 팀이 먼저 결정할 것</h2></div>
        <ol>
          <li><b>01</b><span><strong>핵심 사용자 흐름</strong><small>Report-first Manager와 Dashboard-first Practitioner를 제품 기준으로 채택할지</small></span></li>
          <li><b>02</b><span><strong>첫 Dataset과 Ontology</strong><small>실제 프로젝트에서 먼저 연결할 Dataset과 Object·Link 범위</small></span></li>
          <li><b>03</b><span><strong>초기 MVP Workbench</strong><small>Dashboard, Reports, Analysis, Ontology 중 초기 릴리스 범위</small></span></li>
          <li><b>04</b><span><strong>Ownership</strong><small>Frontend, Backend, Data, Ontology mapping과 검증 책임</small></span></li>
        </ol>
        <div className="team-share-review-actions"><button type="button" className="primary" onClick={() => navigate("/login")}>실제 앱 열기 <ArrowRight size={13} /></button><button type="button" onClick={() => navigate("/reference")}>Analysis reference</button></div>
      </section>

      <footer className="team-share-footer">
        <div><strong>Ontology Dashboard</strong><span>Organization → Project → Workspace → Role experience → Personal preference</span></div>
        <small>Team share package · verified 2026-08-03 · interactive HTML story</small>
      </footer>
    </main>
  );
}
