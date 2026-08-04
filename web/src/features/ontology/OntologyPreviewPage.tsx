import { Button, Callout, Card, HTMLSelect, InputGroup, Spinner, Tag, TextArea } from "@blueprintjs/core";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@blueprintjs/core/lib/css/blueprint.css";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";
import {
  getOntologyRegistry,
  getProject3Status,
  getProject3Subgraph,
  queryOntologyObjects,
  runAgentQuery,
} from "../../api";
import { navigate } from "../../routing";
import type { AgentRunResponse } from "../agent/types";
import type {
  ObjectRecord,
  ObjectTypeDefinition,
  OntologyRegistry,
  Project3DegradedResponse,
  Project3IntegrationSnapshot,
  Project3Subgraph,
} from "./types";

interface OntologyPreviewPageProps {
  projectId: string;
  workspaceId: string;
}

function isDegraded(value: Project3Subgraph | Project3DegradedResponse | null): value is Project3DegradedResponse {
  return Boolean(value && "available" in value && value.available === false);
}

function normalized(value: string) {
  return value.replace(/[^a-z0-9]/gi, "").toLowerCase();
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function objectIdentity(record: ObjectRecord): string {
  const preferred = [
    "equipment_id",
    "event_id",
    "work_order_id",
    "inspection_id",
    "action_id",
    "evidence_id",
    "name",
  ];
  for (const key of preferred) {
    const value = record.properties[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return record.id;
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
    const angle = (index / Math.max(1, subgraph.nodes.length)) * Math.PI * 2;
    return {
      id,
      position: {
        x: 320 + Math.cos(angle) * (150 + (index % 3) * 28),
        y: 220 + Math.sin(angle) * (120 + (index % 2) * 36),
      },
      data: {
        label: graphNodeLabel(row, `Object ${index + 1}`),
        raw: row,
      },
      className: "ontology-flow-node",
    } satisfies Node;
  });
  const edges = subgraph.relationships.flatMap((row, index) => {
    const source = relationEndpoint(row, ["source", "source_id", "start", "start_id", "from"]);
    const target = relationEndpoint(row, ["target", "target_id", "end", "end_id", "to"]);
    if (!source || !target || !ids.has(source) || !ids.has(target)) return [];
    const relation = row.type ?? row.relationship_type ?? row.label ?? "RELATED_TO";
    return [{
      id: String(row.id ?? `edge-${index}`),
      source,
      target,
      label: String(relation),
      animated: false,
    } satisfies Edge];
  });
  return { nodes, edges };
}

export function OntologyPreviewPage({ projectId, workspaceId }: OntologyPreviewPageProps) {
  const [registry, setRegistry] = useState<OntologyRegistry | null>(null);
  const [status, setStatus] = useState<Project3IntegrationSnapshot | null>(null);
  const [selectedType, setSelectedType] = useState<string>("");
  const [search, setSearch] = useState("");
  const [objects, setObjects] = useState<ObjectRecord[]>([]);
  const [objectOffset, setObjectOffset] = useState(0);
  const [objectTotal, setObjectTotal] = useState(0);
  const [selectedObject, setSelectedObject] = useState<ObjectRecord | null>(null);
  const [subgraph, setSubgraph] = useState<Project3Subgraph | Project3DegradedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [graphLoading, setGraphLoading] = useState(false);
  const [agentQuestion, setAgentQuestion] = useState("");
  const [agentRun, setAgentRun] = useState<AgentRunResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [error, setError] = useState("");

  const objectTypes = registry?.object_types ?? [];
  const selectedDefinition = objectTypes.find((item) => item.id === selectedType) ?? null;
  const graph = useMemo(
    () => flowElements(isDegraded(subgraph) ? null : subgraph),
    [subgraph],
  );

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
    queryOntologyObjects({
      workspace_id: workspaceId,
      object_type: selectedType,
      search: search.trim() || undefined,
      offset: objectOffset,
      limit: 50,
    })
      .then((payload) => {
        if (cancelled) return;
        setObjects(payload.items);
        setObjectTotal(payload.total);
        setSelectedObject((current) => {
          if (current && payload.items.some((item) => item.id === current.id)) return current;
          return payload.items[0] ?? null;
        });
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Object 검색에 실패했습니다.");
      });
    return () => { cancelled = true; };
  }, [objectOffset, search, selectedType, workspaceId]);

  useEffect(() => {
    setObjectOffset(0);
  }, [search, selectedType]);

  useEffect(() => {
    if (!selectedObject || !status?.schema) {
      setSubgraph(null);
      return;
    }
    const schemaLabel = status.schema.node_identities.find(
      (item) => normalized(item.label) === normalized(selectedObject.object_type),
    )?.label ?? status.schema.node_identities[0]?.label;
    if (!schemaLabel) return;
    setGraphLoading(true);
    getProject3Subgraph({
      project_id: projectId,
      label: schemaLabel,
      identity: objectIdentity(selectedObject),
      depth: 2,
      limit: 80,
    })
      .then(setSubgraph)
      .catch((reason: unknown) => setSubgraph({
        status: "degraded",
        available: false,
        project_id: projectId,
        error: {
          code: "project3_request_failed",
          message: reason instanceof Error ? reason.message : "Graph request failed",
          retryable: true,
        },
      }))
      .finally(() => setGraphLoading(false));
  }, [projectId, selectedObject, status]);

  async function askAcrossStores() {
    const question = agentQuestion.trim();
    if (!question || agentLoading) return;
    setAgentLoading(true);
    try {
      const response = await runAgentQuery({
        project_id: projectId,
        workspace_id: workspaceId,
        question,
        object_type: selectedObject?.object_type,
        object_id: selectedObject ? objectIdentity(selectedObject) : undefined,
        route: "auto",
        top_k: 8,
      });
      setAgentRun(response);
      setError("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Multi-store query failed.");
    } finally {
      setAgentLoading(false);
    }
  }

  function addGraphBoard() {
    if (!selectedObject) return;
    sessionStorage.setItem(
      "ontology-dashboard:add-graph-board",
      JSON.stringify({
        projectId,
        workspaceId,
        objectType: selectedObject.object_type,
        objectId: objectIdentity(selectedObject),
        title: `${objectIdentity(selectedObject)} · Relationship Graph`,
      }),
    );
    navigate("/app");
  }

  if (loading) {
    return <main className="ontology-workbench-loading"><Spinner size={32} /><p>Ontology Workbench를 구성하고 있습니다.</p></main>;
  }

  return (
    <main className="ontology-workbench-page">
      <header className="ontology-workbench-header">
        <div>
          <span className="eyebrow">ONTOLOGY WORKBENCH</span>
          <h1>Objects, relationships, and source context</h1>
          <p>{projectId} · {workspaceId}</p>
        </div>
        <div className="ontology-workbench-header-actions">
          <Tag intent={status?.health.available ? "success" : "warning"} minimal>
            Project 3 {status?.health.available ? status.health.status : "DEGRADED"}
          </Tag>
          {status?.health.latency_ms !== null && status?.health.latency_ms !== undefined ? <Tag minimal>{status.health.latency_ms} ms</Tag> : null}
          <Button icon="add-to-artifact" disabled={!selectedObject} onClick={addGraphBoard}>Add Graph Board</Button>
          <Button icon="dashboard" onClick={() => navigate("/app")}>Dashboard</Button>
        </div>
      </header>

      {error ? <Callout intent="danger" title="Workbench error">{error}</Callout> : null}
      {status?.degraded_reason ? (
        <Callout intent="warning" title="Graph service degraded">
          관계 그래프와 RAG 기능은 제한되지만 PostgreSQL-backed object search와 inspector는 계속 사용할 수 있습니다. {status.degraded_reason}
        </Callout>
      ) : null}

      <section className="ontology-agent-panel" aria-label="Ask across stores">
        <div className="pane-heading">
          <div><small>MULTI-STORE ASK</small><strong>Relational + graph + evidence</strong></div>
          {agentRun ? <Tag intent={agentRun.state.status === "succeeded" ? "success" : "danger"}>{agentRun.state.route}</Tag> : null}
        </div>
        <div className="ontology-agent-input-row">
          <TextArea
            fill
            rows={2}
            value={agentQuestion}
            placeholder="M-014와 연결된 최근 위험 사건, 관련 부품, 유사 정비 사례와 SOP를 보여줘."
            onChange={(event) => setAgentQuestion(event.currentTarget.value)}
          />
          <Button
            intent="primary"
            icon="search-around"
            loading={agentLoading}
            disabled={!agentQuestion.trim()}
            onClick={() => void askAcrossStores()}
          >Ask</Button>
        </div>
        {agentRun ? (
          <div className="ontology-agent-result">
            <p>{agentRun.state.answer || agentRun.state.error || "근거를 찾지 못했습니다."}</p>
            <div className="ontology-agent-evidence">
              {agentRun.state.evidence.map((item) => (
                <Card key={item.evidence_id} elevation={0}>
                  <div><Tag minimal>{item.store}</Tag>{item.dataset_version_id ? <Tag minimal>{item.dataset_version_id}</Tag> : null}</div>
                  <strong>{item.title}</strong>
                  <p>{item.content}</p>
                  <small>{item.reference}</small>
                </Card>
              ))}
            </div>
            {agentRun.state.caveats.length ? <Callout intent="warning">{agentRun.state.caveats.join(" ")}</Callout> : null}
          </div>
        ) : null}
      </section>

      <section className="ontology-workbench-grid">
        <aside className="ontology-object-rail">
          <div className="pane-heading">
            <div><small>OBJECT SET</small><strong>{objects.length} objects</strong></div>
            <Tag minimal>{selectedDefinition?.display_name ?? selectedType}</Tag>
          </div>
          <HTMLSelect
            fill
            value={selectedType}
            onChange={(event) => setSelectedType(event.currentTarget.value)}
          >
            {objectTypes.map((item: ObjectTypeDefinition) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
          </HTMLSelect>
          <InputGroup
            leftIcon="search"
            placeholder="Search object properties"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
          />
          <div className="ontology-object-list">
            {objects.map((item) => (
              <button
                type="button"
                key={item.id}
                className={selectedObject?.id === item.id ? "active" : ""}
                onClick={() => setSelectedObject(item)}
              >
                <strong>{objectIdentity(item)}</strong>
                <span>{item.object_type}</span>
                <small>v{item.version} · {item.source_refs.length} source refs</small>
              </button>
            ))}
            {!objects.length ? <div className="ontology-empty">조건에 맞는 Object가 없습니다.</div> : null}
          </div>
          <div className="ontology-pagination">
            <Button
              small
              icon="chevron-left"
              disabled={objectOffset === 0}
              onClick={() => setObjectOffset((current) => Math.max(0, current - 50))}
            >Previous</Button>
            <span>{objectTotal ? `${objectOffset + 1}-${Math.min(objectOffset + objects.length, objectTotal)} / ${objectTotal}` : "0 objects"}</span>
            <Button
              small
              rightIcon="chevron-right"
              disabled={objectOffset + objects.length >= objectTotal}
              onClick={() => setObjectOffset((current) => current + 50)}
            >Next</Button>
          </div>
        </aside>

        <section className="ontology-graph-pane">
          <div className="pane-heading">
            <div><small>PROJECT 3 SUBGRAPH</small><strong>{selectedObject ? objectIdentity(selectedObject) : "Select an object"}</strong></div>
            <div className="pane-tags">
              <Tag minimal>{isDegraded(subgraph) ? 0 : subgraph?.node_count ?? 0} nodes</Tag>
              <Tag minimal>{isDegraded(subgraph) ? 0 : subgraph?.relationship_count ?? 0} relationships</Tag>
            </div>
          </div>
          <div className="ontology-flow-canvas">
            {graphLoading ? <div className="ontology-graph-overlay"><Spinner size={28} /><span>Graph relationships</span></div> : null}
            {isDegraded(subgraph) ? (
              <Callout intent="warning" title="Subgraph unavailable">{subgraph.error.message}</Callout>
            ) : graph.nodes.length ? (
              <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.35} maxZoom={1.8}>
                <Background gap={20} size={1} />
                <MiniMap pannable zoomable />
                <Controls />
              </ReactFlow>
            ) : (
              <div className="ontology-empty-graph">
                <strong>Graph preview</strong>
                <p>Object를 선택하면 Project 3의 검증된 subgraph API로 2-hop 관계를 불러옵니다.</p>
              </div>
            )}
          </div>
        </section>

        <aside className="ontology-inspector-pane">
          <div className="pane-heading"><div><small>OBJECT INSPECTOR</small><strong>{selectedObject?.id ?? "No selection"}</strong></div></div>
          {selectedObject ? (
            <>
              <Card className="ontology-inspector-card" elevation={0}>
                <h3>Relational detail</h3>
                <dl>
                  <div><dt>Object type</dt><dd>{selectedObject.object_type}</dd></div>
                  <div><dt>Workspace</dt><dd>{selectedObject.workspace_id}</dd></div>
                  <div><dt>Version</dt><dd>{selectedObject.version}</dd></div>
                  <div><dt>Source refs</dt><dd>{selectedObject.source_refs.join(", ") || "—"}</dd></div>
                </dl>
              </Card>
              <Card className="ontology-inspector-card" elevation={0}>
                <h3>Properties</h3>
                <dl>
                  {Object.entries(selectedObject.properties).map(([key, value]) => (
                    <div key={key}><dt>{key}</dt><dd>{displayValue(value)}</dd></div>
                  ))}
                </dl>
              </Card>
              <Card className="ontology-inspector-card" elevation={0}>
                <h3>Graph contract</h3>
                <dl>
                  <div><dt>Mapped project</dt><dd>{status?.health.mapped_project_id ?? "—"}</dd></div>
                  <div><dt>Schema version</dt><dd>{status?.schema?.schema_version ?? "—"}</dd></div>
                  <div><dt>Lifecycle</dt><dd>{status?.readiness?.lifecycle_status ?? "degraded"}</dd></div>
                  <div><dt>Graph size</dt><dd>{status?.readiness ? `${status.readiness.node_count} / ${status.readiness.relationship_count}` : "—"}</dd></div>
                </dl>
              </Card>
            </>
          ) : <div className="ontology-empty">Object를 선택하세요.</div>}
        </aside>
      </section>
    </main>
  );
}
