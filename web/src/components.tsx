import { FormEvent, useMemo, useState } from "react";
import type { Evidence, EventSummary, FollowUp, Report, Role, UIBlock } from "./types";

const STATUS_LABEL: Record<string, string> = {
  normal: "정상",
  attention: "관심",
  warning: "경고",
  critical: "긴급 검토",
  data_quality_hold: "데이터 확인",
};

const DECISION_LABEL: Record<string, string> = {
  continue_monitoring: "계속 모니터링",
  request_inspection: "현장 점검 요청",
  review_shutdown: "정지 여부 검토",
  hold_for_data_check: "데이터 확인 전 보류",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABEL[status] ?? status}</span>;
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
  const valid = values.filter((value): value is number => value !== null);
  if (!valid.length) return <div className="empty-state">표시할 유효 데이터가 없습니다.</div>;
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
      <svg viewBox="0 0 300 110" role="img" aria-label={`${label} 시계열`}>
        <line x1="20" x2="280" y1="92" y2="92" className="axis" />
        <polyline points={points} className="trend-line" fill="none" />
        {points.split(" ").map((point, index) => {
          const [cx, cy] = point.split(",");
          return <circle key={`${point}-${index}`} cx={cx} cy={cy} r="3" className="trend-dot" />;
        })}
      </svg>
      <small>범위 {minimum.toFixed(1)}–{maximum.toFixed(1)} {unit}</small>
    </div>
  );
}

function PriorityList({ events, selected, onSelect }: { events: EventSummary[]; selected: string; onSelect: (id: string) => void }) {
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
            <small>{event.equipment.line} · {event.predicted_failure_type}</small>
          </span>
          <StatusBadge status={event.status} />
          <strong>{event.failure_probability === null ? "—" : `${(event.failure_probability * 100).toFixed(1)}%`}</strong>
        </button>
      ))}
    </div>
  );
}

function DecisionCard({ evidence, onDecision }: { evidence: Evidence; onDecision: (decision: string, note: string) => Promise<void> }) {
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState("");
  async function submit(decision: string) {
    await onDecision(decision, note);
    setSaved(`${DECISION_LABEL[decision]} 기록 완료`);
  }
  const options = ["continue_monitoring", "request_inspection", "review_shutdown", "hold_for_data_check"];
  return (
    <div>
      <div className="decision-recommendation">
        <span>시스템 권장</span>
        <strong>{DECISION_LABEL[evidence.recommended_decision]}</strong>
        <small>실제 설비 제어가 아닌 사람의 판단을 위한 권고입니다.</small>
      </div>
      <label className="field-label">
        전달 메모
        <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="담당 엔지니어와 기한을 기록하세요." />
      </label>
      <div className="button-row">
        {options.map((option) => (
          <button key={option} className={option === evidence.recommended_decision ? "primary" : "secondary"} onClick={() => submit(option)}>
            {DECISION_LABEL[option]}
          </button>
        ))}
      </div>
      {saved ? <p className="success-message" role="status">{saved}</p> : null}
    </div>
  );
}

function Checklist({ evidence, onNote }: { evidence: Evidence; onNote: (body: string) => Promise<void> }) {
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  const [memo, setMemo] = useState("");
  const [saved, setSaved] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const completed = evidence.maintenance_context.checklist.filter((_, index) => checked[index]);
    await onNote(`점검 완료: ${completed.join(", ") || "없음"}. 메모: ${memo || "없음"}`);
    setSaved(true);
  }
  return (
    <form onSubmit={submit}>
      <ul className="checklist">
        {evidence.maintenance_context.checklist.map((item, index) => (
          <li key={item}>
            <label>
              <input type="checkbox" checked={Boolean(checked[index])} onChange={(event) => setChecked({ ...checked, [index]: event.target.checked })} />
              <span>{item}</span>
            </label>
          </li>
        ))}
      </ul>
      <label className="field-label">
        현장 메모
        <textarea value={memo} onChange={(event) => setMemo(event.target.value)} placeholder="관찰 내용과 다음 조치를 기록하세요." />
      </label>
      <button className="primary" type="submit">점검 기록 저장</button>
      {saved ? <p className="success-message" role="status">점검 기록이 저장됐습니다.</p> : null}
    </form>
  );
}

function ReadOnlyAction({ message }: { message: string }) {
  return <div className="read-only-action"><strong>조회 전용</strong><p>{message}</p></div>;
}

