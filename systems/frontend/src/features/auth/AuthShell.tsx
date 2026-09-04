import { navigate } from "../../routing";
import { useEffect, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, BarChart3, ClipboardCheck, FileText, Gauge, LockKeyhole, MapPinned, ShieldCheck, Wrench } from "lucide-react";
import { DisplayMenu } from "../../ui/foundry/DisplayMenu";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { HanbitLogo } from "../../ui/foundry/HanbitLogo";

const PRODUCT_STORIES = [
  {
    eyebrow: { ko: "실시간 공장 상태", en: "LIVE FACTORY STATUS" },
    title: { ko: "이상 설비를 위치와 알림으로 먼저 찾습니다.", en: "Find abnormal equipment by location and alert first." },
    detail: {
      ko: "구역·셀 단위 설비 상태와 새 알림 수를 한 화면에서 보고, 클릭 한 번으로 해당 Event와 센서 근거까지 내려갑니다.",
      en: "See zone- and cell-level equipment status and new alerts in one view, then drill into the Event and sensor evidence in one click.",
    },
    visual: "factory" as const,
  },
  {
    eyebrow: { ko: "하나의 CASE · 역할별 구성", en: "ONE CASE · ROLE COMPOSED" },
    title: { ko: "같은 사건을 역할마다 필요한 깊이로 봅니다.", en: "See the same case at the depth each role needs." },
    detail: {
      ko: "엔지니어는 센서와 점검 근거, 운영 관리자는 생산 영향과 승인, 경영진은 KPI와 의사결정 병목을 같은 Case에서 확인합니다.",
      en: "Engineers review sensor and inspection evidence, operations managers review impact and approvals, and executives review KPI and decision bottlenecks from the same case.",
    },
    visual: "roles" as const,
  },
  {
    eyebrow: { ko: "추적 가능한 판단", en: "TRACEABLE DECISION" },
    title: { ko: "Event에서 Outcome까지 판단 근거가 끊기지 않습니다.", en: "Decision evidence stays connected from Event to Outcome." },
    detail: {
      ko: "Evidence → Decision → Action → Maintenance → Outcome을 하나의 lineage로 연결해 누가 왜 무엇을 판단했는지 추적할 수 있습니다.",
      en: "Evidence → Decision → Action → Maintenance → Outcome stays in one lineage so users can trace who decided what and why.",
    },
    visual: "lineage" as const,
  },
  {
    eyebrow: { ko: "근거 기반 보고", en: "GROUNDED REPORTING" },
    title: { ko: "보고서는 별도 문서가 아니라 업무 흐름의 산출물입니다.", en: "Reports are workflow artifacts, not detached documents." },
    detail: {
      ko: "현재 Case의 검증된 근거와 조치 결과를 바탕으로 역할별 보고 언어를 만들고, snapshot 기준을 유지한 채 경영 보고로 전환합니다.",
      en: "Turn verified case evidence and outcomes into role-specific reporting while preserving the evidence snapshot used for the decision.",
    },
    visual: "report" as const,
  },
] as const;

function ProductStoryVisual({ kind, english }: { kind: (typeof PRODUCT_STORIES)[number]["visual"]; english: boolean }) {
  if (kind === "factory") return <div className="auth-story-factory" aria-hidden="true">
    {[0, 1, 2, 3].map((zone) => {
      const alertCount = zone === 1 ? 3 : zone === 3 ? 1 : 0;
      return <section key={zone}>
        <header>
          <strong>{english ? `Zone ${zone + 1}` : `${zone + 1}구역`}</strong>
          <span>{alertCount > 0 ? (english ? `${alertCount} alerts` : `알림 ${alertCount}`) : (english ? "Normal" : "정상")}</span>
        </header>
        <div>{[0, 1, 2, 3, 4].map((cell) => {
          const critical = zone === 1 && cell === 2;
          const warning = zone === 3 && cell === 1;
          return <span key={cell} className={critical ? "critical" : warning ? "warning" : "normal"}>
            <small>{english ? `Cell ${cell + 1}` : `${cell + 1}셀`}</small>
            <em>{critical ? (english ? "Critical" : "긴급") : warning ? (english ? "Attention" : "주의") : (english ? "Normal" : "정상")}</em>
          </span>;
        })}</div>
      </section>;
    })}
  </div>;
  if (kind === "roles") return <div className="auth-story-roles" aria-hidden="true">
    <article><MapPinned size={17} /><strong>{english ? "Engineer" : "엔지니어"}</strong><span>{english ? "Sensors · Inspection evidence" : "센서 · 점검 근거"}</span></article>
    <article><ClipboardCheck size={17} /><strong>{english ? "Operations" : "운영 관리"}</strong><span>{english ? "Production impact · Approval" : "생산 영향 · 승인"}</span></article>
    <article><BarChart3 size={17} /><strong>{english ? "Executive" : "경영진"}</strong><span>{english ? "KPI · Decision bottleneck" : "KPI · 의사결정 병목"}</span></article>
  </div>;
  if (kind === "lineage") {
    const steps = english ? [
      ["Event", "Tool-wear risk detected"],
      ["Evidence", "Sensor and model basis"],
      ["Decision", "Inspection approved"],
      ["Action", "Inspect and maintain"],
      ["Outcome", "Re-predict and verify"],
    ] : [
      ["사건", "공구 마모 위험 감지"],
      ["근거", "센서·모델 근거"],
      ["판단", "점검·정비 승인"],
      ["실행", "현장 점검·정비"],
      ["결과", "재예측·효과 확인"],
    ];
    return <div className="auth-story-lineage" aria-hidden="true">
      {steps.map(([label, example], index) => <span key={label}><i>{index + 1}</i><strong>{label}</strong><small>{example}</small></span>)}
    </div>;
  }
  return <div className="auth-story-report" aria-hidden="true"><FileText size={30} /><div><strong>{english ? "Executive Brief" : "경영 보고"}</strong><span>{english ? "Risk 72% · 4 Decision Cases" : "위험도 72% · 판단 Case 4건"}</span><span>{english ? "Production exposure · Maintenance outcome" : "생산 영향 · 정비 효과"}</span></div><em>{english ? "AS-OF" : "기준 시점"}</em></div>;
}

