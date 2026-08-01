import { useMemo, useState, type FormEvent } from "react";
import { StatusBadge } from "../../components";
import type {
  AuditReconstruction,
  ExecutiveOverview,
  FDEWorkbench,
  FieldTask,
  FieldTaskWorkspace,
  ModelConsole,
  RoleWorkspaceData,
} from "./types";

interface RoleBoardRendererProps {
  renderer: string;
  data: RoleWorkspaceData | null;
  selectedEventId: string;
  onSelectEvent: (eventId: string) => void;
  onAuditCheckpoint: (format: "json" | "csv" | "pdf", reason: string) => Promise<void>;
  onFieldAction: (
    action: "complete" | "issue_found" | "blocked",
    input: {
      checklist: string[];
      measurements: Record<string, number | string>;
      photo_metadata: Array<Record<string, unknown>>;
      note: string;
      location: string;
      safety_risk: boolean;
    },
  ) => Promise<void>;
  onModelRelease: (input: {
    model_version: string;
    dataset_version: string;
    policy_version: string;
    metrics: Record<string, string | number>;
    threshold_evaluation: Record<string, string | number>;
    notes: string;
  }) => Promise<void>;
}

function isExecutive(data: RoleWorkspaceData | null): data is ExecutiveOverview {
  return Boolean(data && "aggregate" in data && "risk_trend" in data);
}

function isAudit(data: RoleWorkspaceData | null): data is AuditReconstruction {
  return Boolean(data && "version_snapshot" in data && "action_history" in data);
}

function isField(data: RoleWorkspaceData | null): data is FieldTaskWorkspace {
  return Boolean(data && "tasks" in data && "offline_queue_design" in data);
}

function isFDE(data: RoleWorkspaceData | null): data is FDEWorkbench {
  return Boolean(data && "customer_workspace" in data && "deployment_checklist" in data);
}

function isModel(data: RoleWorkspaceData | null): data is ModelConsole {
  return Boolean(data && "model_versions" in data && "gold_regression" in data);
}

function DataUnavailable({ label }: { label: string }) {
  return <section className="card role-data-card"><p>{label} 데이터를 불러오고 있습니다.</p></section>;
}

function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  return (
    <div className="role-kv-grid">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{value === null ? "산출 안 함" : typeof value === "object" ? JSON.stringify(value) : String(value)}</strong></div>
      ))}
    </div>
  );
}

function ExecutiveBoard({ renderer, data, onSelectEvent }: { renderer: string; data: ExecutiveOverview; onSelectEvent: (eventId: string) => void }) {
  switch (renderer) {
    case "ExecutivePortfolio":
      return (
        <section className="card role-data-card executive-card">
          <div className="executive-metric-grid">
            <article><span>대상 설비</span><strong>{data.aggregate.equipment_count}</strong></article>
            <article><span>영향 사건</span><strong>{data.aggregate.affected_event_count}</strong></article>
            <article><span>미조치 중요 사건</span><strong>{data.aggregate.unresolved_critical_count}</strong></article>
            <article><span>추정 정지 영향</span><strong>{data.aggregate.estimated_downtime_minutes}분</strong></article>
          </div>
          <div className="status-distribution">
            {data.status_distribution.map((item) => <div key={item.status}><StatusBadge status={item.status} /><strong>{item.count}</strong></div>)}
          </div>
        </section>
      );
    case "ExecutiveRiskTrend": {
      const maxRisk = Math.max(...data.risk_trend.map((item) => item.risk_score ?? 0), 1);
      return (
        <section className="card role-data-card">
          <div className="executive-trend-list">
            {data.risk_trend.map((item) => (
              <button key={item.event_id} type="button" onClick={() => onSelectEvent(item.event_id)}>
                <span><strong>{item.equipment}</strong><small>{item.event_id}</small></span>
                <div className="executive-trend-track"><i style={{ width: `${((item.risk_score ?? 0) / maxRisk) * 100}%` }} /></div>
                <b>{item.risk_score === null ? "—" : `${(item.risk_score * 100).toFixed(1)}%`}</b>
              </button>
            ))}
          </div>
        </section>
      );
    }
    case "ExecutiveUnresolved":
      return (
        <section className="card role-data-card">
          <div className="executive-unresolved-list">
            {data.unresolved_critical_events.map((item) => (
              <button key={item.event_id} type="button" onClick={() => onSelectEvent(item.event_id)}>
                <span><strong>{item.equipment.display_name}</strong><small>{item.equipment.line} · {item.event_id}</small></span>
                <StatusBadge status={item.status} />
                <b>{item.failure_probability === null ? "—" : `${(item.failure_probability * 100).toFixed(1)}%`}</b>
                <small>{item.equipment.estimated_downtime_minutes}분 추정</small>
              </button>
            ))}
          </div>
          {!data.unresolved_critical_events.length ? <p>미조치 중요 사건이 없습니다.</p> : null}
        </section>
      );
    default:
      return (
        <section className="card role-data-card">
          <KeyValueGrid data={data.business_impact} />
          <div className="assumption-panel"><strong>추정 가정</strong><ul>{data.assumptions.map((item) => <li key={item}>{item}</li>)}</ul></div>
        </section>
      );
  }
}

