import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleDot,
  Clock3,
  Database,
  RefreshCw,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import type {
  OperationsConfidence,
  OperationsDecision,
  OperationsProvenance,
  OperationsRiskStatus,
} from "../api/operationsContracts";

export const STATUS_LABEL: Record<OperationsRiskStatus, string> = {
  normal: "정상",
  attention: "주의",
  warning: "경고",
  critical: "위험",
  data_quality_hold: "데이터 확인",
};

export const CONFIDENCE_LABEL: Record<OperationsConfidence, string> = {
  high: "높음",
  medium: "중간",
  low: "낮음",
  unavailable: "사용 불가",
};

export const DECISION_LABEL: Record<OperationsDecision, string> = {
  continue_monitoring: "계속 관찰",
  request_inspection: "현장 점검 요청",
  review_shutdown: "정지 검토 요청",
  hold_for_data_check: "데이터 확인 보류",
};

const STATUS_ICON: Record<OperationsRiskStatus, LucideIcon> = {
  normal: CheckCircle2,
  attention: CircleDot,
  warning: AlertTriangle,
  critical: CircleAlert,
  data_quality_hold: ShieldAlert,
};

export function formatProbability(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function formatMinutes(value: number | null): string {
  if (value === null) return "근거 부족";
  if (value < 60) return `${value.toLocaleString()}분`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return minutes ? `${hours}시간 ${minutes}분` : `${hours}시간`;
}

export function formatTimestamp(value: string | null): string {
  if (!value) return "기록 없음";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

export function OperationsStatusBadge({ status }: { status: OperationsRiskStatus }) {
  const Icon = STATUS_ICON[status];
  return <span className={`operations-status status-${status}`}><Icon size={13} />{STATUS_LABEL[status]}</span>;
}

export function OperationsConfidenceBadge({ confidence }: { confidence: OperationsConfidence }) {
  return <span className={`operations-confidence confidence-${confidence}`}>신뢰도 {CONFIDENCE_LABEL[confidence]}</span>;
}

export function OperationsPanel({
  title,
  eyebrow,
  actions,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`operations-panel ${className}`}>
      <header className="operations-panel-header">
        <div>{eyebrow ? <span>{eyebrow}</span> : null}<h2>{title}</h2></div>
        {actions ? <div className="operations-panel-actions">{actions}</div> : null}
      </header>
      <div className="operations-panel-body">{children}</div>
    </section>
  );
}
export function OperationsState({
  kind,
  title,
  detail,
  onRetry,
}: {
  kind: "loading" | "empty" | "error" | "blocked";
  title: string;
  detail: string;
  onRetry?: () => void;
}) {
  const Icon = kind === "loading" ? RefreshCw : kind === "error" ? CircleAlert : kind === "blocked" ? ShieldAlert : Database;
  return (
    <div className={`operations-state state-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <Icon size={22} className={kind === "loading" ? "is-spinning" : ""} />
      <div><strong>{title}</strong><p>{detail}</p></div>
      {onRetry ? <button type="button" className="operations-button secondary" onClick={onRetry}><RefreshCw size={14} />다시 시도</button> : null}
    </div>
  );
}

export function OperationsProvenanceView({ provenance, compact = false }: { provenance: OperationsProvenance; compact?: boolean }) {
  const rows = [
    ["관측 묶음", provenance.datasetVersionId],
    ["모델", provenance.modelVersion ?? "사용 불가"],
    ["정책", provenance.policyVersion ?? "사용 불가"],
    ["데이터 형식", provenance.schemaVersion ?? "사용 불가"],
    ["보고서 생성", provenance.promptVersion ?? "기본 양식"],
  ];
  return (
    <dl className={`operations-provenance ${compact ? "is-compact" : ""}`}>
      {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd title={value}>{value}</dd></div>)}
      {!compact && provenance.sourceRefs.length ? (
        <div className="is-wide"><dt>원천 참조</dt><dd>{provenance.sourceRefs.map((ref) => <code key={ref}>{ref}</code>)}</dd></div>
      ) : null}
    </dl>
  );
}

export function OperationsFreshness({ observedAt, stale }: { observedAt: string | null; stale: boolean }) {
  return (
    <span className={`operations-freshness ${stale ? "is-stale" : ""}`}>
      <Clock3 size={13} />{stale ? "관측 지연" : "최근 관측"} · {formatTimestamp(observedAt)}
    </span>
  );
}
