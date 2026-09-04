import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  createOperationsDecisionSupportBrief,
  getOperationsDecisionSupportBrief,
} from "../../../api";
import type {
  OperationsDecisionBriefRole,
  OperationsDecisionSupportResponse,
} from "../api/operationsContracts";
import { displayAssetName, humanizeOperationalText } from "../displayLabels";

interface Props {
  assetId: string;
  projectId: string;
  workspaceId: string;
  evidenceSnapshotId: string | null;
  decisionAsOf: string | null;
  riskStatus: string;
  role: OperationsDecisionBriefRole;
  canMaterialize: boolean;
}

const OPTION_LABEL: Record<string, string> = {
  stop_now: "지금 정지",
  planned_maintenance: "계획 정비",
  continue_operation: "제한 운전",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "생성 대기",
  running: "근거 확인 중",
  completed: "근거 확인 완료",
  partial: "일부 근거 확인",
  failed: "근거 확인 실패",
  passed: "시점 일치",
  failed_validation: "시점 불일치",
  not_measured: "시점 미확인",
  calculated: "영향 계산 완료",
  not_calculable: "계산 근거 부족",
  verified: "확인됨",
  assumed_demo: "가정 데이터",
  not_connected: "연결되지 않음",
  unknown: "확인 필요",
  conflicting: "근거 충돌",
  critical: "긴급",
  warning: "주의",
  attention: "관찰 필요",
  normal: "정상",
  data_quality_hold: "데이터 확인 필요",
};

const RELATION_LABEL: Record<string, string> = {
  asset_executes_operation: "설비가 담당하는 공정",
  operation_assigned_to_order: "공정에 연결된 생산오더",
  order_contains_wip: "생산오더의 재공품",
  wip_processed_by_asset: "설비에서 처리 중인 재공품",
  order_contains_lot: "생산오더에 연결된 품질 Lot",
  lot_has_delivery_commitment: "품질 Lot의 납기 약속",
  alternative_resource_supports_operation: "대체 설비가 지원하는 공정",
  asset_requires_part: "정비에 필요한 부품",
  asset_requires_skill: "정비에 필요한 기술",
  technician_has_skill: "작업자가 보유한 기술",
};

const DOMAIN_LABEL: Record<string, string> = {
  production: "생산 계획",
  quality_delivery: "품질·납기",
  maintenance_readiness: "정비 준비",
  inventory: "부품 재고",
  workforce: "작업 인력",
  relation: "업무 관계",
};

const SOURCE_LABEL: Record<string, string> = {
  synthetic_demo_context: "검증용 운영 가정",
  canonical: "확인된 운영 데이터",
  not_declared: "출처 분류 미제공",
};

function labelOf(value: string | null | undefined): string {
  if (!value) return "확인 필요";
  return STATUS_LABEL[value] ?? humanizeOperationalText(value.replaceAll("_", " "));
}

function domainLabel(value: string): string {
  return DOMAIN_LABEL[value] ?? humanizeOperationalText(value.replaceAll("_", " "));
}

function referenceLabel(value: string): string {
  const [kind, ...idParts] = value.split(":");
  const id = idParts.join(":") || value;
  if (kind === "asset") return displayAssetName({ assetId: id });
  const kindLabels: Record<string, string> = {
    operation: "공정",
    production_order: "생산오더",
    wip: "재공품",
    quality_lot: "품질 Lot",
    delivery_commitment: "납기 약속",
    alternative_resource: "대체 설비",
    spare_part: "정비 부품",
    skill: "필요 기술",
    technician: "작업자",
  };
  return kindLabels[kind] ? `${kindLabels[kind]} ${id}` : id;
}

