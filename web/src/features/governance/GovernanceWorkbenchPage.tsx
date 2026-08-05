import { Button, Callout, Card, HTMLSelect, InputGroup, Spinner, Tag } from "@blueprintjs/core";
import { ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  getGovernanceAgentRun,
  getGovernanceOverview,
  listAgentRuns,
  retryGovernanceProjection,
} from "../../api";
import { agentPath, datasetCatalogPath, navigate, ontologyPath } from "../../routing";
import { EntityTitle } from "../../ui/foundry/EntityTitle";
import { FoundryDrawer } from "../../ui/foundry/FoundryDrawer";
import { MetricStrip } from "../../ui/foundry/MetricStrip";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchHeader } from "../../ui/foundry/WorkbenchChrome";
import { useMediaQuery } from "../../ui/foundry/useMediaQuery";
import { WorkbenchState } from "../../ui/foundry/WorkbenchState";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type { AgentRunPage } from "../agent/types";
import { agentOutcomeIntent, agentOutcomeLabel, deriveAgentOutcome } from "../agent/agentOutcome";
import { GovernanceRecordInspector } from "./GovernanceRecordInspector";
import type {
  GovernanceAgentRunDetail,
  GovernanceApproval,
  GovernanceOverview,
  GovernanceProjection,
} from "./types";

type GovernanceTab = "overview" | "agent-runs" | "projections" | "lineage" | "approvals" | "policies";

interface GovernanceWorkbenchPageProps {
  projectId: string;
  workspaceId: string;
}

const TABS: Array<{ id: GovernanceTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "agent-runs", label: "Agent Runs" },
  { id: "projections", label: "Projection Health" },
  { id: "lineage", label: "Data Lineage" },
  { id: "approvals", label: "Approvals" },
  { id: "policies", label: "Access & Policy" },
];

const TAB_LABELS_KO: Record<GovernanceTab, string> = {
  overview: "개요",
  "agent-runs": "Agent 실행",
  projections: "Projection 상태",
  lineage: "데이터 계보",
  approvals: "승인",
  policies: "접근 및 정책",
};

function statusIntent(status: string): "success" | "warning" | "danger" | "none" {
  if (["ready", "succeeded", "approved", "active"].includes(status)) return "success";
  if (["failed", "rejected", "unavailable"].includes(status)) return "danger";
  if (["pending", "indexing", "pending_approval", "running"].includes(status)) return "warning";
  return "none";
}

function pillIntent(status: string): "success" | "warning" | "danger" | "neutral" {
  const resolved = statusIntent(status);
  return resolved === "none" ? "neutral" : resolved;
}