function AuditExportForm({ data, onSubmit }: { data: AuditReconstruction; onSubmit: RoleBoardRendererProps["onAuditCheckpoint"] }) {
  const [format, setFormat] = useState<"json" | "csv" | "pdf">("json");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    setSaving(true);
    try {
      await onSubmit(format, reason.trim());
      setReason("");
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="card role-data-card">
      <form className="role-action-form" onSubmit={submit}>
        <label>Checkpoint 형식<select value={format} onChange={(event) => setFormat(event.target.value as typeof format)}><option value="json">JSON</option><option value="csv">CSV</option><option value="pdf">PDF</option></select></label>
        <label>감사 목적<textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="예: 분기 품질 검토 증적" /></label>
        <button type="submit" className="primary" disabled={saving || !reason.trim()}>{saving ? "기록 중" : "Export checkpoint 기록"}</button>
      </form>
      <div className="checkpoint-list">
        {data.export_checkpoints.map((item) => <article key={item.id}><div><strong>{item.export_format.toUpperCase()} · {item.reason}</strong><small>{item.requested_by_name} · {new Date(item.created_at).toLocaleString()}</small></div><code>{item.content_hash}</code></article>)}
      </div>
    </section>
  );
}

function AuditBoard({ renderer, data, onAuditCheckpoint }: { renderer: string; data: AuditReconstruction; onAuditCheckpoint: RoleBoardRendererProps["onAuditCheckpoint"] }) {
  switch (renderer) {
    case "AuditReconstruction":
      return (
        <section className="card role-data-card">
          <div className="reconstruction-flow">
            <article><span>1. Input</span><strong>{String(data.input_snapshot.scenario_id)}</strong><small>schema {String(data.input_snapshot.schema_version)}</small></article>
            <article><span>2. Evidence</span><strong>{String(data.version_snapshot.evidence_id)}</strong><small>{String(data.version_snapshot.model_version)}</small></article>
            <article><span>3. Report</span><strong>{String(data.version_snapshot.report_id)}</strong><small>{String(data.version_snapshot.report_mode)}</small></article>
            <article><span>4. Action</span><strong>{data.action_history.length} records</strong><small>human·ontology·field</small></article>
          </div>
          <details><summary>원본 입력 snapshot</summary><pre>{JSON.stringify(data.input_snapshot, null, 2)}</pre></details>
        </section>
      );
    case "AuditVersionSnapshot":
      return <section className="card role-data-card"><KeyValueGrid data={data.version_snapshot} /></section>;
    case "AuditEvidenceTrace":
      return (
        <section className="card role-data-card"><div className="trace-table">{data.evidence_to_report_trace.map((item) => <article key={item.section_id}><div><strong>{item.title}</strong><small>{item.section_id}</small></div><code>{item.evidence_field_ids.join(" → ")}</code></article>)}</div></section>
      );
    case "AuditActionHistory":
      return (
        <section className="card role-data-card"><div className="role-timeline">{data.action_history.map((item, index) => <article key={String(item.id ?? index)}><span>{String(item.type)}</span><strong>{String(item.action ?? item.decision ?? item.body ?? "record")}</strong><small>{String(item.actor ?? "system")} · {item.created_at ? new Date(String(item.created_at)).toLocaleString() : ""}</small>{item.audit_id ? <code>{String(item.audit_id)}</code> : null}</article>)}</div>{!data.action_history.length ? <p>아직 Action 기록이 없습니다.</p> : null}</section>
      );
    default:
      return <AuditExportForm data={data} onSubmit={onAuditCheckpoint} />;
  }
}

