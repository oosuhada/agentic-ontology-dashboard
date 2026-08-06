import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowRight, FilterX, Search, Wrench } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { MvpAsset, MvpBootstrapModel, MvpEventDetailModel, MvpRiskStatus } from "../api/mvpContracts";
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

function matches(asset: MvpAsset, search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  return [asset.assetId, asset.displayName, asset.assetType, asset.site, asset.line, asset.cell, asset.assignedEngineer]
    .some((value) => String(value ?? "").toLowerCase().includes(query));
}

export function MvpObjectsPage({
  model,
  selectedAssetId,
  detail,
  detailLoading,
  detailError,
  onSelectAsset,
  onOpenOperations,
  onRetryDetail,
}: {
  model: MvpBootstrapModel;
  selectedAssetId: string | null;
  detail: MvpEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  onSelectAsset: (asset: MvpAsset) => void;
  onOpenOperations: (asset: MvpAsset) => void;
  onRetryDetail: () => void;
}) {
  const [search, setSearch] = useState("");
  const [line, setLine] = useState("all");
  const [status, setStatus] = useState<MvpRiskStatus | "all">("all");
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

  function resetFilters() {
    setSearch("");
    setLine("all");
    setStatus("all");
    setAssignee("all");
  }

  return (
    <div className="mvp-page mvp-objects-page" data-testid="mvp-objects">
      <div className="mvp-object-layout">
        <MvpPanel title={`설비 목록 · ${visibleAssets.length.toLocaleString()}`} eyebrow="DENSE OBJECT TABLE" className="mvp-object-table-panel">
          <div className="mvp-object-filters">
            <label className="mvp-search"><Search size={15} /><input aria-label="설비 검색" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="설비 ID, 이름, 라인, 담당자 검색" /></label>
            <label><span>라인</span><select aria-label="라인 필터" value={line} onChange={(event) => setLine(event.target.value)}><option value="all">전체 라인</option>{lines.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label><span>상태</span><select aria-label="상태 필터" value={status} onChange={(event) => setStatus(event.target.value as MvpRiskStatus | "all")}><option value="all">전체 상태</option><option value="critical">위험</option><option value="warning">경고</option><option value="attention">주의</option><option value="normal">정상</option><option value="data_quality_hold">데이터 확인</option></select></label>
            <label><span>담당자</span><select aria-label="담당자 필터" value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="all">전체 담당자</option>{assignees.map((item) => <option key={item}>{item}</option>)}</select></label>
            <button type="button" className="mvp-icon-button" onClick={resetFilters} aria-label="필터 초기화"><FilterX size={16} /></button>
          </div>

          <div className="mvp-object-table" role="table" aria-label="설비 목록">
            <div className="mvp-object-table-head" role="row"><span>설비</span><span>유형·위치</span><span>상태</span><span>고장 확률</span><span>신뢰도</span><span>중요도</span><span>담당자</span></div>
            {visibleAssets.length ? (
              <div className="mvp-object-table-scroll" ref={tableRef}>
                <div style={{ height: `${virtualizer.getTotalSize()}px`, position: "relative" }}>
                  {virtualizer.getVirtualItems().map((virtualRow) => {
                    const asset = visibleAssets[virtualRow.index];
                    return (
                      <button
                        type="button"
                        role="row"
                        key={asset.assetId}
                        className={`mvp-object-row ${selectedAssetId === asset.assetId ? "is-selected" : ""}`}
                        style={{ transform: `translateY(${virtualRow.start}px)` }}
                        onClick={() => onSelectAsset(asset)}
                      >
                        <span><strong>{asset.displayName}</strong><code>{asset.assetId}</code></span>
                        <span><strong>{asset.assetType.toUpperCase()}</strong><small>{asset.line} · {asset.cell}</small></span>
                        <span><MvpStatusBadge status={asset.status} /></span>
                        <span><b>{formatProbability(asset.failureProbability)}</b></span>
                        <span><MvpConfidenceBadge confidence={asset.confidence} /></span>
                        <span><strong>{asset.criticality}</strong></span>
                        <span><strong>{asset.assignedEngineer ?? "미배정"}</strong></span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : <MvpState kind="empty" title="조건에 맞는 설비가 없습니다" detail="검색어나 필터를 초기화해 다시 확인하세요." />}
          </div>
        </MvpPanel>

        <aside className="mvp-object-inspector" aria-label="선택 설비 Inspector">
          {!selectedAsset ? (
            <MvpState kind="empty" title="설비를 선택하세요" detail={selectedAssetId ? `요청한 설비 ${selectedAssetId}를 현재 Dataset Version에서 찾지 못했습니다.` : "목록에서 설비를 선택하면 속성·근거·업무 연결을 확인할 수 있습니다."} />
          ) : (
            <>
              <header className="mvp-inspector-hero">
                <div><span>ASSET INSPECTOR</span><h2>{selectedAsset.displayName}</h2><code>{selectedAsset.assetId}</code></div>
                <MvpStatusBadge status={selectedAsset.status} />
              </header>
              <dl className="mvp-inspector-summary">
                <div><dt>고장 확률</dt><dd>{formatProbability(selectedAsset.failureProbability)}</dd></div>
                <div><dt>신뢰도</dt><dd>{selectedAsset.confidenceScore === null ? selectedAsset.confidence : formatProbability(selectedAsset.confidenceScore)}</dd></div>
                <div><dt>예상 영향</dt><dd>{formatMinutes(selectedAsset.estimatedDowntimeMinutes)}</dd></div>
                <div><dt>담당자</dt><dd>{selectedAsset.assignedEngineer ?? "미배정"}</dd></div>
                <div><dt>위치</dt><dd>{selectedAsset.site} · {selectedAsset.line} · {selectedAsset.cell}</dd></div>
                <div><dt>관측 시각</dt><dd>{formatTimestamp(selectedAsset.observedAt)}</dd></div>
              </dl>

              {selectedAsset.status === "data_quality_hold" ? <div className="mvp-quality-callout"><strong>데이터 품질 확인 필요</strong><p>확률을 고장으로 해석하지 않고 원천 센서와 파이프라인 상태를 먼저 확인합니다.</p></div> : null}
              {selectedAsset.confidence === "low" || selectedAsset.confidence === "unavailable" ? <div className="mvp-confidence-callout"><strong>낮은 신뢰도</strong><p>추가 현장 확인 전에는 원인이나 고장을 확정하지 않습니다.</p></div> : null}

              <section className="mvp-inspector-section"><header><span>Prediction</span><strong>{selectedAsset.predictedFailureType}</strong></header><p>권장 조치: <b>{DECISION_LABEL[selectedAsset.recommendedDecision]}</b></p></section>

              <section className="mvp-inspector-section">
                <header><span>핵심 센서</span><strong>{detailLoading ? "불러오는 중" : `${detail?.sensors.length ?? 0} fields`}</strong></header>
                {detailLoading ? <MvpState kind="loading" title="Evidence 로딩" detail="선택 Event의 센서 근거를 확인하고 있습니다." /> : detailError ? <MvpState kind="error" title="센서 근거를 불러오지 못했습니다" detail={detailError} onRetry={onRetryDetail} /> : detail?.sensors.length ? <dl className="mvp-sensor-grid">{detail.sensors.map((sensor) => <div key={sensor.id}><dt>{sensor.label}</dt><dd>{sensor.value === null || sensor.value === "" ? "—" : String(sensor.value)} {sensor.unit}</dd></div>)}</dl> : <p className="mvp-muted">이 설비와 연결된 Event Evidence가 없습니다.</p>}
              </section>

              <section className="mvp-inspector-section">
                <header><span>Top factors</span><strong>{factors.length} factors</strong></header>
                {factors.length ? <div className="mvp-factor-list">{factors.slice(0, 5).map((factor) => <article key={factor.id}><div><strong>{factor.label}</strong><span>{factor.value === null ? "—" : factor.value.toLocaleString()} {factor.unit}</span></div><div className="mvp-factor-track"><i style={{ width: `${Math.max(4, Math.min(100, factor.contribution * 100))}%` }} /></div><b>{factor.direction === "risk_up" ? "위험 증가" : "위험 완화"}</b></article>)}</div> : <p className="mvp-muted">설명 가능한 기여 요인이 제공되지 않았습니다.</p>}
              </section>

              {provenance ? <section className="mvp-inspector-section"><header><span>Provenance</span><strong>Dataset → Model → UI</strong></header><MvpProvenanceView provenance={provenance} /></section> : null}

              <button type="button" className="mvp-button primary mvp-inspector-action" onClick={() => onOpenOperations(selectedAsset)} disabled={!selectedAsset.eventId}><Wrench size={15} />Operations에서 조치 검토<ArrowRight size={15} /></button>
              {!selectedAsset.eventId ? <small className="mvp-muted">이 Result Artifact에는 연결된 운영 Event가 없어 읽기 전용으로 표시됩니다.</small> : null}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
