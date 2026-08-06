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
  MvpConfidence,
  MvpDecision,
  MvpProvenance,
  MvpRiskStatus,
} from "../api/mvpContracts";

export const STATUS_LABEL: Record<MvpRiskStatus, string> = {
  normal: "정상",
  attention: "주의",
  warning: "경고",
  critical: "위험",
  data_quality_hold: "데이터 확인",
};

export const CONFIDENCE_LABEL: Record<MvpConfidence, string> = {
  high: "높음",
  medium: "중간",
  low: "낮음",
  unavailable: "사용 불가",
};

export const DECISION_LABEL: Record<MvpDecision, string> = {
  continue_monitoring: "계속 관찰",
  request_inspection: "현장 점검 요청",
  review_shutdown: "정지 검토 요청",
  hold_for_data_check: "데이터 확인 보류",
};

const STATUS_ICON: Record<MvpRiskStatus, LucideIcon> = {
  normal: CheckCircle2,
  attention: CircleDot,
  warning: AlertTriangle,
  critical: CircleAlert,
  data_quality_hold: ShieldAlert,
};

export function formatProbability(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function formatMinutes(value: number): string {
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

export function MvpStatusBadge({ status }: { status: MvpRiskStatus }) {
  const Icon = STATUS_ICON[status];
  return <span className={`mvp-status status-${status}`}><Icon size={13} />{STATUS_LABEL[status]}</span>;
}

export function MvpConfidenceBadge({ confidence }: { confidence: MvpConfidence }) {
  return <span className={`mvp-confidence confidence-${confidence}`}>신뢰도 {CONFIDENCE_LABEL[confidence]}</span>;
}

export function MvpPanel({
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
    <section className={`mvp-panel ${className}`}>
      <header className="mvp-panel-header">
        <div>{eyebrow ? <span>{eyebrow}</span> : null}<h2>{title}</h2></div>
        {actions ? <div className="mvp-panel-actions">{actions}</div> : null}
      </header>
      <div className="mvp-panel-body">{children}</div>
    </section>
  );
}
export function MvpState({
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
    <div className={`mvp-state state-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <Icon size={22} className={kind === "loading" ? "is-spinning" : ""} />
      <div><strong>{title}</strong><p>{detail}</p></div>
      {onRetry ? <button type="button" className="mvp-button secondary" onClick={onRetry}><RefreshCw size={14} />다시 시도</button> : null}
    </div>
  );
}

export function MvpProvenanceView({ provenance, compact = false }: { provenance: MvpProvenance; compact?: boolean }) {
  const rows = [
    ["Dataset Version", provenance.datasetVersionId],
    ["Model", provenance.modelVersion ?? "사용 불가"],
    ["Policy", provenance.policyVersion ?? "사용 불가"],
    ["Schema", provenance.schemaVersion ?? "사용 불가"],
    ["Prompt", provenance.promptVersion ?? "템플릿 또는 미연결"],
  ];
  return (
    <dl className={`mvp-provenance ${compact ? "is-compact" : ""}`}>
      {rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd title={value}>{value}</dd></div>)}
      {!compact && provenance.sourceRefs.length ? (
        <div className="is-wide"><dt>Source refs</dt><dd>{provenance.sourceRefs.map((ref) => <code key={ref}>{ref}</code>)}</dd></div>
      ) : null}
    </dl>
  );
}

export function MvpFreshness({ observedAt, stale }: { observedAt: string | null; stale: boolean }) {
  return (
    <span className={`mvp-freshness ${stale ? "is-stale" : ""}`}>
      <Clock3 size={13} />{stale ? "오래된 데이터" : "최근 관측"} · {formatTimestamp(observedAt)}
    </span>
  );
}