function agentTagIntent(input: Parameters<typeof deriveAgentOutcome>[0]): "success" | "warning" | "danger" | "none" {
  const intent = agentOutcomeIntent(deriveAgentOutcome(input));
  return intent === "neutral" ? "none" : intent;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function JsonPreview({ value }: { value: unknown }) {
  return <pre className="governance-json-preview">{JSON.stringify(value, null, 2)}</pre>;
}

export function GovernanceWorkbenchPage({ projectId, workspaceId }: GovernanceWorkbenchPageProps) {
  const isMobile = useMediaQuery("(max-width: 760px)");
  const { t, locale } = useI18n();
  const [overview, setOverview] = useState<GovernanceOverview | null>(null);
  const [activeTab, setActiveTab] = useState<GovernanceTab>("overview");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedProjectionId, setSelectedProjectionId] = useState<string | null>(null);
  const [selectedApprovalId, setSelectedApprovalId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<GovernanceAgentRunDetail | null>(null);
  const [runPage, setRunPage] = useState<AgentRunPage>({ items: [], offset: 0, limit: 20, total: 0 });
  const [runSearch, setRunSearch] = useState("");
  const [runStatus, setRunStatus] = useState("");
  const [runRoute, setRunRoute] = useState("");
  const [runOffset, setRunOffset] = useState(0);
  const [runListLoading, setRunListLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [recordInspectorOpen, setRecordInspectorOpen] = useState(false);

  async function refreshRunList(nextOffset = runOffset) {
    setRunListLoading(true);
    try {
      const payload = await listAgentRuns({
        project_id: projectId,
        workspace_id: workspaceId,
        offset: nextOffset,
        limit: 20,
        status: runStatus || undefined,
        route: runRoute || undefined,
        search: runSearch.trim() || undefined,
      });
      setRunPage(payload);
      setRunOffset(payload.offset);
      setSelectedRunId((current) => {
        if (current && payload.items.some((item) => item.run_id === current)) return current;
        return payload.items[0]?.run_id ?? null;
      });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Agent run 목록을 불러오지 못했습니다.");
    } finally {
      setRunListLoading(false);
    }
  }

  async function refresh() {
    setLoading(true);
    try {
      const payload = await getGovernanceOverview(projectId, workspaceId);
      setOverview(payload);
      setSelectedRunId((current) => current ?? payload.agent_runs[0]?.run_id ?? null);
      setSelectedProjectionId((current) => current && payload.projections.some((item) => item.id === current) ? current : payload.projections[0]?.id ?? null);
      setSelectedApprovalId((current) => current && payload.approvals.some((item) => item.id === current) ? current : payload.approvals[0]?.id ?? null);
      setError("");
      await refreshRunList(0);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Governance Workbench를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [projectId, workspaceId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshRunList(0), 250);
    return () => window.clearTimeout(timer);
  }, [runSearch, runStatus, runRoute]);

  useEffect(() => {
    if (!selectedRunId) {
      setRunDetail(null);
      return;
    }
    let cancelled = false;
    setRunLoading(true);
    getGovernanceAgentRun(projectId, workspaceId, selectedRunId)
      .then((payload) => {
        if (!cancelled) setRunDetail(payload);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Agent run trace를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setRunLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId, selectedRunId, workspaceId]);

  const failedProjections = useMemo(
    () => overview?.projections.filter((item) => item.status === "failed") ?? [],
    [overview],
  );
  const pendingProjections = useMemo(
    () => overview?.projections.filter((item) => item.status !== "ready" && item.status !== "failed") ?? [],
    [overview],
  );
  const noEvidenceRuns = useMemo(
    () => overview?.agent_runs.filter((run) => deriveAgentOutcome({ status: run.status, evidenceCount: run.evidence_count, claimCount: run.claim_count, caveats: run.caveats }) === "no_evidence").length ?? 0,
    [overview],
  );
  const permissionGroups = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const permission of overview?.access.permissions ?? []) {
      const group = permission.split(".")[0] || "other";
      groups.set(group, [...(groups.get(group) ?? []), permission]);
    }
    return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
  }, [overview]);
  const selectedProjection = useMemo(
    () => overview?.projections.find((item) => item.id === selectedProjectionId) ?? null,
    [overview, selectedProjectionId],
  );
  const selectedApproval = useMemo(
    () => overview?.approvals.find((item) => item.id === selectedApprovalId) ?? null,
    [overview, selectedApprovalId],
  );

  async function retryProjection(projection: GovernanceProjection) {
    setRetryingId(projection.id);
    try {
      const result = await retryGovernanceProjection(projectId, workspaceId, projection.id);
      setNotice(result.message);
      await refresh();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Projection retry에 실패했습니다.");
    } finally {
      setRetryingId(null);
    }
  }

  if (loading && !overview) {
    return <main className="governance-workbench-loading"><WorkbenchState kind="loading" title="Governance evidence를 재구성하고 있습니다." /></main>;
  }

  return (
    <main className="governance-workbench-page">
      <WorkbenchHeader
        className="governance-workbench-header"
        title={<EntityTitle icon={ShieldCheck} eyebrow="GOVERNANCE WORKBENCH" title={locale === "ko-KR" ? "프로젝트 점검 상태" : "Project Checkpoints"} subtitle={`${projectId} · ${workspaceId} · ${locale === "ko-KR" ? "갱신" : "generated"} ${formatDate(overview?.generated_at)}`} />}
        metadata={<StatusPill intent={failedProjections.length ? "danger" : pendingProjections.length || noEvidenceRuns ? "warning" : "success"}>{locale === "ko-KR" ? `조치 필요 ${failedProjections.length + pendingProjections.length + noEvidenceRuns}` : `${failedProjections.length + pendingProjections.length + noEvidenceRuns} need attention`}</StatusPill>}
        actions={<div className="governance-header-actions"><Button icon="refresh" onClick={() => void refresh()}>{t("common.refresh")}</Button><Button icon="diagram-tree" onClick={() => navigate(ontologyPath(projectId, workspaceId))}>{t("common.ontology")}</Button><Button icon="database" onClick={() => navigate(datasetCatalogPath(projectId))}>{t("common.datasets")}</Button><Button icon="dashboard" onClick={() => navigate(`/app/projects/${encodeURIComponent(projectId)}`)}>{t("common.dashboard")}</Button></div>}
      />

      {error ? <Callout intent="danger" title="Governance error"><span>{error}</span> <Button minimal small onClick={() => setError("")}>{t("common.dismiss")}</Button></Callout> : null}
      {notice ? <Callout intent="success" title="Governance action"><span>{notice}</span> <Button minimal small onClick={() => setNotice("")}>{t("common.dismiss")}</Button></Callout> : null}
      <Callout intent="primary" icon="shield" title="Project governance boundary">
        계정 승인·비밀번호·tenant-level 사용자 관리는 Admin 앱에 남겨두고, 이 화면은 현재 Project의 agent trace, evidence, lineage, approval, projection 상태만 다룹니다.
      </Callout>

      <nav className="governance-tabs" aria-label="Governance sections">
        {TABS.map((tab) => (
          <button key={tab.id} type="button" className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)}>
            {locale === "ko-KR" ? TAB_LABELS_KO[tab.id] : tab.label}
          </button>
        ))}
      </nav>

      {overview && activeTab === "overview" ? (
        <section className="governance-overview" aria-label="Governance overview">
          <MetricStrip className="governance-kpi-grid" metrics={[
            { id: "ready-projections", label: locale === "ko-KR" ? "정상 Projection" : "Ready projections", value: overview.projections.filter((item) => item.status === "ready").length, detail: `${overview.counts.projections} total`, tone: "success" },
            { id: "projection-attention", label: locale === "ko-KR" ? "Projection 조치 필요" : "Projection attention", value: failedProjections.length + pendingProjections.length, detail: `${failedProjections.length} failed · ${pendingProjections.length} pending`, tone: failedProjections.length ? "danger" : pendingProjections.length ? "warning" : "success" },
            { id: "agent-evidence", label: locale === "ko-KR" ? "근거 없는 Agent 실행" : "Runs without evidence", value: noEvidenceRuns, detail: `${overview.counts.agent_runs} total runs`, tone: noEvidenceRuns ? "warning" : "success" },
            { id: "approvals", label: locale === "ko-KR" ? "승인 대기" : "Pending approvals", value: overview.counts.pending_approvals, detail: locale === "ko-KR" ? "검토 대기" : "pending review", tone: overview.counts.pending_approvals ? "warning" : "success" },
            { id: "datasets", label: "Datasets", value: overview.counts.datasets, detail: `${overview.counts.dataset_versions} versions` },
          ]} />
          <div className="governance-overview-grid">
            <section className="governance-panel">
              <div className="governance-panel-heading"><div><small>RECENT AGENT RUNS</small><strong>Grounded execution trace</strong></div><Button minimal small onClick={() => setActiveTab("agent-runs")}>Inspect all</Button></div>
              <div className="governance-run-list compact">
                {overview.agent_runs.slice(0, 6).map((run) => (
                  <button key={run.run_id} type="button" onClick={() => { setSelectedRunId(run.run_id); setActiveTab("agent-runs"); }}>
                    <div><strong>{run.question}</strong><small>{run.run_id}</small></div>
                    <div><Tag minimal>{run.route}</Tag><Tag minimal intent={agentTagIntent({ status: run.status, evidenceCount: run.evidence_count, claimCount: run.claim_count })}>{agentOutcomeLabel(deriveAgentOutcome({ status: run.status, evidenceCount: run.evidence_count, claimCount: run.claim_count }), locale)}</Tag></div>
                  </button>
                ))}
                {!overview.agent_runs.length ? <p className="governance-empty">아직 저장된 agent run이 없습니다.</p> : null}
              </div>
            </section>
            <section className="governance-panel">
              <div className="governance-panel-heading"><div><small>PROJECTION ATTENTION</small><strong>Eventually consistent stores</strong></div><Button minimal small onClick={() => setActiveTab("projections")}>Open health</Button></div>
              <div className="governance-projection-summary">
                {overview.projections.filter((item) => item.status !== "ready").slice(0, 8).map((item) => (
                  <article key={item.id}>
                    <div><strong>{item.dataset_name}</strong><small>{item.version_label} · {item.store_kind}</small></div>
                    <Tag intent={statusIntent(item.status)}>{item.status}</Tag>
                  </article>
                ))}
                {!overview.projections.some((item) => item.status !== "ready") ? <p className="governance-empty">모든 projection이 ready 상태입니다.</p> : null}
              </div>
            </section>
          </div>
        </section>
      ) : null}

      {overview && activeTab === "agent-runs" ? (
        <section className="governance-agent-layout" aria-label="Agent run governance">
          <aside className="governance-agent-rail">
            <div className="governance-panel-heading"><div><small>AGENT RUNS</small><strong>{runPage.total} persisted runs</strong></div>{runListLoading ? <Spinner size={16} /> : null}</div>
            <div className="governance-run-filters">
              <InputGroup aria-label="Governance agent question filter" leftIcon="search" placeholder="Question filter" value={runSearch} onChange={(event) => setRunSearch(event.currentTarget.value)} />
              <div>
                <HTMLSelect fill value={runStatus} onChange={(event) => setRunStatus(event.currentTarget.value)}>
                  <option value="">All status</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="running">Running</option>
                </HTMLSelect>
                <HTMLSelect fill value={runRoute} onChange={(event) => setRunRoute(event.currentTarget.value)}>
                  <option value="">All routes</option><option value="relational">Relational</option><option value="graph">Graph</option><option value="vector">Vector</option><option value="hybrid">Hybrid</option>
                </HTMLSelect>
              </div>
            </div>
            <div className="governance-run-list">
              {runPage.items.map((run) => (
                <button key={run.run_id} type="button" className={selectedRunId === run.run_id ? "active" : ""} onClick={() => setSelectedRunId(run.run_id)}>
                  <div><strong>{run.question}</strong><small>{run.run_id} · {run.evidence_count} evidence · {new Date(run.created_at).toLocaleString()}</small></div>
                  <Tag minimal intent={agentTagIntent({ status: run.status, evidenceCount: run.evidence_count, claimCount: run.claim_count })}>{agentOutcomeLabel(deriveAgentOutcome({ status: run.status, evidenceCount: run.evidence_count, claimCount: run.claim_count }), locale)}</Tag>
                </button>
              ))}
              {!runListLoading && !runPage.items.length ? <p className="governance-empty">조건에 맞는 Agent run이 없습니다.</p> : null}
            </div>
            <footer className="governance-run-pagination">
              <Button small icon="chevron-left" disabled={runOffset === 0 || runListLoading} onClick={() => void refreshRunList(Math.max(0, runOffset - runPage.limit))}>{t("common.previous")}</Button>
              <span>{runPage.total ? `${runOffset + 1}-${Math.min(runOffset + runPage.items.length, runPage.total)} / ${runPage.total}` : "0 runs"}</span>
              <Button small rightIcon="chevron-right" disabled={runOffset + runPage.items.length >= runPage.total || runListLoading} onClick={() => void refreshRunList(runOffset + runPage.limit)}>{t("common.next")}</Button>
            </footer>
          </aside>
          <section className="governance-agent-detail">
            {runLoading ? <div className="governance-detail-loading"><Spinner size={24} />Trace reconstruction</div> : null}
            {runDetail ? (
              <>
                <div className="governance-panel-heading"><div><small>RUN DETAIL</small><strong>{runDetail.state.run_id}</strong></div><div><Tag minimal>{runDetail.state.route}</Tag>{(() => { const input = { status: runDetail.state.status, evidenceCount: runDetail.state.evidence.length, claimCount: runDetail.state.claims.length, failedStepCount: runDetail.traces.filter((trace) => trace.status === "failed").length, caveats: runDetail.state.caveats }; const outcome = deriveAgentOutcome(input); return <Tag intent={agentTagIntent(input)}>{agentOutcomeLabel(outcome, locale)}</Tag>; })()}<Button small icon="search-around" onClick={() => navigate(agentPath(projectId, workspaceId, { runId: runDetail.state.run_id }))}>Open Agent Evidence</Button></div></div>
                <div className="governance-detail-scroll">
                  <Card elevation={0} className="governance-answer-card">
                    <small>QUESTION</small><h2>{runDetail.state.question}</h2>
                    <small>GROUNDED ANSWER</small><p>{runDetail.state.answer || runDetail.state.error || "No grounded answer"}</p>
                  </Card>
                  <section className="governance-detail-section"><header><small>VALIDATED CLAIMS</small><strong>{runDetail.state.claims.length}</strong></header>{runDetail.state.claims.map((claim) => <article key={claim.claim_id} className="governance-claim"><div><Tag minimal intent={claim.validated ? "success" : "danger"}>{claim.validated ? "validated" : "unvalidated"}</Tag><Tag minimal>{claim.confidence}</Tag></div><p>{claim.text}</p><small>{claim.evidence_ids.join(" · ")}</small></article>)}</section>
                  <section className="governance-detail-section"><header><small>EVIDENCE SOURCES</small><strong>{runDetail.state.evidence.length}</strong></header><div className="governance-evidence-grid">{runDetail.state.evidence.map((item) => <Card key={item.evidence_id} elevation={0}><div><Tag minimal>{item.store}</Tag>{item.dataset_version_id ? <Tag minimal>{item.dataset_version_id}</Tag> : null}</div><strong>{item.title}</strong><p>{item.content}</p><small>{item.reference}</small></Card>)}</div></section>
                  <section className="governance-detail-section"><header><small>EXECUTION TRACE</small><strong>{runDetail.traces.length}</strong></header><div className="governance-trace-table">{runDetail.traces.map((trace) => <article key={trace.id}><div><strong>{trace.step_name}</strong><small>{trace.store_kind ?? "orchestrator"} · {trace.latency_ms ?? 0} ms · {formatDate(trace.created_at)}</small></div><Tag intent={statusIntent(trace.status)}>{trace.status}</Tag><details><summary>Validated metadata</summary><JsonPreview value={{ input: trace.input, output: trace.output }} /></details></article>)}</div></section>
                  <section className="governance-detail-section"><header><small>CHECKPOINTS</small><strong>{runDetail.checkpoints.length}</strong></header><div className="governance-checkpoint-list">{runDetail.checkpoints.map((checkpoint) => <article key={checkpoint.id}><strong>#{checkpoint.sequence} · {checkpoint.node_name}</strong><span>{formatDate(checkpoint.created_at)}</span></article>)}</div></section>
                </div>
              </>
            ) : <p className="governance-empty">Agent run을 선택하세요.</p>}
          </section>
        </section>
      ) : null}

      {overview && activeTab === "projections" ? (
        <section className="governance-record-layout" aria-label="Projection health">
          <section className="governance-table-panel">
            <div className="governance-panel-heading"><div><small>STORE PROJECTIONS</small><strong>Relational source and eventual-consistency stores</strong></div><StatusPill intent={overview.access.can_retry_projection ? "success" : "neutral"}>{overview.access.can_retry_projection ? "retry enabled" : "read only"}</StatusPill></div>
            <div className="fd-resource-table governance-record-table" role="table">
              <div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: "minmax(210px,1.4fr) 85px 90px 80px 80px 130px" }}><span>Dataset / version</span><span>Store</span><span>Status</span><span>Records</span><span>Attempts</span><span>Updated</span></div>
              {overview.projections.map((item) => <button type="button" role="row" key={item.id} className={`fd-resource-table__row ${selectedProjectionId === item.id ? "active" : ""}`} style={{ gridTemplateColumns: "minmax(210px,1.4fr) 85px 90px 80px 80px 130px" }} onClick={() => { setSelectedProjectionId(item.id); if (isMobile) setRecordInspectorOpen(true); }}><div className="fd-resource-table__primary"><strong>{item.dataset_name}</strong><small>{item.version_label} · {item.dataset_version_id}</small></div><span>{item.store_kind}</span><span><StatusPill intent={pillIntent(item.status)}>{item.status}</StatusPill></span><span className="fd-resource-table__numeric">{item.record_count.toLocaleString()}</span><span className="fd-resource-table__numeric">{item.attempt_count}</span><span>{formatDate(item.updated_at)}</span></button>)}
            </div>
          </section>
          {!isMobile ? <GovernanceRecordInspector projection={selectedProjection} retrying={retryingId === selectedProjection?.id} onRetryProjection={(projection) => void retryProjection(projection)} /> : null}
        </section>
      ) : null}

      {overview && activeTab === "lineage" ? (
        <section className="governance-lineage-grid" aria-label="Dataset lineage">
          {overview.lineage.map((item) => <Card key={item.dataset_id} elevation={0}><header><div><small>DATASET LINEAGE</small><h2>{item.dataset_name}</h2></div><Tag minimal>{item.version_count} versions</Tag></header><dl><div><dt>Dataset</dt><dd>{item.dataset_id}</dd></div><div><dt>Latest version</dt><dd>{item.latest_version_id ?? "—"}</dd></div><div><dt>Source version</dt><dd>{item.latest_source_version ?? "—"}</dd></div><div><dt>Materializations</dt><dd>{item.materialization_count}</dd></div></dl><div className="governance-reference-list"><small>DOWNSTREAM / SOURCE REFERENCES</small>{item.downstream_references.map((reference) => <code key={reference}>{reference}</code>)}{!item.downstream_references.length ? <span>No materialized downstream reference</span> : null}</div></Card>)}
          {!overview.lineage.length ? <p className="governance-empty">등록된 Dataset lineage가 없습니다.</p> : null}
        </section>
      ) : null}

      {overview && activeTab === "approvals" ? (
        <section className="governance-record-layout" aria-label="Project approvals">
          <section className="governance-table-panel">
            <div className="governance-panel-heading"><div><small>APPROVAL RECORDS</small><strong>Template publish and model release checkpoints</strong></div><StatusPill intent={overview.counts.pending_approvals ? "warning" : "success"}>{overview.counts.pending_approvals} pending</StatusPill></div>
            <div className="fd-resource-table governance-record-table" role="table">
              <div className="fd-resource-table__header" role="row" style={{ gridTemplateColumns: "minmax(150px,1fr) 130px 100px 130px minmax(150px,1fr)" }}><span>Workflow</span><span>Target</span><span>Status</span><span>Requested</span><span>Requester / decision</span></div>
              {overview.approvals.map((item) => <button type="button" role="row" key={item.id} className={`fd-resource-table__row ${selectedApprovalId === item.id ? "active" : ""}`} style={{ gridTemplateColumns: "minmax(150px,1fr) 130px 100px 130px minmax(150px,1fr)" }} onClick={() => { setSelectedApprovalId(item.id); if (isMobile) setRecordInspectorOpen(true); }}><div className="fd-resource-table__primary"><strong>{item.workflow_type}</strong><small>{item.id}</small></div><span>{item.target_role ?? "Model release"}</span><span><StatusPill intent={pillIntent(item.status)}>{item.status}</StatusPill></span><span>{formatDate(item.created_at)}</span><div className="fd-resource-table__primary"><strong>{item.requested_by_name}</strong><small>{item.decision_by_name ?? "Pending decision"}</small></div></button>)}
              {!overview.approvals.length ? <p className="governance-empty">현재 Project에 기록된 승인 요청이 없습니다.</p> : null}
            </div>
          </section>
          {!isMobile ? <GovernanceRecordInspector approval={selectedApproval} /> : null}
        </section>
      ) : null}

      {overview && activeTab === "policies" ? (
        <section className="governance-policy-layout" aria-label="Access and policy">
          <Card elevation={0}><small>ACTIVE SCOPE</small><h2>{overview.access.project_id}</h2><dl><div><dt>Organization</dt><dd>{overview.access.organization_id}</dd></div><div><dt>Workspace</dt><dd>{overview.access.workspace_id}</dd></div><div><dt>Roles</dt><dd>{overview.access.roles.join(", ")}</dd></div><div><dt>Projection retry</dt><dd>{overview.access.can_retry_projection ? "Allowed" : "Read only"}</dd></div></dl></Card>
          <Card elevation={0}><small>POLICY BOUNDARIES</small><h2>Governed operations</h2><ol>{overview.policy_boundaries.map((policy) => <li key={policy}>{policy}</li>)}</ol></Card>
          <Card elevation={0} className="governance-permissions-card"><small>EFFECTIVE PERMISSIONS</small><h2>{overview.access.permissions.length} permissions</h2><div className="governance-permission-groups">{permissionGroups.map(([group, permissions]) => <details key={group}><summary><strong>{group}</strong><span>{permissions.length}</span></summary><div>{permissions.map((permission) => <Tag key={permission} minimal>{permission}</Tag>)}</div></details>)}</div></Card>
        </section>
      ) : null}
      {isMobile && recordInspectorOpen && activeTab === "projections" ? <FoundryDrawer ariaLabel="Projection inspector" title="Projection inspector" position="bottom" onClose={() => setRecordInspectorOpen(false)}><GovernanceRecordInspector projection={selectedProjection} retrying={retryingId === selectedProjection?.id} onRetryProjection={(projection) => void retryProjection(projection)} /></FoundryDrawer> : null}
      {isMobile && recordInspectorOpen && activeTab === "approvals" ? <FoundryDrawer ariaLabel="Approval inspector" title="Approval inspector" position="bottom" onClose={() => setRecordInspectorOpen(false)}><GovernanceRecordInspector approval={selectedApproval} /></FoundryDrawer> : null}
    </main>
  );
}
