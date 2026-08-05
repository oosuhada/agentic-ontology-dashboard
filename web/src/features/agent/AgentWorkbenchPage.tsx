import { Button, Callout, Card, HTMLSelect, InputGroup, Tag } from "@blueprintjs/core";
import { Bot, PanelRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getAgentRun, getProject3Status, listAgentRuns, runAgentQuery } from "../../api";
import { governancePath, navigate, ontologyPath } from "../../routing";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { FoundryDrawer } from "../../ui/foundry/FoundryDrawer";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchHeader } from "../../ui/foundry/WorkbenchChrome";
import { WorkbenchState } from "../../ui/foundry/WorkbenchState";
import { useMediaQuery } from "../../ui/foundry/useMediaQuery";
import { useI18n } from "../../ui/i18n/I18nProvider";
import { AgentQueryBoard } from "./AgentQueryBoard";
import { AgentRunInspector } from "./AgentRunInspector";
import { GroundedClaimList } from "./GroundedClaimList";
import { agentOutcomeIntent, agentOutcomeLabel, deriveAgentOutcome } from "./agentOutcome";
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

function currentSearch(): URLSearchParams {
  return new URLSearchParams(window.location.search);
}

export function AgentWorkbenchPage({ projectId, workspaceId }: AgentWorkbenchPageProps) {
  const { t, locale } = useI18n();
  const isMobile = useMediaQuery("(max-width: 760px)");
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
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [graphRoutesAvailable, setGraphRoutesAvailable] = useState(true);

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
    if (isMobile) setInspectorOpen(false);
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
    void getProject3Status(projectId)
      .then((status) => setGraphRoutesAvailable(Boolean(status.health.available)))
      .catch(() => setGraphRoutesAvailable(false));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshRunList(0), 250);
    return () => window.clearTimeout(timer);
  }, [runSearch, runStatus, runRoute]);

  return (
    <main className="agent-workbench-page">
      <WorkbenchHeader
        className="agent-workbench-header"
        title={<EntityTitle icon={Bot} eyebrow="AGENT EVIDENCE WORKBENCH" title="Grounded Evidence Terminal" subtitle={`${projectId} · ${workspaceId} · typed tools only`} />}
        metadata={run ? (() => {
          const outcome = deriveAgentOutcome({
            status: run.state.status,
            evidenceCount: run.state.evidence.length,
            claimCount: run.state.claims.length,
            failedStepCount: run.traces.filter((trace) => trace.status === "failed").length,
            caveats: run.state.caveats,
          });
          return <div className="agent-header-status"><StatusPill intent={agentOutcomeIntent(outcome)}>{agentOutcomeLabel(outcome, locale)}</StatusPill><StatusPill intent="primary">{run.state.route}</StatusPill></div>;
        })() : null}
        actions={<div className="agent-header-actions"><Button icon="diagram-tree" onClick={() => navigate(ontologyPath(projectId, workspaceId))}>Ontology</Button><Button icon="shield" onClick={() => navigate(governancePath(projectId, workspaceId))}>Governance</Button><Button icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>Dashboard</Button></div>}
      />

      {error ? <Callout intent="danger" title="Agent Workbench error"><span>{error}</span> <Button minimal small onClick={() => setError("")}>{t("common.dismiss")}</Button></Callout> : null}
      <Callout intent="primary" icon="lock" title="Execution boundary">
        Project 2는 scope·routing·evidence merge·claim validation만 수행합니다. Text-to-Cypher와 graph RAG는 Project 3의 typed HTTP API 안에 유지되며 임의 SQL·Cypher 입력은 노출하지 않습니다.
      </Callout>

      <section className="agent-workbench-grid">
        <aside className="agent-query-rail">
          <section className="agent-recent-runs agent-server-runs">
            <header><span className="eyebrow">PERSISTED RUNS</span><strong>{runPage.total}</strong></header>
            <div className="agent-run-filters">
              <InputGroup aria-label="Agent question filter" leftIcon="search" placeholder="Question filter" value={runSearch} onChange={(event) => setRunSearch(event.currentTarget.value)} />
              <HTMLSelect fill value={runStatus} onChange={(event) => setRunStatus(event.currentTarget.value)}>
                <option value="">All status</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="running">Running</option>
              </HTMLSelect>
              <HTMLSelect fill value={runRoute} onChange={(event) => setRunRoute(event.currentTarget.value)}>
                <option value="">All routes</option><option value="relational">Relational</option><option value="graph">Graph</option><option value="vector">Vector</option><option value="hybrid">Hybrid</option>
              </HTMLSelect>
            </div>
            <div>
              {runListLoading ? <WorkbenchState kind="refreshing" compact /> : null}
              {runPage.items.map((item) => (
                <button type="button" key={item.run_id} className={run?.state.run_id === item.run_id ? "active" : ""} onClick={() => void loadRun(item.run_id)}>
                  <strong>{item.question}</strong>
                  <span>{item.run_id}</span>
                  <small>{item.route} · {agentOutcomeLabel(deriveAgentOutcome({ status: item.status, evidenceCount: item.evidence_count, claimCount: item.claim_count }), locale)} · {item.evidence_count} evidence · {new Date(item.created_at).toLocaleString(locale)}</small>
                </button>
              ))}
              {!runListLoading && !runPage.items.length ? <WorkbenchState kind="empty" compact detail="조건에 맞는 persisted run이 없습니다." /> : null}
            </div>
            <footer className="agent-run-pagination">
              <Button small icon="chevron-left" disabled={runOffset === 0 || runListLoading} onClick={() => void refreshRunList(Math.max(0, runOffset - runPage.limit))}>{t("common.previous")}</Button>
              <span>{runPage.total ? `${runOffset + 1}-${Math.min(runOffset + runPage.items.length, runPage.total)} / ${runPage.total}` : "0 runs"}</span>
              <Button small rightIcon="chevron-right" disabled={runOffset + runPage.items.length >= runPage.total || runListLoading} onClick={() => void refreshRunList(runOffset + runPage.limit)}>{t("common.next")}</Button>
            </footer>
          </section>
          {recentRuns.length ? <small className="agent-local-history-note">Browser local history retained for offline recovery: {recentRuns.length}</small> : null}
        </aside>

        <section className="agent-answer-pane">
          {!run && (loading || loadingRun) ? <WorkbenchState kind="loading" title="Scoped evidence를 수집하고 있습니다." /> : null}
          {run ? (
            <>
              <div className="agent-pane-heading">
                <div><small>GROUNDED ANSWER</small><strong>{run.state.run_id}</strong></div>
                <div><Tag minimal>{run.state.evidence.length} evidence</Tag><Tag minimal>{run.state.claims.length} claims</Tag>{isMobile ? <button type="button" className="fd-toolbar-button" onClick={() => setInspectorOpen(true)}><PanelRight size={12} /> Inspector</button> : null}</div>
              </div>
              <div className="agent-answer-scroll">
                {(() => {
                  const outcome = deriveAgentOutcome({
                    status: run.state.status,
                    evidenceCount: run.state.evidence.length,
                    claimCount: run.state.claims.length,
                    failedStepCount: run.traces.filter((trace) => trace.status === "failed").length,
                    caveats: run.state.caveats,
                  });
                  if (outcome === "no_evidence") return <Callout intent="warning" title={agentOutcomeLabel(outcome, locale)}>{locale === "ko-KR" ? "질의 실행은 완료됐지만 현재 Scope에서 검증 가능한 근거를 찾지 못했습니다. 성공 결과로 오해하지 않도록 근거 없음 상태로 표시합니다." : "The query completed, but no verifiable evidence matched the current scope."}</Callout>;
                  if (outcome === "partial") return <Callout intent="warning" title={agentOutcomeLabel(outcome, locale)}>{locale === "ko-KR" ? "일부 Evidence Store가 응답하지 않아 제한된 근거만 사용했습니다." : "One or more evidence stores were unavailable, so the answer uses limited evidence."}</Callout>;
                  return null;
                })()}
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
              </div>
            </>
          ) : (
            <div className="agent-empty-canvas">
              <strong>Run a governed query</strong>
              <p>답변만 보여주지 않고 어떤 store·Dataset Version·Object에서 근거가 왔는지 함께 표시합니다.</p>
            </div>
          )}
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
            graphRoutesAvailable={graphRoutesAvailable}
          />
        </section>

        {!isMobile ? <AgentRunInspector run={run} selectedEvidenceId={selectedEvidenceId} onSelectEvidence={setSelectedEvidenceId} /> : null}
      </section>
      {isMobile && inspectorOpen ? (
        <FoundryDrawer ariaLabel="Agent run inspector" title="Agent run inspector" position="bottom" onClose={() => setInspectorOpen(false)}>
          <AgentRunInspector run={run} selectedEvidenceId={selectedEvidenceId} onSelectEvidence={setSelectedEvidenceId} />
        </FoundryDrawer>
      ) : null}
    </main>
  );
}
