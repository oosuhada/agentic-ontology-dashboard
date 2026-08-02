import { Button, Callout, Card, HTMLSelect, InputGroup, Spinner, Tag } from "@blueprintjs/core";
import { useEffect, useMemo, useState } from "react";
import { getAgentRun, listAgentRuns, runAgentQuery } from "../../api";
import { governancePath, navigate, ontologyPath } from "../../routing";
import { AgentQueryBoard } from "./AgentQueryBoard";
import { EvidenceTraceList } from "./EvidenceTraceList";
import { GroundedClaimList } from "./GroundedClaimList";
import { OrchestrationStepper } from "./OrchestrationStepper";
import type { AgentQueryInput, AgentRunPage, AgentRunResponse } from "./types";

interface AgentWorkbenchPageProps {
  projectId: string;
  workspaceId: string;
}

interface RecentAgentRun {
  runId: string;
  question: string;
  route: string;
  status: string;
  savedAt: string;
}

function recentKey(projectId: string, workspaceId: string): string {
  return `ontology-dashboard:agent-runs:${projectId}:${workspaceId}`;
}

function loadRecent(projectId: string, workspaceId: string): RecentAgentRun[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(recentKey(projectId, workspaceId)) ?? "[]") as unknown;
    return Array.isArray(parsed) ? parsed.slice(0, 12) as RecentAgentRun[] : [];
  } catch {
    return [];
  }
}

function statusIntent(status: string): "success" | "danger" | "warning" | "none" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "awaiting_approval") return "warning";
  return "none";
}

function currentSearch(): URLSearchParams {
  return new URLSearchParams(window.location.search);
}

