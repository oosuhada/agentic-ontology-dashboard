import { AlertTriangle, CalendarRange, ClipboardCheck, Clock3, DatabaseZap, FileText, Filter, Gauge, Map as MapIcon, Printer, ShieldCheck, Wrench } from "lucide-react";
import { useMemo, useState } from "react";
import type { OperationsAsset, OperationsBootstrapModel, OperationsEvent, OperationsEventDetailModel, OperationsReportTab, OperationsRiskStatus } from "../api/operationsContracts";
import type { ReliabilityExperienceKind } from "../../predictive-maintenance/workspace/roleExperience";
import { DECISION_LABEL, formatMinutes, formatProbability, formatTimestamp } from "../components/OperationsUi";
import { displayAssetName, displayAssetShortName, displayDataSource, displayEventAssetName, fieldFactorItem, fieldFailureLabel } from "../displayLabels";
import { OperationsExecutiveReportPage } from "./OperationsExecutiveReportPage";
import { OperationsInspectionReportPage } from "./OperationsInspectionReportPage";
import { OperationsMapReportAssetDetailView } from "./OperationsMapReportAssetDetailView";

const REPORT_TABS: Array<{ id: OperationsReportTab; label: string; description: string; icon: typeof MapIcon }> = [
  { id: "status-map", label: "상태 요약", description: "설비 상태 맵과 우선순위", icon: MapIcon },
  { id: "inspection-request", label: "점검 요청", description: "현장 확인 항목", icon: ClipboardCheck },
  { id: "summary-report", label: "요약 보고서", description: "관리자 공유본", icon: FileText },
  { id: "executive-brief", label: "Executive Brief", description: "선택 이벤트 보고서", icon: FileText },
];

const MAP_STATUS_META: Record<OperationsRiskStatus, { label: string; tone: string; sentence: string }> = {
  critical: { label: "위험", tone: "critical", sentence: "즉시 점검이 필요한 위험 신호" },
  warning: { label: "경고", tone: "warning", sentence: "우선순위 점검 후보" },
  attention: { label: "주의", tone: "attention", sentence: "추가 관찰 필요" },
  normal: { label: "정상", tone: "normal", sentence: "특이 위험 신호 없음" },
  data_quality_hold: { label: "데이터 확인", tone: "hold", sentence: "데이터 확인 후 판단" },
};

const SUMMARY_STATUS_ORDER: OperationsRiskStatus[] = ["critical", "warning", "attention", "normal", "data_quality_hold"];

function MapStatusBadge({ status }: { status: OperationsRiskStatus }) {
  const meta = MAP_STATUS_META[status];
  return <span className={`status-badge ${meta.tone}`}>{meta.label}</span>;
}

