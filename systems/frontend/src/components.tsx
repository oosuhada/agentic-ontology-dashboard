import { FormEvent, useMemo, useState } from "react";
import { StatusBadge } from "./components/StatusBadge";
import type { Evidence, EventSummary, FollowUp, Report, Role, UIBlock } from "./types";
import { useI18n } from "./ui/i18n/I18nProvider";
import type { AppLocale } from "./ui/i18n/messages";

export { StatusBadge } from "./components/StatusBadge";

const DECISION_LABEL: Record<string, [string, string]> = {
  continue_monitoring: ["계속 모니터링", "Continue monitoring"],
  request_inspection: ["현장 점검 요청", "Request a field inspection"],
  review_shutdown: ["정지 여부 검토", "Review a shutdown"],
  hold_for_data_check: ["데이터 확인 전 보류", "Hold until data is verified"],
};

function decisionLabel(value: string, locale: AppLocale) {
  const pair = DECISION_LABEL[value];
  return pair ? pair[locale === "ko-KR" ? 0 : 1] : value.replaceAll("_", " ");
}

function blockCopy(locale: AppLocale) {
  return locale === "ko-KR" ? {
    noValidData: "표시할 유효 데이터가 없습니다.",
    timeSeries: "시계열",
    range: "범위",
    systemRecommendation: "시스템 권장",
    recommendationDetail: "실제 설비 제어가 아닌 사람의 판단을 위한 권고입니다.",
    handoffNote: "전달 메모",
    handoffPlaceholder: "담당 엔지니어와 기한을 기록하세요.",
    recorded: "기록 완료",
    fieldNote: "현장 메모",
    fieldPlaceholder: "관찰 내용과 다음 조치를 기록하세요.",
    saveInspection: "점검 기록 저장",
    inspectionSaved: "점검 기록이 저장됐습니다.",
    inspectionNotePrefix: "점검 완료",
    none: "없음",
    memo: "메모",
    readOnly: "조회 전용",
    questions: ["왜 위험한가?", "정상 설비와 비교해줘.", "매니저용으로 짧게 요약해줘.", "무엇을 먼저 점검해야 하는가?", "모델 상세를 보여줘."],
    askPlaceholder: "현재 Evidence 범위에서 질문하세요.",
    followUpQuestion: "후속 질문",
    ask: "질문",
    answer: "답변",
    unsupported: "지원 범위 안내",
    notCalculated: "산출 안 함",
    evidence: "Evidence",
    failureRisk: "고장 위험도",
    threshold: "표시 임계값",
    confidence: "신뢰도",
    criticality: "설비 중요도",
    recommendedDecision: "권장 결정",
    downtimeImpact: "예상 정지 영향",
    fixtureEstimate: "현재 기준 추정치",
    assignedEngineer: "담당 엔지니어",
    sparePart: "예비 부품",
    available: "확보",
    unavailable: "미확보",
    lastMaintenance: "최근 정비",
    decisionReadOnly: "현재 역할은 운영 판단을 조회할 수 있지만 새 판단을 기록할 수 없습니다.",
    toolWear: "공구 마모",
    torque: "토크",
    processTemperature: "공정 온도",
    rotationalSpeed: "회전 속도",
    start: "시작",
    current: "현재",
    status: "상태",
    reference: "참고",
    evidenceColumn: "근거",
    value: "값",
    referenceRange: "참고 범위",
    direction: "방향",
    source: "출처",
    riskUp: "위험 증가",
    riskDown: "위험 감소",
    humanApproval: "사람 승인 필요",
    automatic: "자동",
    evidencePolicy: "Evidence 정책",
    checklistReadOnly: "현재 역할은 체크리스트를 검토할 수 있지만 점검 기록을 저장할 수 없습니다.",
    qualityHold: "유효한 값으로 다시 검증하기 전 정상 또는 고장으로 단정하지 않습니다.",
    qualityBoundary: "센서 값은 유효하지만 위험 근거가 경계 수준이거나 서로 충돌해 신뢰도가 낮습니다.",
    qualityConfirm: "추가 관측과 간단 현장 확인 전 고장 원인이나 정지 필요성을 확정하지 않습니다.",
    model: "모델",
    policy: "정책",
    mode: "모드",
    context: "Context",
    lineage: "Lineage",
    unsupportedBlock: "지원하지 않는 블록",
    unsupportedBlockDetail: "등록되지 않은 블록은 렌더링하지 않습니다.",
  } : {
    noValidData: "No valid data to display.",
    timeSeries: "time series",
    range: "Range",
    systemRecommendation: "System recommendation",
    recommendationDetail: "This is a recommendation for human judgment, not an automatic equipment-control action.",
    handoffNote: "Handoff note",
    handoffPlaceholder: "Record the responsible engineer and due date.",
    recorded: "recorded",
    fieldNote: "Field note",
    fieldPlaceholder: "Record observations and the next action.",
    saveInspection: "Save inspection record",
    inspectionSaved: "The inspection record was saved.",
    inspectionNotePrefix: "Inspection completed",
    none: "none",
    memo: "Memo",
    readOnly: "Read only",
    questions: ["Why is this risky?", "Compare it with a normal asset.", "Summarize it for a manager.", "What should be inspected first?", "Show model details."],
    askPlaceholder: "Ask a question within the current evidence scope.",
    followUpQuestion: "Follow-up question",
    ask: "Ask",
    answer: "Answer",
    unsupported: "Supported-scope guidance",
    notCalculated: "Not calculated",
    evidence: "Evidence",
    failureRisk: "Failure risk",
    threshold: "Display threshold",
    confidence: "Confidence",
    criticality: "Asset criticality",
    recommendedDecision: "Recommended decision",
    downtimeImpact: "Estimated downtime impact",
    fixtureEstimate: "current reference estimate",
    assignedEngineer: "Assigned engineer",
    sparePart: "Spare part",
    available: "Available",
    unavailable: "Unavailable",
    lastMaintenance: "Last maintenance",
    decisionReadOnly: "The current role can review operational decisions but cannot record a new decision.",
    toolWear: "Tool wear",
    torque: "Torque",
    processTemperature: "Process temperature",
    rotationalSpeed: "Rotational speed",
    start: "Start",
    current: "Current",
    status: "Status",
    reference: "Reference",
    evidenceColumn: "Evidence",
    value: "Value",
    referenceRange: "Reference range",
    direction: "Direction",
    source: "Source",
    riskUp: "Risk increase",
    riskDown: "Risk decrease",
    humanApproval: "Human approval required",
    automatic: "Automatic",
    evidencePolicy: "Evidence policy",
    checklistReadOnly: "The current role can review the checklist but cannot save an inspection record.",
    qualityHold: "Do not classify the asset as normal or failed until valid values are verified.",
    qualityBoundary: "Sensor values are valid, but risk evidence is near a boundary or conflicts, so confidence is low.",
    qualityConfirm: "Do not confirm a failure cause or shutdown requirement before additional observations and a basic field check.",
    model: "Model",
    policy: "Policy",
    mode: "Mode",
    context: "Context",
    lineage: "Lineage",
    unsupportedBlock: "Unsupported block",
    unsupportedBlockDetail: "Unregistered blocks are not rendered.",
  };
}

