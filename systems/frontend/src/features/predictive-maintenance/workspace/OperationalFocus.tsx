import {
  Activity,
  ArrowRight,
  ChevronRight,
  Clock3,
  Factory,
  SearchCheck,
  UserRound,
  Workflow,
} from "lucide-react";
import type {
  OperationalFocusAssetViewModel,
  OperationalFocusEvidenceViewModel,
  OperationalFocusFreshnessViewModel,
  OperationalFocusLifecycleViewModel,
  OperationalFocusPrimaryActionViewModel,
  OperationalFocusSituationViewModel,
} from "./workspaceViewModels";
import "./operational-focus.css";

type OperationalFocusLocale = "ko-KR" | "en-US";

const COPY = {
  "ko-KR": {
    eyebrow: "운영 판단 포커스",
    situation: "현재 상황",
    impact: "운영 영향",
    evidence: "핵심 근거",
    lifecycle: "현재 업무 흐름",
    current: "현재 단계",
    next: "다음 단계",
    owner: "담당",
    action: "다음 행동",
    freshness: "데이터 최신성",
    noEvidence: "연결된 핵심 근거가 없습니다.",
    unavailable: "확인되지 않음",
  },
  "en-US": {
    eyebrow: "OPERATIONAL FOCUS",
    situation: "Current situation",
    impact: "Operational impact",
    evidence: "Key evidence",
    lifecycle: "Current workflow",
    current: "Current stage",
    next: "Next stage",
    owner: "Owner",
    action: "Next action",
    freshness: "Data freshness",
    noEvidence: "No key evidence is linked.",
    unavailable: "Not available",
  },
} as const;

export interface OperationalFocusProps {
  asset: OperationalFocusAssetViewModel;
  situation: OperationalFocusSituationViewModel;
  evidence: OperationalFocusEvidenceViewModel[];
  lifecycle: OperationalFocusLifecycleViewModel;
  primaryAction?: OperationalFocusPrimaryActionViewModel | null;
  freshness?: OperationalFocusFreshnessViewModel | null;
  locale?: OperationalFocusLocale;
  onPrimaryAction?: () => void;
  focusLabel?: string;
  actionLabel?: string;
}

function freshnessText(
  freshness: OperationalFocusFreshnessViewModel | null | undefined,
  fallback: string,
  locale: OperationalFocusLocale,
) {
  if (!freshness) return fallback;
  const raw = freshness.label || freshness.observedAt;
  if (!raw) return fallback;
  const timestamp = Date.parse(raw);
  if (!Number.isFinite(timestamp)) return raw;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(timestamp));
}

