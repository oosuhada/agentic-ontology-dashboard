import { ArrowLeft, Bot, Clock3, Printer, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { createOperationsAgentReviewSummary, getOperationsAgentReviewSummary } from "../../../api";
import type {
  OperationsAgentReviewSummaryResponse,
  OperationsBootstrapModel,
  OperationsEvent,
  OperationsEventDetailModel,
} from "../api/operationsContracts";
import {
  DECISION_LABEL,
  CONFIDENCE_LABEL,
  OperationsProvenanceView,
  OperationsState,
  OperationsStatusBadge,
  formatMinutes,
  formatProbability,
  formatTimestamp,
} from "../components/OperationsUi";
import {
  displayAssetName,
  displayAssignee,
  displayCriticality,
  displayEventAssetName,
  displayLineLabel,
  displayReviewPriority,
  fieldFactorItem,
  fieldFailureLabel,
  humanizeOperationalText,
} from "../displayLabels";

function reportAgentSummaryStatusLabel(payload: OperationsAgentReviewSummaryResponse | null): string {
  if (payload?.summary?.mode === "llm") return "근거 연결 완료";
  if (payload?.summary) return "운영 데이터 기반";
  return "현재 데이터 기반";
}

function selectedDecisionHeadline(event: OperationsEvent): string {
  if (event.status === "data_quality_hold") return `${displayEventAssetName(event)}의 데이터 확인이 필요합니다.`;
  if (event.recommendedDecision === "review_shutdown") return `${displayEventAssetName(event)}의 운전 지속 여부를 검토해야 합니다.`;
  if (event.recommendedDecision === "request_inspection") return `${displayEventAssetName(event)}의 현장 점검이 필요합니다.`;
  return `${displayEventAssetName(event)}은 현재 관찰 대상입니다.`;
}

function evidenceGapMessage(field: string): string | null {
  if (field.includes("production_impact")) return "생산 영향 데이터가 아직 연결되지 않아 영향 수준은 별도로 확인해야 합니다.";
  if (field.includes("history.points")) return "장기 센서 추세 데이터가 아직 연결되지 않아 현재 관측값 중심으로 판단합니다.";
  if (field.includes("equipment_history")) return "설비 작업 이력의 일부가 현재 보고 범위에 포함되지 않았습니다.";
  if (field.includes("maintenance_context")) return "최근 정비 맥락 중 일부 항목은 추가 확인이 필요합니다.";
  if (field.includes("review_priority")) return "검토 우선순위 산정에 필요한 일부 운영 정보가 아직 연결되지 않았습니다.";
  return null;
}

interface ExecutiveBriefSnapshot {
  schemaVersion: "executive-brief-snapshot-v1";
  snapshotId: string;
  artifactId: string;
  asOf: string;
  generatedAt: string;
  contextObservedAt: string | null;
  model: OperationsBootstrapModel;
  event: OperationsEvent;
  detail: OperationsEventDetailModel;
  agentSummary: OperationsAgentReviewSummaryResponse["summary"];
}

export function executiveBriefIsStale(input: {
  snapshotEventId: string;
  snapshotAssetId: string;
  snapshotContextObservedAt: string | null;
  selectedEventId: string | null;
  selectedAssetId: string | null;
  currentContextObservedAt: string | null;
}): boolean {
  const newerEventForSameAsset = Boolean(
    input.selectedEventId
    && input.selectedAssetId === input.snapshotAssetId
    && input.selectedEventId !== input.snapshotEventId,
  );
  const newerMonitoringObservation = Boolean(
    input.currentContextObservedAt
    && input.snapshotContextObservedAt
    && input.currentContextObservedAt > input.snapshotContextObservedAt,
  );
  return newerEventForSameAsset || newerMonitoringObservation;
}

function snapshotStorageKey(userScope: string, projectId: string): string {
  return `ontology-dashboard:executive-brief:${userScope}:${projectId}`;
}

function readSnapshot(key: string): ExecutiveBriefSnapshot | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ExecutiveBriefSnapshot;
    return parsed?.schemaVersion === "executive-brief-snapshot-v1" ? parsed : null;
  } catch {
    return null;
  }
}

