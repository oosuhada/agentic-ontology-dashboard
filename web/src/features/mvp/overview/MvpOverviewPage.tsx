import { ArrowRight, Boxes, ClipboardCheck, FileText, RefreshCw } from "lucide-react";
import type { MvpBootstrapModel } from "../api/mvpContracts";
import {
  DECISION_LABEL,
  MvpConfidenceBadge,
  MvpPanel,
  MvpState,
  MvpStatusBadge,
  formatMinutes,
  formatProbability,
  formatTimestamp,
} from "../components/MvpUi";

export function MvpOverviewPage({
  model,
  onOpenAsset,
  onOpenEvent,
  onOpenReport,
  onRefresh,
}: {
  model: MvpBootstrapModel;
  onOpenAsset: (assetId: string, eventId: string | null) => void;
  onOpenEvent: (eventId: string, assetId: string) => void;
  onOpenReport: (eventId: string | null, assetId: string | null) => void;
  onRefresh: () => void;
}) {
  const { metrics } = model;
  const topAssets = model.assets.slice(0, 6);
  const pendingEvents = model.events.filter((item) => item.recommendedDecision !== "continue_monitoring").slice(0, 6);
  const maxLineRisk = Math.max(1, ...model.lineRisk.map((item) => item.averageRisk ?? 0));

  return (
    <div className="mvp-page mvp-overview-page" data-testid="mvp-overview">
      <section className="mvp-kpi-grid" aria-label="운영 위험 KPI">
        <article className="mvp-kpi is-critical"><span>Critical</span><strong>{metrics.critical}</strong><small>사람의 긴급 검토가 필요한 설비</small></article>
        <article className="mvp-kpi is-warning"><span>Warning</span><strong>{metrics.warning}</strong><small>현장 점검이 필요한 설비</small></article>
        <article className="mvp-kpi"><span>평균 위험도</span><strong>{formatProbability(metrics.averageRisk)}</strong><small>품질 보류를 제외한 평균</small></article>
        <article className="mvp-kpi"><span>예상 Downtime</span><strong>{formatMinutes(metrics.estimatedDowntimeMinutes)}</strong><small>Event 기준 생산 영향 합계</small></article>
        <article className="mvp-kpi"><span>판단 대기</span><strong>{metrics.pendingDecisions}</strong><small>점검·정지 검토·데이터 확인</small></article>
        <article className="mvp-kpi is-hold"><span>Data quality hold</span><strong>{metrics.dataQualityHold}</strong><small>고장 집계가 아닌 판단 보류</small></article>
      </section>

      <section className="mvp-overview-actions" aria-label="주요 이동">
        <button type="button" className="mvp-button primary" onClick={() => topAssets[0] && onOpenAsset(topAssets[0].assetId, topAssets[0].eventId)} disabled={!topAssets.length}><Boxes size={15} />우선 설비 열기</button>
        <button type="button" className="mvp-button secondary" onClick={() => pendingEvents[0] && onOpenEvent(pendingEvents[0].eventId, pendingEvents[0].assetId)} disabled={!pendingEvents.length}><ClipboardCheck size={15} />판단 업무 열기</button>
        <button type="button" className="mvp-button secondary" onClick={() => onOpenReport(pendingEvents[0]?.eventId ?? null, pendingEvents[0]?.assetId ?? null)}><FileText size={15} />Executive Report</button>
        <button type="button" className="mvp-button ghost" onClick={onRefresh}><RefreshCw size={15} />새로고침</button>
      </section>

      <div className="mvp-overview-grid">
        <MvpPanel title="라인별 위험 현황" eyebrow="PRODUCTION RISK">
          {model.lineRisk.length ? (
            <div className="mvp-line-risk-list">
              {model.lineRisk.slice(0, 8).map((line) => (
                <article key={line.line}>
                  <header><strong>{line.line}</strong><span>{line.total} assets · 평균 {formatProbability(line.averageRisk)}</span></header>
                  <div className="mvp-risk-track" aria-label={`${line.line} 평균 위험 ${formatProbability(line.averageRisk)}`}><i style={{ width: `${Math.max(4, ((line.averageRisk ?? 0) / maxLineRisk) * 100)}%` }} /></div>
                  <footer><span className="is-critical">위험 {line.critical}</span><span className="is-warning">경고 {line.warning}</span><span>주의 {line.attention}</span>{line.dataQualityHold ? <span className="is-hold">데이터 확인 {line.dataQualityHold}</span> : null}</footer>
                </article>
              ))}
            </div>
          ) : <MvpState kind="empty" title="라인 데이터가 없습니다" detail="연결된 Result Artifact에 라인 또는 위치 정보가 없습니다." />}
        </MvpPanel>

        <MvpPanel title="고위험 설비 Top N" eyebrow="ASSET PRIORITY">
          {topAssets.length ? (
            <div className="mvp-priority-list">
              {topAssets.map((asset, index) => (
                <button type="button" key={asset.assetId} onClick={() => onOpenAsset(asset.assetId, asset.eventId)}>
                  <span className="mvp-rank">{String(index + 1).padStart(2, "0")}</span>
                  <div><strong>{asset.displayName}</strong><small>{asset.assetId} · {asset.line}</small></div>
                  <MvpStatusBadge status={asset.status} />
                  <b>{formatProbability(asset.failureProbability)}</b>
                  <ArrowRight size={15} />
                </button>
              ))}
            </div>
          ) : <MvpState kind="empty" title="표시할 설비가 없습니다" detail="현재 Dataset Version에서 조회된 설비가 없습니다." />}
        </MvpPanel>
      </div>

      <MvpPanel title="판단 대기 Event" eyebrow="OPERATIONS INBOX" className="mvp-event-inbox-panel">
        {pendingEvents.length ? (
          <div className="mvp-event-inbox">
            {pendingEvents.map((item) => (
              <button type="button" key={item.eventId} onClick={() => onOpenEvent(item.eventId, item.assetId)}>
                <div className="mvp-event-title"><MvpStatusBadge status={item.status} /><strong>{item.assetName}</strong><code>{item.eventId}</code></div>
                <div className="mvp-event-metrics"><span>위험 <b>{formatProbability(item.failureProbability)}</b></span><MvpConfidenceBadge confidence={item.confidence} /><span>영향 <b>{formatMinutes(item.estimatedDowntimeMinutes)}</b></span></div>
                <div className="mvp-event-decision"><span>{DECISION_LABEL[item.recommendedDecision]}</span><small>{item.assignedEngineer ?? "미배정"} · {formatTimestamp(item.observedAt)}</small></div>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        ) : <MvpState kind="empty" title="판단 대기 Event가 없습니다" detail="현재 정책 기준으로 즉시 점검하거나 보류할 Event가 없습니다." />}
      </MvpPanel>
    </div>
  );
}
