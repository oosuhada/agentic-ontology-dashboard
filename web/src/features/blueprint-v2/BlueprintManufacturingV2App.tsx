import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alignment,
  Button,
  ButtonGroup,
  Callout,
  Card,
  Divider,
  FormGroup,
  HTMLSelect,
  HTMLTable,
  Icon,
  InputGroup,
  Menu,
  MenuDivider,
  MenuItem,
  Navbar,
  NavbarDivider,
  NavbarGroup,
  NavbarHeading,
  NumericInput,
  ProgressBar,
  Spinner,
  Switch,
  Tab,
  Tabs,
  Tag,
  TextArea,
} from "@blueprintjs/core";
import ReactECharts from "echarts-for-react";
import {
  getOntologyRegistry,
  getProject,
  getProjectEvents,
  getProjectWorkspaces,
  invokeOntologyAction,
  queryOntologyObjects,
} from "../../api";
import {
  blueprintProjectPath,
  navigate,
  ontologyPath,
  projectDashboardPath,
} from "../../routing";
import type { EventSummary, Project, Workspace } from "../../types";
import type {
  ActionTypeDefinition,
  ObjectRecord,
  ObjectTypeDefinition,
  OntologyRegistry,
} from "../ontology/types";
import { useAuth } from "../auth/AuthContext";
import "./blueprint-manufacturing-v2.css";

type WorkbenchTab = "objects" | "analysis" | "operations";
type InspectorTab = "properties" | "actions" | "history";
type SortDirection = "asc" | "desc";

interface BlueprintManufacturingV2AppProps {
  projectId: string;
}

interface AuditItem {
  id: string;
  title: string;
  detail: string;
  timestamp: string;
  intent: "none" | "primary" | "success" | "warning" | "danger";
}

const STATUS_INTENT: Record<string, "none" | "primary" | "success" | "warning" | "danger"> = {
  critical: "danger",
  warning: "warning",
  attention: "primary",
  data_quality_hold: "warning",
  normal: "success",
};

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

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (value >= 0 && value <= 1 && !Number.isInteger(value)) return `${Math.round(value * 100)}%`;
    return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function objectTitle(item: ObjectRecord | null) {
  if (!item) return "No object selected";
  return String(item.properties.display_name ?? item.properties.name ?? item.properties.equipment_id ?? item.id);
}

function eventRisk(event: EventSummary) {
  return event.failure_probability === null ? "—" : `${Math.round(event.failure_probability * 100)}%`;
}

function objectRisk(item: ObjectRecord) {
  return Number(item.properties.failure_probability ?? 0);
}

function objectStatus(item: ObjectRecord) {
  const status = String(item.properties.status ?? item.properties.risk_band ?? "normal");
  return status || "normal";
}

function readBlueprintV2PreviewQuery() {
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get("view");
  const requestedInspector = params.get("inspector");
  return {
    view: requestedView === "objects" || requestedView === "analysis" || requestedView === "operations"
      ? requestedView as WorkbenchTab
      : null,
    inspector: requestedInspector === "properties" || requestedInspector === "actions" || requestedInspector === "history"
      ? requestedInspector as InspectorTab
      : null,
  };
}

