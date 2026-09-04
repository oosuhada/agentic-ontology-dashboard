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
  locale?: "ko-KR" | "en-US";
}

const OPTION_LABEL: Record<string, [string, string]> = {
  stop_now: ["지금 정지", "Stop now"],
  planned_maintenance: ["계획 정비", "Planned maintenance"],
  continue_operation: ["제한 운전", "Continue with limits"],
};

const STATUS_LABEL: Record<string, [string, string]> = {
  pending: ["생성 대기", "Pending generation"],
  running: ["근거 확인 중", "Reviewing evidence"],
  completed: ["근거 확인 완료", "Evidence review complete"],
  partial: ["일부 근거 확인", "Partial evidence"],
  failed: ["근거 확인 실패", "Evidence review failed"],
  passed: ["시점 일치", "Timestamp aligned"],
  failed_validation: ["시점 불일치", "Timestamp mismatch"],
  not_measured: ["시점 미확인", "Timestamp not verified"],
  calculated: ["영향 계산 완료", "Impact calculated"],
  not_calculable: ["계산 근거 부족", "Insufficient calculation evidence"],
  verified: ["확인됨", "Verified"],
  assumed_demo: ["가정 데이터", "Assumed data"],
  not_connected: ["연결되지 않음", "Not connected"],
  unknown: ["확인 필요", "Needs review"],
  conflicting: ["근거 충돌", "Conflicting evidence"],
  critical: ["긴급", "Critical"],
  warning: ["주의", "Warning"],
  attention: ["관찰 필요", "Attention"],
  normal: ["정상", "Normal"],
  data_quality_hold: ["데이터 확인 필요", "Data quality hold"],
};

const RELATION_LABEL: Record<string, [string, string]> = {
  asset_executes_operation: ["설비가 담당하는 공정", "Operation executed by asset"],
  operation_assigned_to_order: ["공정에 연결된 생산오더", "Production order assigned to operation"],
  order_contains_wip: ["생산오더의 재공품", "WIP in production order"],
  wip_processed_by_asset: ["설비에서 처리 중인 재공품", "WIP processed by asset"],
  order_contains_lot: ["생산오더에 연결된 품질 Lot", "Quality lot in production order"],
  lot_has_delivery_commitment: ["품질 Lot의 납기 약속", "Delivery commitment for quality lot"],
  alternative_resource_supports_operation: ["대체 설비가 지원하는 공정", "Operation supported by alternate resource"],
  asset_requires_part: ["정비에 필요한 부품", "Part required for maintenance"],
  asset_requires_skill: ["정비에 필요한 기술", "Skill required for maintenance"],
  technician_has_skill: ["작업자가 보유한 기술", "Technician skill"],
};

const DOMAIN_LABEL: Record<string, [string, string]> = {
  production: ["생산 계획", "Production planning"],
  quality_delivery: ["품질·납기", "Quality & delivery"],
  maintenance_readiness: ["정비 준비", "Maintenance readiness"],
  inventory: ["부품 재고", "Parts inventory"],
  workforce: ["작업 인력", "Workforce"],
  relation: ["업무 관계", "Operational relationships"],
};

const SOURCE_LABEL: Record<string, [string, string]> = {
  synthetic_demo_context: ["검증용 운영 가정", "Validation assumption"],
  canonical: ["확인된 운영 데이터", "Verified operational data"],
  not_declared: ["출처 분류 미제공", "Source classification unavailable"],
};

function localize(english: boolean, ko: string, en: string): string {
  return english ? en : ko;
}

function localizedFallback(value: string, english: boolean): string {
  return english ? value.replaceAll("_", " ") : humanizeOperationalText(value.replaceAll("_", " "));
}

function labelOf(value: string | null | undefined, english: boolean): string {
  if (!value) return localize(english, "확인 필요", "Needs review");
  return STATUS_LABEL[value]?.[english ? 1 : 0] ?? localizedFallback(value, english);
}