function ReportKpi({
  icon: Icon,
  label,
  value,
  detail,
  tone = "",
}: {
  icon: typeof Gauge;
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <article className={`kpi ${tone}`}>
      <Icon size={18} />
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function statusCount(model: OperationsBootstrapModel, status: OperationsRiskStatus) {
  if (status === "critical") return model.metrics.critical;
  if (status === "warning") return model.metrics.warning;
  if (status === "attention") return model.metrics.attention;
  if (status === "normal") return model.metrics.normal;
  return model.metrics.dataQualityHold;
}

function OperationsSummaryGraphBoard({
  model,
  selected,
}: {
  model: OperationsBootstrapModel;
  selected: OperationsEvent | null;
}) {
  const selectedAsset = model.assets.find((asset) => asset.eventId === selected?.eventId)
    ?? model.assets.find((asset) => asset.assetId === selected?.assetId)
    ?? null;
  const maxLineRisk = Math.max(...model.lineRisk.map((line) => line.averageRisk ?? 0), 0.01);
  const riskPercent = selected?.failureProbability === null || selected?.failureProbability === undefined
    ? null
    : Math.round(selected.failureProbability * 100);

  return (
    <section className="summary-graph-board" data-testid="operations-summary-map-report-graphs">
      <header className="asset-graph-toolbar">
        <div>
          <span>MAP-REPORT GRAPH SNAPSHOT</span>
          <h2>상태 맵 · 라인 위험 · 선택 설비를 한 장으로 압축</h2>
        </div>
        <div className="asset-range-meta"><CalendarRange size={15} />동일 snapshot · {formatTimestamp(model.context.observedAt ?? model.context.refreshedAt)}</div>
      </header>

      <div className="summary-graph-grid">
        <article className="summary-status-chart" aria-label="상태 분포 그래프">
          <div className="panel-heading compact"><div><span>STATUS DISTRIBUTION</span><h2>상태 분포</h2></div></div>
          <div className="summary-stack-bar" aria-hidden="true">
            {SUMMARY_STATUS_ORDER.map((status) => {
              const count = statusCount(model, status);
              const basis = Math.max(1, model.metrics.totalAssets);
              return <i key={status} className={MAP_STATUS_META[status].tone} style={{ width: `${Math.max(3, (count / basis) * 100)}%` }} />;
            })}
          </div>
          <div className="summary-status-legend">
            {SUMMARY_STATUS_ORDER.map((status) => (
              <div key={status}>
                <i className={`dot ${MAP_STATUS_META[status].tone}`} />
                <span>{MAP_STATUS_META[status].label}</span>
                <strong>{statusCount(model, status)}대</strong>
              </div>
            ))}
          </div>
        </article>

        <article className="summary-line-chart" aria-label="라인별 위험 막대 그래프">
          <div className="panel-heading compact"><div><span>LINE RISK BARS</span><h2>라인별 평균 위험</h2></div></div>
          <div className="summary-line-bars">
            {[...model.lineRisk]
              .sort((a, b) => (b.averageRisk ?? -1) - (a.averageRisk ?? -1))
              .slice(0, 5)
              .map((line) => (
                <div key={line.line}>
                  <span>{line.line}</span>
                  <i><b style={{ width: `${Math.max(4, ((line.averageRisk ?? 0) / maxLineRisk) * 100)}%` }} /></i>
                  <strong>{formatProbability(line.averageRisk)}</strong>
                </div>
              ))}
          </div>
        </article>

        <article className="summary-selected-graph" aria-label="선택 설비 위험 그래프">
          <div className="panel-heading compact">
            <div>
              <span>선택 설비</span>
              <h2>{selected ? displayEventAssetName(selected) : displayAssetName(selectedAsset)}</h2>
            </div>
            {selected ? <MapStatusBadge status={selected.status} /> : selectedAsset ? <MapStatusBadge status={selectedAsset.status} /> : null}
          </div>
          <div className="summary-risk-meter">
            <div>
              <span>위험 예측 확률</span>
              <strong>{riskPercent === null ? "-" : `${riskPercent}%`}</strong>
            </div>
            <i aria-hidden="true"><b style={{ width: `${riskPercent ?? 0}%` }} /></i>
            <small>map-report 원본처럼 고장 확정이 아니라 점검 우선순위 판단 근거로 표시합니다.</small>
          </div>
          <dl className="summary-selected-facts">
            <div><dt>권장 조치</dt><dd>{selected ? DECISION_LABEL[selected.recommendedDecision] : "선택 필요"}</dd></div>
            <div><dt>예상 영향</dt><dd>{formatMinutes(selected?.estimatedDowntimeMinutes ?? selectedAsset?.estimatedDowntimeMinutes ?? null)}</dd></div>
            <div><dt>근거</dt><dd>{selectedAsset?.topFactors[0] ? fieldFactorItem(selectedAsset.topFactors[0]) : fieldFailureLabel(selected?.predictedFailureType ?? "unavailable")}</dd></div>
          </dl>
        </article>
      </div>
    </section>
  );
}

function lineKey(asset: OperationsAsset) {
  return asset.line || asset.cell || asset.site || "미분류 라인";
}

interface StatusMapNode {
  id: string;
  label: string;
  status: OperationsRiskStatus;
  probability: number | null;
  asset: OperationsAsset | null;
  event: OperationsEvent | null;
}

function buildLineMapNodes(assets: OperationsAsset[], eventById: Map<string, OperationsEvent>) {
  return assets.map((asset): StatusMapNode => ({
    id: asset.assetId,
    label: displayAssetShortName(asset),
    status: asset.status,
    probability: asset.failureProbability,
    asset,
    event: asset.eventId ? eventById.get(asset.eventId) ?? null : null,
  })).sort((a, b) => a.label.localeCompare(b.label, "ko", { numeric: true }));
}

function OperationsStatusMapReport({
  model,
  selectedEvent,
  onSelectEvent,
}: {
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  onSelectEvent: (event: OperationsEvent) => void;
}) {
  const [focusedMapNodeId, setFocusedMapNodeId] = useState<string | null>(null);
  const eventById = useMemo(() => new Map(model.events.map((event) => [event.eventId, event])), [model.events]);
  const selectedAsset = model.assets.find((asset) => asset.eventId === selectedEvent?.eventId)
    ?? model.assets.find((asset) => asset.assetId === selectedEvent?.assetId)
    ?? model.assets[0]
    ?? null;
  const groupedLines = useMemo(() => {
    const buckets = new Map<string, OperationsAsset[]>();
    for (const asset of model.assets) {
      const key = lineKey(asset);
      buckets.set(key, [...(buckets.get(key) ?? []), asset]);
    }
    return [...buckets.entries()].map(([line, assets]) => ({
      line,
      assets,
      summary: model.lineRisk.find((item) => item.line === line),
      nodes: buildLineMapNodes(assets, eventById),
    }));
  }, [eventById, model.assets, model.events, model.lineRisk]);
  const priorityAssets = model.assets
    .filter((asset) => asset.recommendedDecision !== "continue_monitoring")
    .slice(0, 6);

  return (
    <div data-testid="operations-status-map-report">
      <header className="topbar">
        <div>
          <span>상태 요약 보고서</span>
          <h1>예지보전 상태 요약 보고서</h1>
          <p>현재 관측된 설비 판단과 운영 이벤트를 기준으로 위험 상태, 판단 대기, 데이터 품질 보류를 라인별로 요약합니다.</p>
        </div>
        <div className="report-meta">
          <small>생성 시각</small>
          <strong>{formatTimestamp(model.context.refreshedAt)}</strong>
          <span>{model.context.sourceMode === "canonical-runtime" ? "운영 데이터" : "보조 데이터"}</span>
        </div>
      </header>

      <section className="kpis" aria-label="예지보전 상태 KPI">
        <ReportKpi icon={Gauge} label="전체 설비" value={`${model.metrics.totalAssets}대`} detail={displayDataSource(model.context.sourceVersion)} />
        <ReportKpi icon={AlertTriangle} label="위험/경고" value={`${model.metrics.critical + model.metrics.warning}대`} detail={`위험 ${model.metrics.critical} · 경고 ${model.metrics.warning}`} tone="warm" />
        <ReportKpi icon={ClipboardCheck} label="판단 대기" value={`${model.metrics.pendingDecisions}건`} detail="점검·정지 검토·데이터 확인" />
        <ReportKpi icon={Clock3} label="예상 영향" value={formatMinutes(model.metrics.estimatedDowntimeMinutes)} detail="이벤트 합산" />
        <ReportKpi icon={DatabaseZap} label="품질 보류" value={`${model.metrics.dataQualityHold}건`} detail="고장 확정 표현 금지" tone="hold" />
      </section>

      <section className="priority-panel">
        <div className="panel-heading">
          <div><span>우선 확인 설비</span><h2>미결정 이벤트 우선순위</h2></div>
          <button type="button" className="filter-button"><Filter size={15} />미결정만</button>
        </div>
        <div className="priority-list">
          {priorityAssets.map((asset) => {
            const event = asset.eventId ? eventById.get(asset.eventId) : null;
            return (
              <button key={asset.assetId} type="button" className={asset.assetId === selectedAsset?.assetId ? "active" : ""} onClick={() => event && onSelectEvent(event)} disabled={!event}>
                <MapStatusBadge status={asset.status} />
                <strong>{displayAssetName(asset)}</strong>
                <span>{asset.line}</span>
                <b>{formatProbability(asset.failureProbability)}</b>
                <small>{DECISION_LABEL[asset.recommendedDecision]}</small>
                <em>{asset.assignedEngineer ? `담당 ${asset.assignedEngineer}` : "담당 미배정"}</em>
              </button>
            );
          })}
        </div>
      </section>

      <div className="main-grid">
        <section className="map-panel">
          <div className="panel-heading">
            <div><span>설비 상태 맵</span><h2>라인별 설비 상태</h2></div>
            <div className="legend">
              {Object.entries(MAP_STATUS_META).map(([key, meta]) => <i key={key} className={`dot ${meta.tone}`}>{meta.label}</i>)}
            </div>
          </div>
          <div className="line-map">
            {groupedLines.map((line) => (
              <article key={line.line} className="line-row">
                <header>
                  <strong>{line.line}</strong>
                  <small>맵 표시 {line.nodes.length}대 · 평균 위험 {formatProbability(line.summary?.averageRisk ?? null)}</small>
                </header>
                <div className="asset-grid">
                  {line.nodes.map((node) => {
                    const selected = focusedMapNodeId === node.id || (!focusedMapNodeId && node.asset?.assetId === selectedAsset?.assetId);
                    return (
                      <button
                        key={node.id}
                        type="button"
                        className={`asset-node ${MAP_STATUS_META[node.status].tone} ${selected ? "selected" : ""}`}
                        aria-pressed={selected}
                        aria-disabled={!node.event}
                        onClick={() => {
                          setFocusedMapNodeId(node.id);
                          if (node.event) onSelectEvent(node.event);
                        }}
                        title={`${node.asset ? displayAssetName(node.asset) : `${line.line} ${node.label} 설비`} · ${MAP_STATUS_META[node.status].label} · 위험 예측 확률 ${formatProbability(node.probability)}${node.asset ? "" : " · 클릭 시 같은 라인 대표 이벤트로 이동"}`}
                      >
                        <span>{node.label}</span>
                      </button>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="report-panel">
          {selectedAsset ? (
            <>
              <div className="panel-heading compact">
                <div>
                  <span>선택 설비 상세</span>
                  <h2>{selectedAsset.displayName}</h2>
                  <small className="sub-id">{selectedAsset.line} · {selectedAsset.assignedEngineer ? `담당 ${selectedAsset.assignedEngineer}` : "담당 미배정"}</small>
                </div>
                <MapStatusBadge status={selectedAsset.status} />
              </div>
              <dl className="detail-grid">
                <div><dt>설비 유형</dt><dd>{selectedAsset.assetType}</dd></div>
                <div><dt>위치</dt><dd>{selectedAsset.site} / {selectedAsset.cell}</dd></div>
                <div><dt>위험 예측 확률</dt><dd>{formatProbability(selectedAsset.failureProbability)}</dd></div>
                <div><dt>신뢰도</dt><dd>{selectedAsset.confidence}</dd></div>
                <div><dt>권장 조치</dt><dd>{DECISION_LABEL[selectedAsset.recommendedDecision]}</dd></div>
                <div><dt>예상 영향</dt><dd>{formatMinutes(selectedAsset.estimatedDowntimeMinutes)}</dd></div>
              </dl>
              <section className="narrative">
                <span>보고서 요약</span>
                <p>{selectedAsset.status === "data_quality_hold" ? `${selectedAsset.displayName}는 데이터 품질 확인 보류 상태입니다. 고장 위험으로 단정하지 않고 센서 수집 상태와 데이터 처리 상태를 먼저 확인해야 합니다.` : `${selectedAsset.displayName}는 ${MAP_STATUS_META[selectedAsset.status].label} 상태이며, ${DECISION_LABEL[selectedAsset.recommendedDecision]} 대상으로 분류됩니다. 모델 결과는 점검 우선순위 판단 근거이며 고장 확정은 아닙니다.`}</p>
              </section>
              <section className="inspection-card">
                <header><Wrench size={16} /><strong>점검 근거</strong></header>
                <ul>
                  {selectedAsset.topFactors.slice(0, 3).map((factor) => <li key={factor.id}><b>{factor.label}</b>: {Math.round(factor.contribution * 100)}%</li>)}
                  {!selectedAsset.topFactors.length ? <li>세부 설명 요인이 제공되지 않았습니다.</li> : null}
                </ul>
              </section>
              <section className="limitations">
                <header><ShieldCheck size={16} /><strong>한계</strong></header>
                <p>공정 순서도나 실제 공장 도면이 아니라 운영 요약용 상태 맵입니다. 모델은 원인과 고장 발생을 확정하지 않습니다.</p>
              </section>
            </>
          ) : <p>선택 가능한 설비가 없습니다.</p>}
        </aside>
      </div>
    </div>
  );
}

function OperationsSummaryReport({
  model,
  selectedEvent,
  detail,
  onSelectEvent,
}: {
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  onSelectEvent: (event: OperationsEvent) => void;
}) {
  const actionableEvents = model.events
    .filter((event) => event.recommendedDecision !== "continue_monitoring")
    .slice(0, 5);
  const criticalLines = [...model.lineRisk]
    .sort((a, b) => (b.averageRisk ?? -1) - (a.averageRisk ?? -1))
    .slice(0, 4);
  const qualityEvents = model.events.filter((event) => event.status === "data_quality_hold");
  const selected = selectedEvent ?? actionableEvents[0] ?? model.events[0] ?? null;

  return (
    <div className="operations-summary-report" data-testid="operations-summary-report">
      <header className="topbar">
        <div>
          <span>요약 보고서</span>
          <h1>예지보전 운영 요약 보고서</h1>
          <p>상태 맵의 전체 흐름과 점검 요청의 현장 항목을 공유하기 쉬운 한 장 요약으로 정리합니다.</p>
        </div>
        <div className="report-meta">
          <small>작성 상태</small>
          <strong>{model.context.sourceMode === "canonical-runtime" ? "운영 데이터 요약" : "보조 데이터 요약"}</strong>
          <span>{formatTimestamp(model.context.refreshedAt)}</span>
        </div>
      </header>

      <section className="summary-hero">
        <div>
          <span>이번 스냅샷 판단</span>
          <h2>{model.metrics.critical + model.metrics.warning}대 설비가 위험/경고 상태이며 {model.metrics.pendingDecisions}건의 사람 판단이 대기 중입니다.</h2>
          <p>이 보고서는 고장 확정이나 정비 완료를 주장하지 않고, 모델 예측 결과를 기준으로 운영 검토·현장 점검·데이터 확인 대상을 분리합니다.</p>
        </div>
        <dl>
          <div><dt>전체 설비</dt><dd>{model.metrics.totalAssets}대</dd></div>
          <div><dt>평균 위험</dt><dd>{formatProbability(model.metrics.averageRisk)}</dd></div>
          <div><dt>예상 영향</dt><dd>{formatMinutes(model.metrics.estimatedDowntimeMinutes)}</dd></div>
          <div><dt>품질 보류</dt><dd>{qualityEvents.length}건</dd></div>
        </dl>
      </section>

      <OperationsSummaryGraphBoard model={model} selected={selected} />

      <OperationsMapReportAssetDetailView model={model} selectedEvent={selectedEvent} detail={detail} onSelectEvent={onSelectEvent} statusMeta={MAP_STATUS_META} />

      <div className="summary-grid">
        <section className="report-panel">
          <div className="panel-heading compact"><div><span>MANAGER SUMMARY</span><h2>운영 판단 요약</h2></div></div>
          <div className="summary-decision-list">
            <article><strong>1. 우선순위</strong><p>위험/경고 설비를 먼저 확인하고, 생산 영향이 큰 설비는 Operations에서 결정 메모를 남깁니다.</p></article>
            <article><strong>2. 현장 확인</strong><p>점검 요청 보고서의 설비별 센서 근거와 위치 근거 유무를 현장 담당자에게 전달합니다.</p></article>
            <article><strong>3. 데이터 품질</strong><p>품질 보류 이벤트는 위험 수치로 단정하지 않고 원천 데이터 확인 대상으로 분리합니다.</p></article>
          </div>
        </section>

        <section className="report-panel">
          <div className="panel-heading compact"><div><span>LINE RISK</span><h2>라인별 위험 상위</h2></div></div>
          <div className="summary-line-list">
            {criticalLines.map((line) => (
              <article key={line.line}>
                <div><strong>{line.line}</strong><span>설비 {line.total}대 · 위험 {line.critical} · 경고 {line.warning}</span></div>
                <b>{formatProbability(line.averageRisk)}</b>
              </article>
            ))}
          </div>
        </section>
      </div>

      <section className="priority-panel summary-event-panel">
        <div className="panel-heading">
          <div><span>검토 이벤트</span><h2>보고서에 포함할 이벤트</h2></div>
          {selected ? <MapStatusBadge status={selected.status} /> : null}
        </div>
        <div className="summary-event-list">
          {actionableEvents.map((event) => (
            <button key={event.eventId} type="button" className={event.eventId === selected?.eventId ? "active" : ""} onClick={() => onSelectEvent(event)}>
              <strong>{displayEventAssetName(event)}</strong>
              <span>{event.line} · 관측 {formatTimestamp(event.observedAt)}</span>
              <b>{formatProbability(event.failureProbability)}</b>
              <small>{DECISION_LABEL[event.recommendedDecision]}</small>
            </button>
          ))}
        </div>
        {selected ? (
          <aside className="summary-selected-note">
            <strong>{displayEventAssetName(selected)}</strong>
            <p>{selected.status === "data_quality_hold" ? "데이터 품질 확인이 먼저 필요한 이벤트입니다." : `${DECISION_LABEL[selected.recommendedDecision]} 대상으로 분류됐으며 예상 영향은 ${formatMinutes(selected.estimatedDowntimeMinutes)}입니다.`}</p>
          </aside>
        ) : null}
      </section>

      <section className="priority-panel warning-strip">
        <ShieldCheck size={18} />
        <p>이 요약 보고서는 운영 공유용 스냅샷입니다. 고장 발생, 원인 확정, 정비 완료, 자동 제어 수행을 의미하지 않습니다.</p>
      </section>
    </div>
  );
}

export function OperationsReportsPage({
  activeTab,
  model,
  selectedEvent,
  detail,
  detailLoading,
  detailError,
  canMaterializeAgentSummary,
  experienceKind,
  userScope,
  onSelectTab,
  onSelectEvent,
  onBackToOverview,
  onOpenOperations,
  onRetryDetail,
}: {
  activeTab: OperationsReportTab;
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  detailLoading: boolean;
  detailError: string | null;
  canMaterializeAgentSummary: boolean;
  experienceKind: ReliabilityExperienceKind;
  userScope: string;
  onSelectTab: (tab: OperationsReportTab) => void;
  onSelectEvent: (event: OperationsEvent) => void;
  onBackToOverview: () => void;
  onOpenOperations: (event: OperationsEvent) => void;
  onRetryDetail: () => void;
}) {
  const visibleTabs = experienceKind === "executive"
    ? REPORT_TABS.filter((tab) => tab.id === "executive-brief")
    : REPORT_TABS;
  return (
    <div className="operations-page operations-reports-page" data-testid="operations-reports">
      <div className="operations-report-tabs" role="tablist" aria-label="보고서 종류">
        {visibleTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => onSelectTab(tab.id)}>
              <Icon size={16} />
              <span>{tab.label}</span>
              <small>{tab.description}</small>
            </button>
          );
        })}
        <button type="button" className="operations-report-print" onClick={() => window.print()}><Printer size={15} />출력</button>
      </div>

      {activeTab === "status-map" ? (
        <OperationsStatusMapReport model={model} selectedEvent={selectedEvent} onSelectEvent={onSelectEvent} />
      ) : activeTab === "inspection-request" ? (
        <OperationsInspectionReportPage />
      ) : activeTab === "summary-report" ? (
        <OperationsSummaryReport model={model} selectedEvent={selectedEvent} detail={detail} onSelectEvent={onSelectEvent} />
      ) : (
        <OperationsExecutiveReportPage model={model} selectedEvent={selectedEvent} detail={detail} detailLoading={detailLoading} detailError={detailError} canMaterializeAgentSummary={canMaterializeAgentSummary} userScope={userScope} onBackToOverview={onBackToOverview} onOpenOperations={onOpenOperations} onRetryDetail={onRetryDetail} />
      )}
    </div>
  );
}
