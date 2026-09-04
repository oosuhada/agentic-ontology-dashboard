import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowRight, ClipboardCheck, FileText, FilterX, Search, Wrench } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { OperationsAsset, OperationsBootstrapModel, OperationsEventDetailModel, OperationsRiskStatus } from "../api/operationsContracts";
import {
  DECISION_LABEL,
  OperationsConfidenceBadge,
  OperationsPanel,
  OperationsProvenanceView,
  OperationsState,
  OperationsStatusBadge,
  formatMinutes,
  formatProbability,
  formatTimestamp,
} from "../components/OperationsUi";
import {
  displayAssetName,
  displayAssetType,
  displayReviewPriority,
  fieldFailureLabel,
} from "../displayLabels";

function qualityLabel(value: string | undefined) {
  if (value === "good") return "정상";
  if (value === "bad") return "불량";
  if (value === "unknown") return "확인 필요";
  return "미제공";
}

function matches(asset: OperationsAsset, search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  return [asset.assetId, asset.displayName, asset.assetType, asset.site, asset.line, asset.cell, asset.assignedEngineer]
    .some((value) => String(value ?? "").toLowerCase().includes(query));
}

function valueOrGap(value: unknown, suffix = "") {
  if (value === null || value === undefined || value === "") return "확인 필요";
  return `${value}${suffix}`;
}

