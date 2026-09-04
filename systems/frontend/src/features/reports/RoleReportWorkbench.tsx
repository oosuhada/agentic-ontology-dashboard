import { AlertTriangle, BarChart3, Check, FilePenLine, LayoutDashboard, Printer, RefreshCw, RotateCcw, Save, TrendingUp, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getReportDraft, saveReportDraft } from "../../api";
import type { Evidence, EventSummary, Report } from "../../types";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { WorkbenchState } from "../../ui/foundry/WorkbenchState";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type { AppLocale } from "../../ui/i18n/messages";
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

function reportCopy(locale: AppLocale) {
  return locale === "ko-KR" ? {
    noTrend: "시계열 근거 없음",
    noTrendDetail: "선택한 리포트에 시각화할 수치 이력이 없습니다.",
    trendAria: "리포트 근거 추세",
    sharedRevision: "공유 리비전",
    generatedReport: "생성된 리포트",
    saving: "저장 중",
    saveReport: "리포트 저장",
    resolvingReport: "리포트 확인 중",
    editReport: "리포트 편집",
    cancelEdit: "편집 취소",
    resetChanges: "변경 되돌리기",
    unsavedChanges: "저장되지 않은 변경",
    unsavedConfirm: "저장하지 않은 변경 사항이 있습니다. 이 화면을 벗어나시겠습니까?",
    printPdf: "인쇄 / PDF",
    openDashboard: "상세 대시보드 열기",
    documentId: "문서 ID",
    issued: "발행일",
    status: "상태",
    confidence: "신뢰도",
    reportSubject: "리포트 대상",
    primaryObject: "주요 Object",
    risk: "위험도",
    openEvents: "미종결 이벤트",
    highRisk: "고위험",
    decisionRequired: "운영 판단 필요",
    riskLevel: "위험 수준",
    operationalImpact: "운영 영향",
    owner: "담당자",
    high: "높음",
    medium: "중간",
    low: "낮음",
    minutes: "분",
    loadingRevision: "선택 언어의 리포트 리비전을 불러오는 중",
    evidenceFinding: "근거 기반 분석",
    recommendedActions: "권장 조치",
    actionsHeading: "승인 후 실행할 조치",
    approvalRequired: "사람의 승인 필요",
    governedExecution: "관리형 실행 준비됨",
    limitations: "제약 사항",
    linkedTrend: "리포트 본문과 선택 Object에 연결됨",
    contributingEvidence: "기여 근거",
    groundedFactors: "개의 근거 요인",
    technicalEvidence: "기술 근거 필드",
    decisionContext: "판단 Context",
    decisionContextDetail: "리포트에 연결된 운영 영향",
    decision: "권장 결정",
    downtime: "예상 비가동",
    governedBriefing: "관리형 운영 브리핑",
    generatedBaseline: "생성된 기본본",
    reportLoadFailed: "리포트를 불러오지 못했습니다.",
    saveFailed: "리포트 저장에 실패했습니다.",
    savedMessage: "한국어 리포트 리비전 {revision}을 저장했습니다.",
    preparingTitle: "역할별 리포트를 준비하고 있습니다",
    preparingDetail: "선택 언어의 서술 항목을 관리형 근거와 시각화에 연결하고 있습니다.",
  } : {
    noTrend: "No time-series evidence",
    noTrendDetail: "The selected report has no numeric history to visualize.",
    trendAria: "Report evidence trend",
    sharedRevision: "Shared revision",
    generatedReport: "Generated report",
    saving: "Saving",
    saveReport: "Save report",
    resolvingReport: "Resolving report",
    editReport: "Edit report",
    cancelEdit: "Cancel editing",
    resetChanges: "Reset changes",
    unsavedChanges: "Unsaved changes",
    unsavedConfirm: "You have unsaved changes. Leave this report without saving?",
    printPdf: "Print / PDF",
    openDashboard: "Open detailed dashboard",
    documentId: "Document ID",
    issued: "Issued",
    status: "Status",
    confidence: "Confidence",
    reportSubject: "Report subject",
    primaryObject: "Primary object",
    risk: "Risk",
    openEvents: "Open events",
    highRisk: "High risk",
    decisionRequired: "Operational decision required",
    riskLevel: "Risk level",
    operationalImpact: "Operational impact",
    owner: "Accountable owner",
    high: "High",
    medium: "Medium",
    low: "Low",
    minutes: "min",
    loadingRevision: "Loading the report revision for the selected language",
    evidenceFinding: "Evidence-based finding",
    recommendedActions: "Recommended actions",
    actionsHeading: "Actions to execute after approval",
    approvalRequired: "Human approval required",
    governedExecution: "Ready for governed execution",
    limitations: "Limitations",
    linkedTrend: "Linked to the narrative and selected object",
    contributingEvidence: "Contributing evidence",
    groundedFactors: " grounded factors",
    technicalEvidence: "Technical evidence fields",
    decisionContext: "Decision context",
    decisionContextDetail: "Operational impact linked to the report",
    decision: "Decision",
    downtime: "Downtime",
    governedBriefing: "Governed operational briefing",
    generatedBaseline: "generated baseline",
    reportLoadFailed: "Report draft could not be loaded.",
    saveFailed: "Report could not be saved.",
    savedMessage: "Saved English report revision {revision}.",
    preparingTitle: "Preparing role briefing",
    preparingDetail: "Linking the selected-language narrative to governed evidence and visualizations.",
  };
}

