export type ReliabilityAssistantLocale = "ko-KR" | "en-US";

export interface ReliabilityAssistantContext {
  roleKind?: "executive" | "operations" | "engineering" | "maintenance" | null;
  assetId?: string | null;
  assetName?: string | null;
  eventId?: string | null;
  failureProbability?: number | null;
  statusLabel?: string | null;
  lineLabel?: string | null;
  operationalImpact?: string | null;
  recommendedDecisionLabel?: string | null;
  predictedFailureType?: string | null;
  assignedEngineer?: string | null;
  currentLifecycleLabel?: string | null;
  nextLifecycleLabel?: string | null;
  primaryActionLabel?: string | null;
  evidenceCount?: number | null;
  evidenceSummary?: string | null;
  workOrderCount?: number | null;
  maintenanceState?: string | null;
  workHistorySummary?: string | null;
  postMaintenanceSummary?: string | null;
  observedAt?: string | null;
  freshnessLabel?: string | null;
  priorityReasons?: string[];
  evidenceItems?: string[];
  historyItems?: string[];
  aiSummary?: string | null;
  aiSummaryMode?: "llm" | "deterministic_fallback" | null;
  aiProvider?: string | null;
  retrievalProvider?: string | null;
  retrievalCount?: number | null;
}

export interface ReliabilityAssistantMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  contextHint?: string | null;
}

export interface ReliabilityAssistantPrompt {
  id: string;
  label: string;
}

function hasText(value: string | null | undefined): value is string {
  return Boolean(value?.trim());
}

export function hasReliabilityAssistantSelection(context: ReliabilityAssistantContext | null | undefined) {
  return Boolean(context && (hasText(context.assetId) || hasText(context.assetName) || hasText(context.eventId)));
}

export function reliabilityAssistantAssetLabel(
  context: ReliabilityAssistantContext | null | undefined,
  locale: ReliabilityAssistantLocale = "ko-KR",
) {
  if (!context) return locale === "en-US" ? "No selection" : "선택 없음";
  return context.assetName?.trim() || context.assetId?.trim() || context.eventId?.trim()
    || (locale === "en-US" ? "No selection" : "선택 없음");
}