function selectedTask(data: FieldTaskWorkspace, selectedEventId: string): FieldTask | null {
  return data.tasks.find((task) => task.event_id === selectedEventId) ?? data.tasks[0] ?? null;
}

function FieldActionForm({ task, onSubmit }: { task: FieldTask; onSubmit: RoleBoardRendererProps["onFieldAction"] }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [measurements, setMeasurements] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [photoName, setPhotoName] = useState("");
  const [photoCaption, setPhotoCaption] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(action: "complete" | "issue_found" | "blocked") {
    setSaving(true);
    try {
      const normalizedMeasurements = Object.fromEntries(Object.entries(measurements).filter(([, value]) => value !== "").map(([key, value]) => [key, Number.isNaN(Number(value)) ? value : Number(value)]));
      const photoMetadata = photoName.trim() ? [{ filename: photoName.trim(), caption: photoCaption.trim(), captured_at: new Date().toISOString(), mime_type: "image/jpeg" }] : [];
      await onSubmit(action, {
        checklist: task.checklist.filter((item) => checked[item]),
        measurements: normalizedMeasurements,
        photo_metadata: photoMetadata,
        note,
        location: task.location,
        safety_risk: action === "blocked",
      });
      setNote("");
      setPhotoName("");
      setPhotoCaption("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card role-data-card field-action-card">
      <div className="mobile-checklist">{task.checklist.map((item) => <label key={item}><input type="checkbox" checked={Boolean(checked[item])} onChange={(event) => setChecked({ ...checked, [item]: event.target.checked })} /><span>{item}</span></label>)}</div>
      <div className="measurement-input-grid">{Object.keys(task.measurement_schema).map((field) => <label key={field}>{field}<input inputMode="decimal" value={measurements[field] ?? ""} onChange={(event) => setMeasurements({ ...measurements, [field]: event.target.value })} /></label>)}</div>
      <div className="photo-metadata-input"><label>사진 파일명<input value={photoName} onChange={(event) => setPhotoName(event.target.value)} placeholder="binary 업로드 없이 metadata만 기록" /></label><label>사진 설명<input value={photoCaption} onChange={(event) => setPhotoCaption(event.target.value)} /></label></div>
      <label className="field-label">현장 메모<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="완료 handoff 또는 문제·작업 불가 사유" /></label>
      <div className="field-action-buttons"><button type="button" className="primary" disabled={saving || !Object.values(checked).some(Boolean)} onClick={() => void submit("complete")}>작업 완료</button><button type="button" className="secondary issue-button" disabled={saving || !note.trim()} onClick={() => void submit("issue_found")}>문제 발견</button><button type="button" className="secondary blocked-button" disabled={saving || !note.trim()} onClick={() => void submit("blocked")}>작업 불가</button></div>
    </section>
  );
}

function FieldBoard({ renderer, data, selectedEventId, onSelectEvent, onFieldAction }: { renderer: string; data: FieldTaskWorkspace; selectedEventId: string; onSelectEvent: (eventId: string) => void; onFieldAction: RoleBoardRendererProps["onFieldAction"] }) {
  const task = selectedTask(data, selectedEventId);
  if (!task) return <section className="card role-data-card"><p>배정된 현장 작업이 없습니다.</p></section>;
  switch (renderer) {
    case "FieldTask":
      return (
        <section className="card role-data-card mobile-task-card">
          <div className="mobile-task-hero"><div><span>{task.task_id}</span><h3>{task.equipment.display_name}</h3><p>{task.location} · 담당 {task.equipment.assigned_engineer}</p></div><div><StatusBadge status={task.risk_status} /><strong>{task.task_status}</strong></div></div>
          <div className="mobile-task-switcher">{data.tasks.map((item) => <button key={item.task_id} className={item.event_id === task.event_id ? "active" : ""} onClick={() => onSelectEvent(item.event_id)}><strong>{item.equipment.display_name}</strong><small>{item.risk_status} · {item.task_status}</small></button>)}</div>
        </section>
      );
    case "FieldSafetyLocation":
      return <section className="card role-data-card"><div className="location-chip">위치 · {task.location}</div><ul className="safety-list">{task.safety.map((item) => <li key={item}>{item}</li>)}</ul><small>안전 위험이 있으면 작업을 진행하지 말고 작업 불가 Action을 기록합니다.</small></section>;
    case "FieldMeasurements":
      return <section className="card role-data-card"><div className="measurement-schema-list">{Object.entries(task.measurement_schema).map(([field, type]) => <div key={field}><code>{field}</code><span>{type}</span></div>)}</div><div className="photo-policy"><strong>Photo metadata policy</strong><pre>{JSON.stringify(task.photo_policy, null, 2)}</pre></div>{task.latest_action ? <details open><summary>최근 현장 기록</summary><pre>{JSON.stringify(task.latest_action, null, 2)}</pre></details> : null}</section>;
    default:
      return <FieldActionForm task={task} onSubmit={onFieldAction} />;
  }
}

function FDEBoard({ renderer, data }: { renderer: string; data: FDEWorkbench }) {
  switch (renderer) {
    case "FDEWorkspaceOverview":
      return <section className="card role-data-card"><KeyValueGrid data={data.customer_workspace} /><div className="security-boundary-list">{data.security_boundaries.map((item) => <p key={item}>{item}</p>)}</div></section>;
    case "FDEOntologyRegistry":
      return <section className="card role-data-card"><div className="registry-counts"><article><span>Object Types</span><strong>{data.ontology_registry.object_type_count}</strong></article><article><span>Link Types</span><strong>{data.ontology_registry.link_type_count}</strong></article><article><span>Action Types</span><strong>{data.ontology_registry.action_type_count}</strong></article></div><div className="registry-chip-list">{data.ontology_registry.object_types.map((item) => <span key={String(item.id)}>{String(item.id)}</span>)}</div></section>;
    case "FDEDeploymentChecklist":
      return <section className="card role-data-card"><div className="deployment-checklist">{data.deployment_checklist.map((item) => <article key={item.id}><span className={`deployment-status status-${item.status}`}>{item.status}</span><strong>{item.label}</strong></article>)}</div></section>;
    case "FDEDiagnosticEvents":
      return <section className="card role-data-card"><div className="diagnostic-list">{data.diagnostic_events.map((item, index) => <article key={String(item.event_id ?? index)}><strong>{String(item.event_id)}</strong><span>{Array.isArray(item.codes) ? item.codes.join(", ") : "diagnostic"}</span><small>safe fallback · {String(item.safe_fallback)}</small></article>)}</div>{!data.diagnostic_events.length ? <p>현재 unresolved diagnostic event가 없습니다.</p> : null}</section>;
    default:
      return <section className="card role-data-card"><div className="approval-list">{data.template_requests.map((item) => <article key={item.id}><div><strong>{String(item.target_role)} · {String(item.payload.display_name ?? "Template")}</strong><small>{item.requested_by_name} · {new Date(item.created_at).toLocaleString()}</small></div><span className={`approval-status status-${item.status}`}>{item.status}</span></article>)}</div>{!data.template_requests.length ? <p>제출한 template 승인 요청이 없습니다.</p> : null}</section>;
  }
}

function ModelReleaseForm({ data, onSubmit }: { data: ModelConsole; onSubmit: RoleBoardRendererProps["onModelRelease"] }) {
  const defaultModel = String(data.model_versions[0]?.model_version ?? "fixture-heuristic-v2-rc1");
  const defaultDataset = String(data.dataset_versions[0]?.dataset_version ?? "fixture-schema-1.0");
  const policies = data.operational_thresholds.policy_versions as Array<Record<string, unknown>> | undefined;
  const defaultPolicy = String(policies?.[0]?.policy_version ?? "operational-policy-v2-rc1");
  const [modelVersion, setModelVersion] = useState(defaultModel);
  const [datasetVersion, setDatasetVersion] = useState(defaultDataset);
  const [policyVersion, setPolicyVersion] = useState(defaultPolicy);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await onSubmit({
        model_version: modelVersion,
        dataset_version: datasetVersion,
        policy_version: policyVersion,
        metrics: { gold_pass_rate: data.gold_regression.passed / data.gold_regression.scenario_count, scenario_count: data.gold_regression.scenario_count },
        threshold_evaluation: { candidate_threshold: 0.55, relative_cost: Number(data.threshold_cost.find((item) => item.threshold === 0.55)?.relative_cost ?? 0) },
        notes,
      });
      setNotes("");
    } finally {
      setSaving(false);
    }
  }
  return (
    <section className="card role-data-card"><form className="release-candidate-form" onSubmit={submit}><label>Model version<input value={modelVersion} onChange={(event) => setModelVersion(event.target.value)} /></label><label>Dataset version<input value={datasetVersion} onChange={(event) => setDatasetVersion(event.target.value)} /></label><label>Policy version<input value={policyVersion} onChange={(event) => setPolicyVersion(event.target.value)} /></label><label className="release-notes">승인 요청 근거<textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></label><button type="submit" className="primary" disabled={saving || !notes.trim()}>{saving ? "요청 중" : "Release 승인 요청"}</button></form><div className="approval-list">{data.release_requests.map((item) => <article key={item.id}><div><strong>{String(item.payload.model_version)}</strong><small>{String(item.payload.dataset_version)} · {String(item.payload.policy_version)}</small></div><span className={`approval-status status-${item.status}`}>{item.status}</span></article>)}</div></section>
  );
}

