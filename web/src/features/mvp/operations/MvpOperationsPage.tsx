import { ArrowRight, FileText, MessageSquarePlus, Save, ShieldCheck, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import type {
  MvpBootstrapModel,
  MvpDecision,
  MvpEvent,
  MvpEventDetailModel,
} from "../api/mvpContracts";
import {
  DECISION_LABEL,
  MvpConfidenceBadge,
  MvpPanel,
  MvpProvenanceView,
  MvpState,
  MvpStatusBadge,
  formatMinutes,
  formatProbability,
  formatTimestamp,
} from "../components/MvpUi";

const DECISIONS: MvpDecision[] = [
  "continue_monitoring",
  "request_inspection",
  "review_shutdown",
  "hold_for_data_check",
];

export function MvpOperationsPage({
  model,
  selectedEventId,
  detail,
  detailLoading,
  detailError,
  canDecide,
  canNote,
  onSelectEvent,
  onOpenAsset,
  onOpenReport,
  onDecision,
  onNote,
  onRetryDetail,
}: {
  model: MvpBootstrapModel;
  selectedEventId: string | null;
  detail: MvpEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  canDecide: boolean;
  canNote: boolean;
  onSelectEvent: (event: MvpEvent) => void;
  onOpenAsset: (event: MvpEvent) => void;
  onOpenReport: (event: MvpEvent) => void;
  onDecision: (decision: MvpDecision, note: string) => Promise<void>;
  onNote: (body: string) => Promise<void>;
  onRetryDetail: () => void;
}) {
  const selectedEvent = model.events.find((item) => item.eventId === selectedEventId) ?? null;
  const [decision, setDecision] = useState<MvpDecision>(selectedEvent?.recommendedDecision ?? "request_inspection");
  const [decisionNote, setDecisionNote] = useState("");
  const [fieldNote, setFieldNote] = useState("");
  const [savingDecision, setSavingDecision] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const queue = useMemo(() => model.events.filter((item) => item.recommendedDecision !== "continue_monitoring" || item.status !== "normal"), [model.events]);

  async function saveDecision() {
    setSavingDecision(true);
    setMessage(null);
    try {
      await onDecision(decision, decisionNote);
      setDecisionNote("");
      setMessage({ kind: "success", text: `${DECISION_LABEL[decision]} 기록이 실제 Event API에 저장됐습니다.` });
    } catch (reason) {
      setMessage({ kind: "error", text: reason instanceof Error ? reason.message : "운영 판단 저장에 실패했습니다." });
    } finally {
      setSavingDecision(false);
    }
  }

  async function saveNote() {
    if (!fieldNote.trim()) return;
    setSavingNote(true);
    setMessage(null);
    try {
      await onNote(fieldNote.trim());
      setFieldNote("");
      setMessage({ kind: "success", text: "현장 메모가 실제 Event API에 저장됐습니다." });
    } catch (reason) {
      setMessage({ kind: "error", text: reason instanceof Error ? reason.message : "현장 메모 저장에 실패했습니다." });
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <div className="mvp-page mvp-operations-page" data-testid="mvp-operations">
      <div className="mvp-operations-layout">
        <MvpPanel title={`Event Queue · ${queue.length}`} eyebrow="OPERATIONAL INBOX" className="mvp-operation-queue-panel">
          {queue.length ? <div className="mvp-operation-queue">{queue.map((event) => (
            <button type="button" key={event.eventId} className={event.eventId === selectedEventId ? "is-selected" : ""} onClick={() => { setDecision(event.recommendedDecision); onSelectEvent(event); }}>
              <div><MvpStatusBadge status={event.status} /><strong>{event.assetName}</strong><code>{event.eventId}</code></div>
              <dl><div><dt>위험</dt><dd>{formatProbability(event.failureProbability)}</dd></div><div><dt>영향</dt><dd>{formatMinutes(event.estimatedDowntimeMinutes)}</dd></div></dl>
              <span>{DECISION_LABEL[event.recommendedDecision]}</span>
              <small>{event.assignedEngineer ?? "미배정"}</small>
            </button>
          ))}</div> : <MvpState kind="empty" title="운영 Queue가 비어 있습니다" detail="현재 Dataset Version에서 검토할 위험 Event가 없습니다." />}
        </MvpPanel>

        <section className="mvp-operation-detail">
          {!selectedEvent ? (
            <MvpState kind="empty" title="Event를 선택하세요" detail={selectedEventId ? `요청한 Event ${selectedEventId}를 현재 Dataset Version에서 찾지 못했습니다.` : "Queue에서 Event를 선택하면 근거·Action·Activity를 확인할 수 있습니다."} />
          ) : (
            <>
              <MvpPanel title={selectedEvent.assetName} eyebrow={`EVENT · ${selectedEvent.eventId}`} actions={<><button type="button" className="mvp-button secondary" onClick={() => onOpenAsset(selectedEvent)}><Wrench size={14} />Objects</button><button type="button" className="mvp-button secondary" onClick={() => onOpenReport(selectedEvent)}><FileText size={14} />Report</button></>}>
                <div className="mvp-operation-hero">
                  <div><MvpStatusBadge status={selectedEvent.status} /><MvpConfidenceBadge confidence={selectedEvent.confidence} /></div>
                  <dl><div><dt>고장 확률</dt><dd>{formatProbability(selectedEvent.failureProbability)}</dd></div><div><dt>예상 고장 유형</dt><dd>{selectedEvent.predictedFailureType}</dd></div><div><dt>설비 중요도</dt><dd>{selectedEvent.criticality}</dd></div><div><dt>Downtime</dt><dd>{formatMinutes(selectedEvent.estimatedDowntimeMinutes)}</dd></div><div><dt>담당자</dt><dd>{selectedEvent.assignedEngineer ?? "미배정"}</dd></div><div><dt>부품</dt><dd>{selectedEvent.sparePartAvailable === null ? "확인 필요" : selectedEvent.sparePartAvailable ? "확보" : "미확보"}</dd></div></dl>
                </div>
                {selectedEvent.status === "data_quality_hold" ? <div className="mvp-quality-callout"><strong>추론 억제 상태</strong><p>필수 데이터 품질 검증 전까지 고장 확률과 정지 판단을 확정하지 않습니다. 권장 결정은 데이터 확인 보류입니다.</p></div> : null}
              </MvpPanel>

              {detailLoading ? <MvpPanel title="근거와 Activity" eyebrow="PARTIAL LOADING"><MvpState kind="loading" title="Event 상세 로딩" detail="Evidence, Report, Activity를 독립적으로 확인하고 있습니다." /></MvpPanel> : detailError ? <MvpPanel title="근거와 Activity" eyebrow="ISOLATED ERROR"><MvpState kind="error" title="Event 상세을 불러오지 못했습니다" detail={detailError} onRetry={onRetryDetail} /></MvpPanel> : detail ? (
                <>
                  {detail.warnings.length ? <div className="mvp-inline-warning" role="status"><strong>부분 API 경고</strong><ul>{detail.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}
                  <div className="mvp-operation-evidence-grid">
                    <MvpPanel title="권장 결정과 근거" eyebrow="EVIDENCE">
                      <div className="mvp-recommendation"><span>Policy recommendation</span><strong>{DECISION_LABEL[selectedEvent.recommendedDecision]}</strong><p>모델 결과와 운영 정책을 결합한 추천이며 실제 사용자 결정과 구분됩니다.</p></div>
                      {detail.topFactors.length ? <div className="mvp-factor-list">{detail.topFactors.slice(0, 4).map((factor) => <article key={factor.id}><div><strong>{factor.label}</strong><span>{factor.value ?? "—"} {factor.unit}</span></div><div className="mvp-factor-track"><i style={{ width: `${Math.max(4, Math.min(100, factor.contribution * 100))}%` }} /></div><b>{factor.direction === "risk_up" ? "점검 우선 후보" : "완화 요인"}</b></article>)}</div> : <p className="mvp-muted">Top factor가 제공되지 않았습니다. 원인을 임의로 단정하지 않습니다.</p>}
                      {detail.threshold !== null ? <p className="mvp-threshold-note">현재 운영 임계값 <strong>{formatProbability(detail.threshold)}</strong> · 미탐·오탐 비용 가정에 따라 달라질 수 있습니다.</p> : null}
                    </MvpPanel>

                    <MvpPanel title="판단 기록" eyebrow="GOVERNED ACTION">
                      <div className="mvp-write-status"><ShieldCheck size={16} /><div><strong>{canDecide ? "실제 저장 API 연결" : "읽기 전용"}</strong><span>{canDecide ? "POST /api/events/{event_id}/decision" : "현재 역할에는 events.decision 권한이 없습니다."}</span></div></div>
                      <label className="mvp-field"><span>결정</span><select value={decision} onChange={(event) => setDecision(event.target.value as MvpDecision)} disabled={!canDecide}>{DECISIONS.map((item) => <option key={item} value={item}>{DECISION_LABEL[item]}</option>)}</select></label>
                      <label className="mvp-field"><span>판단 메모</span><textarea value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder="결정 근거와 다음 확인 시점을 기록하세요." disabled={!canDecide} /></label>
                      {decision === "review_shutdown" ? <div className="mvp-safety-note"><strong>자동 정지 아님</strong><span>권한 있는 담당자의 정지 검토를 요청할 뿐 설비 제어 명령을 실행하지 않습니다.</span></div> : null}
                      <button type="button" className="mvp-button primary" onClick={saveDecision} disabled={!canDecide || savingDecision}><Save size={14} />{savingDecision ? "저장 중" : "판단 기록"}</button>
                    </MvpPanel>
                  </div>

                  <div className="mvp-operation-bottom-grid">
                    <MvpPanel title="현장 메모" eyebrow="FIELD NOTE">
                      <div className="mvp-write-status"><MessageSquarePlus size={16} /><div><strong>{canNote ? "실제 저장 API 연결" : "읽기 전용"}</strong><span>{canNote ? "POST /api/events/{event_id}/notes" : "현재 역할에는 events.note 권한이 없습니다."}</span></div></div>
                      <label className="mvp-field"><span>점검 결과 또는 전달 사항</span><textarea value={fieldNote} onChange={(event) => setFieldNote(event.target.value)} placeholder="공구 상태, 센서 확인, 작업 가능 여부를 기록하세요." disabled={!canNote} /></label>
                      <button type="button" className="mvp-button secondary" onClick={saveNote} disabled={!canNote || savingNote || !fieldNote.trim()}><Save size={14} />{savingNote ? "저장 중" : "메모 저장"}</button>
                    </MvpPanel>

                    <MvpPanel title="Activity · Audit" eyebrow="SHARED EVENT HISTORY">
                      {detail.activity.length ? <div className="mvp-activity-list">{detail.activity.map((activity) => <article key={activity.id}><span className={`activity-${activity.kind}`} /><div><strong>{activity.decision ? DECISION_LABEL[activity.decision] : activity.title}</strong><p>{activity.detail || "상세 기록 없음"}</p><small>{activity.actor} · {formatTimestamp(activity.createdAt)}</small></div></article>)}</div> : <MvpState kind="empty" title="기록된 Activity가 없습니다" detail="판단 또는 현장 메모가 저장되면 이 Event 이력에 표시됩니다." />}
                    </MvpPanel>
                  </div>

                  <MvpPanel title="Dataset·Model provenance" eyebrow="TRACEABILITY"><MvpProvenanceView provenance={detail.provenance} /></MvpPanel>
                </>
              ) : null}
              {message ? <div className={`mvp-action-message is-${message.kind}`} role="status"><strong>{message.kind === "success" ? "저장 완료" : "저장 실패"}</strong><span>{message.text}</span></div> : null}
              <button type="button" className="mvp-report-bridge" onClick={() => onOpenReport(selectedEvent)}><div><FileText size={18} /><span>Executive Report 반영</span><strong>동일 Event의 최신 위험·대응 상태로 보고서를 확인합니다.</strong></div><ArrowRight size={17} /></button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
