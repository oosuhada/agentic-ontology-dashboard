import { ArrowRight, CheckCircle2, ClipboardCheck, DatabaseZap, Eye, FileText, MessageSquarePlus, PauseCircle, Save, ShieldAlert, ShieldCheck, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type {
  OperationsBootstrapModel,
  OperationsDecision,
  OperationsEvent,
  OperationsEventDetailModel,
} from "../api/operationsContracts";
import {
  DECISION_LABEL,
  OperationsConfidenceBadge,
  OperationsPanel,
  OperationsState,
  OperationsStatusBadge,
  formatMinutes,
  formatProbability,
  formatTimestamp,
} from "../components/OperationsUi";
import {
  displayDataSource,
  displayEventAssetName,
  displayModelRelease,
  fieldFailureLabel,
} from "../displayLabels";

const DECISION_OPTIONS: Array<{
  decision: OperationsDecision;
  category: string;
  title: string;
  detail: string;
  tone: "calm" | "work" | "warning" | "hold";
  Icon: typeof CheckCircle2;
}> = [
  {
    decision: "request_inspection",
    category: "점검",
    title: DECISION_LABEL.request_inspection,
    detail: "현장 담당자에게 확인 업무를 넘깁니다.",
    tone: "work",
    Icon: ClipboardCheck,
  },
  {
    decision: "hold_for_data_check",
    category: "데이터",
    title: DECISION_LABEL.hold_for_data_check,
    detail: "근거가 부족하면 판단을 보류하고 데이터부터 확인합니다.",
    tone: "hold",
    Icon: DatabaseZap,
  },
  {
    decision: "review_shutdown",
    category: "정지 검토",
    title: DECISION_LABEL.review_shutdown,
    detail: "자동 정지가 아니라 승인권자 검토 안건으로 올립니다.",
    tone: "warning",
    Icon: ShieldAlert,
  },
  {
    decision: "continue_monitoring",
    category: "관찰",
    title: DECISION_LABEL.continue_monitoring,
    detail: "추가 조치 없이 같은 관측 기준으로 계속 봅니다.",
    tone: "calm",
    Icon: PauseCircle,
  },
];

const QUICK_NOTES: Record<OperationsDecision, string[]> = {
  request_inspection: ["현장 점검 요청", "센서와 부품 상태 확인", "교대 전 확인 필요"],
  hold_for_data_check: ["근거 부족으로 보류", "센서 신뢰도 재확인", "데이터 갱신 후 재판단"],
  review_shutdown: ["생산 영향 확인 필요", "승인권자 정지 검토", "안전 확인 후 진행"],
  continue_monitoring: ["추가 조치 없이 관찰", "다음 관측까지 유지", "이상 변화 시 재검토"],
};

const QUEUE_STATUS_WEIGHT: Record<OperationsEvent["status"], number> = {
  critical: 5,
  data_quality_hold: 4,
  warning: 3,
  attention: 2,
  normal: 1,
};

export function OperationsOperationsPage({
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
  model: OperationsBootstrapModel;
  selectedEventId: string | null;
  detail: OperationsEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  canDecide: boolean;
  canNote: boolean;
  onSelectEvent: (event: OperationsEvent) => void;
  onOpenAsset: (event: OperationsEvent) => void;
  onOpenReport: (event: OperationsEvent) => void;
  onDecision: (decision: OperationsDecision, note: string) => Promise<void>;
  onNote: (body: string) => Promise<void>;
  onRetryDetail: () => void;
}) {
  const selectedEvent = model.events.find((item) => item.eventId === selectedEventId) ?? null;
  const [decision, setDecision] = useState<OperationsDecision>(selectedEvent?.recommendedDecision ?? "request_inspection");
  const [decisionNote, setDecisionNote] = useState("");
  const [fieldNote, setFieldNote] = useState("");
  const [savingDecision, setSavingDecision] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const queue = useMemo(() => model.events
    .filter((item) => item.recommendedDecision !== "continue_monitoring" || item.status !== "normal")
    .sort((left, right) => (
      QUEUE_STATUS_WEIGHT[right.status] - QUEUE_STATUS_WEIGHT[left.status]
      || (right.failureProbability ?? -1) - (left.failureProbability ?? -1)
      || String(right.observedAt ?? "").localeCompare(String(left.observedAt ?? ""))
    )), [model.events]);
  const selectedAsset = selectedEvent ? model.assets.find((asset) => asset.assetId === selectedEvent.assetId) ?? null : null;
  const suspectedPart = selectedAsset?.topFactors[0]?.label ?? selectedEvent?.predictedFailureType ?? "부품 근거 없음";
  const latestDecision = detail?.activity.find((activity) => activity.kind === "decision") ?? null;
  const selectedDecisionOption = DECISION_OPTIONS.find((option) => option.decision === decision) ?? DECISION_OPTIONS[0];
  const SelectedDecisionIcon = selectedDecisionOption.Icon;
  const isInspectionRequestDecision = decision === "request_inspection" || decision === "review_shutdown";
  const canSubmitDecision = canDecide && (!isInspectionRequestDecision || Boolean(detail?.snapshotBasis));
  const snapshotBasisFailed = Boolean(
    detail?.warnings.some((warning) => warning.startsWith("설비 상세 조회 지연:")),
  );
  const decisionActionLabel = isInspectionRequestDecision ? "작업요청 생성" : `${DECISION_LABEL[decision]} 기록`;
  const recommendedOption = selectedEvent
    ? DECISION_OPTIONS.find((option) => option.decision === selectedEvent.recommendedDecision) ?? DECISION_OPTIONS[0]
    : DECISION_OPTIONS[0];
  const gapCount = detail?.evidenceGaps.length ?? 0;
  const evidenceStatus = detailLoading
    ? "근거 확인 중"
    : detailError || snapshotBasisFailed
      ? "근거 확인 실패"
      : detail
        ? "근거 연결됨"
        : "근거 대기";
  const limitationStatus = gapCount > 0
    ? `${gapCount}개 확인 필요`
    : detailLoading
      ? "확인 중"
      : "주요 제한 없음";
  const decisionStatus = latestDecision?.decision
    ? DECISION_LABEL[latestDecision.decision]
    : "사람 결정 대기";
  const queueRank = selectedEvent ? queue.findIndex((item) => item.eventId === selectedEvent.eventId) + 1 : 0;
  const nextOwnerLabel = detail?.closedLoop?.primaryAction?.ownerLabel ?? "다음 책임 역할 미확정";
  const nextActionLabel = detail?.closedLoop?.primaryAction?.label ?? DECISION_LABEL[selectedEvent?.recommendedDecision ?? "continue_monitoring"];
  const planningContext = detail?.operationContext ?? null;
  const eventImpact = planningContext?.eventImpact ?? null;
  const plannedUnits = planningContext?.productionPlan?.plannedUnits ?? null;
  const estimatedLostUnits = eventImpact?.estimatedLostUnits ?? null;
  const estimatedDowntime = eventImpact?.basis.estimatedDowntimeMinutes ?? selectedEvent?.estimatedDowntimeMinutes ?? null;

  useEffect(() => {
    if (!selectedEvent) return;
    setDecision(selectedEvent.recommendedDecision);
    setDecisionNote("");
  }, [selectedEvent?.eventId, selectedEvent?.recommendedDecision]);

  async function saveDecision() {
    if (isInspectionRequestDecision && !detail?.snapshotBasis) {
      setMessage({ kind: "error", text: "현재 화면 기준 근거가 아직 로드되지 않아 작업요청을 생성할 수 없습니다." });
      return;
    }
    setSavingDecision(true);
    setMessage(null);
    try {
      await onDecision(decision, decisionNote);
      setDecisionNote("");
      setMessage({
        kind: "success",
        text: isInspectionRequestDecision
          ? "현재 화면 근거 기준으로 점검 작업요청이 생성됐습니다."
          : `${DECISION_LABEL[decision]} 기록이 저장됐습니다.`,
      });
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
      setMessage({ kind: "success", text: "현장 메모가 저장됐습니다." });
    } catch (reason) {
      setMessage({ kind: "error", text: reason instanceof Error ? reason.message : "현장 메모 저장에 실패했습니다." });
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <div className="operations-page operations-operations-page" data-testid="operations-operations">
      <div className="operations-operations-layout">
        <OperationsPanel title={`작업요청 후보 · ${queue.length}`} eyebrow="작업요청 대기열" className="operations-operation-queue-panel">
          {queue.length ? <div className="operations-operation-queue">{queue.map((event) => (
            <button type="button" key={event.eventId} className={event.eventId === selectedEventId ? "is-selected" : ""} onClick={() => { setDecision(event.recommendedDecision); onSelectEvent(event); }}>
              <div><OperationsStatusBadge status={event.status} /><strong>{displayEventAssetName(event)}</strong><span>관측 {formatTimestamp(event.observedAt)}</span></div>
              <dl><div><dt>위험</dt><dd>{formatProbability(event.failureProbability)}</dd></div><div><dt>영향</dt><dd>{formatMinutes(event.estimatedDowntimeMinutes)}</dd></div></dl>
              <span>{DECISION_LABEL[event.recommendedDecision]} · Decision Case</span>
              <small>{event.assignedEngineer ?? "미배정"}</small>
            </button>
          ))}</div> : <OperationsState kind="empty" title="처리할 작업 후보가 없습니다" detail="현재 관측 기준으로 작업요청 후보가 필요한 이벤트가 없습니다." />}
        </OperationsPanel>

        <section className="operations-operation-detail">
          {!selectedEvent ? (
            <OperationsState kind="empty" title="작업요청 후보를 선택하세요" detail={selectedEventId ? "요청한 과거 Case를 현재 데이터에서 찾지 못했습니다. 목록에서 다른 Case를 선택해 주세요." : "왼쪽 큐에서 후보를 선택하면 관련 설비, 근거, 허용된 기록 액션을 확인할 수 있습니다."} />
          ) : (
            <>
              <OperationsPanel title={displayEventAssetName(selectedEvent)} eyebrow={`작업요청 후보 · 관측 ${formatTimestamp(selectedEvent.observedAt)}`} actions={<><button type="button" className="operations-button secondary" onClick={() => onOpenAsset(selectedEvent)}><Wrench size={14} />설비 보기</button><button type="button" className="operations-button secondary" onClick={() => onOpenReport(selectedEvent)}><FileText size={14} />보고서 보기</button></>}>
                <section className="operations-manager-impact-strip" aria-label="생산 영향과 판단 기준">
                  <article><span>생산 계획</span><strong>{plannedUnits === null ? "-" : `${plannedUnits.toLocaleString()}개`}</strong><small>{planningContext?.productionPlan?.planDate ?? "계획 데이터 확인 중"}</small></article>
                  <article><span>제품 / 라인</span><strong>{eventImpact?.productVariant ?? "-"}</strong><small>{eventImpact?.line ?? selectedEvent.line}</small></article>
                  <article className="is-critical"><span>예상 계획 영향</span><strong>{estimatedLostUnits === null ? "-" : `${estimatedLostUnits.toLocaleString()}개`}</strong><small>{planningContext?.productionImpact ?? "영향 확인 필요"}</small></article>
                  <article><span>예상 정지</span><strong>{formatMinutes(estimatedDowntime)}</strong><small>Decision Case 기준</small></article>
                </section>
                <div className="operations-guided-action">
                  <div>
                    <span>{queueRank > 0 ? `DECISION CASE · 우선순위 #${queueRank}` : "DECISION CASE"}</span>
                    <strong>{recommendedOption.title}</strong>
                    <p>{snapshotBasisFailed
                      ? "현재 선택한 예측의 정본 근거를 불러오지 못했습니다. 상세 조회를 다시 시도하세요."
                      : gapCount > 0
                        ? `${gapCount}개 제한을 확인한 뒤 기록하세요.`
                        : "현재 Product Result/Evidence snapshot과 생산 영향 근거를 함께 확인한 뒤 판단을 기록합니다."}</p>
                  </div>
                  <div>
                    {canDecide ? (
                      <button type="button" className="operations-button primary" onClick={saveDecision} disabled={!canSubmitDecision || savingDecision}>
                        <Save size={14} />{savingDecision ? "처리 중" : decisionActionLabel}
                      </button>
                    ) : (
                      <button type="button" className="operations-button primary" onClick={() => onOpenAsset(selectedEvent)}><Eye size={14} />근거 확인</button>
                    )}
                    <button type="button" className="operations-button secondary" onClick={() => onOpenReport(selectedEvent)}><FileText size={14} />보고서 보기</button>
                  </div>
                </div>
                <section className="operations-decision-routing" aria-label="Decision Case 책임과 다음 액션">
                  <div><span>현재 담당</span><strong>{selectedEvent.assignedEngineer ?? "미배정"}</strong><small>현재 기록된 owner</small></div>
                  <div><span>검토 우선순위</span><strong>{detail?.reviewPriority?.level ?? selectedEvent.status}</strong><small>위험·운영 맥락 기반</small></div>
                  <div><span>다음 책임 역할</span><strong>{nextOwnerLabel}</strong><small>Backend Closed-loop policy</small></div>
                  <div><span>다음 허용 액션</span><strong>{nextActionLabel}</strong><small>가짜 배정/우선순위 변경 없음</small></div>
                </section>
                <div className="operations-operation-hero">
                  <div><OperationsStatusBadge status={selectedEvent.status} /><OperationsConfidenceBadge confidence={selectedEvent.confidence} /></div>
                  <dl><div><dt>대상 설비</dt><dd>{displayEventAssetName(selectedEvent)}</dd></div><div><dt>의심 부품</dt><dd>{suspectedPart}</dd></div><div><dt>고장 확률</dt><dd>{formatProbability(selectedEvent.failureProbability)}</dd></div><div><dt>추천 상태</dt><dd>{DECISION_LABEL[selectedEvent.recommendedDecision]}</dd></div><div><dt>최근 사람 결정</dt><dd>{latestDecision?.decision ? DECISION_LABEL[latestDecision.decision] : "기록 없음"}</dd></div><div><dt>담당자</dt><dd>{selectedEvent.assignedEngineer ?? "미배정"}</dd></div><div><dt>부품</dt><dd>{selectedEvent.sparePartAvailable === null ? "확인 필요" : selectedEvent.sparePartAvailable ? "확보" : "미확보"}</dd></div></dl>
                </div>
                <section className="operations-always-action" aria-label="현재 허용된 작업">
                  <header><span>Allowed Action</span><strong>{canDecide ? "판단 기록 가능" : "읽기 전용"}</strong></header>
                  <div className="operations-action-row">
                    <button type="button" className="operations-button primary" onClick={saveDecision} disabled={!canSubmitDecision || savingDecision}><Save size={14} />{savingDecision ? "처리 중" : decisionActionLabel}</button>
                    <button type="button" className="operations-button secondary" onClick={() => onOpenAsset(selectedEvent)}><Wrench size={14} />Asset 근거</button>
                    <button type="button" className="operations-button ghost" onClick={() => onOpenReport(selectedEvent)}><FileText size={14} />Report</button>
                  </div>
                </section>
                <ol className="operations-decision-flow" aria-label="업무 진행 상태">
                  <li className={detailError || snapshotBasisFailed ? "is-warning" : "is-complete"}><span>1</span><div><strong>{evidenceStatus}</strong><small>근거 확인</small></div></li>
                  <li className={gapCount > 0 ? "is-warning" : "is-complete"}><span>2</span><div><strong>{limitationStatus}</strong><small>제한 확인</small></div></li>
                  <li className={latestDecision ? "is-complete" : "is-current"}><span>3</span><div><strong>{decisionStatus}</strong><small>판단 기록</small></div></li>
                </ol>
                {selectedEvent.status === "data_quality_hold" ? <div className="operations-quality-callout"><strong>추론 억제 상태</strong><p>필수 데이터 품질 검증 전까지 고장 확률과 정지 판단을 확정하지 않습니다. 권장 결정은 데이터 확인 보류입니다.</p></div> : null}
              </OperationsPanel>

              {detailLoading ? <OperationsPanel title="업무 상세" eyebrow="LOADING"><OperationsState kind="loading" title="업무 상세 로딩" detail="선택 업무의 근거, 보고서, 활동 이력을 확인하고 있습니다." /></OperationsPanel> : detailError ? <OperationsPanel title="업무 상세" eyebrow="ERROR"><OperationsState kind="error" title="업무 상세를 불러오지 못했습니다" detail={detailError} onRetry={onRetryDetail} /></OperationsPanel> : detail ? (
                <>
                  {detail.warnings.length ? <div className="operations-inline-warning" role="status"><strong>부분 연결 경고</strong><ul>{detail.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}
                  <div className="operations-operation-evidence-grid">
                    <OperationsPanel title="Allowed Action" eyebrow="사람 기록">
                      <div className="operations-recommendation"><span>추천</span><strong>{DECISION_LABEL[selectedEvent.recommendedDecision]}</strong><p>버튼 하나를 고르면 아래 기록 액션에 바로 반영됩니다.</p></div>
                      <dl className="operations-inspector-summary">
                        <div><dt>검토 우선순위</dt><dd>{detail.reviewPriority?.level ?? "확인 필요"}</dd></div>
                        <div><dt>중요도</dt><dd>{detail.assetCriticality ?? "확인 필요"}</dd></div>
                        <div><dt>생산 영향</dt><dd>{detail.operationContext?.productionImpact ?? "확인 필요"}{estimatedLostUnits !== null ? ` · 약 ${estimatedLostUnits.toLocaleString()}개` : ""}</dd></div>
                        <div><dt>열린 작업</dt><dd>{detail.maintenanceContext?.openWorkOrderExists === null || detail.maintenanceContext?.openWorkOrderExists === undefined ? "확인 필요" : detail.maintenanceContext.openWorkOrderExists ? "있음" : "없음"}</dd></div>
                      </dl>
                      {detail.reviewPriority?.reasons.length ? <p className="operations-threshold-note">{detail.reviewPriority.reasons.join(" · ")}</p> : <p className="operations-threshold-note">필수 맥락이 없으면 Operations가 우선순위를 임의 계산하지 않습니다.</p>}
                      <div className="operations-decision-option-grid" role="radiogroup" aria-label="판단 종류">
                        {DECISION_OPTIONS.map((option) => {
                          const Icon = option.Icon;
                          return (
                            <button
                              type="button"
                              key={option.decision}
                              className={`operations-decision-option tone-${option.tone}${decision === option.decision ? " is-selected" : ""}`}
                              onClick={() => setDecision(option.decision)}
                              aria-checked={decision === option.decision}
                              role="radio"
                              disabled={!canDecide}
                            >
                              <Icon size={17} />
                              <span>{option.category}</span>
                              <strong>{option.title}</strong>
                              <small>{option.detail}</small>
                            </button>
                          );
                        })}
                      </div>
                    </OperationsPanel>

                    <OperationsPanel title="작업요청 맥락" eyebrow="관련 설비와 근거">
                      <dl className="operations-sensor-grid">
                        <div><dt>근거 Snapshot</dt><dd>{detail.snapshotBasis?.artifactId ? "연결됨" : "확인 필요"}</dd></div>
                        <div><dt>작업 상태</dt><dd>{detail.closedLoop?.lifecycleSummary?.currentStepLabel ?? "판단 대기"}</dd></div>
                        <div><dt>위험</dt><dd>{formatProbability(selectedEvent.failureProbability)} · {fieldFailureLabel(selectedEvent.predictedFailureType)}</dd></div>
                        <div><dt>운영 영향</dt><dd>{selectedEvent.criticality ?? "중요도 근거 부족"} · {formatMinutes(selectedEvent.estimatedDowntimeMinutes)}</dd></div>
                        <div><dt>결정 전 확인</dt><dd>{detail.evidenceGaps.length ? `${detail.evidenceGaps.length}개 항목 확인 필요` : detail.threshold === null ? "임계값 근거 부족" : `임계값 ${formatProbability(detail.threshold)}`}</dd></div>
                        <div><dt>상세 근거</dt><dd><button type="button" className="operations-link-button" onClick={() => onOpenAsset(selectedEvent)}>전체 근거 보기</button></dd></div>
                      </dl>
                      {detail.evidenceGaps.length ? <ul className="operations-gap-list">{detail.evidenceGaps.slice(0, 3).map((gap) => <li key={`${gap.ownerDomain}-${gap.field}`}><strong>{gap.field}</strong><span>{gap.ownerDomain} · {gap.reason}</span></li>)}</ul> : null}
                    </OperationsPanel>

                    <OperationsPanel title="기록하기" eyebrow="사람 판단">
                      <div className="operations-write-status"><ShieldCheck size={16} /><div><strong>{canSubmitDecision ? (isInspectionRequestDecision ? "작업요청 생성 가능" : "결정 기록 가능") : "읽기 전용"}</strong><span>{!canDecide ? "현재 역할에는 결정 기록 권한이 없습니다." : isInspectionRequestDecision && !detail.snapshotBasis ? "현재 화면 기준 근거를 불러온 뒤 작업요청을 생성할 수 있습니다." : isInspectionRequestDecision ? "현재 화면 근거 기준으로 점검 작업요청을 생성합니다." : "현재 역할로 이 업무의 결정을 남길 수 있습니다."}</span></div></div>
                      <div className={`operations-selected-decision tone-${selectedDecisionOption.tone}`}>
                        <SelectedDecisionIcon size={18} />
                        <div><span>선택한 판단</span><strong>{selectedDecisionOption.title}</strong><small>{selectedDecisionOption.detail}</small></div>
                      </div>
                      <div className="operations-quick-note-list" aria-label="빠른 메모">
                        {QUICK_NOTES[decision].map((note) => (
                          <button type="button" key={note} onClick={() => setDecisionNote(note)} disabled={!canDecide} className={decisionNote === note ? "is-selected" : ""}>{note}</button>
                        ))}
                      </div>
                      <label className="operations-field"><span>추가 메모 선택 입력</span><textarea value={decisionNote} onChange={(event) => setDecisionNote(event.target.value)} placeholder="필요할 때만 짧게 남기세요." disabled={!canDecide} /></label>
                      {decision === "review_shutdown" ? <div className="operations-safety-note"><strong>자동 정지 아님</strong><span>권한 있는 담당자의 정지 검토를 요청할 뿐 설비 제어 명령을 실행하지 않습니다.</span></div> : null}
                      <button type="button" className="operations-button primary operations-wide-action" onClick={saveDecision} disabled={!canSubmitDecision || savingDecision}><Save size={14} />{savingDecision ? "처리 중" : isInspectionRequestDecision ? "점검 작업요청 생성" : `${selectedDecisionOption.title} 기록하기`}</button>
                    </OperationsPanel>
                  </div>

                  <div className="operations-operation-bottom-grid">
                    <OperationsPanel title="현장 메모" eyebrow="FIELD NOTE">
                      <div className="operations-write-status"><MessageSquarePlus size={16} /><div><strong>{canNote ? "메모 기록 가능" : "읽기 전용"}</strong><span>{canNote ? "현장 확인 내용과 전달 사항을 남길 수 있습니다." : "현재 역할에는 메모 작성 권한이 없습니다."}</span></div></div>
                      <label className="operations-field"><span>점검 결과 또는 전달 사항</span><textarea value={fieldNote} onChange={(event) => setFieldNote(event.target.value)} placeholder="공구 상태, 센서 확인, 작업 가능 여부를 기록하세요." disabled={!canNote} /></label>
                      <button type="button" className="operations-button secondary" onClick={saveNote} disabled={!canNote || savingNote || !fieldNote.trim()}><Save size={14} />{savingNote ? "저장 중" : "메모 저장"}</button>
                    </OperationsPanel>

                    <OperationsPanel title="Activity · Audit" eyebrow="SHARED EVENT HISTORY">
                      {detail.activity.length ? <div className="operations-activity-list">{detail.activity.map((activity) => <article key={activity.id}><span className={`activity-${activity.kind}`} /><div><strong>{activity.decision ? DECISION_LABEL[activity.decision] : activity.title}</strong><p>{activity.detail || "상세 기록 없음"}</p><small>{activity.actor} · {formatTimestamp(activity.createdAt)}</small></div></article>)}</div> : <OperationsState kind="empty" title="기록된 작업 이력이 없습니다" detail="판단 또는 현장 메모가 저장되면 이 이벤트 이력에 표시됩니다." />}
                    </OperationsPanel>
                  </div>

                  <OperationsPanel title="근거 위치" eyebrow="TRACEABILITY"><p className="operations-muted">{displayDataSource(detail.provenance.sourceVersion)}와 {displayModelRelease(detail.provenance.modelVersion)}를 기준으로 작성했습니다. 자세한 센서, 판단 근거, 기술 출처는 전체 근거 화면에서 확인합니다.</p></OperationsPanel>
                </>
              ) : null}
              {message ? <div className={`operations-action-message is-${message.kind}`} role="status"><strong>{message.kind === "success" ? "저장 완료" : "저장 실패"}</strong><span>{message.text}</span></div> : null}
              <button type="button" className="operations-report-bridge" onClick={() => onOpenReport(selectedEvent)}><div><FileText size={18} /><span>보고서 보기</span><strong>같은 관측 시점의 위험, 제한, 대응 상태를 공유용 문서로 확인합니다.</strong></div><ArrowRight size={17} /></button>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