export function reliabilityAssistantRiskLabel(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${Math.round(value * 100)}%`;
}

export function reliabilityAssistantPrompts(
  context: ReliabilityAssistantContext | null | undefined,
  locale: ReliabilityAssistantLocale = "ko-KR",
): ReliabilityAssistantPrompt[] {
  if (!hasReliabilityAssistantSelection(context)) return [];

  const english = locale === "en-US";
  if (context?.roleKind) {
    const rolePrompts: Record<NonNullable<ReliabilityAssistantContext["roleKind"]>, ReliabilityAssistantPrompt[]> = {
      engineering: english ? [
        { id: "engineer-why", label: "Why was this asset flagged as abnormal?" },
        { id: "engineer-sensor", label: "Which sensors should I check first?" },
        { id: "engineer-checklist", label: "What should I inspect now?" },
        { id: "engineer-history", label: "Is this related to recent maintenance history?" },
      ] : [
        { id: "engineer-why", label: "왜 이 설비가 이상으로 판단됐나요?" },
        { id: "engineer-sensor", label: "어떤 센서를 먼저 확인해야 하나요?" },
        { id: "engineer-checklist", label: "점검 항목은 무엇인가요?" },
        { id: "engineer-history", label: "최근 정비 이력과 관련이 있나요?" },
      ],
      maintenance: english ? [
        { id: "maintenance-next", label: "What approved work should I perform now?" },
        { id: "maintenance-evidence", label: "What evidence should I verify on site?" },
        { id: "maintenance-history", label: "Summarize recent maintenance history" },
        { id: "maintenance-after", label: "How should I verify the result after maintenance?" },
      ] : [
        { id: "maintenance-next", label: "지금 수행해야 할 승인 작업은 무엇인가요?" },
        { id: "maintenance-evidence", label: "현장에서 확인할 근거는 무엇인가요?" },
        { id: "maintenance-history", label: "최근 정비 이력을 요약해줘" },
        { id: "maintenance-after", label: "정비 후 결과를 어떻게 확인해야 하나요?" },
      ],
      operations: english ? [
        { id: "manager-action", label: "What action should I approve now?" },
        { id: "manager-impact", label: "What is the production impact?" },
        { id: "manager-delay", label: "What risk increases if we defer this?" },
        { id: "manager-report", label: "Create an executive report draft" },
      ] : [
        { id: "manager-action", label: "지금 승인해야 하는 조치는 무엇인가요?" },
        { id: "manager-impact", label: "생산 영향은 어느 정도인가요?" },
        { id: "manager-delay", label: "보류하면 어떤 리스크가 있나요?" },
        { id: "manager-report", label: "경영진 보고 초안을 만들어줘" },
      ],
      executive: english ? [
        { id: "executive-brief", label: "Summarize this issue in one paragraph for reporting" },
        { id: "executive-kpi", label: "How does this issue affect KPI performance?" },
        { id: "executive-delay", label: "Summarize the currently delayed decisions" },
        { id: "executive-risk", label: "Summarize this week's operational risk" },
      ] : [
        { id: "executive-brief", label: "보고용으로 한 문단 요약해줘" },
        { id: "executive-kpi", label: "이번 이슈가 KPI에 미치는 영향은?" },
        { id: "executive-delay", label: "현재 판단 지연 항목을 요약해줘" },
        { id: "executive-risk", label: "이번 주 운영 리스크를 요약해줘" },
      ],
    };
    return rolePrompts[context.roleKind];
  }

  const prompts: ReliabilityAssistantPrompt[] = [];
  const asset = reliabilityAssistantAssetLabel(context, locale);
  const risk = reliabilityAssistantRiskLabel(context?.failureProbability);

  if (context?.failureProbability !== null && context?.failureProbability !== undefined) {
    prompts.push({
      id: "priority",
      label: english
        ? `Why is ${asset}${risk ? ` (${risk})` : ""} prioritized?`
        : `${asset}${risk ? ` (${risk})` : ""}가 우선인 이유는?`,
    });
  }
  if ((context?.evidenceCount ?? 0) > 0 || hasText(context?.evidenceSummary)) {
    prompts.push({
      id: "evidence",
      label: english
        ? `Summarize the ${context?.evidenceCount ?? 0} linked evidence items`
        : `현재 연결 근거 ${context?.evidenceCount ?? 0}건을 요약해줘`,
    });
  }
  if (hasText(context?.currentLifecycleLabel) || hasText(context?.nextLifecycleLabel)) {
    prompts.push({
      id: "lifecycle",
      label: english
        ? `What happens after “${context?.currentLifecycleLabel ?? "current step"}”?`
        : `현재 “${context?.currentLifecycleLabel ?? "처리 단계"}” 다음은 무엇인가?`,
    });
  }
  if (hasText(context?.primaryActionLabel)) {
    prompts.push({
      id: "next-action",
      label: english
        ? `Why is “${context?.primaryActionLabel}” the next action?`
        : `왜 다음 행동이 “${context?.primaryActionLabel}”인가?`,
    });
  }
  if (hasText(context?.workHistorySummary)) {
    prompts.push({
      id: "work-history",
      label: english ? "Summarize recent work history" : "최근 작업 이력 요약",
    });
  }
  if (hasText(context?.postMaintenanceSummary)) {
    prompts.push({
      id: "post-maintenance",
      label: english ? "Summarize changes after maintenance" : "정비 후 결과 변화 요약",
    });
  }

  return prompts;
}

function includesAny(value: string, needles: string[]) {
  return needles.some((needle) => value.includes(needle));
}

export function groundedReliabilityAssistantAnswer(
  context: ReliabilityAssistantContext | null | undefined,
  question: string,
  locale: ReliabilityAssistantLocale = "ko-KR",
) {
  const english = locale === "en-US";
  if (!hasReliabilityAssistantSelection(context)) {
    return deterministicReliabilityAssistantAnswer(context, locale);
  }

  const normalized = question.trim().toLowerCase();
  const asset = reliabilityAssistantAssetLabel(context, locale);
  const risk = reliabilityAssistantRiskLabel(context?.failureProbability);

  if (includesAny(normalized, ["보고", "brief", "executive", "한 문단", "report draft", "kpi", "운영 리스크"])) {
    const summary = context?.aiSummary?.trim();
    const impact = hasText(context?.operationalImpact) ? context.operationalImpact : null;
    const decision = hasText(context?.recommendedDecisionLabel) ? context.recommendedDecisionLabel : null;
    const lifecycle = hasText(context?.currentLifecycleLabel) ? context.currentLifecycleLabel : null;
    const evidence = context?.evidenceItems?.filter(Boolean).slice(0, 2) ?? [];
    const facts = [
      risk ? (english ? `risk ${risk}` : `위험도 ${risk}`) : null,
      impact,
      decision ? (english ? `recommended action ${decision}` : `권고 조치 ${decision}`) : null,
      lifecycle ? (english ? `current step ${lifecycle}` : `현재 단계 ${lifecycle}`) : null,
      evidence.length ? evidence.join(english ? "; " : " · ") : null,
    ].filter((value): value is string => Boolean(value));
    if (summary) {
      return english
        ? `${summary} Executive reporting basis: ${facts.join("; ")}.`
        : `${summary} 경영 보고 기준으로 보면 ${facts.join(" · ")}입니다.`;
    }
    return english
      ? `${asset}: ${facts.join("; ")}. This draft converts the connected operational evidence into reporting language and should be reviewed before sharing.`
      : `${asset}은(는) ${facts.join(" · ")} 상태입니다. 연결된 운영 근거를 경영 보고 언어로 변환한 초안이며 공유 전 확인이 필요합니다.`;
  }

  if (includesAny(normalized, ["우선", "priority", "prioritized", "왜 이 설비"])) {
    const reasons = context?.priorityReasons?.filter(Boolean) ?? [];
    const canonicalReasons = [
      hasText(context?.statusLabel) ? (english ? `status ${context.statusLabel}` : `상태 ${context.statusLabel}`) : null,
      hasText(context?.operationalImpact) ? context.operationalImpact : null,
      hasText(context?.recommendedDecisionLabel)
        ? (english ? `recommended decision ${context.recommendedDecisionLabel}` : `권고 판단 ${context.recommendedDecisionLabel}`)
        : null,
      hasText(context?.predictedFailureType)
        ? (english ? `predicted issue ${context.predictedFailureType}` : `예측 이상 ${context.predictedFailureType}`)
        : null,
      hasText(context?.currentLifecycleLabel)
        ? (english ? `current step ${context.currentLifecycleLabel}` : `현재 단계 ${context.currentLifecycleLabel}`)
        : null,
      hasText(context?.primaryActionLabel)
        ? (english ? `next action ${context.primaryActionLabel}` : `다음 행동 ${context.primaryActionLabel}`)
        : null,
      context?.evidenceSummary ?? null,
    ].filter((value): value is string => Boolean(value));
    const reasonText = reasons.length
      ? reasons.slice(0, 4).join(english ? "; " : " · ")
      : canonicalReasons.slice(0, 5).join(english ? "; " : " · ");
    if (reasonText) {
      return english
        ? `${asset}${risk ? ` is currently at ${risk} risk` : ""}${context?.lineLabel ? ` on ${context.lineLabel}` : ""}. The connected review-priority basis is: ${reasonText}. This is prioritization evidence, not a failure confirmation.`
        : `${asset}${risk ? `의 현재 위험도는 ${risk}` : ""}${context?.lineLabel ? `이며 위치는 ${context.lineLabel}` : ""}입니다. 연결된 우선순위 근거는 ${reasonText}입니다. 이는 점검·검토 우선순위 근거이며 고장 확정이 아닙니다.`;
    }
  }

  if (includesAny(normalized, ["근거", "evidence", "요인", "factor"])) {
    const items = context?.evidenceItems?.filter(Boolean) ?? [];
    if (items.length) {
      return english
        ? `${asset}: the current connected evidence is ${items.slice(0, 4).join("; ")}. ${context?.retrievalCount ? `${context.retrievalCount} governed SOP guidance result(s) are also linked.` : ""}`
        : `${asset}의 현재 연결 근거는 ${items.slice(0, 4).join(" · ")}입니다.${context?.retrievalCount ? ` 또한 검증된 SOP 안내 ${context.retrievalCount}건이 연결되어 있습니다.` : ""}`;
    }
  }

  if (includesAny(normalized, ["단계", "workflow", "lifecycle", "다음", "next action", "행동"])) {
    const current = context?.currentLifecycleLabel;
    const next = context?.nextLifecycleLabel;
    const action = context?.primaryActionLabel;
    return english
      ? `${asset}: current step is ${current ?? "not provided"}${next ? `, next canonical step is ${next}` : ""}${action ? `, and the connected primary action is “${action}”` : ""}.`
      : `${asset}의 현재 단계는 ${current ?? "업무 단계 정보가 아직 없습니다"}${next ? `, 다음 단계는 ${next}` : ""}${action ? `이며 연결된 주요 행동은 “${action}”` : ""}입니다.`;
  }

  if (includesAny(normalized, ["이력", "history", "정비", "maintenance"])) {
    const history = context?.historyItems?.filter(Boolean) ?? [];
    if (history.length) {
      return english
        ? `${asset}: ${history.slice(0, 4).join("; ")}`
        : `${asset}의 연결된 최근 이력은 ${history.slice(0, 4).join(" · ")}입니다.`;
    }
  }

  if (hasText(context?.aiSummary)) {
    const source = context?.aiSummaryMode === "llm"
      ? (english ? `LLM grounded summary (${context?.aiProvider ?? "configured provider"})` : `LLM 근거 요약 (${context?.aiProvider ?? "configured provider"})`)
      : (english ? "validated deterministic fallback" : "검증된 deterministic fallback");
    return english
      ? `${context.aiSummary} Source: ${source}.`
      : `${context.aiSummary} · 출처: ${source}.`;
  }

  return deterministicReliabilityAssistantAnswer(context, locale);
}

export function deterministicReliabilityAssistantAnswer(
  context: ReliabilityAssistantContext | null | undefined,
  locale: ReliabilityAssistantLocale = "ko-KR",
) {
  const english = locale === "en-US";
  if (!hasReliabilityAssistantSelection(context)) {
    return english
      ? "Select an asset or event first. This preview only summarizes the operational context currently connected to the workspace."
      : "먼저 설비나 이벤트를 선택하세요. 이 preview는 workspace에 현재 연결된 운영 문맥만 요약합니다.";
  }

  const asset = reliabilityAssistantAssetLabel(context, locale);
  const risk = reliabilityAssistantRiskLabel(context?.failureProbability);
  const facts: string[] = [];

  if (risk) facts.push(english ? `risk ${risk}` : `위험도 ${risk}`);
  if (hasText(context?.statusLabel)) facts.push(english ? `status ${context.statusLabel}` : `상태 ${context.statusLabel}`);
  if (hasText(context?.operationalImpact)) facts.push(context.operationalImpact);
  if (hasText(context?.recommendedDecisionLabel)) {
    facts.push(english ? `recommended decision “${context.recommendedDecisionLabel}”` : `권고 판단 “${context.recommendedDecisionLabel}”`);
  }
  if (hasText(context?.currentLifecycleLabel)) {
    facts.push(english ? `current step “${context.currentLifecycleLabel}”` : `현재 단계 “${context.currentLifecycleLabel}”`);
  }
  if (hasText(context?.primaryActionLabel)) {
    facts.push(english ? `primary action “${context.primaryActionLabel}”` : `다음 주요 행동 “${context.primaryActionLabel}”`);
  }
  if ((context?.evidenceCount ?? 0) > 0) {
    facts.push(english ? `${context?.evidenceCount} linked evidence item(s)` : `연결 근거 ${context?.evidenceCount}건`);
  }
  if ((context?.workOrderCount ?? 0) > 0) {
    facts.push(english ? `${context?.workOrderCount} linked work order(s)` : `연결 WorkOrder ${context?.workOrderCount}건`);
  }

  if (!facts.length) {
    return english
      ? `${asset} is selected, but there are no additional connected facts to summarize in this context.`
      : `${asset}이(가) 선택되어 있지만 이 문맥에서 추가로 요약할 연결 정보는 없습니다.`;
  }

  return english
    ? `${asset}: ${facts.join(", ")}. This is a deterministic summary of connected data, not an approval or execution decision.`
    : `${asset}: ${facts.join(", ")}가 확인됩니다. 연결된 데이터를 규칙 기반으로 정리한 내용이며 승인이나 실행 판단이 아닙니다.`;
}
