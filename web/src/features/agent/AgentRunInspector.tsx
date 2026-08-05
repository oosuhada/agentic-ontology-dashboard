import { CheckSquare, FileSearch, GitBranch, ListChecks } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ActivityTimeline } from "../../ui/foundry/ActivityTimeline";
import { InspectorTabs } from "../../ui/foundry/InspectorTabs";
import { PropertyTable } from "../../ui/foundry/PropertyTable";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { EvidenceTraceList } from "./EvidenceTraceList";
import { GroundedClaimList } from "./GroundedClaimList";
import { OrchestrationStepper } from "./OrchestrationStepper";
import { agentOutcomeIntent, agentOutcomeLabel, deriveAgentOutcome } from "./agentOutcome";
import type { AgentRunResponse } from "./types";
import { useI18n } from "../../ui/i18n/I18nProvider";

type AgentInspectorTab = "evidence" | "claims" | "orchestration" | "trace";

interface AgentRunInspectorProps {
  run: AgentRunResponse | null;
  selectedEvidenceId: string | null;
  onSelectEvidence: (evidenceId: string) => void;
}

export function AgentRunInspector({ run, selectedEvidenceId, onSelectEvidence }: AgentRunInspectorProps) {
  const { locale } = useI18n();
  const [activeTab, setActiveTab] = useState<AgentInspectorTab>("evidence");
  const outcome = run ? deriveAgentOutcome({
    status: run.state.status,
    evidenceCount: run.state.evidence.length,
    claimCount: run.state.claims.length,
    failedStepCount: run.traces.filter((trace) => trace.status === "failed").length,
    caveats: run.state.caveats,
  }) : null;
  const tabs = useMemo(() => {
    const next = [] as Array<{ id: AgentInspectorTab; label: string; count: number; icon: ReactNode }>;
    if ((run?.state.evidence.length ?? 0) > 0) next.push({ id: "evidence", label: "EVIDENCE", count: run?.state.evidence.length ?? 0, icon: <FileSearch size={11} /> });
    if ((run?.state.claims.length ?? 0) > 0) next.push({ id: "claims", label: "CLAIMS", count: run?.state.claims.length ?? 0, icon: <CheckSquare size={11} /> });
    next.push({ id: "orchestration", label: "CHECKPOINTS", count: run?.state.steps.length ?? 0, icon: <GitBranch size={11} /> });
    next.push({ id: "trace", label: "TRACE", count: run?.traces.length ?? 0, icon: <ListChecks size={11} /> });
    return next;
  }, [run]);
  useEffect(() => {
    if (!tabs.some((tab) => tab.id === activeTab)) setActiveTab(tabs[0]?.id ?? "orchestration");
  }, [activeTab, tabs]);
  return (
    <aside className="agent-lineage-pane">
      <div className="agent-pane-heading"><div><small>ORCHESTRATION LINEAGE</small><strong>{run?.state.run_id ?? "No active run"}</strong></div>{outcome ? <StatusPill intent={agentOutcomeIntent(outcome)}>{agentOutcomeLabel(outcome, locale)}</StatusPill> : null}</div>
      <InspectorTabs
        activeTab={activeTab}
        onChange={setActiveTab}
        label="Agent run inspector"
        tabs={tabs}
      />
      <div className="agent-lineage-scroll">
        {!run ? <EmptyState title="No run selected" detail="Run a governed query or open a persisted run to inspect evidence and orchestration." /> : null}
        {run && activeTab === "evidence" ? <EvidenceTraceList items={run.state.evidence} selectedEvidenceId={selectedEvidenceId} onSelectEvidence={onSelectEvidence} /> : null}
        {run && activeTab === "claims" ? <GroundedClaimList claims={run.state.claims} onSelectEvidence={onSelectEvidence} /> : null}
        {run && activeTab === "orchestration" ? <><PropertyTable rows={[
          { id: "route", label: "Route", value: run.state.route, type: "classifier" },
          { id: "checkpoint", label: "Checkpoint sequence", value: run.state.checkpoint_sequence, type: "integer", numeric: true },
          { id: "object", label: "Object context", value: run.state.object_id ?? "unconstrained", type: run.state.object_type ?? "scope", mono: true },
          { id: "evidence", label: "Evidence merged", value: run.state.evidence.length, type: "integer", numeric: true },
        ]} /><OrchestrationStepper run={run} /></> : null}
        {run && activeTab === "trace" ? <ActivityTimeline items={run.traces.map((trace) => ({
          id: trace.id,
          title: trace.step_name,
          detail: `${trace.store_kind ?? "orchestrator"} · ${trace.latency_ms ?? 0} ms`,
          meta: new Date(trace.created_at).toLocaleString(),
          status: { label: trace.status, intent: trace.status === "succeeded" ? "success" : trace.status === "failed" ? "danger" : "warning" },
          expandable: trace.input || trace.output ? <details><summary>Execution metadata</summary><pre>{JSON.stringify({ input: trace.input, output: trace.output }, null, 2)}</pre></details> : undefined,
        }))} emptyMessage="No persisted trace records." /> : null}
      </div>
    </aside>
  );
}