function tokenLabel(value: string, locale: AppLocale) {
  const labels: Record<string, [string, string]> = {
    normal: ["정상", "Normal"],
    attention: ["관찰", "Attention"],
    warning: ["경고", "Warning"],
    critical: ["긴급 검토", "Critical"],
    data_quality_hold: ["데이터 확인", "Data quality hold"],
    low: ["낮음", "Low"],
    medium: ["중간", "Medium"],
    high: ["높음", "High"],
    failure_risk: ["고장 위험", "Failure risk"],
    no_significant_risk: ["유의한 위험 없음", "No significant risk"],
    tool_wear_failure: ["공구 마모 위험", "Tool-wear risk"],
    heat_dissipation_failure: ["열 방출 이상 가능성", "Possible heat-dissipation issue"],
    power_or_overstrain_failure: ["동력·과부하 이상 가능성", "Possible power or overstrain issue"],
    multi_factor_risk: ["복합 이상 가능성", "Multi-factor risk"],
  };
  const pair = labels[value];
  return pair ? pair[locale === "ko-KR" ? 0 : 1] : value.replaceAll("_", " ");
}

function factorLabel(fieldId: string, displayName: string, locale: AppLocale) {
  if (locale === "ko-KR") return displayName;
  const id = fieldId.replace(/^factor[:.]/, "").replace(/^factor\.\d+\./, "");
  const labels: Record<string, string> = {
    air_temperature_k: "Air temperature",
    process_temperature_k: "Process temperature",
    rotational_speed_rpm: "Rotational speed",
    torque_nm: "Torque",
    tool_wear_min: "Tool wear",
    power_w: "Mechanical power",
    temperature_gap_k: "Process-to-air temperature gap",
    overstrain_load: "Tool-wear torque load",
    rotation_raw_6h_mean: "6-hour rotational-speed mean",
    rotation_raw_6h_abs_mean: "6-hour rotational-speed absolute mean",
    rotation_raw_6h_std: "6-hour rotational-speed standard deviation",
  };
  return labels[id] ?? (/[가-힣]/.test(displayName) ? id.replaceAll("_", " ") : displayName);
}

