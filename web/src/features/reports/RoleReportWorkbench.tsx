import { AlertTriangle, BarChart3, Check, FilePenLine, LayoutDashboard, RefreshCw, Save, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getReportDraft, saveReportDraft } from "../../api";
import type { Evidence, EventSummary, Report } from "../../types";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchState } from "../../ui/foundry/WorkbenchState";
import type { ReportDraftRecord, ReportDraftSection } from "../dashboard/types";
import type { AdaptiveExperienceProfile } from "../manufacturing/adaptiveExperience";

interface RoleReportWorkbenchProps {
  workspaceId: string;
  roleLabel: string;
  projectName: string;
  profile: AdaptiveExperienceProfile;
  report: Report | null;
  evidence: Evidence | null;
  events: EventSummary[];
  selectedEventId: string;
  canEdit: boolean;
  onSelectEvent: (eventId: string) => void;
  onOpenDashboard: () => void;
}

function generatedSections(report: Report): ReportDraftSection[] {
  return report.sections.map((section) => ({
    section_id: section.section_id,
    title: section.title,
    body: section.body,
    evidence_field_ids: section.evidence_field_ids,
  }));
}

function metricValues(evidence: Evidence | null, profile: AdaptiveExperienceProfile) {
  if (!evidence?.history.length) return [];
  const keys = profile.id === "compressor-monitoring"
    ? ["rotational_speed_rpm", "process_temperature_k", "torque_nm"]
    : ["tool_wear_min", "torque_nm", "rotational_speed_rpm", "process_temperature_k"];
  const key = keys.find((candidate) => evidence.history.some((point) => typeof point[candidate as keyof typeof point] === "number"));
  if (!key) return [];
  return evidence.history.map((point) => Number(point[key as keyof typeof point] ?? 0));
}

