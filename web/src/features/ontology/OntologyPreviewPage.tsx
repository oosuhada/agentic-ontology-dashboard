import { Button, Callout, Card, HTMLSelect, InputGroup, Spinner, Tag } from "@blueprintjs/core";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { Boxes, Check, GitBranch, Link2, MessageSquare, Network, Search, Table2, Waypoints, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  getOntologyRegistry,
  getProject3Status,
  getProject3Subgraph,
  invokeOntologyAction,
  queryOntologyObjects,
  runAgentQuery,
  traverseOntologyObject,
} from "../../api";
import { navigate } from "../../routing";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { ErrorState, LoadingState } from "../../ui/foundry/WorkbenchState";
import { FoundryDrawer } from "../../ui/foundry/FoundryDrawer";
import { useMediaQuery } from "../../ui/foundry/useMediaQuery";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { WorkbenchHeader } from "../../ui/foundry/WorkbenchChrome";
import { useAuth } from "../auth/AuthContext";
import type { AgentRunResponse } from "../agent/types";
import { ObjectSetTable } from "./ObjectSetTable";
import { ObjectViewInspector } from "./ObjectViewInspector";
import { objectIdentity } from "./objectPresentation";
import { objectTypeIcon } from "./objectTypeIcon";
import type {
  ActionTypeDefinition,
  ObjectRecord,
  OntologyRegistry,
  OntologyTraversal,
  Project3DegradedResponse,
  Project3IntegrationSnapshot,
  Project3Subgraph,
} from "./types";

interface OntologyPreviewPageProps {
  projectId: string;
  workspaceId: string;
}

type OntologyView = "table" | "exploration" | "graph";

type GraphDirection = "outgoing" | "incoming" | "both";
type SelectionMergeMode = "replace" | "union" | "intersection" | "difference";

function isDegraded(value: Project3Subgraph | Project3DegradedResponse | null): value is Project3DegradedResponse {
  return Boolean(value && "available" in value && value.available === false);
}

function normalized(value: string) {
  return value.replace(/[^a-z0-9]/gi, "").toLowerCase();
}

function graphNodeId(row: Record<string, unknown>, index: number): string {
  for (const key of ["id", "identity", "element_id", "equipment_id", "event_id", "name"]) {
    const value = row[key];
    if (typeof value === "string" && value) return value;
  }
  return `node-${index}`;
}

function graphNodeLabel(row: Record<string, unknown>, fallback: string): string {
  for (const key of ["display_name", "name", "identity", "equipment_id", "event_id", "id"]) {
    const value = row[key];
    if (typeof value === "string" && value) return value;
  }
  return fallback;
}

function relationEndpoint(row: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "string" && value) return value;
    if (value && typeof value === "object") {
      const nested = value as Record<string, unknown>;
      const id = nested.id ?? nested.identity ?? nested.element_id;
      if (typeof id === "string" && id) return id;
    }
  }
  return null;
}

function flowElements(subgraph: Project3Subgraph | null): { nodes: Node[]; edges: Edge[] } {
  if (!subgraph) return { nodes: [], edges: [] };
  const ids = new Map<string, string>();
  const nodes = subgraph.nodes.map((row, index) => {
    const id = graphNodeId(row, index);
    ids.set(id, id);
    const columns = Math.max(2, Math.ceil(Math.sqrt(subgraph.nodes.length)));
    return {
      id,
      position: { x: 80 + (index % columns) * 190, y: 70 + Math.floor(index / columns) * 120 },
      data: { label: graphNodeLabel(row, `Object ${index + 1}`), raw: row },
      className: "ontology-flow-node",
    } satisfies Node;
  });
  const edges = subgraph.relationships.flatMap((row, index) => {
    const source = relationEndpoint(row, ["source", "source_id", "start", "start_id", "from"]);
    const target = relationEndpoint(row, ["target", "target_id", "end", "end_id", "to"]);
    if (!source || !target || !ids.has(source) || !ids.has(target)) return [];
    return [{ id: String(row.id ?? `edge-${index}`), source, target, label: String(row.type ?? row.relationship_type ?? row.label ?? "RELATED_TO") } satisfies Edge];
  });
  return { nodes, edges };
}