export function BlueprintManufacturingV2App({ projectId }: BlueprintManufacturingV2AppProps) {
  const { user } = useAuth();
  const previewQuery = useMemo(readBlueprintV2PreviewQuery, []);
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
  const [riskThreshold, setRiskThreshold] = useState(0.6);
  const [sortKey, setSortKey] = useState("failure_probability");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [activeTab, setActiveTab] = useState<WorkbenchTab>(previewQuery.view ?? "objects");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>(previewQuery.inspector ?? "properties");
  const [leftOpen, setLeftOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  const [objectLoading, setObjectLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [actionNote, setActionNote] = useState("");
  const [actionRunning, setActionRunning] = useState(false);
  const [auditItems, setAuditItems] = useState<AuditItem[]>([
    {
      id: "v2-ready",
      title: "Blueprint V2 dense workbench opened",
      detail: "Original and Blueprint V1 remain unchanged.",
      timestamp: new Date().toISOString(),
      intent: "primary",
    },
  ]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 920px)");
    const syncPanels = () => {
      if (media.matches) {
        setLeftOpen(false);
        setInspectorOpen(false);
      } else {
        setLeftOpen(true);
        setInspectorOpen(true);
      }
    };
    syncPanels();
    media.addEventListener("change", syncPanels);
    return () => media.removeEventListener("change", syncPanels);
  }, []);

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
        setSelectedEventId(eventPayload[0]?.event_id ?? "");
        setWorkspaceId(projectPayload.default_workspace_id ?? workspacePayload[0]?.id ?? "manufacturing-demo");
        setObjectType(registryPayload.object_types.find((item) => item.id === "equipment")?.id ?? registryPayload.object_types[0]?.id ?? "equipment");
        setError("");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "V2 Workbench 데이터를 불러오지 못했습니다."))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [projectId]);

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

  const activeRole = user?.active_project_roles[0] ?? user?.roles[0] ?? "process_manager";
  const selectedType = useMemo(
    () => registry?.object_types.find((item) => item.id === objectType) ?? null,
    [objectType, registry],
  );
  const selectedObject = useMemo(
    () => objects.find((item) => item.id === selectedObjectId) ?? objects[0] ?? null,
    [objects, selectedObjectId],
  );
  const selectedEvent = useMemo(
    () => events.find((item) => item.event_id === selectedEventId) ?? events[0] ?? null,
    [events, selectedEventId],
  );
  const actions = useMemo(
    () => (registry?.action_types ?? []).filter((item) => item.object_type === selectedObject?.object_type),
    [registry, selectedObject?.object_type],
  );

  const columns = useMemo(() => {
    const available = new Set(selectedType?.properties.map((property) => property.id) ?? []);
    const preferred = ["equipment_id", "line", "status", "failure_probability", "criticality", "assigned_engineer", "spare_part_available"];
    return preferred.filter((column) => available.has(column)).slice(0, 6);
  }, [selectedType]);

  const visibleObjects = useMemo(() => {
    const filtered = riskOnly
      ? objects.filter((item) => objectRisk(item) >= riskThreshold || ["critical", "warning"].includes(objectStatus(item)))
      : objects;
    return [...filtered].sort((left, right) => {
      const leftValue = left.properties[sortKey] ?? "";
      const rightValue = right.properties[sortKey] ?? "";
      const comparison = typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue));
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [objects, riskOnly, riskThreshold, sortDirection, sortKey]);

  const kpis = useMemo(() => {
    const probabilities = events.map((item) => item.failure_probability).filter((value): value is number => value !== null);
    return {
      critical: events.filter((item) => item.status === "critical").length,
      warning: events.filter((item) => item.status === "warning").length,
      average: probabilities.length ? probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length : 0,
      downtime: events.reduce((sum, item) => sum + item.equipment.estimated_downtime_minutes, 0),
    };
  }, [events]);

  const chartOption = useMemo(() => ({
    animationDuration: 250,
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    grid: { left: 44, right: 18, top: 32, bottom: 42 },
    xAxis: {
      type: "category",
      data: events.map((item) => item.equipment.display_name.replace(" 설비 ", "-")),
      axisLabel: { color: "#abb3bf", interval: 0, rotate: events.length > 6 ? 25 : 0 },
      axisLine: { lineStyle: { color: "#5f6b7c" } },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      axisLabel: { color: "#abb3bf", formatter: (value: number) => `${Math.round(value * 100)}%` },
      splitLine: { lineStyle: { color: "rgba(95,107,124,.25)" } },
    },
    series: [{
      type: "bar",
      barMaxWidth: 34,
      data: events.map((item) => ({
        value: item.failure_probability ?? 0,
        itemStyle: { color: item.status === "critical" ? "#cd4246" : item.status === "warning" ? "#d9822b" : "#2d72d2" },
      })),
    }],
  }), [events]);

  const toggleSort = useCallback((column: string) => {
    if (sortKey === column) setSortDirection((current) => current === "asc" ? "desc" : "asc");
    else {
      setSortKey(column);
      setSortDirection("asc");
    }
  }, [sortKey]);

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
      setNotice(`${action.display_name} completed · ${result.invocation_id}`);
      setAuditItems((items) => [{
        id: String(result.audit_id ?? result.invocation_id ?? crypto.randomUUID()),
        title: action.display_name,
        detail: `${objectTitle(selectedObject)} · ${result.state}`,
        timestamp: String(result.completed_at ?? new Date().toISOString()),
        intent: "success" as const,
      }, ...items].slice(0, 20));
      setInspectorTab("history");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Action 실행에 실패했습니다.";
      setError(message);
      setAuditItems((items) => [{
        id: crypto.randomUUID(),
        title: `${action.display_name} failed`,
        detail: message,
        timestamp: new Date().toISOString(),
        intent: "danger" as const,
      }, ...items].slice(0, 20));
    } finally {
      setActionRunning(false);
    }
  }, [actionNote, selectedObject, workspaceId]);

  const recordDecision = useCallback((title: string) => {
    setAuditItems((items) => [{
      id: crypto.randomUUID(),
      title,
      detail: selectedEvent ? `${selectedEvent.equipment.display_name} · ${selectedEvent.event_id}` : "No event selected",
      timestamp: new Date().toISOString(),
      intent: "success" as const,
    }, ...items].slice(0, 20));
    setNotice(`${title} 상태를 V2 비교 세션에 기록했습니다.`);
  }, [selectedEvent]);

  if (loading) {
    return (
      <main className="blueprint-v2 blueprint-v2-loading bp6-dark">
        <Spinner size={44} />
        <strong>Blueprint V2 Workbench</strong>
        <span>Loading Object Types, Object Sets, events, and actions</span>
      </main>
    );
  }

  return (
    <main className="blueprint-v2 bp6-dark">
      <Navbar className="bpv2-navbar" fixedToTop>
        <NavbarGroup align={Alignment.LEFT}>
          <Button minimal icon="menu" aria-label="Object navigation" onClick={() => setLeftOpen((current) => !current)} />
          <NavbarHeading><Icon icon="polygon-filter" /> Ontology Workbench</NavbarHeading>
          <NavbarDivider />
          <div className="bpv2-breadcrumbs" aria-label="Project breadcrumb">
            <span>Projects</span><Icon icon="chevron-right" size={12} /><strong>{project?.display_name ?? projectId}</strong><Icon icon="chevron-right" size={12} /><span>Equipment Object Set</span>
          </div>
          <Tag intent="primary">V2</Tag>
        </NavbarGroup>
        <NavbarGroup align={Alignment.RIGHT}>
          <HTMLSelect
            className="bpv2-workspace-select"
            value={workspaceId}
            onChange={(event) => setWorkspaceId(event.currentTarget.value)}
            options={workspaces.map((workspace) => ({ label: workspace.display_name, value: workspace.id }))}
          />
          <Tag minimal icon="person">{ROLE_LABELS[activeRole] ?? activeRole}</Tag>
          <NavbarDivider />
          <Button minimal icon="comparison" onClick={() => window.open(projectDashboardPath(projectId), "_blank")}>Original</Button>
          <Button minimal icon="dashboard" onClick={() => navigate(blueprintProjectPath(projectId))}>Blueprint V1</Button>
          <Button minimal icon="settings" aria-label="Inspector" onClick={() => setInspectorOpen((current) => !current)} />
        </NavbarGroup>
      </Navbar>

      <div className="bpv2-commandbar">
        <ButtonGroup minimal>
          <Button icon="floppy-disk" onClick={() => setNotice("Object Set view saved for this comparison session.")}>Save view</Button>
          <Button icon="refresh" onClick={() => window.location.reload()}>Refresh</Button>
          <Button icon="share" onClick={() => navigate(ontologyPath(projectId, workspaceId))}>Open full Ontology</Button>
        </ButtonGroup>
        <Divider />
        <Tag minimal icon="database">Canonical V3.1</Tag>
        <Tag minimal intent="success" icon="automatic-updates">Runtime ready</Tag>
        <span className="bpv2-command-spacer" />
        <Button small minimal icon="drawer-right" onClick={() => setInspectorOpen((current) => !current)}>Inspector</Button>
      </div>

      {error ? <Callout className="bpv2-message" intent="danger" icon="error" title="Workbench error">{error}</Callout> : null}
      {notice ? <Callout className="bpv2-message" intent="success" icon="tick">{notice}<Button small minimal icon="cross" onClick={() => setNotice("")} aria-label="Dismiss" /></Callout> : null}

      <div className={`bpv2-shell ${leftOpen ? "has-left" : ""} ${inspectorOpen ? "has-inspector" : ""}`}>
        {leftOpen ? (
          <aside className="bpv2-left-panel" aria-label="Object navigation">
            <div className="bpv2-panel-title"><span>ONTOLOGY</span><Button small minimal icon="cross" onClick={() => setLeftOpen(false)} aria-label="Close navigation" /></div>
            <Menu className="bpv2-menu">
              <MenuDivider title="Applications" />
              <MenuItem active={activeTab === "objects"} icon="cube" text="Object Explorer" labelElement={<Tag minimal>{objectTotal}</Tag>} onClick={() => setActiveTab("objects")} />
              <MenuItem active={activeTab === "analysis"} icon="diagram-tree" text="Analysis" labelElement={<Tag minimal>5 cards</Tag>} onClick={() => setActiveTab("analysis")} />
              <MenuItem active={activeTab === "operations"} icon="endorsed" text="Operations" labelElement={<Tag minimal>{events.length}</Tag>} onClick={() => setActiveTab("operations")} />
              <MenuDivider title="Object types" />
              {(registry?.object_types ?? []).map((item) => (
                <MenuItem
                  key={item.id}
                  active={objectType === item.id}
                  icon="cube"
                  text={item.display_name}
                  label={item.id}
                  onClick={() => {
                    setObjectType(item.id);
                    setActiveTab("objects");
                  }}
                />
              ))}
              <MenuDivider title="Saved Object Sets" />
              <MenuItem icon="filter-list" text="High-risk equipment" label={`≥ ${Math.round(riskThreshold * 100)}%`} onClick={() => { setRiskOnly(true); setActiveTab("objects"); }} />
              <MenuItem icon="person" text="Assigned to me" label="Dynamic" />
              <MenuItem icon="history" text="Recently inspected" label="24h" />
            </Menu>
            <div className="bpv2-left-footer">
              <Tag minimal>Blueprint 6.18</Tag>
              <small>Dense desktop workbench experiment</small>
            </div>
          </aside>
        ) : null}

        <section className="bpv2-center">
          <div className="bpv2-tabbar">
            <Tabs
              id="bpv2-workbench-tabs"
              selectedTabId={activeTab}
              onChange={(next) => setActiveTab(next as WorkbenchTab)}
              renderActiveTabPanelOnly
            >
              <Tab id="objects" title="Objects" />
              <Tab id="analysis" title="Analysis" />
              <Tab id="operations" title="Operations" />
            </Tabs>
            <div className="bpv2-tab-actions"><Tag minimal>{workspaceId}</Tag><Button small minimal icon="more" aria-label="More" /></div>
          </div>

          {activeTab === "objects" ? (
            <ObjectsWorkspace
              registry={registry}
              objectType={objectType}
              setObjectType={setObjectType}
              selectedType={selectedType}
              search={search}
              setSearch={setSearch}
              riskOnly={riskOnly}
              setRiskOnly={setRiskOnly}
              riskThreshold={riskThreshold}
              setRiskThreshold={setRiskThreshold}
              visibleObjects={visibleObjects}
              objectTotal={objectTotal}
              objectLoading={objectLoading}
              columns={columns}
              selectedObjectId={selectedObject?.id ?? ""}
              setSelectedObjectId={setSelectedObjectId}
              sortKey={sortKey}
              sortDirection={sortDirection}
              toggleSort={toggleSort}
              openInspector={() => setInspectorOpen(true)}
            />
          ) : null}

          {activeTab === "analysis" ? (
            <AnalysisWorkspace
              events={events}
              kpis={kpis}
              chartOption={chartOption}
              riskThreshold={riskThreshold}
              setRiskThreshold={setRiskThreshold}
            />
          ) : null}

          {activeTab === "operations" ? (
            <OperationsWorkspace
              events={events}
              selectedEvent={selectedEvent}
              setSelectedEventId={setSelectedEventId}
              auditItems={auditItems}
              recordDecision={recordDecision}
            />
          ) : null}
        </section>

        {inspectorOpen ? (
          <InspectorPanel
            activeTab={activeTab}
            inspectorTab={inspectorTab}
            setInspectorTab={setInspectorTab}
            selectedObject={selectedObject}
            selectedType={selectedType}
            selectedEvent={selectedEvent}
            actions={actions}
            actionNote={actionNote}
            setActionNote={setActionNote}
            actionRunning={actionRunning}
            runAction={runAction}
            auditItems={auditItems}
            onClose={() => setInspectorOpen(false)}
          />
        ) : null}
      </div>

      <footer className="bpv2-statusbar">
        <span><Icon icon="small-tick" size={12} /> API connected</span>
        <span>Object Set: {visibleObjects.length}/{objectTotal}</span>
        <span>Selected: {selectedObject ? objectTitle(selectedObject) : "None"}</span>
        <span className="bpv2-status-spacer" />
        <span>Original and V1 preserved</span>
      </footer>
    </main>
  );
}