function domainLabel(value: string, english: boolean): string {
  return DOMAIN_LABEL[value]?.[english ? 1 : 0] ?? localizedFallback(value, english);
}

function referenceLabel(value: string, english: boolean): string {
  const [kind, ...idParts] = value.split(":");
  const id = idParts.join(":") || value;
  if (kind === "asset") return english ? id : displayAssetName({ assetId: id });
  const kindLabels: Record<string, [string, string]> = {
    operation: ["공정", "Operation"],
    production_order: ["생산오더", "Production order"],
    wip: ["재공품", "WIP"],
    quality_lot: ["품질 Lot", "Quality lot"],
    delivery_commitment: ["납기 약속", "Delivery commitment"],
    alternative_resource: ["대체 설비", "Alternate resource"],
    spare_part: ["정비 부품", "Spare part"],
    skill: ["필요 기술", "Required skill"],
    technician: ["작업자", "Technician"],
  };
  return kindLabels[kind] ? `${kindLabels[kind][english ? 1 : 0]} ${id}` : id;
}

function formatDecisionTime(value: string | null | undefined, english: boolean): string {
  if (!value) return localize(english, "미연결", "Not connected");
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(english ? "en-US" : "ko-KR", {
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
  locale = "ko-KR",
}: Props) {
  const english = locale === "en-US";
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
        if (active) setError(reason instanceof Error ? reason.message : localize(english, "운영 판단 지원을 불러오지 못했습니다.", "Unable to load operational decision support."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [english, request]);

  const materialize = async () => {
    if (!request || !canMaterialize) return;
    setMaterializing(true);
    setError("");
    try {
      setResponse(await createOperationsDecisionSupportBrief({ ...request, riskStatus }));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : localize(english, "운영 판단 지원을 생성하지 못했습니다.", "Unable to generate operational decision support."));
    } finally {
      setMaterializing(false);
    }
  };

  const brief = response?.brief;
  const versions = brief ? Object.entries(brief.frame.context_version_set) : [];

  return (
    <section className="mvp-decision-support" aria-label={localize(english, "운영 판단 지원", "Operational decision support")}>
      <header>
        <div>
          <strong>{localize(english, "운영 판단 지원", "Operational decision support")}</strong>
          <small>{localize(english, "근거·운영 맥락 기반 읽기 전용 Brief", "Read-only brief grounded in evidence and operational context")}</small>
        </div>
        <button
          type="button"
          className="mvp-agent-review-refresh"
          onClick={() => void materialize()}
          disabled={!request || !canMaterialize || materializing}
        >
          <RefreshCw size={13} className={materializing ? "mvp-action-spinner" : ""} />
          {materializing ? localize(english, "생성 중", "Generating") : canMaterialize ? localize(english, "맥락 갱신", "Refresh context") : localize(english, "조회 전용", "Read only")}
        </button>
      </header>

      {!request ? <p>{localize(english, "Evidence snapshot과 관측 시점이 연결되면 판단 맥락을 조회할 수 있습니다.", "Decision context becomes available when the evidence snapshot and observation timestamp are connected.")}</p> : null}
      {loading ? <p>{localize(english, "저장된 판단 맥락을 조회하는 중입니다.", "Loading stored decision context.")}</p> : null}
      {error ? <p className="mvp-decision-support__error">{error}</p> : null}
      {!loading && request && !error && !brief ? (
        <p>{localize(english, "저장된 Brief가 없습니다. 권한이 있는 담당자가 명시적으로 생성해야 합니다.", "No stored brief is available. An authorized user must generate it explicitly.")}</p>
      ) : null}

      {brief ? (
        <>
          <div className="mvp-decision-support__status">
            <span>{labelOf(response?.trace.status, english)}</span>
            <span>{response?.trace.reused ? localize(english, "저장본 재사용", "Stored brief reused") : localize(english, "새 맥락 생성", "New context generated")}</span>
            <span>{labelOf(response?.trace.temporal_validation, english)}</span>
          </div>

          <dl className="mvp-decision-support__facts">
            <div><dt>{localize(english, "위험 상태", "Risk status")}</dt><dd>{labelOf(brief.frame.risk_status, english)}</dd></div>
            <div><dt>{localize(english, "생산오더", "Production orders")}</dt><dd>{brief.why_now.order_ids.join(", ") || localize(english, "미연결", "Not connected")}</dd></div>
            <div><dt>{localize(english, "재공 수량", "WIP units")}</dt><dd>{brief.why_now.wip_units ?? localize(english, "미산정", "Not calculated")}</dd></div>
            <div><dt>{localize(english, "가장 가까운 납기", "Nearest due date")}</dt><dd>{formatDecisionTime(brief.why_now.earliest_due_at, english)}</dd></div>
          </dl>

          <div className="mvp-decision-support__section">
            <strong>{localize(english, "관계와 제약", "Relationships and constraints")}</strong>
            {brief.relationships.length ? (
              <ol>
                {brief.relationships.slice(0, 6).map((item, index) => (
                  <li key={`${item.relationship_type}-${item.from_ref}-${item.to_ref}-${index}`}>
                    <b>{RELATION_LABEL[item.relationship_type]?.[english ? 1 : 0] ?? localizedFallback(item.relationship_type, english)}</b>
                    <span>{referenceLabel(item.from_ref, english)} → {referenceLabel(item.to_ref, english)}</span>
                    <small>{labelOf(item.status, english)}</small>
                  </li>
                ))}
              </ol>
            ) : <p>{localize(english, "확인 가능한 관계가 없습니다.", "No verifiable relationships are available.")}</p>}
          </div>

          <div className="mvp-decision-support__section">
            <strong>{localize(english, "조건부 선택지 비교", "Conditional option comparison")}</strong>
            <div className="mvp-decision-support__options">
              {brief.option_comparison.map((item) => (
                <article key={item.option}>
                  <b>{OPTION_LABEL[item.option]?.[english ? 1 : 0] ?? item.option}</b>
                  <span>{labelOf(item.calculation_state, english)}</span>
                  <small>{localize(english, "자동 선택하지 않음", "Not selected automatically")}</small>
                </article>
              ))}
            </div>
          </div>

          {brief.gaps.length || brief.why_now.decision_blockers.length ? (
            <div className="mvp-decision-support__section is-warning">
              <strong>{localize(english, "판단에 필요한 추가 확인", "Additional checks required for decision")}</strong>
              <ul>
                {brief.why_now.decision_blockers.map((item) => <li key={item}>{localizedFallback(item, english)}</li>)}
                {brief.gaps.map((item, index) => (
                  <li key={`${item.owner_domain}-${item.state}-${index}`}>
                    {domainLabel(item.owner_domain, english)}: {labelOf(item.state, english)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <details className="mvp-decision-support__sources">
            <summary>{localize(english, "기술 출처와 기준 시점", "Technical sources and reference time")}</summary>
            <small>{localize(english, "판단 기준", "Decision basis")} {formatDecisionTime(brief.frame.decision_as_of, english)}</small>
            {versions.map(([domain, version]) => (
              <code key={domain}>{domainLabel(domain, english)}: {version}</code>
            ))}
            {Object.entries(brief.source_classifications).map(([domain, source]) => (
              <small key={domain}>{domainLabel(domain, english)}: {SOURCE_LABEL[source]?.[english ? 1 : 0] ?? labelOf(source, english)}</small>
            ))}
          </details>
          <small>{localize(english, "AI는 계산 결과를 설명하며 WorkOrder·정비 실행을 생성하지 않습니다.", "AI explains calculated results and does not create WorkOrders or execute maintenance.")}</small>
        </>
      ) : null}
    </section>
  );
}
