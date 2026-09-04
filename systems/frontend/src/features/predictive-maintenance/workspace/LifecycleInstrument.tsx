import {
  Ban,
  Check,
  ChevronDown,
  Circle,
  CircleDot,
  TriangleAlert,
} from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { ActivityTimeline, type ActivityTimelineItem } from "./ActivityTimeline";

export type LifecycleCurrentState = "active" | "blocked" | "failed";

export interface LifecycleStagePresentation {
  id: string;
  label: string;
  detail?: string | null;
  state?: LifecycleCurrentState;
}

export interface LifecycleInstrumentProps {
  completedSteps?: LifecycleStagePresentation[];
  current: LifecycleStagePresentation | null;
  next?: LifecycleStagePresentation | null;
  timeline?: ActivityTimelineItem[];
  locale?: "ko-KR" | "en-US";
  title?: string;
  expanded?: boolean;
  defaultExpanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
  mode?: "idle" | "compact" | "full";
}

type CompactStageKind = "completed" | "current" | "next" | "empty";

function CurrentStateIcon({ state }: { state: LifecycleCurrentState }): ReactNode {
  if (state === "blocked") return <Ban aria-hidden="true" size={13} />;
  if (state === "failed") return <TriangleAlert aria-hidden="true" size={13} />;
  return <CircleDot aria-hidden="true" size={13} />;
}

function CompactStageIcon({ kind, state = "active" }: { kind: CompactStageKind; state?: LifecycleCurrentState }): ReactNode {
  if (kind === "completed") return <Check aria-hidden="true" size={13} />;
  if (kind === "current") return <CurrentStateIcon state={state} />;
  return <Circle aria-hidden="true" size={12} />;
}

function currentStateLabel(state: LifecycleCurrentState, locale: "ko-KR" | "en-US") {
  if (locale === "ko-KR") {
    if (state === "blocked") return "현재 단계 · 차단됨";
    if (state === "failed") return "현재 단계 · 실패";
    return "현재 단계";
  }
  if (state === "blocked") return "Current · Blocked";
  if (state === "failed") return "Current · Failed";
  return "Current step";
}