export function OperationalFocus({
  asset,
  situation,
  evidence,
  lifecycle,
  primaryAction = null,
  freshness = null,
  locale = "ko-KR",
  onPrimaryAction,
  focusLabel,
  actionLabel,
}: OperationalFocusProps) {
  const copy = COPY[locale];
  const domId = asset.id.replace(/[^A-Za-z0-9_-]/g, "-");
  const tone = situation.tone ?? "neutral";
  const evidencePreview = evidence.slice(0, 4);
  const actionDisabled = Boolean(primaryAction?.disabled || primaryAction?.disabledReason || !onPrimaryAction);
  const actionReasonId = primaryAction?.disabledReason ? `operational-focus-action-reason-${domId}` : undefined;
  const ownerLabel = lifecycle.ownerLabel || primaryAction?.ownerLabel;

  return (
    <section className={`operational-focus tone-${tone}`} aria-labelledby={`operational-focus-title-${domId}`}>
      <div className="operational-focus-grid" aria-hidden="true" />

      <header className="operational-focus-object">
        <div className="operational-focus-object-mark" aria-hidden="true"><Factory size={16} /></div>
        <div className="operational-focus-object-copy">
          <span>{focusLabel ?? copy.eyebrow}</span>
          <h2 id={`operational-focus-title-${domId}`}>{asset.name}</h2>
          <div className="operational-focus-object-meta">
            {asset.contextLabel ? <small>{asset.contextLabel}</small> : null}
          </div>
        </div>
        <div className="operational-focus-status">
          <i aria-hidden="true" />
          <span>{situation.statusLabel}</span>
        </div>
      </header>

      <div className="operational-focus-situation">
        <section className="operational-focus-situation-copy" aria-label={copy.situation}>
          <span className="operational-focus-kicker"><Activity size={12} />{copy.situation}</span>
          {situation.headline ? <h3>{situation.headline}</h3> : null}
          {situation.detail ? <p>{situation.detail}</p> : null}
        </section>

        <div className="operational-focus-situation-metrics">
          {situation.risk ? (
            <div className="operational-focus-risk">
              <span>{situation.risk.label}</span>
              <strong>
                {situation.risk.previousValueLabel ? <del>{situation.risk.previousValueLabel}</del> : null}
                {situation.risk.previousValueLabel && situation.risk.valueLabel ? <ArrowRight size={13} aria-hidden="true" /> : null}
                {situation.risk.valueLabel ?? copy.unavailable}
              </strong>
            </div>
          ) : null}
          {situation.operationalImpact ? (
            <div className="operational-focus-impact">
              <span><Factory size={11} />{copy.impact}</span>
              <strong>{situation.operationalImpact}</strong>
            </div>
          ) : null}
        </div>
      </div>

      <section className="operational-focus-evidence" aria-labelledby={`operational-focus-evidence-${domId}`}>
        <div className="operational-focus-section-heading">
          <span><SearchCheck size={13} /></span>
          <div>
            <small>{locale === "ko-KR" ? "판단 근거" : "WHY"}</small>
            <strong id={`operational-focus-evidence-${domId}`}>{copy.evidence}</strong>
          </div>
        </div>
        {evidencePreview.length ? (
          <ul>
            {evidencePreview.map((item) => (
              <li key={item.id}>
                <div>
                  <strong>{item.label}</strong>
                  {item.detail ? <small>{item.detail}</small> : null}
                </div>
                {item.value ? <b>{item.value}</b> : null}
              </li>
            ))}
          </ul>
        ) : <p className="operational-focus-empty">{copy.noEvidence}</p>}
      </section>

      <section className="operational-focus-lifecycle" aria-labelledby={`operational-focus-lifecycle-${domId}`}>
        <div className="operational-focus-section-heading">
          <span><Workflow size={13} /></span>
          <div>
            <small>{locale === "ko-KR" ? "업무 흐름" : "CANONICAL LIFECYCLE"}</small>
            <strong id={`operational-focus-lifecycle-${domId}`}>{copy.lifecycle}</strong>
          </div>
        </div>
        <div className="operational-focus-lifecycle-track">
          <div className="is-current">
            <span>{copy.current}</span>
            <strong>{lifecycle.currentLabel}</strong>
          </div>
          <ChevronRight size={14} aria-hidden="true" />
          <div className="is-next">
            <span>{copy.next}</span>
            <strong>{lifecycle.nextLabel ?? copy.unavailable}</strong>
          </div>
          <div className="operational-focus-owner">
            <span><UserRound size={11} />{copy.owner}</span>
            <strong>{ownerLabel ?? copy.unavailable}</strong>
          </div>
        </div>
      </section>

      <footer className="operational-focus-footer">
        <div className="operational-focus-action">
          <div>
            <span>{actionLabel ?? copy.action}</span>
            {primaryAction?.ownerLabel && primaryAction.ownerLabel !== lifecycle.ownerLabel ? <small>{primaryAction.ownerLabel}</small> : null}
          </div>
          {primaryAction ? (
            <button
              type="button"
              disabled={actionDisabled}
              aria-describedby={actionReasonId}
              onClick={onPrimaryAction}
            >
              <span>{primaryAction.label}</span>
              <ArrowRight size={14} aria-hidden="true" />
            </button>
          ) : <strong className="operational-focus-no-action">{copy.unavailable}</strong>}
          {primaryAction?.disabledReason ? <p id={actionReasonId}>{primaryAction.disabledReason}</p> : null}
        </div>

        <div className="operational-focus-freshness">
          <span><Clock3 size={11} />{copy.freshness}</span>
          <strong>
            {freshness?.observedAt ? (
              <time dateTime={freshness.observedAt}>{freshnessText(freshness, copy.unavailable, locale)}</time>
            ) : freshnessText(freshness, copy.unavailable, locale)}
          </strong>
          {freshness?.sourceLabel ? <small>{freshness.sourceLabel}</small> : null}
        </div>
      </footer>
    </section>
  );
}