function localizedDecision(value: string, locale: AppLocale) {
  const labels: Record<string, [string, string]> = {
    continue_monitoring: ["계속 모니터링", "Continue monitoring"],
    request_inspection: ["현장 점검 요청", "Request a field inspection"],
    review_shutdown: ["권한자 정지 검토", "Review a shutdown with an authorized operator"],
    hold_for_data_check: ["데이터 확인 전 판단 보류", "Hold the decision until data is verified"],
  };
  const pair = labels[value];
  return pair ? pair[locale === "ko-KR" ? 0 : 1] : value.replaceAll("_", " ");
}

function localizedStatus(value: string, locale: AppLocale) {
  const labels: Record<string, [string, string]> = {
    critical: ["긴급 검토", "Critical"],
    warning: ["경고", "Warning"],
    attention: ["관찰", "Attention"],
    data_quality_hold: ["데이터 확인", "Data quality hold"],
    normal: ["정상", "Normal"],
    high: ["높음", "High"],
    medium: ["중간", "Medium"],
    low: ["낮음", "Low"],
  };
  const pair = labels[value];
  return pair ? pair[locale === "ko-KR" ? 0 : 1] : value.replaceAll("_", " ");
}

function localizedFailureType(value: string, locale: AppLocale) {
  const labels: Record<string, [string, string]> = {
    power_or_overstrain_failure: ["동력·과부하 이상", "Power or overstrain failure"],
    tool_wear_failure: ["공구 마모 이상", "Tool wear failure"],
    heat_dissipation_failure: ["방열 이상", "Heat dissipation failure"],
    multi_factor_risk: ["복합 위험", "Multi-factor risk"],
    uncertain: ["불확실", "Uncertain"],
    unavailable: ["판단 불가", "Unavailable"],
    none: ["이상 없음", "No predicted failure"],
  };
  const pair = labels[value];
  return pair ? pair[locale === "ko-KR" ? 0 : 1] : value.replaceAll("_", " ");
}

function localizedNarrativeText(value: string, locale: AppLocale) {
  const formatted = value.replace(
    /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})/g,
    (timestamp) => {
      const parsed = new Date(timestamp);
      return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
    },
  );
  if (locale === "ko-KR") {
    return formatted
      .replace(/신뢰도는 high입니다/g, "신뢰도는 높음입니다")
      .replace(/신뢰도는 medium입니다/g, "신뢰도는 중간입니다")
      .replace(/신뢰도는 low입니다/g, "신뢰도는 낮음입니다");
  }
  return formatted;
}