function checklistItems(evidence: Evidence, locale: AppLocale) {
  const source = evidence.maintenance_context.checklist;
  if (locale === "ko-KR" || source.every((item) => !/[가-힣]/.test(item))) return source;
  return [
    "Review the governed top factors",
    "Confirm the latest sensor window",
    "Check maintenance evidence before approval",
  ];
}

function Card({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}

function MiniLine({ values, label, unit }: { values: Array<number | null>; label: string; unit: string }) {
  const { locale } = useI18n();
  const copy = blockCopy(locale);
  const valid = values.filter((value): value is number => value !== null);
  if (!valid.length) return <div className="empty-state">{copy.noValidData}</div>;
  const minimum = Math.min(...valid);
  const maximum = Math.max(...valid);
  const range = maximum - minimum || 1;
  const points = values
    .map((value, index) => {
      if (value === null) return null;
      const x = 20 + (index * 260) / Math.max(values.length - 1, 1);
      const y = 92 - ((value - minimum) / range) * 64;
      return `${x},${y}`;
    })
    .filter(Boolean)
    .join(" ");
  return (
    <div className="mini-chart">
      <div className="chart-header"><strong>{label}</strong><span>{valid.at(-1)?.toFixed(1)} {unit}</span></div>
      <svg viewBox="0 0 300 110" role="img" aria-label={`${label} ${copy.timeSeries}`}>
        <line x1="20" x2="280" y1="92" y2="92" className="axis" />
        <polyline points={points} className="trend-line" fill="none" />
        {points.split(" ").map((point, index) => {
          const [cx, cy] = point.split(",");
          return <circle key={`${point}-${index}`} cx={cx} cy={cy} r="3" className="trend-dot" />;
        })}
      </svg>
      <small>{copy.range} {minimum.toFixed(1)}–{maximum.toFixed(1)} {unit}</small>
    </div>
  );
}

function PriorityList({ events, selected, onSelect }: { events: EventSummary[]; selected: string; onSelect: (id: string) => void }) {
  const { locale } = useI18n();
  return (
    <div className="priority-list">
      {events.map((event, index) => (
        <button
          key={event.event_id}
          className={`priority-row ${selected === event.event_id ? "selected" : ""}`}
          onClick={() => onSelect(event.event_id)}
        >
          <span className="rank">{index + 1}</span>
          <span className="priority-main">
            <strong>{event.equipment.display_name}</strong>
            <small>{event.equipment.line} · {tokenLabel(event.predicted_failure_type, locale)}</small>
          </span>
          <StatusBadge status={event.status} />
          <strong>{event.failure_probability === null ? "—" : `${(event.failure_probability * 100).toFixed(1)}%`}</strong>
        </button>
      ))}
    </div>
  );
}

function DecisionCard({ evidence, onDecision }: { evidence: Evidence; onDecision: (decision: string, note: string) => Promise<void> }) {
  const { locale } = useI18n();
  const copy = blockCopy(locale);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState("");
  async function submit(decision: string) {
    await onDecision(decision, note);
    setSaved(`${decisionLabel(decision, locale)} ${copy.recorded}`);
  }
  const options = ["continue_monitoring", "request_inspection", "review_shutdown", "hold_for_data_check"];
  return (
    <div>
      <div className="decision-recommendation">
        <span>{copy.systemRecommendation}</span>
        <strong>{decisionLabel(evidence.recommended_decision, locale)}</strong>
        <small>{copy.recommendationDetail}</small>
      </div>
      <label className="field-label">
        {copy.handoffNote}
        <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder={copy.handoffPlaceholder} />
      </label>
      <div className="button-row">
        {options.map((option) => (
          <button key={option} className={option === evidence.recommended_decision ? "primary" : "secondary"} onClick={() => submit(option)}>
            {decisionLabel(option, locale)}
          </button>
        ))}
      </div>
      {saved ? <p className="success-message" role="status">{saved}</p> : null}
    </div>
  );
}

function Checklist({ evidence, onNote }: { evidence: Evidence; onNote: (body: string) => Promise<void> }) {
  const { locale } = useI18n();
  const copy = blockCopy(locale);
  const items = checklistItems(evidence, locale);
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [memo, setMemo] = useState("");
  const [saved, setSaved] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const completed = items.filter((_, index) => checked[index]);
    await onNote(`${copy.inspectionNotePrefix}: ${completed.join(", ") || copy.none}. ${copy.memo}: ${memo || copy.none}`);
    setSaved(true);
  }
  return (
    <form onSubmit={submit}>
      <ul className="checklist">
        {items.map((item, index) => (
          <li key={item}>
            <label>
              <input type="checkbox" checked={Boolean(checked[index])} onChange={(event) => setChecked({ ...checked, [index]: event.target.checked })} />
              <span>{item}</span>
            </label>
          </li>
        ))}
      </ul>
      <label className="field-label">
        {copy.fieldNote}
        <textarea value={memo} onChange={(event) => setMemo(event.target.value)} placeholder={copy.fieldPlaceholder} />
      </label>
      <button className="primary" type="submit">{copy.saveInspection}</button>
      {saved ? <p className="success-message" role="status">{copy.inspectionSaved}</p> : null}
    </form>
  );
}

