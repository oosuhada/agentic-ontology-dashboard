import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  ButtonGroup,
  Callout,
  Card,
  HTMLSelect,
  Icon,
  Navbar,
  NavbarDivider,
  NavbarGroup,
  NavbarHeading,
  Tag,
} from "@blueprintjs/core";
import {
  ontologyPath,
  blueprintProjectPath,
  blueprintV2ProjectPath,
  projectDashboardPath,
} from "../../routing";
import type { AuthUser } from "../../types";
import { useAuth } from "../auth/AuthContext";
import "./blueprint-comparison.css";

type VersionId = "original" | "v1" | "v2";
type LayoutId = "triple" | "original-v1" | "v1-v2" | "original-v2";

interface BlueprintComparisonPageProps {
  projectId: string;
}

interface PreviewVersion {
  id: VersionId;
  label: string;
  shortLabel: string;
  path: string;
  intent: "none" | "primary" | "success";
  summary: string;
  characteristics: string[];
}

interface ComparisonScenario {
  id: "overview" | "objects" | "analysis" | "operations";
  eyebrow: string;
  title: string;
  description: string;
  guidance: string;
  paths: Record<VersionId, string>;
  summaries: Record<VersionId, string>;
}

const VIEWPORTS = {
  desktop: { label: "Desktop · 1440 × 900", width: 1440, height: 900 },
  laptop: { label: "Laptop · 1280 × 800", width: 1280, height: 800 },
  tablet: { label: "Tablet · 1024 × 768", width: 1024, height: 768 },
} as const;

type ViewportId = keyof typeof VIEWPORTS;

const LAYOUT_VERSIONS: Record<LayoutId, VersionId[]> = {
  triple: ["original", "v1", "v2"],
  "original-v1": ["original", "v1"],
  "v1-v2": ["v1", "v2"],
  "original-v2": ["original", "v2"],
};

const RUBRIC = [
  {
    criterion: "첫 화면의 중심",
    original: "운영 보고서와 선택 설비 설명",
    v1: "역할별 KPI와 Workbench 진입",
    v2: "Object Table과 즉시 실행 가능한 작업",
  },
  {
    criterion: "시각적 밀도",
    original: "여백과 서술이 많은 보고서형",
    v1: "카드형 Dashboard와 도구 UI의 혼합",
    v2: "Toolbar·Table·Inspector 중심의 고밀도 UI",
  },
  {
    criterion: "탐색 구조",
    original: "제품 Navigation → 보고서 상세",
    v1: "Overview·Objects·Analysis·Operations",
    v2: "Application·Object Type·Saved Set Navigator",
  },
  {
    criterion: "선택 항목 편집",
    original: "보고서 내부 정보 패널",
    v1: "선택 상태에 따라 바뀌는 우측 Inspector",
    v2: "Properties·Actions·History 고정 Inspector",
  },
  {
    criterion: "주요 사용 목적",
    original: "결과를 읽고 판단 근거 확인",
    v1: "조회·분석·운영 Workflow 통합",
    v2: "Object를 선택하고 바로 분석·Action 실행",
  },
] as const;

type ComparisonHostWindow = Window & {
  __ONTOLOGY_COMPARISON_USER__?: AuthUser | null;
};

const READY_SELECTORS: Record<VersionId, string> = {
  original: ".od-workbench-main, .ontology-dashboard-shell, .fd-route-shell",
  v1: ".blueprint-preview:not(.blueprint-loading)",
  v2: ".blueprint-v2:not(.blueprint-v2-loading) .bpv2-shell",
};

function embeddedComparisonPath(path: string) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("comparison_embed", "1");
  return `${url.pathname}${url.search}${url.hash}`;
}

