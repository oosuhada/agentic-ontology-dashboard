import { ChevronRight, PanelRightClose, Send, Sparkles } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  hasReliabilityAssistantSelection,
  reliabilityAssistantAssetLabel,
  reliabilityAssistantPrompts,
  reliabilityAssistantRiskLabel,
  type ReliabilityAssistantContext,
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
  const suggestedPrompts = useMemo(
    () => prompts ?? reliabilityAssistantPrompts(context, locale),
    [context, locale, prompts],
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
          <small>{context?.freshnessLabel ?? context?.observedAt ?? ""}</small>
        </div>
        <strong className="rw-context-assistant__asset">{assetLabel}</strong>
        {!selected ? (
          <p className="rw-context-assistant__empty-context">
            {english ? "Select an asset or event in the workspace to establish context." : "workspace에서 설비나 이벤트를 선택하면 해당 문맥을 기준으로 요약합니다."}
          </p>
        ) : (
          <dl className="rw-context-assistant__facts">
            {(context?.roleKind === "engineering" || context?.roleKind === "maintenance") && context?.assetId ? <div><dt>{english ? "Asset ID" : "설비 ID"}</dt><dd>{context.assetId}</dd></div> : null}
            {(context?.roleKind === "engineering" || context?.roleKind === "maintenance") && context?.eventId ? <div><dt>{english ? "Event ID" : "이벤트 ID"}</dt><dd>{context.eventId}</dd></div> : null}
            {riskLabel ? <div><dt>{english ? "Risk" : "위험도"}</dt><dd>{riskLabel}</dd></div> : null}
            {context?.currentLifecycleLabel ? <div><dt>{english ? "Current step" : "현재 단계"}</dt><dd>{context.currentLifecycleLabel}</dd></div> : null}
            {context?.nextLifecycleLabel ? <div><dt>{english ? "Next step" : "다음 단계"}</dt><dd>{context.nextLifecycleLabel}</dd></div> : null}
            {context?.primaryActionLabel ? <div className="is-action"><dt>{english ? "Primary action" : "다음 행동"}</dt><dd>{context.primaryActionLabel}</dd></div> : null}
            {context?.evidenceCount !== null && context?.evidenceCount !== undefined ? <div><dt>{english ? "Evidence" : "근거"}</dt><dd>{context.evidenceCount}</dd></div> : null}
            {context?.workOrderCount !== null && context?.workOrderCount !== undefined ? <div><dt>{english ? "Work items" : "작업 건수"}</dt><dd>{context.workOrderCount}</dd></div> : null}
            {context?.maintenanceState ? <div><dt>{english ? "Maintenance status" : "정비 상태"}</dt><dd>{context.maintenanceState}</dd></div> : null}
          </dl>
        )}
        {context?.evidenceSummary ? <p className="rw-context-assistant__evidence-summary">{context.evidenceSummary}</p> : null}
        {selected ? (
          <div className="rw-context-assistant__sources" aria-label={english ? "Assistant grounding sources" : "Assistant 근거 소스"}>
            <span>{loading ? (english ? "Refreshing context…" : "문맥 갱신 중…") : (english ? "Live context" : "실시간 문맥")}</span>
            {context?.aiSummaryMode ? (
              <strong className={`mode-${context.aiSummaryMode}`}>
                {context.aiSummaryMode === "llm"
                  ? (english ? "LLM grounded" : "LLM 근거 요약")
                  : (english ? "Validated fallback" : "검증 fallback")}
              </strong>
            ) : null}
            {context?.retrievalCount !== null && context?.retrievalCount !== undefined ? (
              <small>{english ? "Validated SOP guidance" : "검증된 SOP 안내"} · {context.retrievalCount}</small>
            ) : null}
          </div>
        ) : null}
        {error ? <p className="rw-context-assistant__error">{error}</p> : null}
        {selected && actions.length ? <div className="rw-context-assistant__actions" aria-label={english ? "Connected workspace actions" : "연결된 화면으로 이동"}>{actions.map((action) => <button type="button" key={action.id} onClick={action.onClick}><span><strong>{action.label}</strong>{action.detail ? <small>{action.detail}</small> : null}</span><ChevronRight size={13} /></button>)}</div> : null}
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
            <span>{message.role === "user" ? (english ? "QUESTION" : "질문") : (english ? "CONNECTED DATA" : "연결 데이터 요약")}</span>
            <p>{message.text}</p>
            {message.contextHint ? <small>{message.contextHint}</small> : null}
          </article>
        )) : (
          <div className="rw-context-assistant__empty-thread">
            <span>{english ? "NO QUESTIONS YET" : "아직 질문 없음"}</span>
            <p>{english
              ? "Questions are answered from the selected live event, Agent Review Packet, stored grounded AI summary, and linked retrieval metadata when available."
              : "선택된 실시간 이벤트, Agent Review Packet, 저장된 근거 기반 AI 요약과 연결 retrieval metadata를 사용해 답합니다."}</p>
          </div>
        )}
        {submitting ? <article className="rw-context-assistant__message is-assistant is-loading" aria-live="polite">
          <span>{english ? "CONNECTED DATA" : "연결 데이터 요약"}</span>
          <p>{english ? "Checking linked evidence and the current case context…" : "연결 근거와 현재 Case 문맥을 확인하고 있습니다…"}</p>
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
            : (english ? "Select an asset or event first" : "먼저 설비나 이벤트를 선택하세요")}
          rows={2}
          disabled={!selected || !onSubmit || submitting}
        />
        <button
          type="submit"
          disabled={!selected || !onSubmit || submitting || !draft.trim()}
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