function persistSnapshot(key: string, snapshot: ExecutiveBriefSnapshot): void {
  try {
    window.sessionStorage.setItem(key, JSON.stringify(snapshot));
  } catch {
    // The report remains usable in memory if browser storage is unavailable.
  }
}

function createSnapshot(
  model: OperationsBootstrapModel,
  event: OperationsEvent,
  detail: OperationsEventDetailModel,
  agentSummary: OperationsAgentReviewSummaryResponse["summary"],
): ExecutiveBriefSnapshot {
  const generatedAt = new Date().toISOString();
  const asOf = detail.report.asOf ?? detail.snapshotBasis?.observedAt ?? event.observedAt ?? model.context.observedAt ?? generatedAt;
  const artifactId = detail.report.artifactId ?? detail.snapshotBasis?.artifactId ?? event.eventId;
  const snapshotId = detail.report.snapshotId
    ?? detail.operationContext?.temporalScope?.snapshotId
    ?? `brief:${artifactId}`;
  return {
    schemaVersion: "executive-brief-snapshot-v1",
    snapshotId,
    artifactId,
    asOf,
    generatedAt,
    contextObservedAt: model.context.observedAt,
    model,
    event,
    detail: {
      ...detail,
      report: {
        ...detail.report,
        snapshotId,
        artifactId,
        asOf,
        generatedAt,
      },
    },
    agentSummary,
  };
}

function shortRef(value: string): string {
  return value.length > 34 ? `${value.slice(0, 31)}…` : value;
}