export function OntologyPreviewPage({ projectId, workspaceId }: OntologyPreviewPageProps) {
  const { t } = useI18n();
  const isMobile = useMediaQuery("(max-width: 760px)");
  const { user } = useAuth();
  const [registry, setRegistry] = useState<OntologyRegistry | null>(null);
  const [status, setStatus] = useState<Project3IntegrationSnapshot | null>(null);
  const [selectedType, setSelectedType] = useState("");
  const [search, setSearch] = useState("");
  const [objects, setObjects] = useState<ObjectRecord[]>([]);
  const [objectOffset, setObjectOffset] = useState(0);
  const [objectTotal, setObjectTotal] = useState(0);
  const [selectedObject, setSelectedObject] = useState<ObjectRecord | null>(null);
  const [view, setView] = useState<OntologyView>("table");
  const [direction, setDirection] = useState<GraphDirection>("both");
  const [depth, setDepth] = useState(1);
  const [traversal, setTraversal] = useState<OntologyTraversal | null>(null);
  const [traversalLoading, setTraversalLoading] = useState(false);
  const [subgraph, setSubgraph] = useState<Project3Subgraph | Project3DegradedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [graphLoading, setGraphLoading] = useState(false);
  const [agentQuestion, setAgentQuestion] = useState("");
  const [agentRun, setAgentRun] = useState<AgentRunResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState("");
  const [error, setError] = useState("");
  const [selectionMode, setSelectionMode] = useState<SelectionMergeMode>("replace");
  const [draftSelectionIds, setDraftSelectionIds] = useState<Set<string>>(new Set());
  const [selectedObjectIds, setSelectedObjectIds] = useState<Set<string>>(new Set());
  const [selectionBusy, setSelectionBusy] = useState(false);

  const objectTypes = registry?.object_types ?? [];
  const selectedDefinition = objectTypes.find((item) => item.id === selectedType) ?? null;
  const objectActions = (registry?.action_types ?? []).filter((action) => action.object_type === selectedType);
  const graph = useMemo(() => flowElements(isDegraded(subgraph) ? null : subgraph), [subgraph]);
  const permissions = user?.permissions ?? [];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([getOntologyRegistry(), getProject3Status(projectId)])
      .then(([nextRegistry, nextStatus]) => {
        if (cancelled) return;
        setRegistry(nextRegistry);
        setStatus(nextStatus);
        setSelectedType((current) => current || nextRegistry.object_types[0]?.id || "");
        setError("");
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Ontology Workbench를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId]);

  useEffect(() => {
    if (!selectedType) return;
    let cancelled = false;
    queryOntologyObjects({ workspace_id: workspaceId, object_type: selectedType, search: search.trim() || undefined, offset: objectOffset, limit: 50 })
      .then((payload) => {
        if (cancelled) return;
        setObjects(payload.items);
        setObjectTotal(payload.total);
        setSelectedObject((current) => current && payload.items.some((item) => item.id === current.id) ? current : payload.items[0] ?? null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Object 검색에 실패했습니다.");
      });
    return () => { cancelled = true; };
  }, [objectOffset, search, selectedType, workspaceId]);

  useEffect(() => setObjectOffset(0), [search, selectedType]);

  useEffect(() => {
    setDraftSelectionIds(new Set());
    setSelectedObjectIds(new Set());
  }, [selectedType]);

  useEffect(() => {
    if (!selectedObject) {
      setTraversal(null);
      return;
    }
    let cancelled = false;
    setTraversalLoading(true);
    traverseOntologyObject(selectedObject.id, { workspace_id: workspaceId, direction, depth })
      .then((payload) => { if (!cancelled) setTraversal(payload); })
      .catch(() => { if (!cancelled) setTraversal(null); })
      .finally(() => { if (!cancelled) setTraversalLoading(false); });
    return () => { cancelled = true; };
  }, [depth, direction, selectedObject, workspaceId]);

  useEffect(() => {
    if (!selectedObject || !status?.schema) {
      setSubgraph(null);
      return;
    }
    const schemaLabel = status.schema.node_identities.find((item) => normalized(item.label) === normalized(selectedObject.object_type))?.label ?? status.schema.node_identities[0]?.label;
    if (!schemaLabel) return;
    setGraphLoading(true);
    getProject3Subgraph({ project_id: projectId, label: schemaLabel, identity: objectIdentity(selectedObject), depth, limit: 80 })
      .then(setSubgraph)
      .catch((reason: unknown) => setSubgraph({ status: "degraded", available: false, project_id: projectId, error: { code: "project3_request_failed", message: reason instanceof Error ? reason.message : "Graph request failed", retryable: true } }))
      .finally(() => setGraphLoading(false));
  }, [depth, projectId, selectedObject, status]);

  async function askAcrossStores() {
    const question = agentQuestion.trim();
    if (!question || agentLoading) return;
    setAgentLoading(true);
    setAskOpen(true);
    try {
      setAgentRun(await runAgentQuery({ project_id: projectId, workspace_id: workspaceId, question, object_type: selectedObject?.object_type, object_id: selectedObject ? objectIdentity(selectedObject) : undefined, route: "auto", top_k: 8 }));
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Multi-store query failed.");
    } finally {
      setAgentLoading(false);
    }
  }

  async function invokeAction(action: ActionTypeDefinition) {
    if (!selectedObject) return;
    setActionBusyId(action.id);
    setActionNotice("");
    try {
      const result = await invokeOntologyAction({ action_type: action.id, object_id: selectedObject.id, workspace_id: workspaceId, parameters: {}, idempotency_key: crypto.randomUUID() });
      setActionNotice(`${action.display_name} succeeded · ${String(result.invocation_id ?? result.audit_id ?? "audited")}`);
    } catch (reason: unknown) {
      setActionNotice(`${action.display_name} failed · ${reason instanceof Error ? reason.message : String(reason)}`);
    } finally {
      setActionBusyId(null);
    }
  }

  function addGraphBoard() {
    if (!selectedObject) return;
    sessionStorage.setItem("ontology-dashboard:add-graph-board", JSON.stringify({ projectId, workspaceId, objectType: selectedObject.object_type, objectId: objectIdentity(selectedObject), title: `${objectIdentity(selectedObject)} · Relationship Graph` }));
    navigate(`/app/projects/${encodeURIComponent(projectId)}`);
  }

  function chooseObject(object: ObjectRecord) {
    setSelectedObject(object);
    if (isMobile) setInspectorOpen(true);
  }

  function toggleDraftSelection(objectId: string, selected: boolean) {
    setDraftSelectionIds((current) => {
      const next = new Set(current);
      if (selected) next.add(objectId); else next.delete(objectId);
      return next;
    });
  }

  function toggleAllDraftSelection(objectIds: string[], selected: boolean) {
    setDraftSelectionIds((current) => {
      const next = new Set(current);
      objectIds.forEach((id) => selected ? next.add(id) : next.delete(id));
      return next;
    });
  }

  function applyObjectSelection() {
    setSelectedObjectIds((current) => {
      if (selectionMode === "replace") return new Set(draftSelectionIds);
      if (selectionMode === "union") return new Set([...current, ...draftSelectionIds]);
      if (selectionMode === "intersection") return new Set(current.size ? [...current].filter((id) => draftSelectionIds.has(id)) : draftSelectionIds);
      return new Set([...current].filter((id) => !draftSelectionIds.has(id)));
    });
    setDraftSelectionIds(new Set());
  }

  async function traverseSelectedObjects() {
    const roots = objects.filter((object) => selectedObjectIds.has(object.id)).slice(0, 8);
    if (!roots.length) return;
    setSelectionBusy(true);
    setTraversalLoading(true);
    try {
      const traversals = await Promise.all(roots.map((object) => traverseOntologyObject(object.id, { workspace_id: workspaceId, direction, depth })));
      const nodeMap = new Map<string, ObjectRecord>();
      const edgeMap = new Map<string, OntologyTraversal["edges"][number]>();
      traversals.forEach((payload) => {
        payload.nodes.forEach((node) => nodeMap.set(node.id, node));
        payload.edges.forEach((edge) => edgeMap.set(edge.id, edge));
      });
      setSelectedObject(roots[0]);
      setTraversal({ root: roots[0], nodes: [...nodeMap.values()], edges: [...edgeMap.values()], direction, depth });
      setView("exploration");
      setActionNotice(`Traversed ${roots.length} selected roots · ${nodeMap.size} objects · ${edgeMap.size} links`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Selected object traversal failed.");
    } finally {
      setSelectionBusy(false);
      setTraversalLoading(false);
    }
  }

  const graphAvailable = Boolean(status?.health.available);

  useEffect(() => {
    if (!graphAvailable && view === "graph") setView("table");
  }, [graphAvailable, view]);

  if (loading) return <main className="ontology-workbench-loading"><LoadingState title="Building Object Explorer" detail="Loading registry, Project scope, and graph readiness." /></main>;

  return (
    <main className="ontology-workbench-page">
      <WorkbenchHeader
        className="ontology-workbench-header"
        title={<EntityTitle icon={Boxes} eyebrow="ONTOLOGY WORKBENCH" title="Object Explorer" subtitle={`${projectId} · ${workspaceId} · governed object discovery and actions`} />}
        metadata={<StatusPill intent={status?.health.available ? "success" : "warning"}>Project 3 {status?.health.available ? status.health.status : "degraded"}</StatusPill>}
        actions={<div className="ontology-workbench-header-actions"><button type="button" className="fd-toolbar-button" disabled={!selectedObject} onClick={addGraphBoard}>{t("dashboard.addBoard")}</button><button type="button" className="fd-toolbar-button" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>{t("common.dashboard")}</button></div>}
      />

      {error ? <Callout intent="danger" title="Workbench error">{error}</Callout> : null}
      {status?.degraded_reason ? <Callout intent="warning" title="Graph service degraded">관계 그래프와 RAG 기능은 제한되지만 PostgreSQL-backed object search와 inspector는 계속 사용할 수 있습니다. {status.degraded_reason}</Callout> : null}

      <section className="ontology-query-toolbar fd-resource-toolbar">
        <div className="fd-resource-toolbar__group ontology-global-search"><Search size={13} /><InputGroup aria-label="Ontology object property search" placeholder="Search object identity or properties" value={search} onChange={(event) => setSearch(event.currentTarget.value)} /><button type="button" className="fd-toolbar-button primary" disabled={!agentQuestion.trim() || agentLoading} onClick={() => void askAcrossStores()}>Ask</button></div>
        <div className="fd-resource-toolbar__group"><InputGroup aria-label="Multi-store ontology question" placeholder="M-014와 연결된 최근 위험 사건, 관련 부품, 유사 정비 사례와 SOP를 보여줘." value={agentQuestion} onChange={(event) => setAgentQuestion(event.currentTarget.value)} /><div className="fd-view-switch" role="group" aria-label="Object Explorer view"><button type="button" className={view === "table" ? "active" : ""} onClick={() => setView("table")}><Table2 size={12} /> Table</button><button type="button" className={view === "exploration" ? "active" : ""} onClick={() => setView("exploration")}><Waypoints size={12} /> Explore</button><button type="button" className={view === "graph" ? "active" : ""} disabled={!graphAvailable} title={graphAvailable ? "Verified Project 3 subgraph" : "Project 3 연결 후 사용할 수 있습니다."} onClick={() => setView("graph")}><Network size={12} /> {graphAvailable ? "Graph" : "Graph · 연결 필요"}</button></div></div>
      </section>

      <section className="ontology-workbench-grid">
        <aside className="ontology-object-rail">
          <div className="pane-heading"><div><small>OBJECT TYPES</small><strong>{objectTypes.length} resources</strong></div><Tag minimal>{objectTotal} objects</Tag></div>
          <div className="ontology-type-list">
            {objectTypes.map((item) => { const TypeIcon = objectTypeIcon(item.id); return <button type="button" key={item.id} title={`${item.display_name} · ${item.domain_pack} · ${item.properties.length} properties`} className={selectedType === item.id ? "active" : ""} onClick={() => setSelectedType(item.id)}><span><TypeIcon size={12} /></span><div><strong>{item.display_name}</strong><small>{item.domain_pack} · {item.properties.length} properties</small></div></button>; })}
          </div>
          <footer className="ontology-pagination"><Button small icon="chevron-left" disabled={objectOffset === 0} onClick={() => setObjectOffset((current) => Math.max(0, current - 50))}>{t("common.previous")}</Button><span>{objectTotal ? `${objectOffset + 1}-${Math.min(objectOffset + objects.length, objectTotal)} / ${objectTotal}` : "0 objects"}</span><Button small rightIcon="chevron-right" disabled={objectOffset + objects.length >= objectTotal} onClick={() => setObjectOffset((current) => current + 50)}>{t("common.next")}</Button></footer>
        </aside>

        <section className={`ontology-graph-pane mode-${view}`}>
          <div className="pane-heading ontology-resource-heading"><div><small>{view === "table" ? "OBJECT SET" : view === "exploration" ? "RELATION EXPLORATION" : "PROJECT 3 SUBGRAPH"}</small><strong>{selectedDefinition?.display_name ?? selectedType}</strong></div><div className="pane-tags"><HTMLSelect value={direction} onChange={(event) => setDirection(event.currentTarget.value as GraphDirection)}><option value="both">Both directions</option><option value="outgoing">Outgoing</option><option value="incoming">Incoming</option></HTMLSelect><HTMLSelect value={depth} onChange={(event) => setDepth(Number(event.currentTarget.value))}><option value={1}>1 hop</option><option value={2}>2 hops</option></HTMLSelect><Tag minimal>{traversal?.edges.length ?? 0} links</Tag></div></div>
          <div className="ontology-primary-view">
            {view === "table" ? <>
              <div className="ontology-selection-toolbar">
                <div><Link2 size={12} /><strong>ObjectSet selection</strong><select aria-label="Selection merge mode" value={selectionMode} onChange={(event) => setSelectionMode(event.currentTarget.value as SelectionMergeMode)}><option value="replace">Replace</option><option value="union">Union</option><option value="intersection">Intersection</option><option value="difference">Difference</option></select><span>{draftSelectionIds.size} staged</span></div>
                <div><button type="button" disabled={!draftSelectionIds.size} onClick={applyObjectSelection}><Check size={11} /> Apply selection</button><button type="button" disabled={!draftSelectionIds.size} onClick={() => setDraftSelectionIds(new Set())}>Clear staged</button></div>
              </div>
              {selectedObjectIds.size ? <div className="ontology-selection-banner"><div><Link2 size={12} /><strong>{selectedObjectIds.size} objects selected</strong><span>{selectionMode} semantics · selection remains independent from row focus</span></div><div className="ontology-linked-actions"><button type="button" disabled={selectionBusy} onClick={() => void traverseSelectedObjects()}><GitBranch size={11} />{selectionBusy ? "Traversing…" : "Traverse selected"}</button><button type="button" onClick={() => { const first = objects.find((object) => selectedObjectIds.has(object.id)); if (first) chooseObject(first); setInspectorOpen(true); }}>Inspect first</button><button type="button" onClick={() => setSelectedObjectIds(new Set())}><X size={11} /> Clear selection</button></div></div> : null}
              <ObjectSetTable objects={objects} definition={selectedDefinition} selectedObjectId={selectedObject?.id ?? null} selectedObjectIds={selectedObjectIds} draftSelectionIds={draftSelectionIds} onSelect={chooseObject} onToggleDraftSelection={toggleDraftSelection} onToggleAllDraftSelection={toggleAllDraftSelection} />
            </> : null}
            {view === "exploration" ? (
              <div className="ontology-exploration-view">
                {selectedObject ? <>{(() => { const RootIcon = objectTypeIcon(selectedObject.object_type); return <article className="ontology-exploration-root"><span><RootIcon size={18} /></span><div><small>{selectedObject.object_type}</small><strong>{objectIdentity(selectedObject)}</strong><code>{selectedObject.id}</code></div></article>; })()}<div className="ontology-exploration-links">{traversalLoading ? <LoadingState title="Loading links" /> : traversal?.edges.map((edge) => { const relatedId = edge.source_object_id === selectedObject.id ? edge.target_object_id : edge.source_object_id; const related = traversal.nodes.find((item) => item.id === relatedId); const RelatedIcon = objectTypeIcon(related?.object_type ?? "object"); return <button type="button" key={edge.id} disabled={!related} onClick={() => related && chooseObject(related)}><StatusPill intent="primary">{edge.link_type}</StatusPill><GitBranch size={14} /><RelatedIcon size={14} /><div><strong>{related ? objectIdentity(related) : relatedId}</strong><small>{related?.object_type ?? "unresolved"} · {edge.source_object_id} → {edge.target_object_id}</small></div></button>; })}</div></> : <ErrorState title="Select an object" detail="Choose an object from Table view to explore governed links." />}
              </div>
            ) : null}
            {view === "graph" ? (
              <div className="ontology-flow-canvas">
                {graphLoading ? <div className="ontology-graph-overlay"><Spinner size={28} /><span>Graph relationships</span></div> : null}
                {isDegraded(subgraph) ? <Callout intent="warning" title="Subgraph unavailable">{subgraph.error.message}</Callout> : graph.nodes.length ? <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.35} maxZoom={1.8} nodesDraggable={false}><Background gap={20} size={1} /><MiniMap pannable zoomable /><Controls /></ReactFlow> : <ErrorState title="Graph preview" detail="Select an object to load its verified Project 3 subgraph." />}
              </div>
            ) : null}
          </div>
        </section>

        {!isMobile ? <ObjectViewInspector object={selectedObject} definition={selectedDefinition} traversal={traversal} traversalLoading={traversalLoading} actions={objectActions} status={status} permissions={permissions} actionBusyId={actionBusyId} actionNotice={actionNotice} onInvokeAction={(action) => void invokeAction(action)} onSelectRelatedObject={(object) => { setSelectedType(object.object_type); chooseObject(object); }} /> : null}
      </section>

      {isMobile && selectedObject ? <button type="button" className="mobile-inspector-trigger" onClick={() => setInspectorOpen(true)}>{t("ontology.selectObject")} · {objectIdentity(selectedObject)}</button> : null}
      {isMobile && inspectorOpen ? <FoundryDrawer ariaLabel={t("ontology.selectObject")} title={objectIdentity(selectedObject ?? objects[0])} position="bottom" onClose={() => setInspectorOpen(false)}><ObjectViewInspector object={selectedObject} definition={selectedDefinition} traversal={traversal} traversalLoading={traversalLoading} actions={objectActions} status={status} permissions={permissions} actionBusyId={actionBusyId} actionNotice={actionNotice} onInvokeAction={(action) => void invokeAction(action)} onSelectRelatedObject={(object) => { setSelectedType(object.object_type); chooseObject(object); }} /></FoundryDrawer> : null}

      {askOpen ? <FoundryDrawer ariaLabel={t("drawer.ontologyAssistant")} title={t("drawer.ontologyAssistant")} onClose={() => setAskOpen(false)} className="ontology-ask-drawer">{agentLoading ? <LoadingState title="Collecting governed evidence" detail={agentQuestion} /> : agentRun ? <div className="ontology-agent-result"><p>{agentRun.state.answer || agentRun.state.error || "근거를 찾지 못했습니다."}</p><div className="ontology-agent-evidence">{agentRun.state.evidence.map((item) => <Card key={item.evidence_id} elevation={0}><div><Tag minimal>{item.store}</Tag>{item.dataset_version_id ? <Tag minimal>{item.dataset_version_id}</Tag> : null}</div><strong>{item.title}</strong><p>{item.content}</p><small>{item.reference}</small></Card>)}</div>{agentRun.state.caveats.length ? <Callout intent="warning">{agentRun.state.caveats.join(" ")}</Callout> : null}</div> : <div className="ontology-ask-empty"><MessageSquare size={22} /><p>Ask a scoped question from the toolbar.</p></div>}</FoundryDrawer> : null}
    </main>
  );
}