function Conversation({ onAsk, lastFollowUp }: { onAsk: (question: string) => Promise<void>; lastFollowUp: FollowUp | null }) {
  const [question, setQuestion] = useState("");
  const examples = ["왜 위험한가?", "정상 설비와 비교해줘.", "매니저용으로 짧게 요약해줘.", "무엇을 먼저 점검해야 하는가?", "모델 상세를 보여줘."];
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
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="현재 Evidence 범위에서 질문하세요." aria-label="후속 질문" />
        <button className="primary" type="submit">질문</button>
      </form>
      {lastFollowUp ? (
        <div className={`conversation-answer ${lastFollowUp.supported ? "" : "unsupported"}`}>
          <strong>{lastFollowUp.supported ? "답변" : "지원 범위 안내"}</strong>
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
  const probability = evidence.failure_probability === null ? "산출 안 함" : `${(evidence.failure_probability * 100).toFixed(1)}%`;
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
          <div className="source-line">Evidence {evidence.evidence_id} · {report.mode}</div>
        </Card>
      );
    case "RiskKpi":
      return (
        <Card title={block.title}>
          <div className="metric-grid">
            <Metric label="고장 위험도" value={probability} hint={`표시 임계값 ${(evidence.threshold * 100).toFixed(0)}%`} />
            <Metric label="신뢰도" value={evidence.confidence} />
            <Metric label="설비 중요도" value={evidence.equipment.criticality} />
            <Metric label="권장 결정" value={DECISION_LABEL[evidence.recommended_decision]} />
          </div>
        </Card>
      );
    case "ImpactSummary":
      return (
        <Card title={block.title}>
          <div className="metric-grid compact">
            <Metric label="예상 정지 영향" value={`${evidence.equipment.estimated_downtime_minutes}분`} hint="fixture 기반 추정치" />
            <Metric label="담당 엔지니어" value={evidence.equipment.assigned_engineer} />
            <Metric label="예비 부품" value={evidence.equipment.spare_part_available ? "확보" : "미확보"} />
            <Metric label="최근 정비" value={evidence.equipment.last_maintenance_date} />
          </div>
        </Card>
      );
    case "ManagerDecisionCard":
      return (
        <Card title={block.title}>
          {canRecordDecision ? (
            <DecisionCard evidence={evidence} onDecision={onDecision} />
          ) : (
            <ReadOnlyAction message="현재 역할은 운영 판단을 조회할 수 있지만 새 판단을 기록할 수 없습니다." />
          )}
        </Card>
      );
    case "SensorLineChart":
      return (
        <Card title={block.title}>
          <div className="chart-grid">
            <MiniLine label="공구 마모" unit="min" values={history.map((item) => item.tool_wear_min)} />
            <MiniLine label="토크" unit="N·m" values={history.map((item) => item.torque_nm)} />
            <MiniLine label="공정 온도" unit="K" values={history.map((item) => item.process_temperature_k)} />
            <MiniLine label="회전 속도" unit="rpm" values={history.map((item) => item.rotational_speed_rpm)} />
          </div>
        </Card>
      );
    case "AnomalyTimeline":
      return (
        <Card title={block.title}>
          <div className="timeline">
            <div><span>시작</span><strong>{evidence.detected_interval.start}</strong></div>
            <div><span>현재</span><strong>{evidence.detected_interval.end}</strong></div>
            <div><span>상태</span><StatusBadge status={evidence.status} /></div>
          </div>
        </Card>
      );
    case "FactorContribution":
      return (
        <Card title={block.title}>
          <div className="factor-list">
            {evidence.top_factors.map((factor) => (
              <div className="factor-row" key={factor.evidence_field_id}>
                <div><strong>{factor.display_name}</strong><small>{factor.value.toLocaleString()} {factor.unit} · 참고 {factor.normal_range}</small></div>
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
          <div className="table-scroll"><table><thead><tr><th>근거</th><th>값</th><th>참고 범위</th><th>방향</th><th>출처</th></tr></thead><tbody>
            {evidence.top_factors.map((factor) => <tr key={factor.evidence_field_id}><td>{factor.display_name}</td><td>{factor.value.toLocaleString()} {factor.unit}</td><td>{factor.normal_range}</td><td>{factor.direction === "risk_up" ? "위험 증가" : "위험 감소"}</td><td>{factor.source_type}</td></tr>)}
          </tbody></table></div>
        </Card>
      );
    case "RecommendedActions":
      return <Card title={block.title}><ol className="action-list">{report.actions.map((action) => <li key={action.action_id}><strong>{action.label}</strong><small>{action.requires_human_approval ? "사람 승인 필요" : "자동"} · {action.source_refs.join(", ") || "Evidence 정책"}</small></li>)}</ol></Card>;
    case "EngineerChecklist":
      return (
        <Card title={block.title}>
          {canRecordNote ? (
            <Checklist evidence={evidence} onNote={onNote} />
          ) : (
            <>
              <ul className="checklist read-only-checklist">
                {evidence.maintenance_context.checklist.map((item) => <li key={item}>{item}</li>)}
              </ul>
              <ReadOnlyAction message="현재 역할은 체크리스트를 검토할 수 있지만 점검 기록을 저장할 수 없습니다." />
            </>
          )}
        </Card>
      );
    case "DataQualityWarning":
      return (
        <Card title={block.title} className="warning-card">
          {evidence.data_quality_warnings.length ? (
            <>
              <ul>{evidence.data_quality_warnings.map((warning) => <li key={`${warning.code}-${warning.field}`}><strong>{warning.field}</strong> — {warning.message}</li>)}</ul>
              <p>유효한 값으로 다시 검증하기 전 정상 또는 고장으로 단정하지 않습니다.</p>
            </>
          ) : (
            <>
              <p>센서 값은 유효하지만 위험 근거가 경계 수준이거나 서로 충돌해 신뢰도가 낮습니다.</p>
              <p>추가 관측과 간단 현장 확인 전 고장 원인이나 정지 필요성을 확정하지 않습니다.</p>
            </>
          )}
        </Card>
      );
    case "ModelDetails":
      return <details className="card details-card" open={!block.collapsed}><summary>{block.title}</summary><dl><dt>모델</dt><dd>{evidence.model.model_version}</dd><dt>정책</dt><dd>{evidence.model.policy_version}</dd><dt>모드</dt><dd>{evidence.model.mode}</dd><dt>Context</dt><dd>{evidence.maintenance_context.provider} · {evidence.maintenance_context.version}</dd><dt>Lineage</dt><dd>{JSON.stringify(evidence.lineage)}</dd></dl></details>;
    case "ConversationThread":
      return <Card title={block.title}><Conversation onAsk={onAsk} lastFollowUp={lastFollowUp} /></Card>;
    default:
      return <Card title="지원하지 않는 블록"><p>등록되지 않은 블록은 렌더링하지 않습니다.</p></Card>;
  }
}
