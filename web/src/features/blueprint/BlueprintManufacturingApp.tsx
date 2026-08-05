import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  ButtonGroup,
  Callout,
  Card,
  Checkbox,
  Divider,
  FormGroup,
  HTMLSelect,
  Icon,
  InputGroup,
  NumericInput,
  ProgressBar,
  Spinner,
  Switch,
  Tag,
  TextArea,
  Tooltip,
} from "@blueprintjs/core";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import ReactECharts from "echarts-for-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  getOntologyRegistry,
  getProject,
  getProjectEvents,
  getProjectWorkspaces,
  invokeOntologyAction,
  queryOntologyObjects,
} from "../../api";
import { navigate, ontologyPath, projectDashboardPath } from "../../routing";
import type { AppRole, EventSummary, Project, Workspace } from "../../types";
import type {
  ActionTypeDefinition,
  ObjectRecord,
  ObjectTypeDefinition,
  OntologyRegistry,
} from "../ontology/types";
import { useAuth } from "../auth/AuthContext";
import "./blueprint-manufacturing.css";

type BlueprintView = "overview" | "objects" | "analysis" | "operations";
type AnalysisMode = "graph" | "canvas";

interface BlueprintManufacturingAppProps {
  projectId: string;
}

interface ActivityItem {
  id: string;
  title: string;
  detail: string;
  timestamp: string;
  intent: "none" | "primary" | "success" | "warning" | "danger";
}

const ROLE_LABELS: Record<string, string> = {
  tenant_admin: "조직 관리자",
  executive_viewer: "운영 매니저·임원",
  process_manager: "공정 매니저",
  process_engineer: "공정 엔지니어",
  maintenance_technician: "정비 기술자",
  quality_auditor: "품질 감사자",
  ml_validator: "ML 검증자",
  fde: "FDE",
};

const VIEW_ITEMS: Array<{
  id: BlueprintView;
  label: string;
  icon: "dashboard" | "cube" | "diagram-tree" | "endorsed";
  description: string;
}> = [
  { id: "overview", label: "Overview", icon: "dashboard", description: "역할별 첫 화면과 운영 KPI" },
  { id: "objects", label: "Objects", icon: "cube", description: "Object Set 검색·필터·Action" },
  { id: "analysis", label: "Analysis", icon: "diagram-tree", description: "Typed Card Graph와 Canvas" },
  { id: "operations", label: "Operations", icon: "endorsed", description: "역할별 Inbox와 Workflow" },
];

const STATUS_INTENT: Record<string, "none" | "primary" | "success" | "warning" | "danger"> = {
  critical: "danger",
  warning: "warning",
  attention: "primary",
  data_quality_hold: "warning",
  normal: "success",
};

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function objectTitle(item: ObjectRecord | null) {
  if (!item) return "Object를 선택하세요";
  const display = item.properties.display_name ?? item.properties.name ?? item.properties.equipment_id ?? item.id;
  return String(display);
}

function eventTitle(event: EventSummary) {
  return `${event.equipment.display_name} · ${event.event_id}`;
}

function roleDefaultView(role: string): BlueprintView {
  if (role === "process_engineer" || role === "maintenance_technician") return "objects";
  if (role === "fde" || role === "ml_validator") return "analysis";
  if (role === "tenant_admin" || role === "quality_auditor") return "operations";
  return "overview";
}

function readBlueprintPreviewQuery() {
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view");
  const requestedMode = params.get("mode");
  return {
    view: requestedView === "overview" || requestedView === "objects" || requestedView === "analysis" || requestedView === "operations"
      ? requestedView as BlueprintView
      : null,
    mode: requestedMode === "graph" || requestedMode === "canvas" ? requestedMode as AnalysisMode : null,
  };
}