export function AuthShell({
  eyebrow,
  title,
  description,
  showDescription = true,
  showTraceabilityNote = true,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  showDescription?: boolean;
  showTraceabilityNote?: boolean;
  children: React.ReactNode;
}) {
  const { locale } = useI18n();
  const english = locale === "en-US";
  const [storyIndex, setStoryIndex] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setStoryIndex((current) => (current + 1) % PRODUCT_STORIES.length), 6500);
    return () => window.clearInterval(timer);
  }, []);

  const story = PRODUCT_STORIES[storyIndex];
  const moveStory = (direction: -1 | 1) => setStoryIndex((current) => (current + direction + PRODUCT_STORIES.length) % PRODUCT_STORIES.length);

  return (
    <main className="auth-page">
      <header className="auth-platform-bar">
        <button className="auth-brand" onClick={() => navigate("/login")}><span className="brand-mark hanbit-brand-mark"><HanbitLogo /></span><span><strong>Hanbit Tech</strong><small>Reliability Operations</small></span></button>
        <div><DisplayMenu className="auth-display-menu" /><span><Activity size={13} /> {english ? "Monitoring live" : "실시간 모니터링"}</span><span><ShieldCheck size={13} /> {english ? "Decision traceable" : "판단 근거 추적"}</span><span>Asia/Seoul</span></div>
      </header>
      <div className="auth-control-plane">
        <aside className="auth-resource-context">
          <header><span><Activity size={20} /></span><div><strong>{english ? "Connect equipment risk to operational decisions" : "설비 리스크를 운영 의사결정으로 연결"}</strong><small>Live status → Decision Case → Outcome</small></div></header>
          <section className={`auth-product-story${story.visual === "report" ? " has-value-strip" : ""}`} aria-roledescription="carousel" aria-label={english ? "Product capabilities" : "제품 주요 기능"}>
            <div className="auth-story-copy" key={story.eyebrow.en}>
              <span className="section-label">{english ? story.eyebrow.en : story.eyebrow.ko}</span>
              <h1>{english ? story.title.en : story.title.ko}</h1>
              <p>{english ? story.detail.en : story.detail.ko}</p>
            </div>
            <ProductStoryVisual kind={story.visual} english={english} />
            {story.visual === "report" ? <section className="auth-value-strip">
              <span><Gauge size={15} /><strong>Live</strong><small>{english ? "Live equipment status" : "실시간 설비 상태"}</small></span>
              <span><ShieldCheck size={15} /><strong>Traceable</strong><small>{english ? "Evidence-based decisions" : "근거 기반 판단"}</small></span>
              <span><Wrench size={15} /><strong>Closed loop</strong><small>{english ? "Maintenance outcomes" : "정비 결과 확인"}</small></span>
            </section> : null}
            <footer className="auth-story-controls">
              <div>{PRODUCT_STORIES.map((item, index) => <button type="button" key={item.eyebrow.en} className={index === storyIndex ? "is-active" : ""} onClick={() => setStoryIndex(index)} aria-label={english ? `Product story ${index + 1}` : `${index + 1}번째 제품 소개`} aria-current={index === storyIndex ? "true" : undefined} />)}</div>
              <span><button type="button" onClick={() => moveStory(-1)} aria-label={english ? "Previous" : "이전"}><ArrowLeft size={14} /></button><button type="button" onClick={() => moveStory(1)} aria-label={english ? "Next" : "다음"}><ArrowRight size={14} /></button></span>
            </footer>
          </section>
        </aside>
        <section className="auth-panel">
          <div className="auth-card">
            <div className="auth-card-heading"><span><LockKeyhole size={18} /></span><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>
            {showDescription ? <p className="auth-description">{description}</p> : null}
            {children}
            {showTraceabilityNote ? <footer><ShieldCheck size={12} /><span>{english
              ? "Monitoring follows the latest observation, while Decision Cases and Executive Briefs stay tied to the evidence snapshot used for the decision."
              : "Monitoring은 최신 관측을 따르고, Decision Case와 Executive Brief는 선택한 근거 snapshot을 기준으로 추적합니다."}</span></footer> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