export function LifecycleInstrument({
  completedSteps = [],
  current,
  next = null,
  timeline = [],
  locale = "ko-KR",
  title,
  expanded,
  defaultExpanded = false,
  onExpandedChange,
  mode = "full",
}: LifecycleInstrumentProps) {
  const [internalExpanded, setInternalExpanded] = useState(defaultExpanded);
  const detailsId = useId();
  const isExpanded = expanded ?? internalExpanded;
  const previous = completedSteps.length ? completedSteps[completedSteps.length - 1] : null;
  const currentState = current?.state ?? "active";
  const english = locale === "en-US";

  function toggleExpanded() {
    const nextExpanded = !isExpanded;
    if (expanded === undefined) setInternalExpanded(nextExpanded);
    onExpandedChange?.(nextExpanded);
  }

  const previousEyebrow = completedSteps.length > 1
    ? (english ? `Previous · ${completedSteps.length} completed` : `이전 완료 · ${completedSteps.length}단계`)
    : (english ? "Previous completed" : "이전 완료 단계");

  if (mode === "idle") {
    return (
      <section className="lifecycle-instrument is-idle" aria-label={title ?? (english ? "No case selected" : "Case 미선택")}>
        <div className="lifecycle-idle-strip">
          <span><Circle aria-hidden="true" size={11} /></span>
          <strong>{english ? "No case selected" : "Case 미선택"}</strong>
          <small>{english ? "Select an asset or event to follow its closed-loop workflow." : "설비나 Event를 선택하면 closed-loop 진행 상태를 표시합니다."}</small>
        </div>
      </section>
    );
  }

  return (
    <section className={`lifecycle-instrument is-${mode}`} aria-label={title ?? (english ? "Reliability lifecycle" : "Reliability lifecycle")}>
      <div className="lifecycle-instrument-bar">
        <div className="lifecycle-instrument-title">
          <span>{english ? "CLOSED-LOOP" : "CLOSED-LOOP"}</span>
          <strong>{title ?? (english ? "Lifecycle" : "Lifecycle")}</strong>
        </div>

        <div className="lifecycle-instrument-track">
          {mode === "full" ? <article className={`lifecycle-stage is-completed ${previous ? "has-value" : "is-empty"}`}>
            <div className="lifecycle-stage-dot"><CompactStageIcon kind={previous ? "completed" : "empty"} /></div>
            <div>
              <span>{previousEyebrow}</span>
              <strong>{previous?.label ?? (english ? "No completed step" : "완료된 단계 없음")}</strong>
            </div>
          </article> : null}

          <article className={`lifecycle-stage is-current is-${currentState} ${current ? "has-value" : "is-empty"}`}>
            <div className="lifecycle-stage-dot"><CompactStageIcon kind="current" state={currentState} /></div>
            <div>
              <span>{currentStateLabel(currentState, locale)}</span>
              <strong>{current?.label ?? (english ? "Current step unavailable" : "현재 단계 정보 없음")}</strong>
              {current?.detail ? <small>{current.detail}</small> : null}
            </div>
          </article>

          <article className={`lifecycle-stage is-next ${next ? "has-value" : "is-empty"}`}>
            <div className="lifecycle-stage-dot"><CompactStageIcon kind={next ? "next" : "empty"} /></div>
            <div>
              <span>{english ? "Next step" : "다음 단계"}</span>
              <strong>{next?.label ?? (english ? "No next step" : "다음 단계 없음")}</strong>
            </div>
          </article>
        </div>

        <button
          type="button"
          className="lifecycle-instrument-toggle"
          aria-expanded={isExpanded}
          aria-controls={detailsId}
          onClick={toggleExpanded}
        >
          <span>{isExpanded ? (english ? "Hide history" : "이력 접기") : (english ? "Show history" : "전체 이력")}</span>
          <ChevronDown aria-hidden="true" size={14} />
        </button>
      </div>

      {isExpanded ? (
        <div id={detailsId} className="lifecycle-instrument-details">
          <section className="lifecycle-known-steps" aria-label={english ? "Known lifecycle steps" : "확인된 lifecycle 단계"}>
            <header>
              <span>{english ? "KNOWN STEPS" : "확인된 단계"}</span>
              <strong>{english ? "Lifecycle summary" : "Lifecycle 요약"}</strong>
            </header>
            <div className="lifecycle-known-steps-list">
              {completedSteps.map((step) => (
                <article key={step.id} className="lifecycle-known-step is-completed">
                  <span><Check aria-hidden="true" size={12} /></span>
                  <div><strong>{step.label}</strong>{step.detail ? <small>{step.detail}</small> : null}</div>
                  <em>{english ? "Completed" : "완료"}</em>
                </article>
              ))}
              {current ? (
                <article className={`lifecycle-known-step is-current is-${currentState}`}>
                  <span><CurrentStateIcon state={currentState} /></span>
                  <div><strong>{current.label}</strong>{current.detail ? <small>{current.detail}</small> : null}</div>
                  <em>{currentStateLabel(currentState, locale)}</em>
                </article>
              ) : null}
              {next ? (
                <article className="lifecycle-known-step is-next">
                  <span><Circle aria-hidden="true" size={11} /></span>
                  <div><strong>{next.label}</strong>{next.detail ? <small>{next.detail}</small> : null}</div>
                  <em>{english ? "Next" : "다음"}</em>
                </article>
              ) : null}
              {!completedSteps.length && !current && !next ? (
                <p className="lifecycle-known-steps-empty">{english ? "No lifecycle summary is available." : "표시할 lifecycle 요약이 없습니다."}</p>
              ) : null}
            </div>
          </section>

          <section className="lifecycle-activity-history" aria-label={english ? "Activity history" : "활동 이력"}>
            <header>
              <span>{english ? "ACTIVITY" : "ACTIVITY"}</span>
              <strong>{english ? "Activity history" : "활동 이력"}</strong>
            </header>
            <ActivityTimeline items={timeline} locale={locale} />
          </section>
        </div>
      ) : null}
    </section>
  );
}