function ReadOnlyAction({ message }: { message: string }) {
  const { locale } = useI18n();
  return <div className="read-only-action"><strong>{blockCopy(locale).readOnly}</strong><p>{message}</p></div>;
}

function Conversation({ onAsk, lastFollowUp }: { onAsk: (question: string) => Promise<void>; lastFollowUp: FollowUp | null }) {
  const { locale } = useI18n();
  const copy = blockCopy(locale);
  const [question, setQuestion] = useState("");
  const examples = copy.questions;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    await onAsk(question);
    setQuestion("");
  }
  return (
    <div>
      <div className="question-chips">
        {examples.map((example) => <button className="chip" key={example} onClick={() => onAsk(example)}>{example}</button>)}
      </div>
      <form className="question-form" onSubmit={submit}>
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={copy.askPlaceholder} aria-label={copy.followUpQuestion} />
        <button className="primary" type="submit">{copy.ask}</button>
      </form>
      {lastFollowUp ? (
        <div className={`conversation-answer ${lastFollowUp.supported ? "" : "unsupported"}`}>
          <strong>{lastFollowUp.supported ? copy.answer : copy.unsupported}</strong>
          <p>{lastFollowUp.answer}</p>
        </div>
      ) : null}
    </div>
  );
}

export interface BlockRendererProps {
  block: UIBlock;
  evidence: Evidence;
  report: Report;
  events: EventSummary[];
  selectedEventId: string;
  role: Role;
  canRecordDecision: boolean;
  canRecordNote: boolean;
  onSelectEvent: (id: string) => void;
  onDecision: (decision: string, note: string) => Promise<void>;
  onNote: (body: string) => Promise<void>;
  onAsk: (question: string) => Promise<void>;
  lastFollowUp: FollowUp | null;
}