export function AgentWorkbenchPage({ projectId, workspaceId }: AgentWorkbenchPageProps) {
  const initial = useMemo(() => currentSearch(), []);
  const [run, setRun] = useState<AgentRunResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<RecentAgentRun[]>(() => loadRecent(projectId, workspaceId));
  const [runPage, setRunPage] = useState<AgentRunPage>({ items: [], offset: 0, limit: 10, total: 0 });
  const [runSearch, setRunSearch] = useState("");
  const [runStatus, setRunStatus] = useState("");
  const [runRoute, setRunRoute] = useState("");
  const [runOffset, setRunOffset] = useState(0);
  const [runListLoading, setRunListLoading] = useState(false);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);
  const [error, setError] = useState("");

  async function refreshRunList(nextOffset = runOffset) {
    setRunListLoading(true);
    try {
      setRunPage(await listAgentRuns({
        project_id: projectId,
        workspace_id: workspaceId,
        offset: nextOffset,
        limit: 10,
        status: runStatus || undefined,
        route: runRoute || undefined,
        search: runSearch.trim() || undefined,
      }));
      setRunOffset(nextOffset);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Persisted agent run list could not be loaded.");
    } finally {
      setRunListLoading(false);
    }
  }

  function remember(nextRun: AgentRunResponse) {
    const item: RecentAgentRun = {
      runId: nextRun.state.run_id,
      question: nextRun.state.question,
      route: nextRun.state.route,
      status: nextRun.state.status,
      savedAt: new Date().toISOString(),
    };
    setRecentRuns((current) => {
      const next = [item, ...current.filter((entry) => entry.runId !== item.runId)].slice(0, 12);
      localStorage.setItem(recentKey(projectId, workspaceId), JSON.stringify(next));
      return next;
    });
  }

  function showRun(nextRun: AgentRunResponse, updateUrl = true) {
    setRun(nextRun);
    setSelectedEvidenceId(nextRun.state.evidence[0]?.evidence_id ?? null);
    setError("");
    remember(nextRun);
    if (updateUrl) {
      const url = new URL(window.location.href);
      url.search = "";
      url.searchParams.set("run", nextRun.state.run_id);
      window.history.replaceState({}, "", `${url.pathname}${url.search}`);
    }
  }

  async function query(input: AgentQueryInput) {
    setLoading(true);
    try {
      showRun(await runAgentQuery(input));
      await refreshRunList(0);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Agent query failed.");
    } finally {
      setLoading(false);
    }
  }

  async function loadRun(runId: string, updateUrl = true) {
    setLoadingRun(true);
    try {
      const response = await getAgentRun(projectId, workspaceId, runId);
      if (response.state.workspace_id !== workspaceId) {
        throw new Error("Persisted run belongs to another workspace.");
      }
      showRun(response, updateUrl);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Persisted run could not be loaded.");
    } finally {
      setLoadingRun(false);
    }
  }

  useEffect(() => {
    const runId = initial.get("run");
    if (runId) void loadRun(runId, false);
    void refreshRunList(0);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshRunList(0), 250);
    return () => window.clearTimeout(timer);
  }, [runSearch, runStatus, runRoute]);

  return (
    <main className="agent-workbench-page">
      <header className="agent-workbench-header">
        <div>
          <span className="eyebrow">AGENT EVIDENCE WORKBENCH</span>
          <h1>Ask, inspect, and trace every claim</h1>
          <p>{projectId} · {workspaceId} · typed tools only</p>
        </div>
        <div className="agent-header-actions">
          {run ? <Tag intent={statusIntent(run.state.status)}>{run.state.status}</Tag> : null}
          {run ? <Tag minimal>{run.state.route}</Tag> : null}
          <Button icon="diagram-tree" onClick={() => navigate(ontologyPath(projectId, workspaceId))}>Ontology</Button>
          <Button icon="shield" onClick={() => navigate(governancePath(projectId, workspaceId))}>Governance</Button>
          <Button icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</Button>
        </div>
      </header>

      {error ? <Callout intent="danger" title="Agent Workbench error"><span>{error}</span> <Button minimal small onClick={() => setError("")}>Dismiss</Button></Callout> : null}
      <Callout intent="primary" icon="lock" title="Execution boundary">
        Project 2는 scope·routing·evidence merge·claim validation만 수행합니다. Text-to-Cypher와 graph RAG는 Project 3의 typed HTTP API 안에 유지되며 임의 SQL·Cypher 입력은 노출하지 않습니다.
      </Callout>

      <section className="agent-workbench-grid">
        <aside className="agent-query-rail">
          <AgentQueryBoard
            projectId={projectId}
            workspaceId={workspaceId}
            initialQuestion={initial.get("question") ?? ""}
            initialObjectType={initial.get("objectType") ?? ""}
            initialObjectId={initial.get("objectId") ?? ""}
            loading={loading}
            loadingRun={loadingRun}
            onQuery={query}
            onLoadRun={loadRun}
          />
          <section className="agent-recent-runs agent-server-runs">
            <header><span className="eyebrow">PERSISTED RUNS</span><strong>{runPage.total}</strong></header>
            <div className="agent-run-filters">
              <InputGroup leftIcon="search" placeholder="Question filter" value={runSearch} onChange={(event) => setRunSearch(event.currentTarget.value)} />
              <HTMLSelect fill value={runStatus} onChange={(event) => setRunStatus(event.currentTarget.value)}>
                <option value="">All status</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="running">Running</option>
              </HTMLSelect>
              <HTMLSelect fill value={runRoute} onChange={(event) => setRunRoute(event.currentTarget.value)}>
                <option value="">All routes</option><option value="relational">Relational</option><option value="graph">Graph</option><option value="vector">Vector</option><option value="hybrid">Hybrid</option>
              </HTMLSelect>
            </div>
            <div>
              {runListLoading ? <p>Persisted runs loading…</p> : null}
              {runPage.items.map((item) => (
                <button type="button" key={item.run_id} className={run?.state.run_id === item.run_id ? "active" : ""} onClick={() => void loadRun(item.run_id)}>
                  <strong>{item.question}</strong>
                  <span>{item.run_id}</span>
                  <small>{item.route} · {item.status} · {item.evidence_count} evidence · {new Date(item.created_at).toLocaleString()}</small>
                </button>
              ))}
              {!runListLoading && !runPage.items.length ? <p>조건에 맞는 persisted run이 없습니다.</p> : null}
            </div>
            <footer className="agent-run-pagination">
              <Button small icon="chevron-left" disabled={runOffset === 0 || runListLoading} onClick={() => void refreshRunList(Math.max(0, runOffset - runPage.limit))}>Previous</Button>
              <span>{runPage.total ? `${runOffset + 1}-${Math.min(runOffset + runPage.items.length, runPage.total)} / ${runPage.total}` : "0 runs"}</span>
              <Button small rightIcon="chevron-right" disabled={runOffset + runPage.items.length >= runPage.total || runListLoading} onClick={() => void refreshRunList(runOffset + runPage.limit)}>Next</Button>
            </footer>
          </section>
          {recentRuns.length ? <small className="agent-local-history-note">Browser local history retained for offline recovery: {recentRuns.length}</small> : null}
        </aside>

        <section className="agent-answer-pane">
          {!run && (loading || loadingRun) ? <div className="agent-loading"><Spinner size={30} /><p>Scoped evidence를 수집하고 있습니다.</p></div> : null}
          {run ? (
            <>
              <div className="agent-pane-heading">
                <div><small>GROUNDED ANSWER</small><strong>{run.state.run_id}</strong></div>
                <div><Tag minimal>{run.state.evidence.length} evidence</Tag><Tag minimal>{run.state.claims.length} claims</Tag></div>
              </div>
              <div className="agent-answer-scroll">
                <Card elevation={0} className="agent-answer-card">
                  <span className="eyebrow">QUESTION</span>
                  <h2>{run.state.question}</h2>
                  <span className="eyebrow">ANSWER</span>
                  <p>{run.state.answer || run.state.error || "검증 가능한 답변이 생성되지 않았습니다."}</p>
                  <dl>
                    <div><dt>Object type</dt><dd>{run.state.object_type ?? "unconstrained"}</dd></div>
                    <div><dt>Object ID</dt><dd>{run.state.object_id ?? "unconstrained"}</dd></div>
                    <div><dt>Checkpoints</dt><dd>{run.state.checkpoint_sequence}</dd></div>
                  </dl>
                </Card>
                {run.state.caveats.length ? <Callout intent="warning" title="Caveats">{run.state.caveats.join(" ")}</Callout> : null}
                <section className="agent-section">
                  <header><div><small>VALIDATED CLAIMS</small><strong>Claims link back to evidence IDs</strong></div><Tag minimal>{run.state.claims.length}</Tag></header>
                  <GroundedClaimList claims={run.state.claims} onSelectEvidence={setSelectedEvidenceId} />
                </section>
                <section className="agent-section">
                  <header><div><small>EVIDENCE TRACE</small><strong>Source, version, object, and score</strong></div><Tag minimal>{run.state.evidence.length}</Tag></header>
                  <EvidenceTraceList items={run.state.evidence} selectedEvidenceId={selectedEvidenceId} onSelectEvidence={setSelectedEvidenceId} />
                </section>
              </div>
            </>
          ) : (
            <div className="agent-empty-canvas">
              <strong>Run a governed query</strong>
              <p>답변만 보여주지 않고 어떤 store·Dataset Version·Object에서 근거가 왔는지 함께 표시합니다.</p>
            </div>
          )}
        </section>

        <aside className="agent-lineage-pane">
          <div className="agent-pane-heading"><div><small>ORCHESTRATION LINEAGE</small><strong>Route → collect → merge → validate</strong></div></div>
          {run ? (
            <div className="agent-lineage-scroll">
              <OrchestrationStepper run={run} />
              <section className="agent-trace-records">
                <header><span className="eyebrow">PERSISTED TRACE</span><strong>{run.traces.length}</strong></header>
                {run.traces.map((trace) => (
                  <article key={trace.id}>
                    <div><strong>{trace.step_name}</strong><Tag minimal intent={statusIntent(trace.status)}>{trace.status}</Tag></div>
                    <small>{trace.store_kind ?? "orchestrator"} · {trace.latency_ms ?? 0} ms · {new Date(trace.created_at).toLocaleString()}</small>
                    {trace.input || trace.output ? <details><summary>Execution metadata</summary><pre>{JSON.stringify({ input: trace.input, output: trace.output }, null, 2)}</pre></details> : null}
                  </article>
                ))}
              </section>
            </div>
          ) : <div className="agent-empty-state"><p>실행 후 checkpoint와 store trace가 표시됩니다.</p></div>}
        </aside>
      </section>
    </main>
  );
}