function ModelBoard({ renderer, data, onModelRelease }: { renderer: string; data: ModelConsole; onModelRelease: RoleBoardRendererProps["onModelRelease"] }) {
  switch (renderer) {
    case "MLVersionMatrix":
      return <section className="card role-data-card"><div className="scope-separation"><article><span>Training metrics</span><strong>{String(data.training_metrics.available) === "true" ? "available" : "not connected"}</strong><small>{String(data.training_metrics.reason ?? "")}</small></article><article><span>Operational thresholds</span><strong>{String((data.operational_thresholds.threshold_values as unknown[])?.join(", ") ?? "-")}</strong><small>{String(data.operational_thresholds.note)}</small></article></div><div className="version-matrix"><pre>{JSON.stringify({ models: data.model_versions, datasets: data.dataset_versions, policies: data.operational_thresholds.policy_versions }, null, 2)}</pre></div></section>;
    case "MLThresholdCost":
      return <section className="card role-data-card"><div className="threshold-cost-grid">{data.threshold_cost.map((item) => <article key={String(item.threshold)}><span>Threshold {String(item.threshold)}</span><strong>비용 {String(item.relative_cost)}</strong><small>개입 {String(item.intervention_count)} · 예상 위험 누락 {String(item.missed_expected_warning_or_critical)}</small></article>)}</div></section>;
    case "MLSliceError":
      return <section className="card role-data-card"><div className="slice-grid">{data.slices.map((item, index) => <article key={index}><strong>{String(item.status)} · {String(item.criticality)}</strong><span>{String(item.count)} cases</span></article>)}</div><details><summary>Gold error items</summary><pre>{JSON.stringify(data.gold_regression.items.filter((item) => item.pass === false), null, 2)}</pre></details></section>;
    case "MLDriftSchema":
      return <section className="card role-data-card"><div className="diagnostic-list">{data.drift_and_schema.map((item, index) => <article key={index}><strong>{String(item.kind)}</strong><pre>{JSON.stringify(item, null, 2)}</pre></article>)}</div></section>;
    case "MLGoldRegression":
      return <section className="card role-data-card"><div className={`gold-regression-hero ${data.gold_regression.pass ? "pass" : "fail"}`}><strong>{data.gold_regression.passed}/{data.gold_regression.scenario_count} PASS</strong><span>{data.gold_regression.failed} failed</span></div><div className="gold-item-grid">{data.gold_regression.items.map((item) => <article key={String(item.event_id)}><strong>{String(item.scenario_id)}</strong><span>{String(item.actual_status)}</span><b>{item.pass ? "PASS" : "FAIL"}</b></article>)}</div></section>;
    default:
      return <ModelReleaseForm data={data} onSubmit={onModelRelease} />;
  }
}

