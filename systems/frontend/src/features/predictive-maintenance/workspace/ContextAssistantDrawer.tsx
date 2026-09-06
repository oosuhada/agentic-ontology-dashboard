import { Check, ChevronDown, ChevronRight, CircleAlert, Clock3, Database, PanelRightClose, Send, Sparkles } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  hasReliabilityAssistantSelection,
  reliabilityAssistantAssetLabel,
  reliabilityAssistantContextSummary,
  reliabilityAssistantPrompts,
  reliabilityAssistantRiskLabel,
  type ReliabilityAssistantContext,
  type ReliabilityAssistantActivityTrace,
  type ReliabilityAssistantLocale,
  type ReliabilityAssistantMessage,
  type ReliabilityAssistantPrompt,
} from "./assistantContext";
import "./context-assistant.css";

export interface ContextAssistantDrawerProps {
  open?: boolean;
  onClose: () => void;
  context?: ReliabilityAssistantContext | null;
  messages?: ReliabilityAssistantMessage[];
  prompts?: ReliabilityAssistantPrompt[];
  onSubmit?: (question: string) => void | Promise<void>;
  locale?: ReliabilityAssistantLocale;
  loading?: boolean;
  submitting?: boolean;
  error?: string | null;
  actions?: Array<{
    id: string;
    label: string;
    detail?: string;
    onClick: () => void;
  }>;
}

function activityStatusLabel(
  status: ReliabilityAssistantActivityTrace["status"],
  english: boolean,
) {
  if (status === "succeeded") return english ? "Completed" : "완료";
  if (status === "fallback") return english ? "Fallback" : "fallback";
  return english ? "Incomplete" : "미완료";
}

function assistantDateTime(value: string | null | undefined, english: boolean) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(english ? "en-US" : "ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function AssistantActivityTrace({
  trace,
  english,
  open,
}: {
  trace: ReliabilityAssistantActivityTrace;
  english: boolean;
  open: boolean;
}) {
  return (
    <details className={`rw-assistant-trace is-${trace.status}`} open={open}>
      <summary>
        <span>
          <Sparkles size={11} aria-hidden="true" />
          {english ? "Execution activity" : "작업 기록"}
        </span>
        <div>
          <small>{activityStatusLabel(trace.status, english)}</small>
          {trace.durationMs ? <small>{trace.durationMs.toLocaleString()}ms</small> : null}
          <ChevronDown size={12} aria-hidden="true" />
        </div>
      </summary>
      <ol>
        {trace.steps.map((step) => (
          <li key={step.id} className={`is-${step.status}`}>
            <i aria-hidden="true">
              {step.status === "succeeded" ? <Check size={10} /> : step.status === "fallback" ? <Database size={10} /> : <CircleAlert size={10} />}
            </i>
            <div>
              <strong>{step.label}</strong>
              {step.detail ? <p>{step.detail}</p> : null}
              <small>
                {step.store ? <span>{step.store}</span> : null}
                {typeof step.latencyMs === "number" ? <span><Clock3 size={9} />{step.latencyMs.toLocaleString()}ms</span> : null}
              </small>
            </div>
          </li>
        ))}
      </ol>
      <footer>
        <span>{english ? `${trace.evidenceCount} evidence · ${trace.claimCount} grounded claims` : `근거 ${trace.evidenceCount}건 · 검증 주장 ${trace.claimCount}건`}</span>
        {trace.route ? <span>{english ? "route" : "경로"} · {trace.route}</span> : null}
        {trace.persistence ? <span>{trace.persistence === "persisted" ? (english ? "history saved" : "기록 저장됨") : (english ? "history not saved" : "기록 저장 안 됨")}</span> : null}
        <small>{english ? "Shows retrieval and validation activity, not the model's private chain of thought." : "검색·검증 실행 기록만 표시하며 모델 내부 사고 과정은 포함하지 않습니다."}</small>
      </footer>
    </details>
  );
}