export function OperationsExecutiveReportPage({
  model,
  selectedEvent,
  detail,
  detailLoading,
  detailError,
  canMaterializeAgentSummary,
  userScope,
  onBackToOverview,
  onRetryDetail,
}: {
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  canMaterializeAgentSummary: boolean;
  userScope: string;
  onBackToOverview: () => void;
  onOpenOperations: (event: OperationsEvent) => void;
  onRetryDetail: () => void;
}) {
  const [agentSummary, setAgentSummary] = useState<OperationsAgentReviewSummaryResponse | null>(null);
  const [agentSummaryLoading, setAgentSummaryLoading] = useState(false);
  const [agentSummaryError, setAgentSummaryError] = useState<string | null>(null);
  const storageKey = snapshotStorageKey(userScope, model.context.projectId);
  const [snapshot, setSnapshot] = useState<ExecutiveBriefSnapshot | null>(() => readSnapshot(storageKey));

  useEffect(() => {
    if (!selectedEvent) {
      setAgentSummary(null);
      setAgentSummaryError(null);
      setAgentSummaryLoading(false);
      return;
    }
    let cancelled = false;
    setAgentSummaryLoading(true);
    setAgentSummaryError(null);
    const request = {
      assetId: selectedEvent.assetId,
      projectId: model.context.projectId,
      datasetVersionId: model.context.datasetVersionId,
      eventId: selectedEvent.eventId,
    };
    getOperationsAgentReviewSummary(request)
      .then((payload) => {
        if (payload.summary || !canMaterializeAgentSummary) return payload;
        return createOperationsAgentReviewSummary({ ...request, trigger: "ui_manual_regeneration" });
      })
      .then((payload) => !cancelled && setAgentSummary(payload))
      .catch((reason: unknown) => {
        if (cancelled) return;
        setAgentSummary(null);
        setAgentSummaryError(reason instanceof Error ? reason.message : "저장된 AI 요약을 불러오지 못했습니다.");
      })
      .finally(() => !cancelled && setAgentSummaryLoading(false));
    return () => { cancelled = true; };
  }, [canMaterializeAgentSummary, model.context.datasetVersionId, model.context.projectId, selectedEvent?.assetId, selectedEvent?.eventId]);

  useEffect(() => {
    if (snapshot || !selectedEvent || !detail || detail.event.eventId !== selectedEvent.eventId) return;
    const next = createSnapshot(model, selectedEvent, detail, agentSummary?.summary ?? null);
    setSnapshot(next);
    persistSnapshot(storageKey, next);
  }, [agentSummary?.summary, detail, model, selectedEvent, snapshot, storageKey]);

  useEffect(() => {
    if (!snapshot || snapshot.agentSummary || !agentSummary?.summary || !selectedEvent) return;
    if (snapshot.event.eventId !== selectedEvent.eventId) return;
    const next = { ...snapshot, agentSummary: agentSummary.summary };
    setSnapshot(next);
    persistSnapshot(storageKey, next);
  }, [agentSummary?.summary, selectedEvent, snapshot, storageKey]);

  const snapshotStale = Boolean(snapshot && executiveBriefIsStale({
    snapshotEventId: snapshot.event.eventId,
    snapshotAssetId: snapshot.event.assetId,
    snapshotContextObservedAt: snapshot.contextObservedAt,
    selectedEventId: selectedEvent?.eventId ?? null,
    selectedAssetId: selectedEvent?.assetId ?? null,
    currentContextObservedAt: model.context.observedAt,
  }));

  async function regenerateSnapshot() {
    if (!selectedEvent || !detail || detail.event.eventId !== selectedEvent.eventId) {
      onRetryDetail();
      return;
    }
    let summary = agentSummary?.summary ?? null;
    if (canMaterializeAgentSummary) {
      try {
        setAgentSummaryLoading(true);
        const payload = await createOperationsAgentReviewSummary({
          assetId: selectedEvent.assetId,
          projectId: model.context.projectId,
          datasetVersionId: model.context.datasetVersionId,
          eventId: selectedEvent.eventId,
          trigger: "ui_manual_regeneration",
        });
        setAgentSummary(payload);
        summary = payload.summary;
      } catch (reason) {
        setAgentSummaryError(reason instanceof Error ? reason.message : "최신 AI 요약을 다시 생성하지 못했습니다.");
      } finally {
        setAgentSummaryLoading(false);
      }
    }
    const next = createSnapshot(model, selectedEvent, detail, summary);
    setSnapshot(next);
    persistSnapshot(storageKey, next);
  }

  if (!snapshot && !selectedEvent) {
    return <div className="operations-page" data-testid="operations-executive-report"><OperationsState kind="empty" title="보고 대상 이벤트를 선택하세요" detail="Overview 또는 Operations에서 이벤트를 선택하면 동일 수치와 대응 상태로 보고서를 구성합니다." /></div>;
  }
  if (!snapshot && detailLoading) return <div className="operations-page" data-testid="operations-executive-report"><OperationsState kind="loading" title="상황 브리핑 준비 중" detail="선택 이벤트의 근거와 보고서 내용을 확인하고 있습니다." /></div>;
  if (!snapshot && detailError) return <div className="operations-page" data-testid="operations-executive-report"><OperationsState kind="error" title="보고서를 준비하지 못했습니다" detail={detailError} onRetry={onRetryDetail} /></div>;
  if (!snapshot && !detail) return <div className="operations-page" data-testid="operations-executive-report"><OperationsState kind="empty" title="보고서 데이터가 없습니다" detail="선택 이벤트의 근거와 보고서 내용을 확인할 수 없습니다." /></div>;

  const reportModel = snapshot?.model ?? model;
  const reportEvent = snapshot?.event ?? selectedEvent!;
  const reportDetail = snapshot?.detail ?? detail!;
  const reportAgentSummary = snapshot?.agentSummary ?? agentSummary?.summary ?? null;

  const report = reportDetail.report;
  const topAssets = reportModel.assets.slice(0, 5);
  const unresolved = reportModel.events.filter((event) => event.recommendedDecision !== "continue_monitoring").slice(0, 6);
  const dataQualityEvents = reportModel.events.filter((event) => event.status === "data_quality_hold");
  const latestDecision = reportDetail.activity.find((activity) => activity.kind === "decision");
  const storedAgentSummary = reportAgentSummary;
  const visibleSections = report.sections.filter((section) => !/release|출처|provenance/i.test(section.title));
  const factorSummary = reportDetail.topFactors.slice(0, 3).map((factor) => fieldFactorItem(factor)).join(", ");
  const automaticSummary = reportEvent.status === "data_quality_hold"
    ? "현재 데이터 품질 확인이 먼저 필요합니다. 원천 관측값을 확인한 뒤 설비 위험과 운영 영향을 다시 판단해야 합니다."
    : `${formatProbability(reportEvent.failureProbability)}의 예측 위험이 관측되었습니다.${factorSummary ? ` 주요 확인 항목은 ${factorSummary}입니다.` : ""} ${DECISION_LABEL[reportEvent.recommendedDecision]}이 현재 권고 조치이며, 최종 판단은 담당자가 연결 근거를 확인한 뒤 확정합니다.`;
  const userFacingGaps = [...new Set(reportDetail.evidenceGaps.map((gap) => evidenceGapMessage(gap.field)).filter((item): item is string => Boolean(item)))];
  const eventImpact = reportDetail.operationContext?.eventImpact ?? null;
  const plannedUnits = reportDetail.operationContext?.productionPlan?.plannedUnits ?? null;
  const estimatedLostUnits = eventImpact?.estimatedLostUnits ?? null;
  const estimatedDowntime = eventImpact?.basis.estimatedDowntimeMinutes ?? reportEvent.estimatedDowntimeMinutes;
  const productionContextUsesCapacityModel = reportDetail.operationContext?.sourceType === "capacity_model";
  const asOf = snapshot?.asOf ?? report.asOf ?? reportEvent.observedAt ?? report.generatedAt;
  const generatedAt = snapshot?.generatedAt ?? report.generatedAt;
  const snapshotId = snapshot?.snapshotId ?? report.snapshotId ?? `event:${reportEvent.eventId}`;
  const artifactId = snapshot?.artifactId ?? report.artifactId ?? reportEvent.eventId;

  return (
    <div className="operations-page operations-report-page" data-testid="operations-executive-report">
      <section className={`operations-report-snapshot-banner ${snapshotStale ? "is-stale" : "is-current"}`} data-testid="executive-brief-snapshot-status">
        <div>
          {snapshotStale ? <Clock3 size={16} /> : <ShieldCheck size={16} />}
          <span>{snapshotStale ? "새 근거 있음" : "AS-OF SNAPSHOT"}</span>
          <strong>{formatTimestamp(asOf)}</strong>
          <small>Snapshot {shortRef(snapshotId)} · Artifact {shortRef(artifactId)}</small>
        </div>
        <p>{snapshotStale ? "Monitoring에는 더 최신 관측이 있지만 이 Executive Brief는 기존 snapshot 내용을 유지합니다." : "이 문서의 수치와 서술은 표시된 snapshot 기준으로 고정됩니다."}</p>
        {snapshotStale ? <button type="button" className="operations-button primary" onClick={() => void regenerateSnapshot()} disabled={agentSummaryLoading}><RefreshCw size={14} />최신 snapshot으로 재생성</button> : null}
      </section>
      <div className="operations-report-toolbar">
        <button type="button" className="operations-button secondary" onClick={onBackToOverview}><ArrowLeft size={14} />현황으로</button>
        <div><span className={`operations-report-mode mode-${report.mode}`}>경영진 보고 snapshot</span><strong>Monitoring은 live, 본 보고서는 as-of 기준입니다.</strong></div>
        <button type="button" className="operations-button primary" onClick={() => window.print()}><Printer size={15} />A4 PDF / 출력</button>
      </div>

      <article className="operations-report-document">
        <header className="operations-report-cover">
          <div className="operations-report-cover-brand"><span>RELIABILITY OPERATIONS</span><strong>Executive Brief</strong></div>
          <div className="operations-report-cover-title"><span>운영 리스크 · 생산 영향 · 의사결정</span><h1>{storedAgentSummary?.title ?? `${displayEventAssetName(reportEvent)} · 운영 판단 브리핑`}</h1><p>{storedAgentSummary?.summary ?? automaticSummary}</p></div>
          <dl className="operations-report-document-meta">
            <div><dt>Snapshot ID</dt><dd title={snapshotId}>{shortRef(snapshotId)}</dd></div>
            <div><dt>Artifact ID</dt><dd title={artifactId}>{shortRef(artifactId)}</dd></div>
            <div><dt>As-of</dt><dd>{formatTimestamp(asOf)}</dd></div>
            <div><dt>Generated</dt><dd>{formatTimestamp(generatedAt)}</dd></div>
            <div><dt>대상 설비</dt><dd>{displayEventAssetName(reportEvent)}</dd></div>
            <div><dt>운영 범위</dt><dd>{reportModel.context.projectName}</dd></div>
          </dl>
        </header>

        <section className="operations-report-executive-summary">
          <div><span>경영 판단 요약</span><h2>{selectedDecisionHeadline(reportEvent)}</h2><p>{reportEvent.status === "data_quality_hold" ? "원천 데이터 확인 전에는 고장 위험과 생산 영향을 확정하지 않습니다." : `현재 예측 위험은 ${formatProbability(reportEvent.failureProbability)}입니다. 예상 정지 영향은 ${formatMinutes(estimatedDowntime)}${estimatedLostUnits !== null ? `, 계획 영향은 약 ${estimatedLostUnits.toLocaleString()}개` : ""}${plannedUnits !== null ? ` (일일 계획 ${plannedUnits.toLocaleString()}개 기준)` : ""}입니다.`}</p>{productionContextUsesCapacityModel ? <small>생산 영향은 현재 capacity model 기반 추정치이며 결산 시 실제 실적과 재검증합니다.</small> : null}</div>
          <aside><OperationsStatusBadge status={reportEvent.status} /><strong>{DECISION_LABEL[reportEvent.recommendedDecision]}</strong><small>최근 사람 결정: {latestDecision?.decision ? DECISION_LABEL[latestDecision.decision] : "아직 기록 없음"}</small><small>판단 기록은 Operations에서 관리</small></aside>
        </section>

        <section className="operations-report-agent-summary">
          <header><Bot size={17} /><span>{storedAgentSummary?.mode === "llm" ? "AI 경영 요약" : "자동 경영 요약"}</span><strong>{storedAgentSummary?.mode === "llm" ? "snapshot 근거 연결" : reportAgentSummaryStatusLabel(agentSummary)}</strong></header>
          {agentSummaryLoading && !storedAgentSummary ? <p>현재 snapshot의 기술·운영 근거를 경영진용 문장으로 정리하고 있습니다.</p> : null}
          {!agentSummaryLoading && agentSummaryError ? <p>자동 요약을 불러오지 못해 현재 운영 데이터 기준 요약을 표시합니다.</p> : null}
          {!agentSummaryLoading && storedAgentSummary ? (
            <>
              <div>
                <strong>{storedAgentSummary.title}</strong>
                <p>{storedAgentSummary.summary}</p>
              </div>
              {storedAgentSummary.role_summaries.length ? (
                <div className="operations-report-agent-quotes">
                  {storedAgentSummary.role_summaries.map((item) => (
                    <figure key={`${storedAgentSummary.asset_id}-${item.role}`}>
                      <figcaption>{item.label}</figcaption>
                      <blockquote>{item.quote}</blockquote>
                    </figure>
                  ))}
                </div>
              ) : null}
              <small>{storedAgentSummary.boundary_note}</small>
            </>
          ) : null}
          {!agentSummaryLoading && !storedAgentSummary ? (
            <div><strong>현재 운영 데이터 기준 요약</strong><p>{automaticSummary}</p></div>
          ) : null}
        </section>

        <section className="operations-report-kpis">
          <article><span>생산 계획</span><strong>{plannedUnits === null ? "-" : plannedUnits.toLocaleString()}</strong><small>{eventImpact?.productVariant ? `${eventImpact.productVariant} 제품군 포함` : "계획 맥락"}</small></article>
          <article><span>선택 이슈 계획 영향</span><strong>{estimatedLostUnits === null ? "-" : `${estimatedLostUnits.toLocaleString()}개`}</strong><small>실적 손실이 아닌 추정치</small></article>
          <article><span>예상 정지 영향</span><strong>{formatMinutes(estimatedDowntime)}</strong><small>선택 Decision Case 기준</small></article>
          <article><span>판단 대기</span><strong>{reportModel.metrics.pendingDecisions}</strong><small>snapshot 기준 미결정</small></article>
          <article><span>고위험 설비</span><strong>{reportModel.metrics.critical + reportModel.metrics.warning}</strong><small>전체 {reportModel.metrics.totalAssets}대 중</small></article>
        </section>

        <div className="operations-report-content-grid">
          <main className="operations-report-narrative">
            {visibleSections.map((section, index) => (
              <section key={section.id}>
                <header><span>{String(index + 1).padStart(2, "0")}</span><h2>{section.title}</h2></header>
                <p>{humanizeOperationalText(section.body)}</p>
              </section>
            ))}

            <section>
              <header><span>{String(visibleSections.length + 1).padStart(2, "0")}</span><h2>대응 상태와 미결정 사항</h2></header>
              {unresolved.length ? <table className="operations-report-table"><thead><tr><th>설비</th><th>상태</th><th>권장 결정</th><th>담당자</th><th>예상 정지</th></tr></thead><tbody>{unresolved.map((event) => <tr key={event.eventId}><td><strong>{displayEventAssetName(event)}</strong><small>{displayLineLabel(event.line)}</small></td><td><OperationsStatusBadge status={event.status} /></td><td>{DECISION_LABEL[event.recommendedDecision]}</td><td>{displayAssignee(event.assignedEngineer)}</td><td>{formatMinutes(event.estimatedDowntimeMinutes)}</td></tr>)}</tbody></table> : <p>현재 미결정 이벤트가 없습니다.</p>}
            </section>

            <section className="operations-report-limitations">
              <header><span>{String(visibleSections.length + 2).padStart(2, "0")}</span><h2>불확실성·데이터 품질·한계</h2></header>
              {dataQualityEvents.length ? <p><strong>{dataQualityEvents.length}개 이벤트</strong>는 데이터 품질 문제로 고장 수치 대신 확인 필요 상태를 표시합니다.</p> : <p>현재 품질 보류 이벤트는 없습니다.</p>}
              <ul>
                <li>위험도는 특정 고장 원인을 확정하는 값이 아니라 향후 고장 가능성을 나타내는 예측값입니다.</li>
                <li>권고 조치는 담당자의 승인이나 실제 작업 실행을 대신하지 않습니다.</li>
                {userFacingGaps.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </section>
          </main>

          <aside className="operations-report-evidence-column">
            <section><span>주요 위험 설비</span><div className="operations-report-asset-list">{topAssets.map((asset, index) => <article key={asset.assetId}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{displayAssetName(asset)}</strong><small>{displayLineLabel(asset.line)}</small></div><span>{formatProbability(asset.failureProbability)}</span></article>)}</div></section>
            <section><span>선택 설비 판단 근거</span><dl><div><dt>고장 위험</dt><dd>{formatProbability(reportEvent.failureProbability)}</dd></div><div><dt>신뢰도</dt><dd>{CONFIDENCE_LABEL[reportEvent.confidence]}</dd></div><div><dt>예측 이상</dt><dd>{fieldFailureLabel(reportEvent.predictedFailureType)}</dd></div><div><dt>중요도</dt><dd>{displayCriticality(reportDetail.assetCriticality ?? reportEvent.criticality)}</dd></div><div><dt>검토 우선순위</dt><dd>{displayReviewPriority(reportDetail.reviewPriority?.level)}</dd></div><div><dt>담당자</dt><dd>{displayAssignee(reportEvent.assignedEngineer)}</dd></div></dl></section>
            <section><span>핵심 확인 항목</span>{reportDetail.topFactors.length ? <dl>{reportDetail.topFactors.slice(0, 5).map((factor, index) => <div key={factor.id}><dt>{fieldFactorItem(factor)}</dt><dd>{index + 1}순위 근거</dd></div>)}</dl> : <p>추가 확인이 필요한 설명 요인이 없습니다.</p>}</section>
            <section><span>데이터 기준</span><p>센서 스트리밍은 Monitoring에 사용하고, 본 Executive Brief는 Product Result/Evidence와 운영 맥락의 as-of snapshot을 기준으로 고정합니다.</p>{productionContextUsesCapacityModel ? <small>운영 영향은 capacity model과 현재 계획 snapshot을 기준으로 산정하며 정산 데이터와 분리해 관리합니다.</small> : null}</section>
          </aside>
        </div>

        <footer className="operations-report-footer"><span>{reportModel.context.projectName}</span><span>{formatTimestamp(generatedAt)}</span><strong>Reliability Operations · as-of Executive Brief</strong></footer>
      </article>
    </div>
  );
}