const ROLE_RENDERERS = new Set([
  "ExecutivePortfolio", "ExecutiveRiskTrend", "ExecutiveUnresolved", "ExecutiveBusinessImpact",
  "AuditReconstruction", "AuditVersionSnapshot", "AuditEvidenceTrace", "AuditActionHistory", "AuditExportCheckpoint",
  "FieldTask", "FieldSafetyLocation", "FieldMeasurements", "FieldTaskActions",
  "FDEWorkspaceOverview", "FDEOntologyRegistry", "FDEDeploymentChecklist", "FDEDiagnosticEvents", "FDEApprovalQueue",
  "MLVersionMatrix", "MLThresholdCost", "MLSliceError", "MLDriftSchema", "MLGoldRegression", "MLReleaseCandidate",
]);

export function isRoleBoardRenderer(renderer: string): boolean {
  return ROLE_RENDERERS.has(renderer);
}

export function RoleBoardRenderer(props: RoleBoardRendererProps) {
  const { renderer, data } = props;
  const label = useMemo(() => renderer.replace(/([A-Z])/g, " $1").trim(), [renderer]);
  if (renderer.startsWith("Executive")) return isExecutive(data) ? <ExecutiveBoard renderer={renderer} data={data} onSelectEvent={props.onSelectEvent} /> : <DataUnavailable label={label} />;
  if (renderer.startsWith("Audit")) return isAudit(data) ? <AuditBoard renderer={renderer} data={data} onAuditCheckpoint={props.onAuditCheckpoint} /> : <DataUnavailable label={label} />;
  if (renderer.startsWith("Field")) return isField(data) ? <FieldBoard renderer={renderer} data={data} selectedEventId={props.selectedEventId} onSelectEvent={props.onSelectEvent} onFieldAction={props.onFieldAction} /> : <DataUnavailable label={label} />;
  if (renderer.startsWith("FDE")) return isFDE(data) ? <FDEBoard renderer={renderer} data={data} /> : <DataUnavailable label={label} />;
  if (renderer.startsWith("ML")) return isModel(data) ? <ModelBoard renderer={renderer} data={data} onModelRelease={props.onModelRelease} /> : <DataUnavailable label={label} />;
  return <DataUnavailable label={label} />;
}