export function ContextAssistantDrawer({
  open = false,
  onClose,
  context = null,
  messages = [],
  prompts,
  onSubmit,
  locale = "ko-KR",
  loading = false,
  submitting = false,
  error = null,
  actions = [],
}: ContextAssistantDrawerProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const [draft, setDraft] = useState("");
  const english = locale === "en-US";
  const selected = hasReliabilityAssistantSelection(context);
  const assetLabel = reliabilityAssistantAssetLabel(context, locale);
  const riskLabel = reliabilityAssistantRiskLabel(context?.failureProbability);
  const contextSummary = reliabilityAssistantContextSummary(context, locale);
  const workspaceLabel = context?.workspaceName?.trim() || (english ? "Workspace overview" : "전체 운영 문맥");
  const suggestedPrompts = useMemo(
    () => prompts ?? reliabilityAssistantPrompts(context, locale),
    [context, locale, prompts],
  );
  const latestAssistantMessageId = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant")?.id ?? null,
    [messages],
  );

  useEffect(() => {
    if (!open) return;
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onClose();
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocusedRef.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed || !onSubmit) return;
    void onSubmit(trimmed);
    setDraft("");
  }

  function submitDraft(event: FormEvent) {
    event.preventDefault();
    submit(draft);
  }

  return (
    <aside
      className="rw-context-assistant"
      role="dialog"
      aria-label={english ? "Reliability Assistant" : "Reliability Assistant"}
    >
      <header className="rw-context-assistant__header">
        <div className="rw-context-assistant__identity">
          <span aria-hidden="true"><Sparkles size={15} /></span>
          <div>
            <strong>Reliability Assistant</strong>
            <small>{english ? "Operational context summary" : "운영 문맥 요약"}</small>
          </div>
        </div>
        <button
          ref={closeButtonRef}
          type="button"
          className="rw-context-assistant__close"
          onClick={onClose}
          aria-label={english ? "Close Reliability Assistant" : "Reliability Assistant 닫기"}
        >
          <PanelRightClose size={16} />
        </button>
      </header>

      <section className="rw-context-assistant__context" aria-labelledby="rw-context-assistant-context-title">
        <div className="rw-context-assistant__section-heading">
          <span id="rw-context-assistant-context-title">{english ? "CURRENT CONTEXT" : "현재 문맥"}</span>
          <small>{assistantDateTime(context?.freshnessLabel ?? context?.observedAt, english)}</small>
        </div>
        <strong className="rw-context-assistant__asset">{selected ? assetLabel : workspaceLabel}</strong>
        {!selected ? (
          <dl className="rw-context-assistant__facts is-workspace-scope">
            {context?.workspaceMetrics ? <>
              <div><dt>{english ? "Assets" : "설비"}</dt><dd>{context.workspaceMetrics.totalAssets}</dd></div>
              <div><dt>{english ? "Critical / warning" : "고위험 / 경고"}</dt><dd>{context.workspaceMetrics.critical} / {context.workspaceMetrics.warning}</dd></div>
              <div><dt>{english ? "Pending decisions" : "판단 대기"}</dt><dd>{context.workspaceMetrics.pendingDecisions}</dd></div>
              <div><dt>{english ? "Data holds" : "품질 보류"}</dt><dd>{context.workspaceMetrics.dataQualityHold}</dd></div>
            </> : null}
          </dl>
        ) : (
          <dl className="rw-context-assistant__facts">
            {(context?.roleKind === "engineering" || context?.roleKind === "maintenance") && context?.assetId ? <div><dt>{english ? "Asset ID" : "설비 ID"}</dt><dd>{context.assetId}</dd></div> : null}
            {riskLabel ? <div><dt>{english ? "Risk" : "위험도"}</dt><dd>{riskLabel}</dd></div> : null}
            {context?.recommendedDecisionLabel ? <div><dt>{english ? "Recommendation" : "권고"}</dt><dd>{context.recommendedDecisionLabel}</dd></div> : null}
            {context?.currentLifecycleLabel ? <div><dt>{english ? "Current step" : "현재 단계"}</dt><dd>{context.currentLifecycleLabel}</dd></div> : null}
            {context?.nextLifecycleLabel ? <div><dt>{english ? "Next step" : "다음 단계"}</dt><dd>{context.nextLifecycleLabel}</dd></div> : null}
            {context?.primaryActionLabel ? <div className="is-action"><dt>{english ? "Primary action" : "다음 행동"}</dt><dd>{context.primaryActionLabel}</dd></div> : null}
            {(context?.evidenceCount ?? 0) > 0 ? <div><dt>{english ? "Evidence" : "근거"}</dt><dd>{context?.evidenceCount}</dd></div> : null}
            {context?.workOrderCount !== null && context?.workOrderCount !== undefined ? <div><dt>{english ? "Work items" : "작업 건수"}</dt><dd>{context.workOrderCount}</dd></div> : null}
            {context?.maintenanceState && context.maintenanceState !== context.currentLifecycleLabel ? <div><dt>{english ? "Maintenance status" : "정비 상태"}</dt><dd>{context.maintenanceState}</dd></div> : null}
          </dl>
        )}
        {contextSummary ? <p className="rw-context-assistant__evidence-summary">{contextSummary}</p> : null}
        {context ? (
          <div className="rw-context-assistant__sources" aria-label={english ? "Assistant grounding sources" : "Assistant 근거 소스"}>
            <span>{loading ? (english ? "Refreshing context…" : "문맥 갱신 중…") : (english ? "Live context" : "실시간 문맥")}</span>
            {context?.aiSummaryMode ? (
              <strong className={`mode-${context.aiSummaryMode}`}>
                {context.aiSummaryMode === "llm"
                  ? (english ? "LLM grounded" : "LLM 근거 요약")
                  : (english ? "Validated baseline" : "검증된 기본 요약")}
              </strong>
            ) : null}
            {selected && context?.retrievalCount !== null && context?.retrievalCount !== undefined ? (
              <small>{english ? "Validated SOP guidance" : "검증된 SOP 안내"} · {context.retrievalCount}</small>
            ) : null}
          </div>
        ) : null}
        {error ? <p className="rw-context-assistant__error">{error}</p> : null}
        {actions.length ? <div className="rw-context-assistant__actions" aria-label={english ? "Connected workspace actions" : "연결된 화면으로 이동"}>{actions.map((action) => <button type="button" key={action.id} onClick={action.onClick}><span><strong>{action.label}</strong>{action.detail ? <small>{action.detail}</small> : null}</span><ChevronRight size={13} /></button>)}</div> : null}
      </section>

      {suggestedPrompts.length ? (
        <section className="rw-context-assistant__prompts" aria-labelledby="rw-context-assistant-prompts-title">
          <div className="rw-context-assistant__section-heading">
            <span id="rw-context-assistant-prompts-title">{english ? "CONTEXT QUESTIONS" : "문맥 질문"}</span>
          </div>
          <div>
            {suggestedPrompts.map((prompt) => (
              <button type="button" key={prompt.id} onClick={() => submit(prompt.label)} disabled={!onSubmit || submitting}>
                <span>{prompt.label}</span><ChevronRight size={13} aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <section className="rw-context-assistant__thread" aria-label={english ? "Context summary thread" : "문맥 요약 대화"}>
        {messages.length ? messages.map((message) => (
          <article key={message.id} className={`rw-context-assistant__message is-${message.role}`}>
            <span>{message.role === "user" ? (english ? "QUESTION" : "질문") : (english ? "OPERATIONAL INTERPRETATION" : "운영 해석")}</span>
            <p>{message.text}</p>
            {message.contextHint ? <small>{message.contextHint}</small> : null}
            {message.role === "assistant" && message.activityTrace ? (
              <AssistantActivityTrace
                trace={message.activityTrace}
                english={english}
                open={message.id === latestAssistantMessageId}
              />
            ) : null}
          </article>
        )) : (
          <div className="rw-context-assistant__empty-thread">
            <span>{english ? "NO QUESTIONS YET" : "아직 질문 없음"}</span>
            <p>{english
              ? (selected
                  ? "Answers use the selected operational event and validated company evidence, then translate them into action and business-value language."
                  : "Ask at workspace scope about plant risk, decisions, maintenance, KPIs, finance, meetings, or company knowledge. Select an asset only when you need case-specific evidence.")
              : (selected
                  ? "선택된 운영 이벤트와 검증된 회사 근거를 바탕으로, 현장 행동과 회사 가치가 연결되도록 설명합니다."
                  : "설비를 선택하지 않아도 공장 전체 리스크, 판단 대기, 정비, KPI, 재무, 회의 기록과 회사 지식에 대해 질문할 수 있습니다. Case 근거가 필요할 때만 설비를 선택하면 됩니다.")}</p>
          </div>
        )}
        {submitting ? <article className="rw-context-assistant__message is-assistant is-loading" aria-live="polite">
          <span>{english ? "OPERATIONAL INTERPRETATION" : "운영 해석"}</span>
          <p>{english ? "Checking the evidence and translating it into operational impact…" : "근거를 확인하고 운영 영향과 가치 관점으로 답변을 구성하고 있습니다…"}</p>
        </article> : null}
      </section>

      <form className="rw-context-assistant__composer" onSubmit={submitDraft}>
        <label htmlFor="rw-context-assistant-question" className="rw-context-assistant__sr-only">
          {english ? "Ask about the current operational context" : "현재 운영 문맥 질문"}
        </label>
        <textarea
          id="rw-context-assistant-question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={selected
            ? (english ? "Ask about the selected operational context" : "선택된 운영 문맥에 대해 질문")
            : (english ? "Ask about plant-wide risk, decisions, KPIs, or company knowledge" : "공장 전체 리스크, 판단, KPI 또는 회사 지식에 대해 질문")}
          rows={2}
          disabled={!onSubmit || submitting}
        />
        <button
          type="submit"
          disabled={!onSubmit || submitting || !draft.trim()}
          aria-label={english ? "Submit context question" : "문맥 질문 보내기"}
        >
          <Send size={15} />
        </button>
      </form>

      <footer className="rw-context-assistant__disclaimer">
        {english
          ? "Read-only assistant. Grounding comes from canonical operational data and Agent Review context; AI generation never approves, executes, or changes workflow state."
          : "읽기 전용 Assistant입니다. 현재 연결된 운영 데이터와 검토 근거를 사용하며 AI 생성은 업무를 승인·실행하거나 workflow 상태를 변경하지 않습니다."}
      </footer>
    </aside>
  );
}