function TrendVisual({ values }: { values: number[] }) {
  if (values.length < 2) return <WorkbenchState kind="empty" compact title="No time-series evidence" detail="The selected report has no numeric history to visualize." />;
  const width = 640;
  const height = 180;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((value, index) => {
    const x = 18 + (index / Math.max(1, values.length - 1)) * (width - 36);
    const y = height - 22 - ((value - min) / Math.max(1, max - min)) * (height - 46);
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg className="role-report-trend" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Report evidence trend">
      {[0, 1, 2, 3].map((line) => <line key={line} x1="18" x2={width - 18} y1={24 + line * 40} y2={24 + line * 40} />)}
      <polyline points={points} />
      <circle cx={points.split(" ").at(-1)?.split(",")[0]} cy={points.split(" ").at(-1)?.split(",")[1]} r="5" />
    </svg>
  );
}

export function RoleReportWorkbench({
  workspaceId,
  roleLabel,
  projectName,
  profile,
  report,
  evidence,
  events,
  selectedEventId,
  canEdit,
  onSelectEvent,
  onOpenDashboard,
}: RoleReportWorkbenchProps) {
  const [savedDraft, setSavedDraft] = useState<ReportDraftRecord | null>(null);
  const [headline, setHeadline] = useState("");
  const [summary, setSummary] = useState("");
  const [sections, setSections] = useState<ReportDraftSection[]>([]);
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!report || !workspaceId || !selectedEventId) return;
    let cancelled = false;
    setLoading(true);
    setMessage("");
    getReportDraft(workspaceId, selectedEventId)
      .then((draft) => {
        if (cancelled) return;
        setSavedDraft(draft);
        setHeadline(draft?.headline ?? report.headline);
        setSummary(draft?.summary ?? report.summary);
        setSections(draft?.sections ?? generatedSections(report));
        setDirty(false);
        setEditing(false);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setSavedDraft(null);
        setHeadline(report.headline);
        setSummary(report.summary);
        setSections(generatedSections(report));
        setMessage(reason instanceof Error ? reason.message : "Report draft could not be loaded.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [report?.report_id, selectedEventId, workspaceId]);

  const trend = useMemo(() => metricValues(evidence, profile), [evidence, profile]);
  const criticalEvents = events.filter((event) => (event.failure_probability ?? 0) >= .7).length;
  const pendingEvents = events.filter((event) => !["closed", "resolved", "completed"].includes(event.status.toLowerCase())).length;

  function changeSection(index: number, patch: Partial<ReportDraftSection>) {
    setSections((current) => current.map((section, sectionIndex) => sectionIndex === index ? { ...section, ...patch } : section));
    setDirty(true);
  }

  async function saveDraft() {
    if (!report || !canEdit || saving) return;
    setSaving(true);
    setMessage("");
    try {
      const saved = await saveReportDraft({
        workspace_id: workspaceId,
        event_id: selectedEventId,
        base_revision: savedDraft?.revision ?? 0,
        headline: headline.trim(),
        summary: summary.trim(),
        sections,
      });
      setSavedDraft(saved);
      setDirty(false);
      setEditing(false);
      setMessage(`공용 보고서 revision ${saved.revision}을 저장했습니다.`);
    } catch (reason: unknown) {
      setMessage(reason instanceof Error ? reason.message : "보고서 저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  if (!report || !evidence) return <div className="role-report-loading"><WorkbenchState kind="loading" title="Preparing role briefing" detail="Linking narrative sections to governed evidence and visualizations." /></div>;

  return (
    <article className={`role-report-workbench profile-${profile.id} ${editing ? "is-editing" : ""}`}>
      <header className="role-report-cover">
        <div>
          <span>{profile.eyebrow}</span>
          <small>{projectName} · {roleLabel} · {profile.datasetSummary}</small>
          {editing ? <input className="role-report-headline-input" value={headline} onChange={(event) => { setHeadline(event.target.value); setDirty(true); }} /> : <h1>{headline}</h1>}
          {editing ? <textarea className="role-report-summary-input" value={summary} onChange={(event) => { setSummary(event.target.value); setDirty(true); }} /> : <p>{summary}</p>}
        </div>
        <div className="role-report-actions">
          <StatusPill intent={savedDraft ? "success" : "primary"}>{savedDraft ? `Shared revision ${savedDraft.revision}` : "Generated report"}</StatusPill>
          {canEdit ? editing
            ? <button type="button" className="primary" disabled={!dirty || saving} onClick={() => void saveDraft()}><Save size={13} /> {saving ? "Saving" : "Save report"}</button>
            : <button type="button" disabled={loading} onClick={() => setEditing(true)}><FilePenLine size={13} /> {loading ? "Resolving report" : "Edit report"}</button>
            : null}
          <button type="button" onClick={onOpenDashboard}><LayoutDashboard size={13} /> Open detailed dashboard</button>
        </div>
      </header>

      <section className="role-report-scopebar">
        <label>Report subject<select aria-label="Report subject" value={selectedEventId} onChange={(event) => onSelectEvent(event.target.value)}>{events.map((event) => <option key={event.event_id} value={event.event_id}>{event.equipment.display_name} · {event.predicted_failure_type}</option>)}</select></label>
        <div><span>Primary object<strong>{evidence.equipment.display_name}</strong></span><span>Risk<strong>{Math.round((evidence.failure_probability ?? 0) * 100)}%</strong></span><span>Open events<strong>{pendingEvents}</strong></span><span>High risk<strong>{criticalEvents}</strong></span></div>
      </section>

      {message ? <div className={`role-report-message ${message.includes("실패") || message.includes("could not") ? "is-error" : ""}`}><Check size={12} />{message}</div> : null}
      {loading ? <div className="role-report-refresh"><RefreshCw className="spin" size={14} /> Loading shared report revision</div> : null}

      <div className="role-report-grid">
        <main className="role-report-narrative">
          {sections.map((section, index) => (
            <section key={section.section_id}>
              <span>{String(index + 1).padStart(2, "0")} · {profile.reportSections[index] ?? "Evidence-based finding"}</span>
              {editing ? <input value={section.title} onChange={(event) => changeSection(index, { title: event.target.value })} /> : <h2>{section.title}</h2>}
              {editing ? <textarea value={section.body} onChange={(event) => changeSection(index, { body: event.target.value })} /> : <p>{section.body}</p>}
              <div className="role-report-citations">{section.evidence_field_ids.map((field) => <code key={field}>{field}</code>)}</div>
            </section>
          ))}
          {report.limitations.length ? <section className="role-report-limitations"><h2><AlertTriangle size={15} /> Limitations</h2>{report.limitations.map((item) => <p key={item}>{item}</p>)}</section> : null}
        </main>

        <aside className="role-report-evidence">
          <section className="role-report-visual-card wide"><header><TrendingUp size={14} /><div><strong>{profile.primaryMetric} trend</strong><small>Linked to the narrative and selected object</small></div></header><TrendVisual values={trend} /></section>
          <section className="role-report-visual-card"><header><BarChart3 size={14} /><div><strong>Contributing evidence</strong><small>{evidence.top_factors.length} grounded factors</small></div></header><div className="role-report-factor-bars">{evidence.top_factors.slice(0, 5).map((factor) => <div key={factor.evidence_field_id}><span>{factor.display_name}</span><i><b style={{ width: `${Math.max(8, Math.min(100, factor.contribution * 100))}%` }} /></i><strong>{Math.round(factor.contribution * 100)}%</strong></div>)}</div></section>
          <section className="role-report-visual-card"><header><LayoutDashboard size={14} /><div><strong>Decision context</strong><small>Operational impact linked to the report</small></div></header><dl><div><dt>Decision</dt><dd>{report.recommended_decision}</dd></div><div><dt>Downtime</dt><dd>{evidence.equipment.estimated_downtime_minutes} min</dd></div><div><dt>Owner</dt><dd>{evidence.equipment.assigned_engineer}</dd></div><div><dt>Confidence</dt><dd>{report.confidence}</dd></div></dl></section>
        </aside>
      </div>
    </article>
  );
}