function TrendVisual({ values, locale }: { values: number[]; locale: AppLocale }) {
  const copy = reportCopy(locale);
  if (values.length < 2) return <WorkbenchState kind="empty" compact title={copy.noTrend} detail={copy.noTrendDetail} />;
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
    <svg className="role-report-trend" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={copy.trendAria}>
      {[0, 1, 2, 3].map((line) => <line key={line} x1="18" x2={width - 18} y1={24 + line * 40} y2={24 + line * 40} />)}
      <polyline points={points} />
      <circle cx={points.split(" ").at(-1)?.split(",")[0]} cy={points.split(" ").at(-1)?.split(",")[1]} r="5" />
    </svg>
  );
}

function formatReportDate(value: string, locale: AppLocale) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
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
  const { locale } = useI18n();
  const copy = reportCopy(locale);
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
    if (!report || report.locale !== locale || !workspaceId || !selectedEventId) return;
    let cancelled = false;
    setLoading(true);
    setMessage("");
    getReportDraft(workspaceId, selectedEventId, report.role, locale)
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
        setMessage(reason instanceof Error ? reason.message : copy.reportLoadFailed);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [copy.reportLoadFailed, locale, report?.report_id, report?.role, selectedEventId, workspaceId]);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const trend = useMemo(() => metricValues(evidence, profile), [evidence, profile]);
  const criticalEvents = events.filter((event) => (event.failure_probability ?? 0) >= .7).length;
  const pendingEvents = events.filter((event) => !["closed", "resolved", "completed"].includes(event.status.toLowerCase())).length;
  const riskPercent = Math.round((evidence?.failure_probability ?? 0) * 100);

  function changeSection(index: number, patch: Partial<ReportDraftSection>) {
    setSections((current) => current.map((section, sectionIndex) => sectionIndex === index ? { ...section, ...patch } : section));
    setDirty(true);
  }

  function restoreBaseline() {
    if (!report) return;
    setHeadline(savedDraft?.headline ?? report.headline);
    setSummary(savedDraft?.summary ?? report.summary);
    setSections(savedDraft?.sections ?? generatedSections(report));
    setDirty(false);
  }

  function cancelEditing() {
    restoreBaseline();
    setEditing(false);
    setMessage("");
  }

  function changeSelectedEvent(nextEventId: string) {
    if (dirty && !window.confirm(copy.unsavedConfirm)) return;
    onSelectEvent(nextEventId);
  }

  async function saveDraft() {
    if (!report || !canEdit || saving) return;
    setSaving(true);
    setMessage("");
    try {
      const saved = await saveReportDraft({
        workspace_id: workspaceId,
        event_id: selectedEventId,
        role: report.role,
        locale,
        base_revision: savedDraft?.revision ?? 0,
        headline: headline.trim(),
        summary: summary.trim(),
        sections,
        content_origin: "edited",
      });
      setSavedDraft(saved);
      setDirty(false);
      setEditing(false);
      setMessage(copy.savedMessage.replace("{revision}", String(saved.revision)));
    } catch (reason: unknown) {
      setMessage(reason instanceof Error ? reason.message : copy.saveFailed);
    } finally {
      setSaving(false);
    }
  }

  if (!report || report.locale !== locale || !evidence) return <div className="role-report-loading"><WorkbenchState kind="loading" title={copy.preparingTitle} detail={copy.preparingDetail} /></div>;

  return (
    <article className={`role-report-workbench profile-${profile.id} ${editing ? "is-editing" : ""}`}>
      <div className="role-report-document">
        <header className="role-report-cover">
          <div>
            <span>{profile.eyebrow}</span>
            <small>{projectName} · {roleLabel} · {profile.datasetSummary}</small>
            {editing ? <input className="role-report-headline-input" value={headline} onChange={(event) => { setHeadline(event.target.value); setDirty(true); }} /> : <h1>{headline}</h1>}
            {editing ? <textarea className="role-report-summary-input" value={summary} onChange={(event) => { setSummary(event.target.value); setDirty(true); }} /> : <p>{summary}</p>}
          </div>
          <div className="role-report-actions">
            <StatusPill intent={savedDraft ? "success" : "primary"}>{savedDraft ? `${copy.sharedRevision} ${savedDraft.revision}` : copy.generatedReport}</StatusPill>
            {dirty ? <StatusPill intent="warning">{copy.unsavedChanges}</StatusPill> : null}
            {canEdit ? editing
              ? <>
                  <button type="button" onClick={cancelEditing}><X size={13} /> {copy.cancelEdit}</button>
                  <button type="button" disabled={!dirty || saving} onClick={restoreBaseline}><RotateCcw size={13} /> {copy.resetChanges}</button>
                  <button type="button" className="primary" disabled={!dirty || saving} onClick={() => void saveDraft()}><Save size={13} /> {saving ? copy.saving : copy.saveReport}</button>
                </>
              : <button type="button" disabled={loading} onClick={() => { setMessage(""); setEditing(true); }}><FilePenLine size={13} /> {loading ? copy.resolvingReport : copy.editReport}</button>
              : null}
            <button type="button" onClick={() => window.print()}><Printer size={13} /> {copy.printPdf}</button>
            <button type="button" onClick={onOpenDashboard}><LayoutDashboard size={13} /> {copy.openDashboard}</button>
          </div>
        </header>

        <section className="role-report-meta" aria-label={copy.documentId}>
          <div><span>{copy.documentId}</span><strong>{report.report_id}</strong></div>
          <div><span>{copy.issued}</span><strong>{formatReportDate(report.generated_at, locale)}</strong></div>
          <div><span>{copy.status}</span><strong title={report.status}>{localizedStatus(report.status, locale)}</strong></div>
          <div><span>{copy.confidence}</span><strong title={report.confidence}>{localizedStatus(report.confidence, locale)}</strong></div>
        </section>

        <section className="role-report-scopebar">
          <label>{copy.reportSubject}<select aria-label={copy.reportSubject} value={selectedEventId} onChange={(event) => changeSelectedEvent(event.target.value)}>{events.map((event) => <option key={event.event_id} value={event.event_id}>{event.equipment.display_name} · {localizedFailureType(event.predicted_failure_type, locale)}</option>)}</select></label>
          <div><span>{copy.primaryObject}<strong>{evidence.equipment.display_name}</strong></span><span>{copy.risk}<strong>{riskPercent}%</strong></span><span>{copy.openEvents}<strong>{pendingEvents}</strong></span><span>{copy.highRisk}<strong>{criticalEvents}</strong></span></div>
        </section>

        <section className="role-report-decision-brief">
          <div>
            <span>{copy.decisionRequired}</span>
            <strong>{localizedDecision(report.recommended_decision, locale)}</strong>
            <p>{locale === "ko-KR"
              ? `현재 위험도는 ${riskPercent}%이며 예상 비가동 영향은 ${evidence.equipment.estimated_downtime_minutes}분입니다. 담당자는 ${evidence.equipment.assigned_engineer}이며, 상세 근거는 아래 분석 항목과 연결되어 있습니다.`
              : `Current risk is ${riskPercent}%, with an estimated downtime exposure of ${evidence.equipment.estimated_downtime_minutes} minutes. The accountable owner is ${evidence.equipment.assigned_engineer}, and the detailed evidence is linked below.`}</p>
          </div>
          <dl>
            <div><dt>{copy.riskLevel}</dt><dd>{riskPercent >= 70 ? copy.high : riskPercent >= 40 ? copy.medium : copy.low}</dd></div>
            <div><dt>{copy.operationalImpact}</dt><dd>{evidence.equipment.estimated_downtime_minutes} {copy.minutes}</dd></div>
            <div><dt>{copy.owner}</dt><dd>{evidence.equipment.assigned_engineer}</dd></div>
          </dl>
        </section>

        {message ? <div className={`role-report-message ${message.includes("실패") || message.includes("could not") ? "is-error" : ""}`}><Check size={12} />{message}</div> : null}
        {loading ? <div className="role-report-refresh"><RefreshCw className="spin" size={14} /> {copy.loadingRevision}</div> : null}

        <div className="role-report-grid">
          <main className="role-report-narrative">
            {sections.map((section, index) => (
              <section key={section.section_id}>
                <span>{String(index + 1).padStart(2, "0")} · {profile.reportSections[index] ?? copy.evidenceFinding}</span>
                {editing ? <input value={section.title} onChange={(event) => changeSection(index, { title: event.target.value })} /> : <h2>{section.title}</h2>}
                {editing ? <textarea value={section.body} onChange={(event) => changeSection(index, { body: event.target.value })} /> : <p>{localizedNarrativeText(section.body, locale)}</p>}
                {section.evidence_field_ids.length ? <details className="role-report-citations"><summary>{copy.technicalEvidence} · {section.evidence_field_ids.length}</summary><div>{section.evidence_field_ids.map((field) => <code key={field}>{field}</code>)}</div></details> : null}
              </section>
            ))}
            {report.actions.length ? <section className="role-report-actions-list"><span>{copy.recommendedActions}</span><h2>{copy.actionsHeading}</h2><ol>{report.actions.map((action) => <li key={action.action_id}><Check size={12} /><div><strong>{action.label}</strong><small>{action.requires_human_approval ? copy.approvalRequired : copy.governedExecution}</small></div></li>)}</ol></section> : null}
            {report.limitations.length ? <section className="role-report-limitations"><h2><AlertTriangle size={15} /> {copy.limitations}</h2>{report.limitations.map((item) => <p key={item}>{item}</p>)}</section> : null}
          </main>

          <aside className="role-report-evidence">
            <section className="role-report-visual-card wide"><header><TrendingUp size={14} /><div><strong>{profile.primaryMetric} {locale === "ko-KR" ? "추세" : "trend"}</strong><small>{copy.linkedTrend}</small></div></header><TrendVisual values={trend} locale={locale} /></section>
            <section className="role-report-visual-card"><header><BarChart3 size={14} /><div><strong>{copy.contributingEvidence}</strong><small>{locale === "ko-KR" ? `${evidence.top_factors.length}${copy.groundedFactors}` : `${evidence.top_factors.length}${copy.groundedFactors}`}</small></div></header><div className="role-report-factor-bars">{evidence.top_factors.slice(0, 5).map((factor) => <div key={factor.evidence_field_id}><span>{factor.display_name}</span><i><b style={{ width: `${Math.max(8, Math.min(100, factor.contribution * 100))}%` }} /></i><strong>{Math.round(factor.contribution * 100)}%</strong></div>)}</div></section>
            <section className="role-report-visual-card"><header><LayoutDashboard size={14} /><div><strong>{copy.decisionContext}</strong><small>{copy.decisionContextDetail}</small></div></header><dl><div><dt>{copy.decision}</dt><dd>{localizedDecision(report.recommended_decision, locale)}</dd></div><div><dt>{copy.downtime}</dt><dd>{evidence.equipment.estimated_downtime_minutes} {copy.minutes}</dd></div><div><dt>{copy.owner}</dt><dd>{evidence.equipment.assigned_engineer}</dd></div><div><dt>{copy.confidence}</dt><dd title={report.confidence}>{localizedStatus(report.confidence, locale)}</dd></div></dl></section>
          </aside>
        </div>

        <footer className="role-report-footer">
          <span>Ontology Dashboard · {copy.governedBriefing}</span>
          <span>{report.report_id} · {savedDraft ? `revision ${savedDraft.revision}` : copy.generatedBaseline}</span>
        </footer>
      </div>
    </article>
  );
}