export function OperationsObjectsPage({
  model,
  selectedAssetId,
  detail,
  detailLoading,
  detailError,
  onSelectAsset,
  onOpenOperations,
  onOpenReport,
  onRetryDetail,
}: {
  model: OperationsBootstrapModel;
  selectedAssetId: string | null;
  detail: OperationsEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  onSelectAsset: (asset: OperationsAsset) => void;
  onOpenOperations: (asset: OperationsAsset) => void;
  onOpenReport: (asset: OperationsAsset) => void;
  onRetryDetail: () => void;
}) {
  const [search, setSearch] = useState("");
  const [line, setLine] = useState("all");
  const [status, setStatus] = useState<OperationsRiskStatus | "all">("all");
  const [assignee, setAssignee] = useState("all");
  const lines = useMemo(() => [...new Set(model.assets.map((asset) => asset.line))].sort(), [model.assets]);
  const assignees = useMemo(() => [...new Set(model.assets.map((asset) => asset.assignedEngineer ?? "미배정"))].sort(), [model.assets]);
  const visibleAssets = useMemo(() => model.assets.filter((asset) => (
    matches(asset, search)
    && (line === "all" || asset.line === line)
    && (status === "all" || asset.status === status)
    && (assignee === "all" || (asset.assignedEngineer ?? "미배정") === assignee)
  )), [assignee, line, model.assets, search, status]);
  const selectedAsset = model.assets.find((asset) => asset.assetId === selectedAssetId) ?? null;
  const tableRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: visibleAssets.length,
    getScrollElement: () => tableRef.current,
    estimateSize: () => 49,
    overscan: 12,
  });
  const factors = detail?.topFactors.length ? detail.topFactors : selectedAsset?.topFactors ?? [];
  const provenance = detail?.provenance ?? selectedAsset?.provenance ?? null;
  const selectedCriticality = detail?.assetCriticality ?? selectedAsset?.criticality ?? null;

  function resetFilters() {
    setSearch("");
    setLine("all");
    setStatus("all");
    setAssignee("all");
  }

  return (
    <div className="operations-page operations-objects-page" data-testid="operations-objects">
      <div className="operations-object-layout">
        <OperationsPanel title={`Assets · ${visibleAssets.length.toLocaleString()}`} eyebrow="ASSET SURFACE" className="operations-object-table-panel">
          <div className="operations-object-filters">
            <label className="operations-search"><Search size={15} /><input aria-label="설비 검색" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="설비 이름, 위치, 담당자 검색" /></label>
            <label><span>라인</span><select aria-label="라인 필터" value={line} onChange={(event) => setLine(event.target.value)}><option value="all">전체 라인</option>{lines.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label><span>상태</span><select aria-label="상태 필터" value={status} onChange={(event) => setStatus(event.target.value as OperationsRiskStatus | "all")}><option value="all">전체 상태</option><option value="critical">위험</option><option value="warning">경고</option><option value="attention">주의</option><option value="normal">정상</option><option value="data_quality_hold">데이터 확인</option></select></label>
            <label><span>담당자</span><select aria-label="담당자 필터" value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="all">전체 담당자</option>{assignees.map((item) => <option key={item}>{item}</option>)}</select></label>
            <button type="button" className="operations-icon-button" onClick={resetFilters} aria-label="필터 초기화"><FilterX size={16} /></button>
          </div>

          <div className="operations-object-table" role="table" aria-label="설비 목록">
            <div className="operations-object-table-head" role="row"><span>설비</span><span>유형·위치</span><span>상태</span><span>고장 확률</span><span>신뢰도</span><span>중요도</span><span>담당자</span></div>
            {visibleAssets.length ? (
              <div className="operations-object-table-scroll" ref={tableRef}>
                <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
                  {virtualizer.getVirtualItems().map((virtualRow) => {
                    const asset = visibleAssets[virtualRow.index];
                    return (
                      <button
                        type="button"
                        role="row"
                        key={asset.assetId}
                        className={`operations-object-row ${selectedAssetId === asset.assetId ? "is-selected" : ""}`}
                        style={{ transform: `translateY(${virtualRow.start}px)` }}
                        onClick={() => onSelectAsset(asset)}
                      >
                        <span><strong>{displayAssetName({ assetId: asset.assetId, displayName: asset.displayName })}</strong><small>최근 관측 {formatTimestamp(asset.observedAt)}</small></span>
                        <span><strong>{displayAssetType(asset.assetType)}</strong><small>{asset.line} · {asset.cell}</small></span>
                        <span><OperationsStatusBadge status={asset.status} /></span>
                        <span><b>{formatProbability(asset.failureProbability)}</b></span>
                        <span><OperationsConfidenceBadge confidence={asset.confidence} /></span>
                        <span><strong>{asset.criticality ?? "확인 필요"}</strong></span>
                        <span><strong>{asset.assignedEngineer ?? "미배정"}</strong></span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : <OperationsState kind="empty" title="조건에 맞는 설비가 없습니다" detail="검색어나 필터를 초기화해 다시 확인하세요." />}
          </div>
        </OperationsPanel>

        <aside className="operations-object-inspector" aria-label="선택 설비 Inspector">
          {!selectedAsset ? (
                <OperationsState kind="empty" title="설비를 선택하세요" detail={selectedAssetId ? "요청한 설비를 현재 데이터에서 찾지 못했습니다. 목록에서 다른 설비를 선택해 주세요." : "목록에서 설비를 선택하면 상태, 근거, 작업 연결을 확인할 수 있습니다."} />
          ) : (
            <>
              <header className="operations-inspector-hero">
                <div><span>선택 설비</span><h2>{displayAssetName({ assetId: selectedAsset.assetId, displayName: selectedAsset.displayName })}</h2><small>{selectedAsset.line} · 최근 관측 {formatTimestamp(selectedAsset.observedAt)}</small></div>
                <OperationsStatusBadge status={selectedAsset.status} />
              </header>
              <section className="operations-inspector-section">
                <header><span>Current State</span><strong>지금 무슨 일이 일어나는가</strong></header>
                <dl className="operations-sensor-grid">
                  <div><dt>Health</dt><dd><OperationsStatusBadge status={selectedAsset.status} /></dd></div>
                  <div><dt>Risk</dt><dd>{formatProbability(selectedAsset.failureProbability)}</dd></div>
                  <div><dt>Criticality</dt><dd>{selectedCriticality ?? "근거 부족"}</dd></div>
                  <div><dt>Impact</dt><dd>{formatMinutes(selectedAsset.estimatedDowntimeMinutes)}</dd></div>
                  <div><dt>Owner</dt><dd>{selectedAsset.assignedEngineer ?? "미배정"}</dd></div>
                  <div><dt>Location</dt><dd>{selectedAsset.site} · {selectedAsset.line} · {selectedAsset.cell}</dd></div>
                  <div><dt>Observed</dt><dd>{formatTimestamp(selectedAsset.observedAt)}</dd></div>
                </dl>
                {selectedAsset.status === "data_quality_hold" ? <div className="operations-quality-callout"><strong>데이터 품질 확인 필요</strong><p>확률을 고장으로 해석하지 않고 원천 센서와 파이프라인 상태를 먼저 확인합니다.</p></div> : null}
                {selectedAsset.confidence === "low" || selectedAsset.confidence === "unavailable" ? <div className="operations-confidence-callout"><strong>낮은 신뢰도</strong><p>추가 현장 확인 전에는 원인이나 고장을 확정하지 않습니다.</p></div> : null}
              </section>

              <section className="operations-inspector-section">
                <header><span>운영 검토</span><strong>{displayReviewPriority(detail?.reviewPriority?.level)}</strong></header>
                <dl className="operations-inspector-summary">
                  <div><dt>검토 우선순위</dt><dd>{displayReviewPriority(detail?.reviewPriority?.level)}</dd></div>
                  <div><dt>중요도 근거</dt><dd>{detail?.criticalityBasis.length ? detail.criticalityBasis.join(", ") : "확인 필요"}</dd></div>
                  <div><dt>마지막 정비</dt><dd>{valueOrGap(detail?.maintenanceContext?.lastMaintenanceDaysAgo, "일 전")}</dd></div>
                  <div><dt>30일 유사 Event</dt><dd>{valueOrGap(detail?.maintenanceContext?.similarEvents30d, "건")}</dd></div>
                  <div><dt>열린 작업</dt><dd>{detail?.maintenanceContext?.openWorkOrderExists === null || detail?.maintenanceContext?.openWorkOrderExists === undefined ? "확인 필요" : detail.maintenanceContext.openWorkOrderExists ? "있음" : "없음"}</dd></div>
                  <div><dt>생산 영향</dt><dd>{detail?.operationContext?.productionImpact ?? "확인 필요"}</dd></div>
                </dl>
                {detail?.reviewPriority?.reasons.length ? <p className="operations-muted">{detail.reviewPriority.reasons.join(" · ")}</p> : <p className="operations-muted">필요한 운영 맥락이 없으면 우선순위를 임의 계산하지 않습니다.</p>}
              </section>

              <section className="operations-inspector-section">
                <header><span>근거 / 진단</span><strong>{fieldFailureLabel(selectedAsset.predictedFailureType)}</strong></header>
                <dl className="operations-sensor-grid">
                  <div><dt>관련 판단</dt><dd>{selectedAsset.eventId ? "현재 관측 Case 연결됨" : "연결된 판단 없음"}</dd></div>
                  <div><dt>진단</dt><dd>{DECISION_LABEL[selectedAsset.recommendedDecision]}</dd></div>
                  <div><dt>신뢰도</dt><dd>{selectedAsset.confidenceScore === null ? selectedAsset.confidence : formatProbability(selectedAsset.confidenceScore)}</dd></div>
                </dl>
                {detailLoading ? <OperationsState kind="loading" title="근거 로딩" detail="선택 이벤트의 현재 관측과 과거 이력을 확인하고 있습니다." /> : detailError ? <OperationsState kind="error" title="센서 근거를 불러오지 못했습니다" detail={detailError} onRetry={onRetryDetail} /> : detail?.sensors.length ? <dl className="operations-sensor-grid">{detail.sensors.map((sensor) => <div key={sensor.id}><dt>{sensor.label}</dt><dd>{sensor.value === null || sensor.value === "" ? "—" : String(sensor.value)} {sensor.unit}<small>현재 {qualityLabel(sensor.qualityStatus)} · 이력 {sensor.historyPointCount ?? 0}개</small></dd></div>)}</dl> : <p className="operations-muted">이 설비와 연결된 이벤트 근거가 없습니다.</p>}
                {factors.length ? <div className="operations-factor-list">{factors.slice(0, 5).map((factor) => <article key={factor.id}><div><strong>{factor.label}</strong><span>{factor.value === null ? "—" : factor.value.toLocaleString()} {factor.unit}</span></div><div className="operations-factor-track"><i style={{ width: `${Math.max(4, Math.min(100, factor.contribution * 100))}%` }} /></div><b>{factor.direction === "risk_up" ? "위험 증가" : "위험 완화"}</b></article>)}</div> : <p className="operations-muted">설명 가능한 기여 요인이 제공되지 않았습니다.</p>}
              </section>

              <section className="operations-inspector-section">
                <header><span>작업 연결</span><strong>작업요청</strong></header>
                <dl className="operations-sensor-grid">
                  <div><dt>작업요청</dt><dd>{selectedAsset.eventId ? "후보 있음 · ID 미생성" : "연결 없음"}</dd></div>
                  <div><dt>정비 조치</dt><dd>계약 없음</dd></div>
                  <div><dt>부품</dt><dd>{selectedAsset.sparePartAvailable === null ? "확인 필요" : selectedAsset.sparePartAvailable ? "확보" : "미확보"}</dd></div>
                </dl>
                {detail?.equipmentHistory.length ? <div className="operations-activity-list">{detail.equipmentHistory.slice(0, 4).map((item) => <article key={`${item.occurredAt}-${item.kind}`}><span className={`activity-${item.tone === "hold" ? "system" : "note"}`} /><div><strong>{item.kind}</strong><p>{item.description}</p><small>{item.source} · {formatTimestamp(item.occurredAt)}</small></div></article>)}</div> : <p className="operations-muted">정비/운영 context 이력이 제공되지 않았습니다.</p>}
              </section>

              <section className="operations-inspector-section">
                <header><span>가능한 이동</span><strong>현재 가능한 이동</strong></header>
                <div className="operations-action-row">
                  <button type="button" className="operations-button primary" onClick={() => onOpenOperations(selectedAsset)} disabled={!selectedAsset.eventId}><ClipboardCheck size={15} />작업요청 후보 열기<ArrowRight size={15} /></button>
                  <button type="button" className="operations-button secondary" onClick={() => selectedAsset.eventId && onOpenOperations(selectedAsset)} disabled={!selectedAsset.eventId}><Wrench size={15} />조치 판단</button>
                  {selectedAsset.eventId ? <button type="button" className="operations-button ghost" onClick={() => onOpenReport(selectedAsset)}><FileText size={15} />관련 보고서</button> : null}
                </div>
                {!selectedAsset.eventId ? <small className="operations-muted">이 설비 판단에는 연결된 운영 이벤트가 없어 읽기 전용으로 표시됩니다.</small> : null}
              </section>

              {detail?.evidenceGaps.length ? <section className="operations-inspector-section"><header><span>Gaps</span><strong>{detail.evidenceGaps.length}개</strong></header><ul className="operations-gap-list">{detail.evidenceGaps.map((gap) => <li key={`${gap.ownerDomain}-${gap.field}`}><strong>{gap.field}</strong><span>{gap.ownerDomain} · {gap.reason}</span></li>)}</ul></section> : null}
              {provenance ? <section className="operations-inspector-section"><header><span>Source</span><strong>데이터 · 모델 · 화면</strong></header><OperationsProvenanceView provenance={provenance} /></section> : null}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