export function BlueprintComparisonPage({ projectId }: BlueprintComparisonPageProps) {
  const { user } = useAuth();
  // Same-origin comparison frames inherit the already validated parent identity.
  // This avoids 15 independent /auth/me bootstrap requests and login fallbacks.
  (window as ComparisonHostWindow).__ONTOLOGY_COMPARISON_USER__ = user;
  const [layout, setLayout] = useState<LayoutId>("triple");
  const [viewportId, setViewportId] = useState<ViewportId>("desktop");
  const [reloadKey, setReloadKey] = useState(0);

  const versions = useMemo<PreviewVersion[]>(() => [
    {
      id: "original",
      label: "V1 · 기존 Dashboard",
      shortLabel: "V1",
      path: projectDashboardPath(projectId),
      intent: "none",
      summary: "운영 보고서와 설비 판단 근거를 읽는 현재 제품 화면",
      characteristics: ["Report-first", "Narrative", "Current production"],
    },
    {
      id: "v1",
      label: "V2 · Blueprint 1차",
      shortLabel: "V2",
      path: blueprintProjectPath(projectId),
      intent: "primary",
      summary: "기존 디자인 언어에 Blueprint 컴포넌트와 Workbench 구조를 결합",
      characteristics: ["Dashboard-first", "Four workspaces", "Card layout"],
    },
    {
      id: "v2",
      label: "V3 · Blueprint 2차",
      shortLabel: "V3",
      path: blueprintV2ProjectPath(projectId),
      intent: "success",
      summary: "Blueprint의 고밀도 도구형 UI를 전면 적용한 Object 중심 Workbench",
      characteristics: ["Object-first", "Dense table", "Fixed inspector"],
    },
  ], [projectId]);

  const scenarios = useMemo<ComparisonScenario[]>(() => {
    const workspaceId = "manufacturing-demo";
    return [
      {
        id: "overview",
        eyebrow: "PAGE 01 · OVERVIEW",
        title: "첫 화면과 운영 개요 비교",
        description: "로그인 직후 무엇을 가장 먼저 보여주는지 비교합니다. V3는 별도 Overview 카드 대신 Object 업무 화면을 첫 화면으로 사용합니다.",
        guidance: "첫 질문, KPI 우선순위, 설명량과 다음 작업으로 이동하는 속도를 확인하세요.",
        paths: {
          original: `${projectDashboardPath(projectId)}?view=dashboard`,
          v1: `${blueprintProjectPath(projectId)}?view=overview`,
          v2: `${blueprintV2ProjectPath(projectId)}?view=objects`,
        },
        summaries: {
          original: "현재 제품의 역할별 Dashboard와 운영 보고 Context",
          v1: "KPI·위험 Portfolio·Decision Inbox 중심 Overview",
          v2: "별도 Hero 없이 Object Table을 바로 여는 Object-first landing",
        },
      },
      {
        id: "objects",
        eyebrow: "PAGE 02 · OBJECTS",
        title: "Object Explorer 비교",
        description: "설비 Object를 검색하고 선택한 뒤 Property와 Action에 도달하는 흐름을 비교합니다.",
        guidance: "검색·필터의 위치, Table 밀도, 선택 행 표현과 Inspector 접근성을 확인하세요.",
        paths: {
          original: ontologyPath(projectId, workspaceId),
          v1: `${blueprintProjectPath(projectId)}?view=objects`,
          v2: `${blueprintV2ProjectPath(projectId)}?view=objects&inspector=properties`,
        },
        summaries: {
          original: "기존 Foundry Shell 안의 Ontology Object Explorer",
          v1: "가상화 Object Set과 동적 Inspector를 결합한 Explorer",
          v2: "고정 Navigator·Dense Table·Properties Inspector의 3분할",
        },
      },
      {
        id: "analysis",
        eyebrow: "PAGE 03 · ANALYSIS",
        title: "Analysis Workbench 비교",
        description: "동일 제조 위험 데이터를 어떤 분석 구조와 시각화 작업 흐름으로 제공하는지 비교합니다.",
        guidance: "데이터 흐름의 가시성, Graph·Canvas 구분, Parameter와 결과의 연결을 확인하세요.",
        paths: {
          original: `${projectDashboardPath(projectId)}?view=analysis`,
          v1: `${blueprintProjectPath(projectId)}?view=analysis&mode=graph`,
          v2: `${blueprintV2ProjectPath(projectId)}?view=analysis`,
        },
        summaries: {
          original: "기존 Risk Event 분석 경로와 Analysis Workbench",
          v1: "React Flow Typed Card Graph와 별도 Canvas",
          v2: "Transformation step 목록과 결과 Canvas를 한 화면에 결합",
        },
      },
      {
        id: "operations",
        eyebrow: "PAGE 04 · OPERATIONS",
        title: "운영 판단과 Action 비교",
        description: "위험 Event를 읽고 검사 요청·정지 검토·담당자 배정으로 이어지는 운영 흐름을 비교합니다.",
        guidance: "판단 근거와 실행 버튼의 거리, Activity·Audit 확인 가능성과 역할 맥락을 확인하세요.",
        paths: {
          original: `${projectDashboardPath(projectId)}?view=report`,
          v1: `${blueprintProjectPath(projectId)}?view=operations`,
          v2: `${blueprintV2ProjectPath(projectId)}?view=operations&inspector=actions`,
        },
        summaries: {
          original: "서술형 운영 Briefing과 보고서 기반 판단",
          v1: "Decision Inbox·상세 판단·Activity의 3개 Panel Workflow",
          v2: "Dense Queue·Decision Detail·Action Inspector 중심 Workflow",
        },
      },
    ];
  }, [projectId]);

  const visibleVersions = LAYOUT_VERSIONS[layout]
    .map((id) => versions.find((version) => version.id === id))
    .filter((version): version is PreviewVersion => Boolean(version));
  const viewport = VIEWPORTS[viewportId];

  return (
    <main className="blueprint-comparison-page bp6-dark">
      <Navbar className="comparison-navbar">
        <NavbarGroup align="left">
          <div className="comparison-mark"><Icon icon="comparison" size={18} /></div>
          <NavbarHeading>Blueprint UI 비교실</NavbarHeading>
          <NavbarDivider />
          <Tag minimal>{projectId}</Tag>
          <Tag intent="primary" minimal>V1 · V2 · V3</Tag>
        </NavbarGroup>
        <NavbarGroup align="right">
          <Button icon="refresh" onClick={() => setReloadKey((value) => value + 1)}>모두 새로고침</Button>
          <Button icon="dashboard" intent="primary" onClick={() => window.open(blueprintV2ProjectPath(projectId), "_blank")}>V3 전체 화면</Button>
        </NavbarGroup>
      </Navbar>

      <nav className="comparison-page-links" aria-label="버전 및 비교 페이지 바로가기">
        <div className="comparison-version-links">
          {versions.map((version) => (
            <Button
              key={version.id}
              icon="open-application"
              intent={version.intent}
              onClick={() => window.open(version.path, "_blank")}
            >
              {version.label} 열기
            </Button>
          ))}
        </div>
        <NavbarDivider />
        <div className="comparison-workflow-links">
          <Button minimal onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>첫 화면</Button>
          <Button minimal onClick={() => document.getElementById("comparison-overview")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Overview</Button>
          <Button minimal onClick={() => document.getElementById("comparison-objects")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Objects</Button>
          <Button minimal onClick={() => document.getElementById("comparison-analysis")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Analysis</Button>
          <Button minimal onClick={() => document.getElementById("comparison-operations")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Operations</Button>
        </div>
      </nav>

      <header className="comparison-intro">
        <div>
          <span className="comparison-eyebrow">LIVE · SAME DATA · SAME VIRTUAL VIEWPORT</span>
          <h1>세 화면을 같은 조건에서 비교하세요</h1>
          <p>각 미리보기는 실제 서비스 화면입니다. 선택한 가상 화면 크기를 각 iframe에 동일하게 적용하고 패널 폭에 맞춰 축소합니다.</p>
        </div>
        <Callout compact icon="info-sign" title="판단 포인트">
          색상보다 첫 화면의 중심, 정보 밀도, 탐색 방식, Inspector와 Action의 접근성을 비교하는 것이 핵심입니다.
        </Callout>
      </header>

      <section className="comparison-controls" aria-label="비교 화면 설정">
        <div className="comparison-control-group">
          <span>비교 조합</span>
          <ButtonGroup>
            <Button active={layout === "triple"} onClick={() => setLayout("triple")}>3개 전체</Button>
            <Button active={layout === "original-v1"} onClick={() => setLayout("original-v1")}>V1 ↔ V2</Button>
            <Button active={layout === "v1-v2"} onClick={() => setLayout("v1-v2")}>V2 ↔ V3</Button>
            <Button active={layout === "original-v2"} onClick={() => setLayout("original-v2")}>V1 ↔ V3</Button>
          </ButtonGroup>
        </div>
        <div className="comparison-control-group">
          <span>동일 가상 화면</span>
          <HTMLSelect
            value={viewportId}
            onChange={(event) => setViewportId(event.currentTarget.value as ViewportId)}
            options={Object.entries(VIEWPORTS).map(([value, item]) => ({ value, label: item.label }))}
          />
        </div>
        <div className="comparison-control-note">
          <Icon icon="zoom-to-fit" />
          <span>{viewport.width}×{viewport.height} 화면을 각 패널에 맞춰 축소 표시</span>
        </div>
      </section>

      <section className={`comparison-live-grid is-${visibleVersions.length}`}>
        {visibleVersions.map((version) => (
          <LivePreview
            key={`${version.id}-${reloadKey}-${viewportId}`}
            version={version}
            viewport={viewport}
          />
        ))}
      </section>

      <section className="comparison-scenarios" aria-labelledby="scenario-comparison-title">
        <div className="comparison-scenarios-header">
          <div>
            <span className="comparison-eyebrow">PAGE-BY-PAGE REVIEW</span>
            <h2 id="scenario-comparison-title">아래에서 각 작업 화면을 따로 비교하세요</h2>
            <p>첫 화면 한 장만 비교하지 않고, 실제 업무 흐름을 구성하는 네 페이지를 동일한 데이터와 가상 화면 크기로 나란히 표시합니다.</p>
          </div>
          <ButtonGroup className="comparison-scenario-jumps">
            {scenarios.map((scenario) => (
              <Button
                key={scenario.id}
                onClick={() => document.getElementById(`comparison-${scenario.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" })}
              >
                {scenario.id === "overview" ? "Overview" : scenario.id === "objects" ? "Objects" : scenario.id === "analysis" ? "Analysis" : "Operations"}
              </Button>
            ))}
          </ButtonGroup>
        </div>

        {scenarios.map((scenario) => (
          <article key={scenario.id} id={`comparison-${scenario.id}`} className="comparison-scenario-section">
            <div className="comparison-scenario-heading">
              <div>
                <span className="comparison-eyebrow">{scenario.eyebrow}</span>
                <h3>{scenario.title}</h3>
                <p>{scenario.description}</p>
              </div>
              <Callout compact icon="eye-open" title="이 화면에서 볼 것">{scenario.guidance}</Callout>
            </div>
            <div className="comparison-live-grid is-3 comparison-scenario-grid">
              {versions.map((version) => (
                <LivePreview
                  key={`${scenario.id}-${version.id}-${reloadKey}-${viewportId}`}
                  version={{
                    ...version,
                    path: scenario.paths[version.id],
                    summary: scenario.summaries[version.id],
                  }}
                  viewport={viewport}
                  defer
                  titlePrefix={scenario.title}
                />
              ))}
            </div>
          </article>
        ))}
      </section>

      <section className="comparison-analysis-section">
        <div className="comparison-section-heading">
          <div>
            <span className="comparison-eyebrow">STRUCTURE REVIEW</span>
            <h2>화면 구조 비교표</h2>
          </div>
          <Tag minimal>실제 화면을 본 뒤 아래 기준으로 판단</Tag>
        </div>
        <div className="comparison-rubric-scroll">
          <table className="comparison-rubric">
            <thead><tr><th>비교 기준</th><th>V1 · 기존 Dashboard</th><th>V2 · Blueprint 1차</th><th>V3 · Blueprint 2차</th></tr></thead>
            <tbody>
              {RUBRIC.map((row) => (
                <tr key={row.criterion}>
                  <th>{row.criterion}</th>
                  <td>{row.original}</td>
                  <td>{row.v1}</td>
                  <td>{row.v2}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

    </main>
  );
}

function LivePreview({
  version,
  viewport,
  defer = false,
  titlePrefix,
}: {
  version: PreviewVersion;
  viewport: { width: number; height: number; label: string };
  defer?: boolean;
  titlePrefix?: string;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [scale, setScale] = useState(0.4);
  const [ready, setReady] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [loadSignal, setLoadSignal] = useState(0);
  const [active, setActive] = useState(!defer);
  const embeddedPath = embeddedComparisonPath(version.path);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const update = () => setScale(Math.min(1, stage.clientWidth / viewport.width));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [viewport.width]);

  useEffect(() => {
    if (!defer || active) return;
    const stage = stageRef.current;
    if (!stage) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setActive(true);
        observer.disconnect();
      }
    }, { rootMargin: "40px 0px", threshold: 0.15 });
    observer.observe(stage);
    return () => observer.disconnect();
  }, [active, defer]);

  useEffect(() => {
    if (!active || loadSignal === 0) return;
    setReady(false);
    setTimedOut(false);
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      try {
        const document = iframeRef.current?.contentDocument;
        if (document?.querySelector(READY_SELECTORS[version.id])) {
          setReady(true);
          setTimedOut(false);
          window.clearInterval(timer);
          return;
        }
      } catch {
        // Same-origin is required; keep the protected loading surface if unavailable.
      }
      if (attempts >= 100) {
        setTimedOut(true);
        window.clearInterval(timer);
      }
    }, 200);
    return () => window.clearInterval(timer);
  }, [active, loadSignal, version.id, embeddedPath]);

  return (
    <Card className="comparison-preview-card" elevation={1}>
      <div className="comparison-preview-header">
        <div>
          <div className="comparison-preview-title">
            <Tag intent={version.intent}>{version.shortLabel}</Tag>
            <strong>{version.label}</strong>
          </div>
          <p>{version.summary}</p>
        </div>
        <ButtonGroup minimal>
          <Button icon="share" onClick={() => window.open(version.path, "_blank")} aria-label={`${version.label} 새 창에서 열기`} />
        </ButtonGroup>
      </div>
      <div className="comparison-characteristics">
        {version.characteristics.map((item) => <Tag key={item} minimal>{item}</Tag>)}
      </div>
      <div
        ref={stageRef}
        className="comparison-frame-stage"
        style={{ height: Math.round(viewport.height * scale) }}
      >
        {!ready ? (
          <div className="comparison-frame-loading">
            <Icon icon={active && !timedOut ? "refresh" : "download"} />
            <span>{!active ? "아래로 이동하면 비교 화면 로드" : timedOut ? "비교 화면 준비가 지연되고 있습니다" : "인증된 비교 화면 준비 중"}</span>
            {timedOut ? <Button small icon="refresh" onClick={() => setLoadSignal((value) => value + 1)}>다시 확인</Button> : null}
          </div>
        ) : null}
        {active ? (
          <iframe
            ref={iframeRef}
            title={titlePrefix ? `${titlePrefix} · ${version.label} live preview` : `${version.label} live preview`}
            src={embeddedPath}
            width={viewport.width}
            height={viewport.height}
            loading={defer ? "lazy" : "eager"}
            onLoad={() => setLoadSignal((value) => value + 1)}
            className={ready ? "is-ready" : ""}
            style={{ transform: `scale(${scale})` }}
          />
        ) : null}
      </div>
      <footer className="comparison-preview-footer">
        <span><Icon icon="desktop" /> {viewport.label}</span>
        <span><Icon icon="zoom-to-fit" /> {Math.round(scale * 100)}%</span>
        <code>{version.path}</code>
      </footer>
    </Card>
  );
}