export function BlueprintManufacturingApp({ projectId }: BlueprintManufacturingAppProps) {
  const { user } = useAuth();
  const previewQuery = useMemo(readBlueprintPreviewQuery, []);
  const [project, setProject] = useState<Project | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [registry, setRegistry] = useState<OntologyRegistry | null>(null);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [objects, setObjects] = useState<ObjectRecord[]>([]);
  const [objectTotal, setObjectTotal] = useState(0);
  const [objectType, setObjectType] = useState("equipment");
  const [search, setSearch] = useState("");
  const [riskOnly, setRiskOnly] = useState(false);
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [view, setView] = useState<BlueprintView>(previewQuery.view ?? "overview");
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>(previewQuery.mode ?? "graph");
  const [selectedAnalysisNode, setSelectedAnalysisNode] = useState("source");
  const [activeRole, setActiveRole] = useState<AppRole>(() => {
    const candidate = user?.active_project_roles[0] ?? user?.roles[0] ?? "process_manager";
    return candidate as AppRole;
  });
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [compactDensity, setCompactDensity] = useState(true);
  const [loading, setLoading] = useState(true);
  const [objectLoading, setObjectLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [actionRunning, setActionRunning] = useState(false);
  const [actionNote, setActionNote] = useState("");
  const [riskThreshold, setRiskThreshold] = useState(0.6);
  const [activity, setActivity] = useState<ActivityItem[]>([
    {
      id: "preview-ready",
      title: "Blueprint 비교 화면 준비됨",
      detail: "기존 Dashboard와 분리된 UI 실험 경로입니다.",
      timestamp: new Date().toISOString(),
      intent: "primary",
    },
  ]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 820px)");
    const syncInspector = () => {
      if (media.matches) setInspectorOpen(false);
    };
    syncInspector();
    media.addEventListener("change", syncInspector);
    return () => media.removeEventListener("change", syncInspector);
  }, []);

  const availableRoles = useMemo(() => {
    const roles = user?.active_project_roles.length ? user.active_project_roles : user?.roles ?? [];
    return roles.filter((role): role is AppRole => role in ROLE_LABELS);
  }, [user]);

  const selectedObject = useMemo(
    () => objects.find((item) => item.id === selectedObjectId) ?? objects[0] ?? null,
    [objects, selectedObjectId],
  );
  const selectedEvent = useMemo(
    () => events.find((item) => item.event_id === selectedEventId) ?? events[0] ?? null,
    [events, selectedEventId],
  );
  const selectedTypeDefinition = useMemo(
    () => registry?.object_types.find((item) => item.id === objectType) ?? null,
    [objectType, registry],
  );
  const applicableActions = useMemo(
    () => (registry?.action_types ?? []).filter((item) => item.object_type === selectedObject?.object_type),
    [registry, selectedObject?.object_type],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getProject(projectId),
      getProjectWorkspaces(projectId),
      getOntologyRegistry(),
      getProjectEvents(projectId),
    ])
      .then(([projectPayload, workspacePayload, registryPayload, eventPayload]) => {
        if (cancelled) return;
        setProject(projectPayload);
        setWorkspaces(workspacePayload);
        setRegistry(registryPayload);
        setEvents(eventPayload);
        setWorkspaceId(projectPayload.default_workspace_id ?? workspacePayload[0]?.id ?? "manufacturing-demo");
        setSelectedEventId(eventPayload[0]?.event_id ?? "");
        const preferred = registryPayload.object_types.find((item) => item.id === "equipment")?.id
          ?? registryPayload.object_types[0]?.id
          ?? "equipment";
        setObjectType(preferred);
        if (!previewQuery.view) setView(roleDefaultView(activeRole));
        setError("");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Blueprint 화면 데이터를 불러오지 못했습니다."))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [previewQuery.view, projectId]);

  useEffect(() => {
    if (!workspaceId || !objectType) return;
    let cancelled = false;
    setObjectLoading(true);
    queryOntologyObjects({ workspace_id: workspaceId, object_type: objectType, search, limit: 200 })
      .then((payload) => {
        if (cancelled) return;
        setObjects(payload.items);
        setObjectTotal(payload.total);
        setSelectedObjectId((current) => payload.items.some((item) => item.id === current) ? current : payload.items[0]?.id ?? "");
        setError("");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Object Set을 불러오지 못했습니다."))
      .finally(() => !cancelled && setObjectLoading(false));
    return () => { cancelled = true; };
  }, [objectType, search, workspaceId]);

  const visibleObjects = useMemo(() => {
    if (!riskOnly) return objects;
    return objects.filter((item) => {
      const status = String(item.properties.status ?? item.properties.risk_band ?? "");
      const probability = Number(item.properties.failure_probability ?? 0);
      return status === "critical" || status === "warning" || probability >= riskThreshold;
    });
  }, [objects, riskOnly, riskThreshold]);

  const objectColumns = useMemo(() => {
    const propertyIds = selectedTypeDefinition?.properties.map((property) => property.id) ?? [];
    const preferred = ["display_name", "equipment_id", "line", "status", "failure_probability", "criticality", "assigned_engineer"];
    return [...preferred.filter((id) => propertyIds.includes(id)), ...propertyIds.filter((id) => !preferred.includes(id))].slice(0, 5);
  }, [selectedTypeDefinition]);

  const objectScrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: visibleObjects.length,
    getScrollElement: () => objectScrollRef.current,
    estimateSize: () => compactDensity ? 42 : 52,
    overscan: 8,
  });

  const kpis = useMemo(() => {
    const critical = events.filter((item) => item.status === "critical").length;
    const warning = events.filter((item) => item.status === "warning").length;
    const probabilities = events.map((item) => item.failure_probability).filter((value): value is number => value !== null);
    const average = probabilities.length ? probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length : 0;
    const downtime = events.reduce((sum, item) => sum + item.equipment.estimated_downtime_minutes, 0);
    return { critical, warning, average, downtime };
  }, [events]);

  const chartOption = useMemo(() => ({
    animationDuration: 350,
    tooltip: { trigger: "axis" },
    grid: { left: 48, right: 20, top: 28, bottom: 48 },
    xAxis: {
      type: "category",
      axisLabel: { color: "#abb3bf", interval: 0, rotate: events.length > 6 ? 24 : 0 },
      data: events.map((item) => item.equipment.display_name.replace("절삭 설비 ", "M-")),
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      axisLabel: { color: "#abb3bf", formatter: (value: number) => `${Math.round(value * 100)}%` },
      splitLine: { lineStyle: { color: "rgba(138,155,173,.16)" } },
    },
    series: [{
      name: "Failure probability",
      type: "bar",
      data: events.map((item) => ({
        value: item.failure_probability ?? 0,
        itemStyle: {
          color: item.status === "critical" ? "#cd4246" : item.status === "warning" ? "#d9822b" : "#2d72d2",
          borderRadius: [3, 3, 0, 0],
        },
      })),
    }],
  }), [events]);

  const analysisNodes = useMemo<Node[]>(() => [
    { id: "source", position: { x: 10, y: 100 }, data: { label: "Object Set\nEquipment" }, className: "bp-analysis-node bp-analysis-source" },
    { id: "filter", position: { x: 230, y: 100 }, data: { label: `Filter\nRisk ≥ ${Math.round(riskThreshold * 100)}%` }, className: "bp-analysis-node" },
    { id: "aggregate", position: { x: 450, y: 100 }, data: { label: "Aggregate\nLine × Status" }, className: "bp-analysis-node" },
    { id: "chart", position: { x: 670, y: 40 }, data: { label: "Chart\nRisk portfolio" }, className: "bp-analysis-node bp-analysis-result" },
    { id: "action", position: { x: 670, y: 180 }, data: { label: "Action Set\nInspection queue" }, className: "bp-analysis-node bp-analysis-action" },
  ], [riskThreshold]);
  const analysisEdges = useMemo<Edge[]>(() => [
    { id: "source-filter", source: "source", target: "filter", animated: true },
    { id: "filter-aggregate", source: "filter", target: "aggregate" },
    { id: "aggregate-chart", source: "aggregate", target: "chart" },
    { id: "aggregate-action", source: "aggregate", target: "action" },
  ], []);

  const switchRole = useCallback((role: AppRole) => {
    setActiveRole(role);
    setView(roleDefaultView(role));
    setActivity((items): ActivityItem[] => [{
      id: crypto.randomUUID(),
      title: `${ROLE_LABELS[role]} 관점으로 전환`,
      detail: "첫 화면, 우선순위, Action 가용 범위를 역할 기준으로 재구성했습니다.",
      timestamp: new Date().toISOString(),
      intent: "primary" as const,
    }, ...items].slice(0, 12));
  }, []);

  const runAction = useCallback(async (action: ActionTypeDefinition) => {
    if (!selectedObject || !workspaceId) return;
    setActionRunning(true);
    setError("");
    try {
      const result = await invokeOntologyAction({
        action_type: action.id,
        object_id: selectedObject.id,
        workspace_id: workspaceId,
        parameters: actionNote ? { note: actionNote } : {},
        idempotency_key: crypto.randomUUID(),
      });
      setNotice(`${action.display_name} 실행 완료 · ${result.invocation_id}`);
      setActivity((items): ActivityItem[] => [{
        id: String(result.invocation_id ?? crypto.randomUUID()),
        title: action.display_name,
        detail: `${objectTitle(selectedObject)} · 감사 기록 ${String(result.audit_id ?? "created")}`,
        timestamp: String(result.completed_at ?? new Date().toISOString()),
        intent: "success" as const,
      }, ...items].slice(0, 12));
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Action 실행에 실패했습니다.";
      setError(message);
      setActivity((items): ActivityItem[] => [{
        id: crypto.randomUUID(),
        title: `${action.display_name} 실행 실패`,
        detail: message,
        timestamp: new Date().toISOString(),
        intent: "danger" as const,
      }, ...items].slice(0, 12));
    } finally {
      setActionRunning(false);
    }
  }, [actionNote, selectedObject, workspaceId]);

  if (loading) {
    return (
      <main className="blueprint-preview blueprint-loading bp6-dark">
        <Spinner size={48} />
        <h1>Blueprint Workbench 구성 중</h1>
        <p>Project, Ontology, Object Set과 운영 Workflow를 불러오고 있습니다.</p>
      </main>
    );
  }

  return (
    <main className={`blueprint-preview bp6-dark ${compactDensity ? "is-compact" : ""}`}>
      <header className="bp-global-header">
        <div className="bp-brand-lockup">
          <div className="bp-product-mark"><Icon icon="polygon-filter" size={18} /></div>
          <div>
            <span>Ontology Dashboard</span>
            <strong>{project?.display_name ?? projectId}</strong>
          </div>
          <Tag intent="primary" minimal>Blueprint preview</Tag>
        </div>
        <div className="bp-header-context">
          <span className="bp-context-label">Workspace</span>
          <HTMLSelect
            value={workspaceId}
            onChange={(event) => setWorkspaceId(event.currentTarget.value)}
            options={workspaces.map((workspace) => ({ label: workspace.display_name, value: workspace.id }))}
          />
          <span className="bp-context-label">Role</span>
          <HTMLSelect
            value={activeRole}
            onChange={(event) => switchRole(event.currentTarget.value as AppRole)}
            options={availableRoles.map((role) => ({ label: ROLE_LABELS[role] ?? role, value: role }))}
          />
        </div>
        <div className="bp-header-actions">
          <Tooltip content="기존 화면과 같은 Project를 새 탭에서 엽니다.">
            <Button icon="comparison" onClick={() => window.open(projectDashboardPath(projectId), "_blank")}>기존 화면 비교</Button>
          </Tooltip>
          <Button icon="settings" minimal onClick={() => setInspectorOpen((current) => !current)} aria-label="Inspector toggle" />
        </div>
      </header>

      <section className="bp-comparison-banner">
        <Callout intent="primary" icon="info-sign" title="기존 Dashboard는 변경하지 않았습니다">
          현재 주소는 Blueprint 기반 비교 버전입니다. 원본 <code>{projectDashboardPath(projectId)}</code>과 기능·밀도·탐색 흐름을 나란히 검토할 수 있습니다.
        </Callout>
      </section>

      {error ? <Callout className="bp-page-message" intent="danger" icon="error" title="처리하지 못한 작업">{error}</Callout> : null}
      {notice ? <Callout className="bp-page-message" intent="success" icon="tick">{notice}<Button minimal small icon="cross" onClick={() => setNotice("")} aria-label="Dismiss notice" /></Callout> : null}

      <div className="bp-workbench-shell">
        <aside className="bp-left-rail" aria-label="Blueprint workbench navigation">
          <div className="bp-rail-section-label">WORKBENCH</div>
          {VIEW_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`bp-rail-item ${view === item.id ? "is-active" : ""}`}
              onClick={() => setView(item.id)}
            >
              <Icon icon={item.icon} size={16} />
              <span><strong>{item.label}</strong><small>{item.description}</small></span>
            </button>
          ))}
          <Divider />
          <div className="bp-rail-section-label">DISPLAY</div>
          <Switch checked={compactDensity} label="Compact density" onChange={(event) => setCompactDensity(event.currentTarget.checked)} />
          <Switch checked={inspectorOpen} label="Inspector" onChange={(event) => setInspectorOpen(event.currentTarget.checked)} />
          <div className="bp-rail-footer">
            <Button minimal icon="arrow-left" onClick={() => navigate(projectDashboardPath(projectId))}>원본으로 돌아가기</Button>
          </div>
        </aside>

        <section className="bp-main-surface">
          <div className="bp-surface-titlebar">
            <div>
              <span className="bp-eyebrow">{VIEW_ITEMS.find((item) => item.id === view)?.label.toUpperCase()}</span>
              <h1>{view === "overview" ? `${ROLE_LABELS[activeRole]} 운영 개요` : view === "objects" ? "Ontology Object Explorer" : view === "analysis" ? "Typed Analysis Workbench" : "Operational Workflow"}</h1>
              <p>{view === "overview" ? "역할에 따라 첫 질문과 정보 우선순위를 바꿉니다." : view === "objects" ? "Object Set을 필터링하고 관계·속성·Action을 한 흐름에서 처리합니다." : view === "analysis" ? "Graph에서 데이터 흐름을 구성하고 Canvas에서 결과를 배치합니다." : "Inbox에서 판단하고 Action과 감사 기록까지 연결합니다."}</p>
            </div>
            <ButtonGroup>
              <Button icon="refresh" onClick={() => window.location.reload()}>새로고침</Button>
              <Button intent="primary" icon="floppy-disk" onClick={() => setNotice("Blueprint preview 상태를 로컬 비교 설정으로 저장했습니다.")}>View 저장</Button>
            </ButtonGroup>
          </div>

          {view === "overview" ? (
            <OverviewSurface
              activeRole={activeRole}
              events={events}
              selectedEvent={selectedEvent}
              setSelectedEventId={setSelectedEventId}
              kpis={kpis}
              chartOption={chartOption}
              setView={setView}
            />
          ) : null}

          {view === "objects" ? (
            <ObjectExplorerSurface
              registry={registry}
              objectType={objectType}
              setObjectType={setObjectType}
              search={search}
              setSearch={setSearch}
              riskOnly={riskOnly}
              setRiskOnly={setRiskOnly}
              riskThreshold={riskThreshold}
              setRiskThreshold={setRiskThreshold}
              objectLoading={objectLoading}
              visibleObjects={visibleObjects}
              objectTotal={objectTotal}
              objectColumns={objectColumns}
              selectedObjectId={selectedObject?.id ?? ""}
              setSelectedObjectId={setSelectedObjectId}
              scrollRef={objectScrollRef}
              virtualizer={virtualizer}
              workspaceId={workspaceId}
              projectId={projectId}
            />
          ) : null}

          {view === "analysis" ? (
            <AnalysisSurface
              mode={analysisMode}
              setMode={setAnalysisMode}
              nodes={analysisNodes}
              edges={analysisEdges}
              selectedNode={selectedAnalysisNode}
              setSelectedNode={setSelectedAnalysisNode}
              riskThreshold={riskThreshold}
              setRiskThreshold={setRiskThreshold}
              events={events}
              chartOption={chartOption}
              kpis={kpis}
            />
          ) : null}

          {view === "operations" ? (
            <OperationsSurface
              activeRole={activeRole}
              availableRoles={availableRoles}
              switchRole={switchRole}
              events={events}
              selectedEvent={selectedEvent}
              setSelectedEventId={setSelectedEventId}
              activity={activity}
              setActivity={setActivity}
            />
          ) : null}
        </section>

        {inspectorOpen ? (
          <aside className="bp-inspector">
            <div className="bp-inspector-header">
              <div>
                <span className="bp-eyebrow">INSPECTOR</span>
                <strong>{view === "analysis" ? selectedAnalysisNode : view === "operations" ? selectedEvent ? eventTitle(selectedEvent) : "Event" : objectTitle(selectedObject)}</strong>
              </div>
              <Button minimal icon="cross" onClick={() => setInspectorOpen(false)} aria-label="Close inspector" />
            </div>
            {view === "analysis" ? (
              <AnalysisInspector selectedNode={selectedAnalysisNode} riskThreshold={riskThreshold} setRiskThreshold={setRiskThreshold} />
            ) : view === "operations" ? (
              <EventInspector selectedEvent={selectedEvent} />
            ) : (
              <ObjectInspector
                selectedObject={selectedObject}
                typeDefinition={selectedTypeDefinition}
                actions={applicableActions}
                actionNote={actionNote}
                setActionNote={setActionNote}
                actionRunning={actionRunning}
                runAction={runAction}
              />
            )}
          </aside>
        ) : null}
      </div>
    </main>
  );
}