export function BlockRenderer(props: BlockRendererProps) {
  const { locale } = useI18n();
  const copy = blockCopy(locale);
  const {
    block,
    evidence,
    report,
    events,
    selectedEventId,
    canRecordDecision,
    canRecordNote,
    onSelectEvent,
    onDecision,
    onNote,
    onAsk,
    lastFollowUp,
  } = props;
  const probability = evidence.failure_probability === null ? copy.notCalculated : `${(evidence.failure_probability * 100).toFixed(1)}%`;
  const history = useMemo(() => [...evidence.history, evidence.observation], [evidence]);

  switch (block.type) {
    case "PriorityList":
      return <Card title={block.title}><PriorityList events={events} selected={selectedEventId} onSelect={onSelectEvent} /></Card>;
    case "StatusSummary":
      return (
        <Card title={block.title} className="status-card">
          <div className="headline-row"><StatusBadge status={evidence.status} /><span>{evidence.equipment.display_name}</span></div>
          <h3>{report.headline}</h3>
          <p>{report.summary}</p>
          <div className="source-line">{copy.evidence} {evidence.evidence_id} · {report.mode}</div>
        </Card>
      );
    case "RiskKpi":
      return (
        <Card title={block.title}>
          <div className="metric-grid">
            <Metric label={copy.failureRisk} value={probability} hint={`${copy.threshold} ${(evidence.threshold * 100).toFixed(0)}%`} />
            <Metric label={copy.confidence} value={tokenLabel(evidence.confidence, locale)} />
            <Metric label={copy.criticality} value={tokenLabel(evidence.equipment.criticality, locale)} />
            <Metric label={copy.recommendedDecision} value={decisionLabel(evidence.recommended_decision, locale)} />
          </div>
        </Card>
      );
    case "ImpactSummary":
      return (
        <Card title={block.title}>
          <div className="metric-grid compact">
            <Metric label={copy.downtimeImpact} value={`${evidence.equipment.estimated_downtime_minutes} ${locale === "ko-KR" ? "분" : "min"}`} hint={copy.fixtureEstimate} />
            <Metric label={copy.assignedEngineer} value={evidence.equipment.assigned_engineer} />
            <Metric label={copy.sparePart} value={evidence.equipment.spare_part_available ? copy.available : copy.unavailable} />
            <Metric label={copy.lastMaintenance} value={evidence.equipment.last_maintenance_date} />
          </div>
        </Card>
      );
    case "ManagerDecisionCard":
      return (
        <Card title={block.title}>
          {canRecordDecision ? (
            <DecisionCard evidence={evidence} onDecision={onDecision} />
          ) : (
            <ReadOnlyAction message={copy.decisionReadOnly} />
          )}
        </Card>
      );
    case "SensorLineChart":
      return (
        <Card title={block.title}>
          <div className="chart-grid">
            <MiniLine label={copy.toolWear} unit="min" values={history.map((item) => item.tool_wear_min)} />
            <MiniLine label={copy.torque} unit="N·m" values={history.map((item) => item.torque_nm)} />
            <MiniLine label={copy.processTemperature} unit="K" values={history.map((item) => item.process_temperature_k)} />
            <MiniLine label={copy.rotationalSpeed} unit="rpm" values={history.map((item) => item.rotational_speed_rpm)} />
          </div>
        </Card>
      );
    case "AnomalyTimeline":
      return (
        <Card title={block.title}>
          <div className="timeline">
            <div><span>{copy.start}</span><strong>{evidence.detected_interval.start}</strong></div>
            <div><span>{copy.current}</span><strong>{evidence.detected_interval.end}</strong></div>
            <div><span>{copy.status}</span><StatusBadge status={evidence.status} /></div>
          </div>
        </Card>
      );
    case "FactorContribution":
      return (
        <Card title={block.title}>
          <div className="factor-list">
            {evidence.top_factors.map((factor) => (
              <div className="factor-row" key={factor.evidence_field_id}>
                <div><strong>{factorLabel(factor.evidence_field_id, factor.display_name, locale)}</strong><small>{factor.value.toLocaleString(locale)} {factor.unit} · {copy.reference} {factor.normal_range}</small></div>
                <div className="bar-track"><span style={{ width: `${Math.max(factor.contribution * 100, 3)}%` }} /></div>
                <strong>{(factor.contribution * 100).toFixed(1)}%</strong>
              </div>
            ))}
          </div>
        </Card>
      );
    case "EvidenceTable":
      return (
        <Card title={block.title}>
          <div className="table-scroll"><table><thead><tr><th>{copy.evidenceColumn}</th><th>{copy.value}</th><th>{copy.referenceRange}</th><th>{copy.direction}</th><th>{copy.source}</th></tr></thead><tbody>
            {evidence.top_factors.map((factor) => <tr key={factor.evidence_field_id}><td>{factorLabel(factor.evidence_field_id, factor.display_name, locale)}</td><td>{factor.value.toLocaleString(locale)} {factor.unit}</td><td>{factor.normal_range}</td><td>{factor.direction === "risk_up" ? copy.riskUp : copy.riskDown}</td><td>{factor.source_type}</td></tr>)}
          </tbody></table></div>
        </Card>
      );
    case "RecommendedActions":
      return <Card title={block.title}><ol className="action-list">{report.actions.map((action) => <li key={action.action_id}><strong>{action.label}</strong><small>{action.requires_human_approval ? copy.humanApproval : copy.automatic} · {action.source_refs.join(", ") || copy.evidencePolicy}</small></li>)}</ol></Card>;
    case "EngineerChecklist":
      return (
        <Card title={block.title}>
          {canRecordNote ? (
            <Checklist evidence={evidence} onNote={onNote} />
          ) : (
            <>
              <ul className="checklist read-only-checklist">
                {checklistItems(evidence, locale).map((item) => <li key={item}>{item}</li>)}
              </ul>
              <ReadOnlyAction message={copy.checklistReadOnly} />
            </>
          )}
        </Card>
      );
    case "DataQualityWarning":
      return (
        <Card title={block.title} className="warning-card">
          {evidence.data_quality_warnings.length ? (
            <>
              <ul>{evidence.data_quality_warnings.map((warning) => <li key={`${warning.code}-${warning.field}`}><strong>{warning.field}</strong> — {locale === "ko-KR" ? warning.message : warning.code.replaceAll("_", " ")}</li>)}</ul>
              <p>{copy.qualityHold}</p>
            </>
          ) : (
            <>
              <p>{copy.qualityBoundary}</p>
              <p>{copy.qualityConfirm}</p>
            </>
          )}
        </Card>
      );
    case "ModelDetails":
      return <details className="card details-card" open={!block.collapsed}><summary>{block.title}</summary><dl><dt>{copy.model}</dt><dd>{evidence.model.model_version}</dd><dt>{copy.policy}</dt><dd>{evidence.model.policy_version}</dd><dt>{copy.mode}</dt><dd>{evidence.model.mode}</dd><dt>{copy.context}</dt><dd>{evidence.maintenance_context.provider} · {evidence.maintenance_context.version}</dd><dt>{copy.lineage}</dt><dd>{JSON.stringify(evidence.lineage)}</dd></dl></details>;
    case "ConversationThread":
      return <Card title={block.title}><Conversation onAsk={onAsk} lastFollowUp={lastFollowUp} /></Card>;
    default:
      return <Card title={copy.unsupportedBlock}><p>{copy.unsupportedBlockDetail}</p></Card>;
  }
}
