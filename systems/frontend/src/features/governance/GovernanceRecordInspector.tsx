import { BadgeCheck, Database, ShieldCheck } from "lucide-react";
import { PropertyTable } from "../../ui/foundry/PropertyTable";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import type { GovernanceApproval, GovernanceProjection } from "./types";

interface GovernanceRecordInspectorProps {
  projection?: GovernanceProjection | null;
  approval?: GovernanceApproval | null;
  retrying?: boolean;
  onRetryProjection?: (projection: GovernanceProjection) => void;
}

function intent(status: string) {
  if (["ready", "approved", "active", "succeeded"].includes(status)) return "success" as const;
  if (["failed", "rejected", "unavailable"].includes(status)) return "danger" as const;
  if (["pending", "indexing", "pending_approval", "running"].includes(status)) return "warning" as const;
  return "neutral" as const;
}

export function GovernanceRecordInspector({ projection, approval, retrying = false, onRetryProjection }: GovernanceRecordInspectorProps) {
  if (!projection && !approval) return <aside className="governance-record-inspector"><EmptyState title="Select a record" detail="Governed status, scope, lineage, and retry or decision context will appear here." /></aside>;

  if (projection) {
    return (
      <aside className="governance-record-inspector">
        <header><div><span className="section-label">PROJECTION RECORD</span><strong>{projection.dataset_name}</strong><small>{projection.id}</small></div><StatusPill intent={intent(projection.status)}>{projection.status}</StatusPill></header>
        <div className="governance-record-inspector__body">
          <div className="governance-record-icon"><Database size={20} /><span><strong>{projection.version_label}</strong><small>{projection.store_kind} projection</small></span></div>
          <PropertyTable rows={[
            { id: "version", label: "Dataset Version", value: projection.dataset_version_id, type: "version", mono: true },
            { id: "store", label: "Store", value: projection.store_kind, type: "projection" },
            { id: "records", label: "Records", value: projection.record_count, type: "integer", numeric: true },
            { id: "attempts", label: "Attempts", value: projection.attempt_count, type: "integer", numeric: true },
            { id: "source", label: "Source version", value: projection.source_version, type: "version", mono: true },
            { id: "namespace", label: "Namespace", value: projection.object_namespace, type: "namespace", mono: true },
            { id: "updated", label: "Updated", value: new Date(projection.updated_at).toLocaleString(), type: "datetime" },
          ]} />
          {projection.last_error ? <p className="governance-record-error">{projection.last_error}</p> : null}
          <button type="button" className="fd-toolbar-button" disabled={!projection.can_retry || retrying} onClick={() => onRetryProjection?.(projection)}>{retrying ? "Retrying" : "Retry projection"}</button>
        </div>
      </aside>
    );
  }

  const selectedApproval = approval!;
  return (
    <aside className="governance-record-inspector">
      <header><div><span className="section-label">APPROVAL RECORD</span><strong>{selectedApproval.workflow_type}</strong><small>{selectedApproval.id}</small></div><StatusPill intent={intent(selectedApproval.status)}>{selectedApproval.status}</StatusPill></header>
      <div className="governance-record-inspector__body">
        <div className="governance-record-icon"><BadgeCheck size={20} /><span><strong>{selectedApproval.target_role ?? "Model release"}</strong><small>{selectedApproval.requested_by_name}</small></span></div>
        <PropertyTable rows={[
          { id: "workspace", label: "Workspace", value: selectedApproval.workspace_id, type: "scope", mono: true },
          { id: "requester", label: "Requested by", value: selectedApproval.requested_by_name, type: "principal" },
          { id: "created", label: "Created", value: new Date(selectedApproval.created_at).toLocaleString(), type: "datetime" },
          { id: "decision", label: "Decision by", value: selectedApproval.decision_by_name ?? "Pending", type: "principal" },
          { id: "note", label: "Decision note", value: selectedApproval.decision_note ?? "—", type: "text" },
        ]} />
        <section className="governance-approval-payload"><span className="section-label"><ShieldCheck size={11} /> APPROVAL PAYLOAD</span><pre>{JSON.stringify(selectedApproval.payload, null, 2)}</pre></section>
      </div>
    </aside>
  );
}