function OverviewSurface({
  activeRole,
  events,
  selectedEvent,
  setSelectedEventId,
  kpis,
  chartOption,
  setView,
}: {
  activeRole: AppRole;
  events: EventSummary[];
  selectedEvent: EventSummary | null;
  setSelectedEventId: (id: string) => void;
  kpis: { critical: number; warning: number; average: number; downtime: number };
  chartOption: object;
  setView: (view: BlueprintView) => void;
}) {
  const roleFocus = activeRole === "process_engineer" || activeRole === "maintenance_technician"
    ? "내 담당 설비의 점검 우선순위"
    : activeRole === "tenant_admin"
      ? "승인·권한·데이터 준비 상태"
      : "라인 중단 영향과 의사결정 대기열";
  return (
    <div className="bp-surface-content">
      <Callout icon="predictive-analysis" title={`첫 질문 · ${roleFocus}`}>
        역할은 메뉴 권한뿐 아니라 첫 화면, KPI 순서, 편집 가능 범위와 추천 Action을 결정합니다.
      </Callout>
      <div className="bp-kpi-strip">
        <Card className="bp-kpi-card" compact><span>Critical</span><strong>{kpis.critical}</strong><Tag intent="danger" minimal>즉시 판단</Tag></Card>
        <Card className="bp-kpi-card" compact><span>Warning</span><strong>{kpis.warning}</strong><Tag intent="warning" minimal>점검 필요</Tag></Card>
        <Card className="bp-kpi-card" compact><span>Average risk</span><strong>{Math.round(kpis.average * 100)}%</strong><ProgressBar value={kpis.average} intent={kpis.average >= 0.6 ? "warning" : "primary"} /></Card>
        <Card className="bp-kpi-card" compact><span>Downtime impact</span><strong>{kpis.downtime.toLocaleString()}m</strong><Tag minimal>전체 Event</Tag></Card>
      </div>
      <div className="bp-overview-grid">
        <Card className="bp-panel bp-chart-panel">
          <div className="bp-panel-header"><div><span>RISK PORTFOLIO</span><strong>설비별 고장확률</strong></div><Button minimal icon="diagram-tree" onClick={() => setView("analysis")}>분석 열기</Button></div>
          <ReactECharts option={chartOption} style={{ height: 320 }} />
        </Card>
        <Card className="bp-panel bp-inbox-panel">
          <div className="bp-panel-header"><div><span>DECISION INBOX</span><strong>판단 대기 Event</strong></div><Tag>{events.length}</Tag></div>
          <div className="bp-event-list">
            {events.map((event) => (
              <button key={event.event_id} className={selectedEvent?.event_id === event.event_id ? "is-selected" : ""} onClick={() => setSelectedEventId(event.event_id)}>
                <Tag intent={STATUS_INTENT[event.status] ?? "none"} minimal>{event.status}</Tag>
                <span><strong>{event.equipment.display_name}</strong><small>{event.predicted_failure_type}</small></span>
                <b>{event.failure_probability === null ? "—" : `${Math.round(event.failure_probability * 100)}%`}</b>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function ObjectExplorerSurface({
  registry,
  objectType,
  setObjectType,
  search,
  setSearch,
  riskOnly,
  setRiskOnly,
  riskThreshold,
  setRiskThreshold,
  objectLoading,
  visibleObjects,
  objectTotal,
  objectColumns,
  selectedObjectId,
  setSelectedObjectId,
  scrollRef,
  virtualizer,
  workspaceId,
  projectId,
}: {
  registry: OntologyRegistry | null;
  objectType: string;
  setObjectType: (value: string) => void;
  search: string;
  setSearch: (value: string) => void;
  riskOnly: boolean;
  setRiskOnly: (value: boolean) => void;
  riskThreshold: number;
  setRiskThreshold: (value: number) => void;
  objectLoading: boolean;
  visibleObjects: ObjectRecord[];
  objectTotal: number;
  objectColumns: string[];
  selectedObjectId: string;
  setSelectedObjectId: (value: string) => void;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  virtualizer: ReturnType<typeof useVirtualizer<HTMLDivElement, Element>>;
  workspaceId: string;
  projectId: string;
}) {
  return (
    <div className="bp-surface-content bp-object-explorer">
      <Card className="bp-filter-bar">
        <FormGroup label="Object type" inline>
          <HTMLSelect
            value={objectType}
            onChange={(event) => setObjectType(event.currentTarget.value)}
            options={(registry?.object_types ?? []).map((item) => ({ label: item.display_name, value: item.id }))}
          />
        </FormGroup>
        <InputGroup leftIcon="search" value={search} placeholder="Property 또는 Object ID 검색" onChange={(event) => setSearch(event.currentTarget.value)} />
        <Checkbox checked={riskOnly} label="위험 Object만" onChange={(event) => setRiskOnly(event.currentTarget.checked)} />
        <NumericInput min={0} max={1} stepSize={0.05} minorStepSize={0.01} value={riskThreshold} onValueChange={(value) => setRiskThreshold(value)} disabled={!riskOnly} />
        <Button icon="filter-list" intent={riskOnly ? "primary" : "none"}>Object Set {visibleObjects.length}</Button>
        <Button icon="share" onClick={() => navigate(ontologyPath(projectId, workspaceId))}>전체 Explorer</Button>
      </Card>
      <Card className="bp-object-table-panel">
        <div className="bp-table-toolbar">
          <div><span className="bp-eyebrow">OBJECT SET</span><strong>{visibleObjects.length.toLocaleString()} visible / {objectTotal.toLocaleString()} total</strong></div>
          <ButtonGroup><Button icon="list">Table</Button><Button icon="grid-view" disabled>Cards</Button><Button icon="map" disabled>Map</Button></ButtonGroup>
        </div>
        <div className="bp-virtual-table-header">
          <span>Object</span>{objectColumns.map((column) => <span key={column}>{column.replaceAll("_", " ")}</span>)}
        </div>
        <div ref={scrollRef} className="bp-virtual-table-scroll">
          {objectLoading ? <div className="bp-inline-loading"><Spinner size={28} /> Object Set loading</div> : null}
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const item = visibleObjects[virtualRow.index];
              if (!item) return null;
              return (
                <button
                  key={item.id}
                  className={`bp-virtual-table-row ${selectedObjectId === item.id ? "is-selected" : ""}`}
                  style={{ transform: `translateY(${virtualRow.start}px)`, height: virtualRow.size }}
                  onClick={() => setSelectedObjectId(item.id)}
                >
                  <span><Icon icon="cube" size={14} /><strong>{objectTitle(item)}</strong><small>{item.id}</small></span>
                  {objectColumns.map((column) => <span key={column}>{formatValue(item.properties[column])}</span>)}
                </button>
              );
            })}
          </div>
        </div>
      </Card>
    </div>
  );
}

function AnalysisSurface({
  mode,
  setMode,
  nodes,
  edges,
  selectedNode,
  setSelectedNode,
  riskThreshold,
  setRiskThreshold,
  events,
  chartOption,
  kpis,
}: {
  mode: AnalysisMode;
  setMode: (mode: AnalysisMode) => void;
  nodes: Node[];
  edges: Edge[];
  selectedNode: string;
  setSelectedNode: (id: string) => void;
  riskThreshold: number;
  setRiskThreshold: (value: number) => void;
  events: EventSummary[];
  chartOption: object;
  kpis: { critical: number; warning: number; average: number; downtime: number };
}) {
  return (
    <div className="bp-surface-content bp-analysis-workbench">
      <Card className="bp-analysis-toolbar">
        <ButtonGroup>
          <Button icon="diagram-tree" active={mode === "graph"} onClick={() => setMode("graph")}>Graph</Button>
          <Button icon="dashboard" active={mode === "canvas"} onClick={() => setMode("canvas")}>Canvas</Button>
        </ButtonGroup>
        <Divider />
        <Tag icon="database">Dataset Version · Canonical V3.1</Tag>
        <Tag icon="automatic-updates" intent="success">Runtime ready</Tag>
        <div className="bp-analysis-toolbar-spacer" />
        <Button icon="add" intent="primary">Card 추가</Button>
        <Button icon="history">Version history</Button>
      </Card>
      {mode === "graph" ? (
        <Card className="bp-analysis-graph">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            nodesDraggable
            onNodeClick={(_, node) => setSelectedNode(node.id)}
            className={selectedNode ? `selected-${selectedNode}` : ""}
          >
            <Background gap={20} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </Card>
      ) : (
        <div className="bp-analysis-canvas">
          <div className="bp-kpi-strip">
            <Card className="bp-kpi-card"><span>Critical</span><strong>{kpis.critical}</strong></Card>
            <Card className="bp-kpi-card"><span>Warning</span><strong>{kpis.warning}</strong></Card>
            <Card className="bp-kpi-card"><span>Avg risk</span><strong>{Math.round(kpis.average * 100)}%</strong></Card>
            <Card className="bp-kpi-card"><span>Impact</span><strong>{kpis.downtime}m</strong></Card>
          </div>
          <Card className="bp-panel bp-chart-panel"><ReactECharts option={chartOption} style={{ height: 360 }} /></Card>
          <Card className="bp-panel">
            <div className="bp-panel-header"><div><span>ACTION SET</span><strong>점검 요청 후보</strong></div><Tag intent="warning">{events.filter((event) => (event.failure_probability ?? 0) >= riskThreshold).length}</Tag></div>
            <div className="bp-action-candidates">{events.filter((event) => (event.failure_probability ?? 0) >= riskThreshold).map((event) => <Tag key={event.event_id} interactive intent={STATUS_INTENT[event.status]}>{event.equipment.display_name} · {Math.round((event.failure_probability ?? 0) * 100)}%</Tag>)}</div>
          </Card>
        </div>
      )}
      <Card className="bp-parameter-bar">
        <span>Published parameter</span>
        <strong>risk_threshold</strong>
        <NumericInput min={0} max={1} stepSize={0.05} minorStepSize={0.01} value={riskThreshold} onValueChange={setRiskThreshold} />
        <ProgressBar value={riskThreshold} intent="primary" />
      </Card>
    </div>
  );
}

function OperationsSurface({
  activeRole,
  availableRoles,
  switchRole,
  events,
  selectedEvent,
  setSelectedEventId,
  activity,
  setActivity,
}: {
  activeRole: AppRole;
  availableRoles: AppRole[];
  switchRole: (role: AppRole) => void;
  events: EventSummary[];
  selectedEvent: EventSummary | null;
  setSelectedEventId: (id: string) => void;
  activity: ActivityItem[];
  setActivity: React.Dispatch<React.SetStateAction<ActivityItem[]>>;
}) {
  const workflowTitle = activeRole === "process_engineer" || activeRole === "maintenance_technician"
    ? "내 담당 설비 점검"
    : activeRole === "tenant_admin" || activeRole === "quality_auditor"
      ? "승인·감사 Control Plane"
      : "운영 판단 Inbox";
  function recordPreviewAction(title: string) {
    setActivity((items): ActivityItem[] => [{
      id: crypto.randomUUID(),
      title,
      detail: selectedEvent ? eventTitle(selectedEvent) : "현재 선택 Event 없음",
      timestamp: new Date().toISOString(),
      intent: "success" as const,
    }, ...items].slice(0, 12));
  }
  return (
    <div className="bp-surface-content bp-operations-surface">
      <div className="bp-role-tabs" role="tablist">
        {availableRoles.map((role) => <Button key={role} active={role === activeRole} onClick={() => switchRole(role)}>{ROLE_LABELS[role] ?? role}</Button>)}
      </div>
      <div className="bp-operations-grid">
        <Card className="bp-panel bp-workflow-inbox">
          <div className="bp-panel-header"><div><span>ROLE WORKSPACE</span><strong>{workflowTitle}</strong></div><Tag>{events.length}</Tag></div>
          <div className="bp-event-list">
            {events.map((event) => (
              <button key={event.event_id} className={selectedEvent?.event_id === event.event_id ? "is-selected" : ""} onClick={() => setSelectedEventId(event.event_id)}>
                <Tag intent={STATUS_INTENT[event.status] ?? "none"} minimal>{event.status}</Tag>
                <span><strong>{event.equipment.display_name}</strong><small>{event.equipment.line} · {event.equipment.assigned_engineer}</small></span>
                <b>{event.failure_probability === null ? "—" : `${Math.round(event.failure_probability * 100)}%`}</b>
              </button>
            ))}
          </div>
        </Card>
        <Card className="bp-panel bp-decision-panel">
          <div className="bp-panel-header"><div><span>DECISION</span><strong>{selectedEvent ? eventTitle(selectedEvent) : "Event 선택"}</strong></div></div>
          {selectedEvent ? (
            <>
              <div className="bp-decision-summary">
                <Tag large intent={STATUS_INTENT[selectedEvent.status] ?? "none"}>{selectedEvent.status}</Tag>
                <strong>{selectedEvent.failure_probability === null ? "결과 없음" : `${Math.round(selectedEvent.failure_probability * 100)}% failure probability`}</strong>
                <p>{selectedEvent.predicted_failure_type} · 권장 조치 {selectedEvent.recommended_decision}</p>
              </div>
              <Callout icon="help" title="근거 기반 판단">설비 중요도 {selectedEvent.equipment.criticality}, 예상 중단 {selectedEvent.equipment.estimated_downtime_minutes}분, 담당자 {selectedEvent.equipment.assigned_engineer}</Callout>
              <div className="bp-decision-actions">
                <Button intent="primary" icon="confirm" onClick={() => recordPreviewAction("검사 요청 승인")}>검사 요청</Button>
                <Button intent="warning" icon="pause" onClick={() => recordPreviewAction("정지 검토 등록")}>정지 검토</Button>
                <Button icon="person" onClick={() => recordPreviewAction("담당자 재배정")}>담당자 배정</Button>
              </div>
            </>
          ) : <Callout>Select an event.</Callout>}
        </Card>
        <Card className="bp-panel bp-activity-panel">
          <div className="bp-panel-header"><div><span>ACTIVITY</span><strong>Action & Audit log</strong></div></div>
          <div className="bp-activity-list">
            {activity.map((item) => (
              <div key={item.id}><span className={`bp-activity-dot is-${item.intent}`} /><div><strong>{item.title}</strong><p>{item.detail}</p><small>{new Date(item.timestamp).toLocaleString()}</small></div></div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function ObjectInspector({
  selectedObject,
  typeDefinition,
  actions,
  actionNote,
  setActionNote,
  actionRunning,
  runAction,
}: {
  selectedObject: ObjectRecord | null;
  typeDefinition: ObjectTypeDefinition | null;
  actions: ActionTypeDefinition[];
  actionNote: string;
  setActionNote: (value: string) => void;
  actionRunning: boolean;
  runAction: (action: ActionTypeDefinition) => Promise<void>;
}) {
  if (!selectedObject) return <Callout icon="cube">Object Set에서 항목을 선택하세요.</Callout>;
  return (
    <div className="bp-inspector-body">
      <div className="bp-object-identity"><Icon icon="cube" size={24} /><div><Tag minimal>{typeDefinition?.display_name ?? selectedObject.object_type}</Tag><h2>{objectTitle(selectedObject)}</h2><code>{selectedObject.id}</code></div></div>
      <section><span className="bp-eyebrow">PROPERTIES</span><div className="bp-property-list">{Object.entries(selectedObject.properties).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatValue(value)}</strong></div>)}</div></section>
      <section><span className="bp-eyebrow">SOURCE & VERSION</span><div className="bp-property-list"><div><span>Version</span><strong>{selectedObject.version}</strong></div><div><span>Source refs</span><strong>{selectedObject.source_refs.join(", ")}</strong></div></div></section>
      <section><span className="bp-eyebrow">ACTIONS</span><TextArea fill value={actionNote} placeholder="Action 메모 또는 근거" onChange={(event) => setActionNote(event.currentTarget.value)} />
        <div className="bp-inspector-actions">{actions.length ? actions.map((action) => <Button key={action.id} fill intent={action.requires_human_approval ? "warning" : "primary"} icon="play" loading={actionRunning} onClick={() => void runAction(action)}>{action.display_name}</Button>) : <Callout icon="lock">현재 Object에 실행 가능한 Action이 없습니다.</Callout>}</div>
      </section>
    </div>
  );
}

function EventInspector({ selectedEvent }: { selectedEvent: EventSummary | null }) {
  if (!selectedEvent) return <Callout>Event를 선택하세요.</Callout>;
  return (
    <div className="bp-inspector-body">
      <div className="bp-object-identity"><Icon icon="pulse" size={24} /><div><Tag intent={STATUS_INTENT[selectedEvent.status]}>{selectedEvent.status}</Tag><h2>{selectedEvent.equipment.display_name}</h2><code>{selectedEvent.event_id}</code></div></div>
      <section><span className="bp-eyebrow">RISK RESULT</span><div className="bp-property-list"><div><span>Failure probability</span><strong>{selectedEvent.failure_probability === null ? "—" : `${Math.round(selectedEvent.failure_probability * 100)}%`}</strong></div><div><span>Failure type</span><strong>{selectedEvent.predicted_failure_type}</strong></div><div><span>Confidence</span><strong>{selectedEvent.confidence}</strong></div></div></section>
      <section><span className="bp-eyebrow">OPERATIONS</span><div className="bp-property-list"><div><span>Line</span><strong>{selectedEvent.equipment.line}</strong></div><div><span>Engineer</span><strong>{selectedEvent.equipment.assigned_engineer}</strong></div><div><span>Downtime</span><strong>{selectedEvent.equipment.estimated_downtime_minutes}m</strong></div><div><span>Spare part</span><strong>{selectedEvent.equipment.spare_part_available ? "Available" : "Not secured"}</strong></div></div></section>
    </div>
  );
}

function AnalysisInspector({ selectedNode, riskThreshold, setRiskThreshold }: { selectedNode: string; riskThreshold: number; setRiskThreshold: (value: number) => void }) {
  const descriptions: Record<string, { title: string; type: string; detail: string }> = {
    source: { title: "Equipment Object Set", type: "ObjectSet<Equipment>", detail: "제조 Workspace의 Equipment Object를 입력으로 사용합니다." },
    filter: { title: "Risk Filter", type: "ObjectSet<Equipment>", detail: "failure_probability Parameter로 Object Set을 줄입니다." },
    aggregate: { title: "Line × Status Aggregate", type: "Table", detail: "라인과 위험 상태를 기준으로 KPI를 집계합니다." },
    chart: { title: "Risk Portfolio Chart", type: "Chart", detail: "ECharts 렌더러에 전달되는 typed chart result입니다." },
    action: { title: "Inspection Action Set", type: "ObjectSet<RiskEvent>", detail: "Workflow에 전달할 점검 대상 Object Set입니다." },
  };
  const item = descriptions[selectedNode] ?? descriptions.source;
  return (
    <div className="bp-inspector-body">
      <Tag intent="primary">{item.type}</Tag><h2>{item.title}</h2><p>{item.detail}</p>
      <Divider />
      <FormGroup label="risk_threshold" helperText="Graph와 Canvas에서 공유되는 published parameter">
        <NumericInput min={0} max={1} stepSize={0.05} minorStepSize={0.01} value={riskThreshold} onValueChange={setRiskThreshold} fill />
      </FormGroup>
      <ProgressBar value={riskThreshold} intent="primary" />
      <Callout icon="git-branch" title="Lineage">Dataset Version → Object Set → {item.title}</Callout>
    </div>
  );
}