function ObjectsWorkspace({
  registry,
  objectType,
  setObjectType,
  selectedType,
  search,
  setSearch,
  riskOnly,
  setRiskOnly,
  riskThreshold,
  setRiskThreshold,
  visibleObjects,
  objectTotal,
  objectLoading,
  columns,
  selectedObjectId,
  setSelectedObjectId,
  sortKey,
  sortDirection,
  toggleSort,
  openInspector,
}: {
  registry: OntologyRegistry | null;
  objectType: string;
  setObjectType: (value: string) => void;
  selectedType: ObjectTypeDefinition | null;
  search: string;
  setSearch: (value: string) => void;
  riskOnly: boolean;
  setRiskOnly: (value: boolean) => void;
  riskThreshold: number;
  setRiskThreshold: (value: number) => void;
  visibleObjects: ObjectRecord[];
  objectTotal: number;
  objectLoading: boolean;
  columns: string[];
  selectedObjectId: string;
  setSelectedObjectId: (value: string) => void;
  sortKey: string;
  sortDirection: SortDirection;
  toggleSort: (column: string) => void;
  openInspector: () => void;
}) {
  return (
    <div className="bpv2-workspace bpv2-objects-workspace">
      <div className="bpv2-title-row">
        <div>
          <span className="bpv2-eyebrow">OBJECT SET</span>
          <h1>{selectedType?.display_name ?? objectType}</h1>
          <p>{selectedType?.description ?? "Ontology-backed objects in the active workspace."}</p>
        </div>
        <ButtonGroup>
          <Button icon="add" intent="primary">New object</Button>
          <Button icon="filter-list">Create Object Set</Button>
        </ButtonGroup>
      </div>

      <div className="bpv2-filterbar">
        <HTMLSelect
          value={objectType}
          onChange={(event) => setObjectType(event.currentTarget.value)}
          options={(registry?.object_types ?? []).map((item) => ({ label: item.display_name, value: item.id }))}
        />
        <InputGroup leftIcon="search" placeholder="Search ID or property" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
        <Switch checked={riskOnly} label="High risk only" onChange={(event) => setRiskOnly(event.currentTarget.checked)} />
        <NumericInput
          min={0}
          max={1}
          stepSize={0.05}
          minorStepSize={0.01}
          value={riskThreshold}
          onValueChange={setRiskThreshold}
          disabled={!riskOnly}
          buttonPosition="none"
        />
        <Tag minimal>{visibleObjects.length.toLocaleString()} visible</Tag>
      </div>

      <div className="bpv2-table-toolbar">
        <div><strong>{visibleObjects.length.toLocaleString()}</strong> of {objectTotal.toLocaleString()} objects</div>
        <ButtonGroup minimal>
          <Button small active icon="list">Table</Button>
          <Button small icon="grid-view" disabled>Cards</Button>
          <Button small icon="map" disabled>Map</Button>
        </ButtonGroup>
      </div>

      <div className="bpv2-table-scroll">
        {objectLoading ? <div className="bpv2-table-loading"><Spinner size={26} /> Loading Object Set</div> : null}
        <HTMLTable className="bpv2-object-table" compact interactive striped>
          <thead>
            <tr>
              <th><button onClick={() => toggleSort("display_name")}>Object {sortKey === "display_name" ? sortDirection === "asc" ? "↑" : "↓" : ""}</button></th>
              {columns.map((column) => (
                <th key={column}><button onClick={() => toggleSort(column)}>{column.replaceAll("_", " ")} {sortKey === column ? sortDirection === "asc" ? "↑" : "↓" : ""}</button></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleObjects.map((item) => {
              const status = objectStatus(item);
              return (
                <tr
                  key={item.id}
                  className={selectedObjectId === item.id ? "is-selected" : ""}
                  onClick={() => { setSelectedObjectId(item.id); openInspector(); }}
                >
                  <td><span className="bpv2-object-name"><Icon icon="cube" size={14} /><span><strong>{objectTitle(item)}</strong><small>{item.id}</small></span></span></td>
                  {columns.map((column) => (
                    <td key={column}>
                      {column === "status" ? <Tag minimal intent={STATUS_INTENT[status] ?? "none"}>{status}</Tag> : formatValue(item.properties[column])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </HTMLTable>
        {!objectLoading && !visibleObjects.length ? <Callout icon="filter-list">현재 필터에 맞는 Object가 없습니다.</Callout> : null}
      </div>
    </div>
  );
}

function AnalysisWorkspace({
  events,
  kpis,
  chartOption,
  riskThreshold,
  setRiskThreshold,
}: {
  events: EventSummary[];
  kpis: { critical: number; warning: number; average: number; downtime: number };
  chartOption: object;
  riskThreshold: number;
  setRiskThreshold: (value: number) => void;
}) {
  const candidates = events.filter((event) => (event.failure_probability ?? 0) >= riskThreshold);
  return (
    <div className="bpv2-workspace bpv2-analysis-workspace">
      <div className="bpv2-title-row">
        <div><span className="bpv2-eyebrow">ANALYSIS</span><h1>Equipment risk portfolio</h1><p>Typed transformations, parameters, chart result, and Action Set in one dense workspace.</p></div>
        <ButtonGroup><Button icon="history">Versions</Button><Button intent="primary" icon="play">Run</Button></ButtonGroup>
      </div>
      <div className="bpv2-analysis-meta">
        <Tag icon="database">Canonical V3.1</Tag><Tag intent="success" icon="automatic-updates">Published</Tag><Tag minimal>5 cards</Tag>
        <span />
        <FormGroup inline label="risk_threshold">
          <NumericInput min={0} max={1} stepSize={0.05} minorStepSize={0.01} value={riskThreshold} onValueChange={setRiskThreshold} buttonPosition="none" />
        </FormGroup>
      </div>
      <div className="bpv2-analysis-grid">
        <div className="bpv2-pipeline">
          <div className="bpv2-pipeline-heading"><strong>Transformation graph</strong><Button small minimal icon="add">Add card</Button></div>
          {[
            ["database", "Equipment Object Set", "ObjectSet<Equipment>", "Source"],
            ["filter-list", `Risk ≥ ${Math.round(riskThreshold * 100)}%`, "ObjectSet<Equipment>", "Filter"],
            ["diagram-tree", "Line × Status", "Table", "Aggregate"],
            ["dashboard", "Risk portfolio", "Chart", "Visualize"],
            ["endorsed", "Inspection queue", "ObjectSet<RiskEvent>", "Action Set"],
          ].map(([icon, title, output, kind], index) => (
            <div className="bpv2-pipeline-step" key={title}>
              <span className="bpv2-step-index">{index + 1}</span><Icon icon={icon as "database"} />
              <span><strong>{title}</strong><small>{kind}</small></span><Tag minimal>{output}</Tag>
            </div>
          ))}
        </div>
        <div className="bpv2-analysis-result">
          <div className="bpv2-kpi-row">
            <div><span>Critical</span><strong>{kpis.critical}</strong></div>
            <div><span>Warning</span><strong>{kpis.warning}</strong></div>
            <div><span>Average risk</span><strong>{Math.round(kpis.average * 100)}%</strong></div>
            <div><span>Downtime</span><strong>{kpis.downtime}m</strong></div>
          </div>
          <div className="bpv2-chart"><ReactECharts option={chartOption} style={{ height: 330 }} /></div>
          <div className="bpv2-action-set"><strong>Inspection Action Set</strong><Tag intent="warning">{candidates.length}</Tag>{candidates.map((event) => <Tag key={event.event_id} interactive minimal intent={STATUS_INTENT[event.status]}>{event.equipment.display_name} · {eventRisk(event)}</Tag>)}</div>
        </div>
      </div>
    </div>
  );
}

function OperationsWorkspace({
  events,
  selectedEvent,
  setSelectedEventId,
  auditItems,
  recordDecision,
}: {
  events: EventSummary[];
  selectedEvent: EventSummary | null;
  setSelectedEventId: (value: string) => void;
  auditItems: AuditItem[];
  recordDecision: (title: string) => void;
}) {
  return (
    <div className="bpv2-workspace bpv2-operations-workspace">
      <div className="bpv2-title-row">
        <div><span className="bpv2-eyebrow">OPERATIONS</span><h1>Decision inbox</h1><p>Event selection, evidence review, human decision, and audit trail.</p></div>
        <Tag intent="danger">{events.filter((event) => event.status === "critical").length} critical</Tag>
      </div>
      <div className="bpv2-operations-grid">
        <section className="bpv2-queue">
          <div className="bpv2-section-header"><strong>Queue</strong><Tag minimal>{events.length}</Tag></div>
          {events.map((event) => (
            <button key={event.event_id} className={selectedEvent?.event_id === event.event_id ? "is-selected" : ""} onClick={() => setSelectedEventId(event.event_id)}>
              <Tag minimal intent={STATUS_INTENT[event.status] ?? "none"}>{event.status}</Tag>
              <span><strong>{event.equipment.display_name}</strong><small>{event.predicted_failure_type} · {event.equipment.line}</small></span>
              <b>{eventRisk(event)}</b>
            </button>
          ))}
        </section>
        <section className="bpv2-decision">
          <div className="bpv2-section-header"><strong>Decision</strong><Tag minimal>{selectedEvent?.event_id ?? "No event"}</Tag></div>
          {selectedEvent ? (
            <>
              <div className="bpv2-decision-hero">
                <Tag large intent={STATUS_INTENT[selectedEvent.status] ?? "none"}>{selectedEvent.status}</Tag>
                <strong>{selectedEvent.equipment.display_name}</strong>
                <span>{eventRisk(selectedEvent)} failure probability</span>
              </div>
              <HTMLTable compact className="bpv2-detail-table">
                <tbody>
                  <tr><th>Failure type</th><td>{selectedEvent.predicted_failure_type}</td></tr>
                  <tr><th>Recommended decision</th><td>{selectedEvent.recommended_decision}</td></tr>
                  <tr><th>Assigned engineer</th><td>{selectedEvent.equipment.assigned_engineer}</td></tr>
                  <tr><th>Downtime impact</th><td>{selectedEvent.equipment.estimated_downtime_minutes} min</td></tr>
                  <tr><th>Spare part</th><td>{selectedEvent.equipment.spare_part_available ? "Available" : "Not secured"}</td></tr>
                </tbody>
              </HTMLTable>
              <Callout compact icon="help" title="Evidence-based decision">Confidence {selectedEvent.confidence}. Human approval remains required for stop decisions.</Callout>
              <ButtonGroup fill>
                <Button intent="primary" icon="confirm" onClick={() => recordDecision("Inspection requested")}>Request inspection</Button>
                <Button intent="warning" icon="pause" onClick={() => recordDecision("Stop review opened")}>Review stop</Button>
                <Button icon="person" onClick={() => recordDecision("Engineer reassigned")}>Assign</Button>
              </ButtonGroup>
            </>
          ) : <Callout>Select an event from the queue.</Callout>}
        </section>
        <section className="bpv2-audit-preview">
          <div className="bpv2-section-header"><strong>Recent activity</strong><Tag minimal>{auditItems.length}</Tag></div>
          {auditItems.slice(0, 8).map((item) => (
            <div className="bpv2-audit-row" key={item.id}><span className={`is-${item.intent}`} /><div><strong>{item.title}</strong><p>{item.detail}</p><small>{new Date(item.timestamp).toLocaleString()}</small></div></div>
          ))}
        </section>
      </div>
    </div>
  );
}

function InspectorPanel({
  activeTab,
  inspectorTab,
  setInspectorTab,
  selectedObject,
  selectedType,
  selectedEvent,
  actions,
  actionNote,
  setActionNote,
  actionRunning,
  runAction,
  auditItems,
  onClose,
}: {
  activeTab: WorkbenchTab;
  inspectorTab: InspectorTab;
  setInspectorTab: (tab: InspectorTab) => void;
  selectedObject: ObjectRecord | null;
  selectedType: ObjectTypeDefinition | null;
  selectedEvent: EventSummary | null;
  actions: ActionTypeDefinition[];
  actionNote: string;
  setActionNote: (value: string) => void;
  actionRunning: boolean;
  runAction: (action: ActionTypeDefinition) => Promise<void>;
  auditItems: AuditItem[];
  onClose: () => void;
}) {
  return (
    <aside className="bpv2-inspector" aria-label="Selection inspector">
      <div className="bpv2-panel-title"><span>INSPECTOR</span><Button small minimal icon="cross" onClick={onClose} aria-label="Close inspector" /></div>
      <div className="bpv2-inspector-identity">
        <Icon icon={activeTab === "operations" ? "pulse" : "cube"} size={22} />
        <div>
          <Tag minimal>{activeTab === "operations" ? selectedEvent?.status ?? "Event" : selectedType?.display_name ?? selectedObject?.object_type ?? "Object"}</Tag>
          <strong>{activeTab === "operations" ? selectedEvent?.equipment.display_name ?? "No event" : objectTitle(selectedObject)}</strong>
          <code>{activeTab === "operations" ? selectedEvent?.event_id ?? "—" : selectedObject?.id ?? "—"}</code>
        </div>
      </div>
      <Tabs id="bpv2-inspector-tabs" selectedTabId={inspectorTab} onChange={(next) => setInspectorTab(next as InspectorTab)}>
        <Tab id="properties" title="Properties" />
        <Tab id="actions" title="Actions" />
        <Tab id="history" title="History" />
      </Tabs>
      <div className="bpv2-inspector-body">
        {inspectorTab === "properties" ? (
          activeTab === "operations" ? (
            selectedEvent ? <EventProperties event={selectedEvent} /> : <Callout>Select an event.</Callout>
          ) : selectedObject ? (
            <div className="bpv2-property-list">
              {Object.entries(selectedObject.properties).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatValue(value)}</strong></div>)}
            </div>
          ) : <Callout>Select an object.</Callout>
        ) : null}

        {inspectorTab === "actions" ? (
          <div className="bpv2-action-panel">
            <Callout compact icon="endorsed" title="Ontology Action">Actions write through the governed API and create an audit record.</Callout>
            <FormGroup label="Evidence note" helperText="Included in the Action parameters when supported.">
              <TextArea fill rows={4} value={actionNote} placeholder="Why is this action required?" onChange={(event) => setActionNote(event.currentTarget.value)} />
            </FormGroup>
            {actions.length ? actions.map((action) => (
              <Card key={action.id} compact className="bpv2-action-card">
                <div><strong>{action.display_name}</strong><p>{action.description}</p><Tag minimal intent={action.requires_human_approval ? "warning" : "success"}>{action.requires_human_approval ? "Human approval" : "Automatic"}</Tag></div>
                <Button intent={action.requires_human_approval ? "warning" : "primary"} icon="play" loading={actionRunning} onClick={() => void runAction(action)}>Run</Button>
              </Card>
            )) : <Callout icon="lock">No actions are available for this Object Type.</Callout>}
          </div>
        ) : null}

        {inspectorTab === "history" ? (
          <div className="bpv2-history-list">
            {selectedObject ? <Callout compact icon="history" title={`Object version ${selectedObject.version}`}>Sources: {selectedObject.source_refs.join(", ") || "No source refs"}</Callout> : null}
            {auditItems.map((item) => <div key={item.id}><span className={`is-${item.intent}`} /><div><strong>{item.title}</strong><p>{item.detail}</p><small>{new Date(item.timestamp).toLocaleString()}</small></div></div>)}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function EventProperties({ event }: { event: EventSummary }) {
  const rows = [
    ["status", event.status],
    ["failure probability", eventRisk(event)],
    ["failure type", event.predicted_failure_type],
    ["confidence", event.confidence],
    ["line", event.equipment.line],
    ["criticality", event.equipment.criticality],
    ["engineer", event.equipment.assigned_engineer],
    ["downtime", `${event.equipment.estimated_downtime_minutes} min`],
  ];
  return <div className="bpv2-property-list">{rows.map(([key, value]) => <div key={key}><span>{key}</span><strong>{value}</strong></div>)}</div>;
}