function formatDecisionTime(value: string | null | undefined): string {
  if (!value) return "미연결";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function OperationalDecisionSupportPanel({
  assetId,
  projectId,
  workspaceId,
  evidenceSnapshotId,
  decisionAsOf,
  riskStatus,
  role,
  canMaterialize,
}: Props) {
  const [response, setResponse] = useState<OperationsDecisionSupportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [materializing, setMaterializing] = useState(false);
  const [error, setError] = useState("");
  const request = useMemo(() => {
    if (!evidenceSnapshotId || !decisionAsOf) return null;
    return {
      assetId,
      projectId,
      workspaceId,
      evidenceSnapshotId,
      decisionAsOf,
      role,
    };
  }, [assetId, decisionAsOf, evidenceSnapshotId, projectId, role, workspaceId]);

  useEffect(() => {
    if (!request) {
      setResponse(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    void getOperationsDecisionSupportBrief(request)
      .then((value) => {
        if (active) setResponse(value);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "운영 판단 지원을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [request]);

  const materialize = async () => {
    if (!request || !canMaterialize) return;
    setMaterializing(true);
    setError("");
    try {
      setResponse(await createOperationsDecisionSupportBrief({ ...request, riskStatus }));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "운영 판단 지원을 생성하지 못했습니다.");
    } finally {
      setMaterializing(false);
    }
  };

  const brief = response?.brief;
  const versions = brief ? Object.entries(brief.frame.context_version_set) : [];

  return (
    <section className="mvp-decision-support" aria-label="운영 판단 지원">
      <header>
        <div>
          <strong>운영 판단 지원</strong>
          <small>근거·운영 맥락 기반 읽기 전용 Brief</small>
        </div>
        <button
          type="button"
          className="mvp-agent-review-refresh"
          onClick={() => void materialize()}
          disabled={!request || !canMaterialize || materializing}
        >
          <RefreshCw size={13} className={materializing ? "mvp-action-spinner" : ""} />
          {materializing ? "생성 중" : canMaterialize ? "맥락 갱신" : "조회 전용"}
        </button>
      </header>

      {!request ? <p>Evidence snapshot과 관측 시점이 연결되면 판단 맥락을 조회할 수 있습니다.</p> : null}
      {loading ? <p>저장된 판단 맥락을 조회하는 중입니다.</p> : null}
      {error ? <p className="mvp-decision-support__error">{error}</p> : null}
      {!loading && request && !error && !brief ? (
        <p>저장된 Brief가 없습니다. 권한이 있는 담당자가 명시적으로 생성해야 합니다.</p>
      ) : null}

      {brief ? (
        <>
          <div className="mvp-decision-support__status">
            <span>{labelOf(response?.trace.status)}</span>
            <span>{response?.trace.reused ? "저장본 재사용" : "새 맥락 생성"}</span>
            <span>{labelOf(response?.trace.temporal_validation)}</span>
          </div>

          <dl className="mvp-decision-support__facts">
            <div><dt>위험 상태</dt><dd>{labelOf(brief.frame.risk_status)}</dd></div>
            <div><dt>생산오더</dt><dd>{brief.why_now.order_ids.join(", ") || "미연결"}</dd></div>
            <div><dt>재공 수량</dt><dd>{brief.why_now.wip_units ?? "미산정"}</dd></div>
            <div><dt>가장 가까운 납기</dt><dd>{formatDecisionTime(brief.why_now.earliest_due_at)}</dd></div>
          </dl>

          <div className="mvp-decision-support__section">
            <strong>관계와 제약</strong>
            {brief.relationships.length ? (
              <ol>
                {brief.relationships.slice(0, 6).map((item, index) => (
                  <li key={`${item.relationship_type}-${item.from_ref}-${item.to_ref}-${index}`}>
                    <b>{RELATION_LABEL[item.relationship_type] ?? humanizeOperationalText(item.relationship_type.replaceAll("_", " "))}</b>
                    <span>{referenceLabel(item.from_ref)} → {referenceLabel(item.to_ref)}</span>
                    <small>{labelOf(item.status)}</small>
                  </li>
                ))}
              </ol>
            ) : <p>확인 가능한 관계가 없습니다.</p>}
          </div>

          <div className="mvp-decision-support__section">
            <strong>조건부 선택지 비교</strong>
            <div className="mvp-decision-support__options">
              {brief.option_comparison.map((item) => (
                <article key={item.option}>
                  <b>{OPTION_LABEL[item.option] ?? item.option}</b>
                  <span>{labelOf(item.calculation_state)}</span>
                  <small>자동 선택하지 않음</small>
                </article>
              ))}
            </div>
          </div>

          {brief.gaps.length || brief.why_now.decision_blockers.length ? (
            <div className="mvp-decision-support__section is-warning">
              <strong>판단에 필요한 추가 확인</strong>
              <ul>
                {brief.why_now.decision_blockers.map((item) => <li key={item}>{humanizeOperationalText(item.replaceAll("_", " "))}</li>)}
                {brief.gaps.map((item, index) => (
                  <li key={`${item.owner_domain}-${item.state}-${index}`}>
                    {domainLabel(item.owner_domain)}: {labelOf(item.state)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <details className="mvp-decision-support__sources">
            <summary>기술 출처와 기준 시점</summary>
            <small>판단 기준 {formatDecisionTime(brief.frame.decision_as_of)}</small>
            {versions.map(([domain, version]) => (
              <code key={domain}>{domainLabel(domain)}: {version}</code>
            ))}
            {Object.entries(brief.source_classifications).map(([domain, source]) => (
              <small key={domain}>{domainLabel(domain)}: {SOURCE_LABEL[source] ?? labelOf(source)}</small>
            ))}
          </details>
          <small>AI는 계산 결과를 설명하며 WorkOrder·정비 실행을 생성하지 않습니다.</small>
        </>
      ) : null}
    </section>
  );
}
