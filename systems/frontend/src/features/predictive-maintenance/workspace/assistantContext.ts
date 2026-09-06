export type ReliabilityAssistantLocale = "ko-KR" | "en-US";

export interface ReliabilityAssistantContext {
  roleKind?: "executive" | "operations" | "engineering" | "maintenance" | null;
  workspaceName?: string | null;
  statusCode?: string | null;
  recommendedDecisionCode?: string | null;
  workspaceMetrics?: {
    totalAssets: number;
    normal: number;
    attention: number;
    warning: number;
    critical: number;
    dataQualityHold: number;
    averageRisk: number | null;
    estimatedDowntimeMinutes: number | null;
    pendingDecisions: number;
  } | null;
  workspaceTopRisks?: Array<{
    assetLabel: string;
    risk: number | null;
    status: string;
  }>;
  assetId?: string | null;
  assetName?: string | null;
  eventId?: string | null;
  failureProbability?: number | null;
  statusLabel?: string | null;
  lineLabel?: string | null;
  operationalImpact?: string | null;
  estimatedDowntimeMinutes?: number | null;
  estimatedLostUnits?: number | null;
  productVariant?: string | null;
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
  activityTrace?: ReliabilityAssistantActivityTrace | null;
}

export interface ReliabilityAssistantActivityStep {
  id: string;
  label: string;
  detail?: string | null;
  store?: string | null;
  status: "succeeded" | "failed" | "skipped" | "fallback";
  latencyMs?: number | null;
}

export interface ReliabilityAssistantActivityTrace {
  runId?: string | null;
  route?: string | null;
  status: "succeeded" | "failed" | "fallback";
  persistence?: "persisted" | "unavailable" | null;
  evidenceCount: number;
  claimCount: number;
  checkpointSequence?: number | null;
  durationMs?: number | null;
  steps: ReliabilityAssistantActivityStep[];
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
  const english = locale === "en-US";
  if (!hasReliabilityAssistantSelection(context)) {
    const role = context?.roleKind ?? "engineering";
    const workspacePrompts: Record<NonNullable<ReliabilityAssistantContext["roleKind"]>, ReliabilityAssistantPrompt[]> = {
      engineering: english ? [
        { id: "workspace-risk", label: "Which assets need engineering attention now?" },
        { id: "workspace-top", label: "Show the highest-risk assets and why they matter" },
        { id: "workspace-quality", label: "Are there any data-quality issues I should check first?" },
        { id: "workspace-value", label: "What operational value is the team protecting right now?" },
      ] : [
        { id: "workspace-risk", label: "지금 엔지니어가 먼저 봐야 할 설비는?" },
        { id: "workspace-top", label: "현재 위험도가 높은 설비와 이유를 요약해줘" },
        { id: "workspace-quality", label: "먼저 확인해야 할 데이터 품질 이슈가 있나요?" },
        { id: "workspace-value", label: "지금 현장팀이 보호하고 있는 운영 가치는 무엇인가요?" },
      ],
      maintenance: english ? [
        { id: "workspace-work", label: "Which maintenance work needs attention now?" },
        { id: "workspace-backlog", label: "Summarize the maintenance backlog and constraints" },
        { id: "workspace-history", label: "What recurring maintenance patterns are visible?" },
        { id: "workspace-material", label: "Are parts or lead times constraining current work?" },
      ] : [
        { id: "workspace-work", label: "지금 정비팀이 먼저 봐야 할 작업은?" },
        { id: "workspace-backlog", label: "정비 backlog와 제약을 요약해줘" },
        { id: "workspace-history", label: "반복되는 정비 패턴이나 재발 징후가 있나요?" },
        { id: "workspace-material", label: "현재 자재나 리드타임이 작업을 막고 있나요?" },
      ],
      operations: english ? [
        { id: "workspace-decisions", label: "Which decisions are waiting for approval now?" },
        { id: "workspace-impact", label: "Which cases have the largest production exposure?" },
        { id: "workspace-priority", label: "What should operations prioritize today?" },
        { id: "workspace-report", label: "Summarize today's operational risk for management" },
      ] : [
        { id: "workspace-decisions", label: "지금 판단 대기 중인 항목은 무엇인가요?" },
        { id: "workspace-impact", label: "생산 영향이 큰 Case부터 요약해줘" },
        { id: "workspace-priority", label: "오늘 운영에서 무엇을 가장 먼저 판단해야 하나요?" },
        { id: "workspace-report", label: "오늘 운영 리스크를 경영 보고용으로 요약해줘" },
      ],
      executive: english ? [
        { id: "workspace-exec-risk", label: "Summarize current plant risk in one paragraph" },
        { id: "workspace-exec-kpi", label: "Which KPIs are most exposed right now?" },
        { id: "workspace-exec-delay", label: "Where are decisions slowing down value protection?" },
        { id: "workspace-exec-value", label: "What business value is current reliability work protecting?" },
      ] : [
        { id: "workspace-exec-risk", label: "현재 공장 리스크를 한 문단으로 요약해줘" },
        { id: "workspace-exec-kpi", label: "지금 어떤 KPI가 가장 영향을 받을 수 있나요?" },
        { id: "workspace-exec-delay", label: "어디에서 판단 지연이 가치 보호를 늦추고 있나요?" },
        { id: "workspace-exec-value", label: "현재 Reliability 업무가 보호하는 회사 가치는 무엇인가요?" },
      ],
    };
    return workspacePrompts[role];
  }

  const monitoringOnly = isMonitoringOnlyContext(context);
  const severe = ["critical", "warning"].includes((context?.statusCode ?? "").toLowerCase());
  const hasMaintenanceOutcome = hasText(context?.postMaintenanceSummary);

  if (context?.roleKind) {
    if (context.roleKind === "engineering" && hasMaintenanceOutcome) {
      return english ? [
        { id: "engineer-after", label: "Did risk and signals improve after maintenance?" },
        { id: "engineer-recurrence", label: "Is there any sign of recurrence?" },
        { id: "engineer-after-evidence", label: "Which before/after evidence matters most?" },
        { id: "engineer-after-value", label: "What operational value has been verified so far?" },
      ] : [
        { id: "engineer-after", label: "정비 후 위험도와 신호가 실제로 좋아졌나요?" },
        { id: "engineer-recurrence", label: "재발 징후가 남아 있나요?" },
        { id: "engineer-after-evidence", label: "정비 전후 어떤 근거를 가장 중요하게 봐야 하나요?" },
        { id: "engineer-after-value", label: "현재까지 검증된 운영 가치는 무엇인가요?" },
      ];
    }
    if (context.roleKind === "engineering" && monitoringOnly) {
      return english ? [
        { id: "engineer-normal", label: "Why is this asset staying in monitoring instead of inspection?" },
        { id: "engineer-normal-signals", label: "Which signals support the current normal assessment?" },
        { id: "engineer-escalation", label: "What would make this asset require inspection?" },
        { id: "engineer-normal-value", label: "What value does avoiding unnecessary maintenance protect?" },
      ] : [
        { id: "engineer-normal", label: "왜 이 설비는 점검보다 모니터링이 우선인가요?" },
        { id: "engineer-normal-signals", label: "현재 정상 판단을 뒷받침하는 신호는 무엇인가요?" },
        { id: "engineer-escalation", label: "어떤 변화가 생기면 점검이 필요해지나요?" },
        { id: "engineer-normal-value", label: "불필요한 정비를 피하는 것이 어떤 운영 가치를 보호하나요?" },
      ];
    }
    if (context.roleKind === "maintenance" && hasMaintenanceOutcome) {
      return english ? [
        { id: "maintenance-after", label: "What changed after the completed maintenance?" },
        { id: "maintenance-recurrence", label: "Is there any sign of recurrence?" },
        { id: "maintenance-proof", label: "Which before/after evidence proves the effect?" },
        { id: "maintenance-value", label: "What value has been verified and what is still estimated?" },
      ] : [
        { id: "maintenance-after", label: "정비 완료 후 무엇이 실제로 달라졌나요?" },
        { id: "maintenance-recurrence", label: "재발 징후가 남아 있나요?" },
        { id: "maintenance-proof", label: "정비 효과를 입증하는 before/after 근거는 무엇인가요?" },
        { id: "maintenance-value", label: "검증된 가치와 아직 추정인 값은 무엇인가요?" },
      ];
    }
    if (context.roleKind === "maintenance" && monitoringOnly) {
      return english ? [
        { id: "maintenance-normal", label: "Why is no maintenance action needed now?" },
        { id: "maintenance-normal-history", label: "Does recent maintenance history suggest recurrence risk?" },
        { id: "maintenance-escalation", label: "What change would trigger maintenance work?" },
        { id: "maintenance-normal-value", label: "What value does avoiding unnecessary work protect?" },
      ] : [
        { id: "maintenance-normal", label: "왜 지금은 정비 작업이 필요하지 않나요?" },
        { id: "maintenance-normal-history", label: "최근 정비 이력에서 재발 위험이 보이나요?" },
        { id: "maintenance-escalation", label: "어떤 변화가 생기면 정비 작업으로 전환되나요?" },
        { id: "maintenance-normal-value", label: "불필요한 작업을 피하는 것이 어떤 가치를 보호하나요?" },
      ];
    }
    if (context.roleKind === "operations" && monitoringOnly) {
      return english ? [
        { id: "manager-normal", label: "Why is monitoring sufficient instead of approving work?" },
        { id: "manager-normal-impact", label: "What production exposure is being watched?" },
        { id: "manager-escalation", label: "What would require an operations decision?" },
        { id: "manager-normal-value", label: "What value does avoiding premature work protect?" },
      ] : [
        { id: "manager-normal", label: "왜 지금은 작업 승인보다 모니터링 유지가 적절한가요?" },
        { id: "manager-normal-impact", label: "현재 어떤 생산 노출을 지켜보고 있나요?" },
        { id: "manager-escalation", label: "어떤 변화가 생기면 운영 판단이 필요해지나요?" },
        { id: "manager-normal-value", label: "성급한 작업을 피하는 것이 어떤 운영 가치를 보호하나요?" },
      ];
    }
    if (context.roleKind === "executive" && monitoringOnly) {
      return english ? [
        { id: "executive-normal", label: "What does this normal state mean for business risk?" },
        { id: "executive-normal-kpi", label: "Which KPI is protected by stable operation?" },
        { id: "executive-normal-value", label: "What value comes from avoiding unnecessary maintenance?" },
        { id: "executive-escalation", label: "What would make this case management-relevant?" },
      ] : [
        { id: "executive-normal", label: "현재 정상 상태가 회사 리스크 측면에서 어떤 의미인가요?" },
        { id: "executive-normal-kpi", label: "안정 운전이 어떤 KPI를 보호하고 있나요?" },
        { id: "executive-normal-value", label: "불필요한 정비를 피하면서 어떤 가치를 지키고 있나요?" },
        { id: "executive-escalation", label: "어떤 변화가 생기면 경영진이 봐야 하는 Case가 되나요?" },
      ];
    }
    const rolePrompts: Record<NonNullable<ReliabilityAssistantContext["roleKind"]>, ReliabilityAssistantPrompt[]> = {
      engineering: english ? [
        { id: "engineer-why", label: severe ? "Why does this asset need immediate review?" : "Why does this asset need inspection?" },
        { id: "engineer-sensor", label: "Which sensors should I check first?" },
        { id: "engineer-checklist", label: "What should I inspect now?" },
        { id: "engineer-value", label: severe ? "What production exposure can early action protect?" : "What operational value does early detection protect?" },
      ] : [
        { id: "engineer-why", label: severe ? "왜 이 설비를 지금 우선 확인해야 하나요?" : "왜 이 설비는 점검이 필요한가요?" },
        { id: "engineer-sensor", label: "어떤 센서를 먼저 확인해야 하나요?" },
        { id: "engineer-checklist", label: "점검 항목은 무엇인가요?" },
        { id: "engineer-value", label: severe ? "지금 대응하면 어떤 생산 손실 노출을 보호할 수 있나요?" : "이 조기 발견이 어떤 운영 가치를 보호하나요?" },
      ],
      maintenance: english ? [
        { id: "maintenance-next", label: "What approved work should I perform now?" },
        { id: "maintenance-evidence", label: "What evidence should I verify on site?" },
        { id: "maintenance-history", label: "Summarize recent maintenance history" },
        { id: "maintenance-after", label: "What operational value should I verify after maintenance?" },
      ] : [
        { id: "maintenance-next", label: "지금 수행해야 할 승인 작업은 무엇인가요?" },
        { id: "maintenance-evidence", label: "현장에서 확인할 근거는 무엇인가요?" },
        { id: "maintenance-history", label: "최근 정비 이력을 요약해줘" },
        { id: "maintenance-after", label: "정비 후 어떤 운영 가치를 확인해야 하나요?" },
      ],
      operations: english ? [
        { id: "manager-action", label: "What action should I approve now?" },
        { id: "manager-impact", label: "What production and cost value can this action protect?" },
        { id: "manager-delay", label: "What risk increases if we defer this?" },
        { id: "manager-report", label: "Create an executive report draft" },
      ] : [
        { id: "manager-action", label: "지금 승인해야 하는 조치는 무엇인가요?" },
        { id: "manager-impact", label: "이 조치로 어떤 생산·비용 가치를 보호할 수 있나요?" },
        { id: "manager-delay", label: "보류하면 어떤 리스크가 있나요?" },
        { id: "manager-report", label: "경영진 보고 초안을 만들어줘" },
      ],
      executive: english ? [
        { id: "executive-brief", label: "Summarize the business value of this case in one paragraph" },
        { id: "executive-kpi", label: "How do avoided exposure and this response affect KPIs?" },
        { id: "executive-delay", label: "Summarize the currently delayed decisions" },
        { id: "executive-risk", label: "Summarize this week's operational risk" },
      ] : [
        { id: "executive-brief", label: "이 Case가 보호·창출하는 가치를 보고용 한 문단으로 요약해줘" },
        { id: "executive-kpi", label: "회피 가능한 손실과 대응이 KPI에 미치는 영향은?" },
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

export function reliabilityAssistantContextSummary(
  context: ReliabilityAssistantContext | null | undefined,
  locale: ReliabilityAssistantLocale = "ko-KR",
) {
  const english = locale === "en-US";
  if (!context) return null;
  if (!hasReliabilityAssistantSelection(context)) {
    const metrics = context.workspaceMetrics;
    if (!metrics) return english
      ? "Ask about plant-wide risk, pending decisions, maintenance history, KPIs, or company knowledge without selecting an asset."
      : "설비를 선택하지 않아도 공장 전체 리스크, 판단 대기, 정비 이력, KPI와 회사 지식에 대해 질문할 수 있습니다.";
    return english
      ? `${metrics.totalAssets} assets · ${metrics.critical} critical · ${metrics.warning} warning · ${metrics.pendingDecisions} pending decisions. Ask at workspace scope or select an asset for case-specific evidence.`
      : `전체 ${metrics.totalAssets}대 · 고위험 ${metrics.critical}대 · 경고 ${metrics.warning}대 · 판단 대기 ${metrics.pendingDecisions}건입니다. 지금은 공장 전체 관점으로 질문하거나 설비를 선택해 Case 근거까지 좁힐 수 있습니다.`;
  }

  const risk = reliabilityAssistantRiskLabel(context.failureProbability);
  const decision = context.recommendedDecisionLabel?.trim();
  if (isMonitoringOnlyContext(context)) {
    return english
      ? `${risk ? `Risk ${risk} · ` : ""}${decision ? `recommendation: ${decision}. ` : ""}The asset is below the current escalation boundary; monitoring is more appropriate than immediate inspection unless the signals change.`
      : `${risk ? `현재 위험도 ${risk} · ` : ""}${decision ? `권고: ${decision}. ` : ""}현재는 즉시 점검보다 추세 관찰이 우선인 상태입니다. 위험 신호가 바뀌면 점검 우선순위가 다시 올라갑니다.`;
  }
  return english
    ? `${risk ? `Risk ${risk} · ` : ""}${decision ? `recommendation: ${decision}. ` : ""}This is a human-review priority, not a confirmed failure. Use the linked signals and workflow state to decide the next action.`
    : `${risk ? `현재 위험도 ${risk} · ` : ""}${decision ? `권고: ${decision}. ` : ""}고장 확정이 아니라 사람의 확인이 필요한 우선 검토 상태입니다. 연결된 신호와 현재 workflow를 기준으로 다음 행동을 판단합니다.`;
}

function workspaceReliabilityAssistantAnswer(
  context: ReliabilityAssistantContext | null | undefined,
  question: string,
  locale: ReliabilityAssistantLocale,
) {
  const english = locale === "en-US";
  const metrics = context?.workspaceMetrics;
  if (!metrics) {
    return english
      ? "No single asset is selected. You can ask about workspace-wide risk, decisions, maintenance history, KPIs, finance, meetings, or company knowledge."
      : "현재 단일 설비는 선택되지 않았습니다. 공장 전체 리스크, 판단 대기, 정비 이력, KPI, 재무, 회의 기록이나 회사 지식에 대해 질문할 수 있습니다.";
  }
  const normalized = question.trim().toLowerCase();
  const top = context?.workspaceTopRisks?.slice(0, 3) ?? [];
  const topText = top.length
    ? top.map((item) => `${item.assetLabel}${typeof item.risk === "number" ? ` ${Math.round(item.risk * 100)}%` : ""}`).join(" · ")
    : null;

  if (includesAny(normalized, ["판단 대기", "승인", "decision", "approve", "backlog", "우선 판단"])) {
    return english
      ? `There are ${metrics.pendingDecisions} pending decisions across the workspace. ${topText ? `The current highest-risk assets are ${topText}. ` : ""}Prioritize cases with the largest production exposure and the clearest next owner rather than treating every alert as maintenance work.`
      : `현재 workspace에는 판단 대기 ${metrics.pendingDecisions}건이 있습니다. ${topText ? `위험도가 높은 설비는 ${topText}입니다. ` : ""}모든 알림을 정비로 넘기기보다 생산 영향이 크고 다음 Owner가 명확한 Case부터 판단하는 것이 우선입니다.`;
  }
  if (includesAny(normalized, ["품질", "quality", "데이터", "hold"])) {
    return english
      ? `${metrics.dataQualityHold} data-quality hold item(s) are active. Resolve those before treating affected risk scores as a basis for maintenance or business-impact claims.`
      : `현재 데이터 품질 보류 항목은 ${metrics.dataQualityHold}건입니다. 해당 항목이 남아 있는 설비는 위험 점수를 정비 판단이나 경영 영향 확정의 근거로 사용하기 전에 먼저 품질 문제를 해소해야 합니다.`;
  }
  if (includesAny(normalized, ["kpi", "가치", "value", "비용", "절감", "경영", "생산 연속성"])) {
    const downtime = typeof metrics.estimatedDowntimeMinutes === "number" && metrics.estimatedDowntimeMinutes > 0
      ? metrics.estimatedDowntimeMinutes
      : null;
    return english
      ? `Reliability work is currently protecting production continuity by separating ${metrics.critical + metrics.warning + metrics.attention} assets that need closer review from ${metrics.normal} assets that can remain in normal monitoring.${downtime ? ` The modeled workspace exposure includes about ${downtime} minutes of downtime.` : ""} This is protected exposure, not booked savings.`
      : `현재 Reliability 업무의 가치는 전체 설비 중 추가 확인이 필요한 ${metrics.critical + metrics.warning + metrics.attention}대와 정상 모니터링을 유지할 ${metrics.normal}대를 구분해 불필요한 정비는 줄이고 필요한 대응은 앞당기는 데 있습니다.${downtime ? ` 현재 모델 기준 workspace 정지 노출은 약 ${downtime}분입니다.` : ""} 이 값은 실제 절감 실적이 아니라 보호 대상 노출입니다.`;
  }
  return english
    ? `Across ${metrics.totalAssets} assets, ${metrics.critical} are critical, ${metrics.warning} warning, ${metrics.attention} attention, and ${metrics.normal} normal.${topText ? ` Highest current risk: ${topText}.` : ""} Select an asset when you want sensor-, evidence-, or workflow-level detail.`
    : `현재 전체 ${metrics.totalAssets}대 중 고위험 ${metrics.critical}대, 경고 ${metrics.warning}대, 주의 ${metrics.attention}대, 정상 ${metrics.normal}대입니다.${topText ? ` 현재 위험 상위 설비는 ${topText}입니다.` : ""} 센서·근거·workflow까지 자세히 보려면 해당 설비를 선택하면 됩니다.`;
}

function includesAny(value: string, needles: string[]) {
  return needles.some((needle) => value.includes(needle));
}

function isMonitoringOnlyContext(context: ReliabilityAssistantContext | null | undefined) {
  const decision = context?.recommendedDecisionLabel?.toLowerCase() ?? "";
  const status = context?.statusLabel?.toLowerCase() ?? "";
  return decision.includes("모니터링")
    || decision.includes("monitor")
    || status.includes("정상")
    || status === "normal"
    || (typeof context?.failureProbability === "number" && context.failureProbability < 0.2);
}

function conciseEvidenceItems(
  context: ReliabilityAssistantContext | null | undefined,
  limit = 2,
) {
  return (context?.evidenceItems ?? [])
    .filter((item) => item.trim())
    .filter((item) => !/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/i.test(item))
    .filter((item) => !/model unit|source[_ ]?ref|artifact manifest|deterministic/i.test(item))
    .slice(0, limit);
}

function valueProtectionFrame(
  context: ReliabilityAssistantContext | null | undefined,
  english: boolean,
  monitoringOnly = isMonitoringOnlyContext(context),
) {
  const downtime = typeof context?.estimatedDowntimeMinutes === "number" && context.estimatedDowntimeMinutes > 0
    ? context.estimatedDowntimeMinutes
    : null;
  const lostUnits = typeof context?.estimatedLostUnits === "number" && context.estimatedLostUnits > 0
    ? context.estimatedLostUnits
    : null;

  if (!downtime && !lostUnits && !context?.productVariant) return null;

  const exposure = [
    downtime
      ? (english ? `up to ${downtime} minutes of potential downtime` : `최대 ${downtime}분의 잠재 비가동`)
      : null,
    lostUnits
      ? (english
          ? `about ${lostUnits.toLocaleString("en-US")} planned units at risk`
          : `계획 생산 약 ${lostUnits.toLocaleString("ko-KR")}개의 손실 가능성`)
      : null,
  ].filter((value): value is string => Boolean(value));

  if (english) {
    const scope = exposure.join(" and ") || `the ${context?.productVariant ?? "current"} production plan`;
    return monitoringOnly
      ? `From a business-value perspective, the current benefit is to keep watching the early signal without triggering unnecessary maintenance, while managing ${scope} before it becomes an actual disruption. This is protected exposure, not booked savings.`
      : `From a business-value perspective, the key opportunity is to act early enough to keep ${scope} from becoming an actual production loss. This is protected exposure, not booked savings.`;
  }

  const scope = exposure.join("과 ") || `${context?.productVariant ?? "현재"} 생산 계획`;
  return monitoringOnly
    ? `회사 관점에서는 지금 불필요한 정비를 서두르지 않으면서 조기 징후를 계속 관찰하고, ${scope}이 실제 생산 차질로 이어지기 전에 관리해 생산 연속성을 보호하는 것이 핵심 가치입니다. 이 수치는 실제 절감액이 아니라 보호 대상 노출입니다.`
    : `회사 관점에서는 조기에 확인하고 대응해 ${scope}이 실제 생산 손실로 이어지는 것을 줄이고 생산 연속성을 보호할 기회를 확보하는 것이 핵심 가치입니다. 이 수치는 실제 절감액이 아니라 보호 대상 노출입니다.`;
}

export function isUserFacingReliabilityAssistantAnswer(answer: string) {
  const normalized = answer.trim();
  if (!normalized) return false;
  const forbiddenTechnicalPatterns = [
    /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/i,
    /model unit/i,
    /generator failure score/i,
    /model selected threshold/i,
    /asset criticality adjustment/i,
    /source[_ ]?ref/i,
    /deterministic fallback/i,
    /team db/i,
    /모델 산출 위험 점수|고위험 판정 기준값|위험 판정 기준값|설비 중요도 보정/,
    /\b\d+\.\d{5,}\b/,
  ];
  return !forbiddenTechnicalPatterns.some((pattern) => pattern.test(normalized));
}

export function groundedReliabilityAssistantAnswer(
  context: ReliabilityAssistantContext | null | undefined,
  question: string,
  locale: ReliabilityAssistantLocale = "ko-KR",
) {
  const english = locale === "en-US";
  if (!hasReliabilityAssistantSelection(context)) {
    return workspaceReliabilityAssistantAnswer(context, question, locale);
  }

  const normalized = question.trim().toLowerCase();
  const asset = reliabilityAssistantAssetLabel(context, locale);
  const risk = reliabilityAssistantRiskLabel(context?.failureProbability);
  const monitoringOnly = isMonitoringOnlyContext(context);
  const valueFrame = valueProtectionFrame(context, english, monitoringOnly);

  if (monitoringOnly && includesAny(normalized, [
    "왜 지금",
    "왜 이 설비",
    "모니터링이 우선",
    "모니터링 유지",
    "정비 작업이 필요하지",
    "작업 승인보다",
    "staying in monitoring",
    "monitoring sufficient",
    "no maintenance action",
  ])) {
    const decision = context?.recommendedDecisionLabel?.trim();
    return english
      ? `${asset} is not currently confirmed as abnormal or failed. ${risk ? `Risk is ${risk}` : "Risk remains low"}${decision ? ` and the recommendation is “${decision}”` : ""}. That means monitoring the trend is more appropriate than starting inspection or maintenance without stronger evidence.${valueFrame ? ` ${valueFrame}` : ""}`
      : `${asset}는 현재 고장이나 이상으로 확정된 상태가 아닙니다. ${risk ? `위험도는 ${risk}` : "위험도는 낮은 편"}${decision ? `이고 권고는 “${decision}”` : ""}입니다. 따라서 더 강한 근거가 생기기 전에는 점검이나 정비를 시작하기보다 추세를 계속 관찰하는 것이 적절합니다.${valueFrame ? ` ${valueFrame}` : ""}`;
  }

  if (monitoringOnly && includesAny(normalized, [
    "정상 판단",
    "뒷받침하는 신호",
    "support the current normal",
    "support the normal assessment",
  ])) {
    const items = conciseEvidenceItems(context, 3);
    if (items.length) {
      return english
        ? `The current normal assessment is supported by ${items.join("; ")}. These signals are being used to justify continued monitoring, not to claim that a physical cause has been proven.`
        : `현재 정상 판단을 뒷받침하는 사용자-facing 근거는 ${items.join(" · ")}입니다. 이 근거는 계속 모니터링할 수 있다는 판단을 돕는 것이며, 물리적 원인을 확정했다는 뜻은 아닙니다.`;
    }
    return english
      ? `The asset remains below the current escalation boundary, but there is not enough user-facing physical sensor evidence to name a specific cause. Keep monitoring until a signal trend or operating state changes materially.`
      : `현재 설비는 점검 전환 기준보다 낮은 상태지만, 특정 물리 원인을 설명할 사용자-facing 센서 근거는 아직 충분하지 않습니다. 센서 추세나 운영 상태가 의미 있게 바뀌는지 계속 관찰하는 것이 맞습니다.`;
  }

  if (monitoringOnly && includesAny(normalized, [
    "어떤 변화",
    "필요해지",
    "전환",
    "trigger",
    "escalat",
    "management-relevant",
  ])) {
    return english
      ? `Escalation becomes appropriate when the risk state leaves normal monitoring, the recommendation changes to inspection or maintenance, or a persistent sensor/operating trend adds new evidence. Until one of those changes occurs, the current decision is to keep observing rather than create work prematurely.`
      : `점검이나 정비로 전환할 시점은 위험 상태가 정상 모니터링 범위를 벗어나거나, 권고가 점검·정비로 바뀌거나, 지속적인 센서·운영 추세가 새로운 근거로 확인될 때입니다. 그 전까지는 성급하게 작업을 만들기보다 관찰을 유지하는 것이 현재 판단입니다.`;
  }

  if (includesAny(normalized, ["보고", "brief", "executive", "한 문단", "report draft", "kpi", "운영 리스크", "비용", "절감", "가치", "value", "saving", "roi"])) {
    const summary = context?.aiSummary?.trim();
    const impact = hasText(context?.operationalImpact) ? context.operationalImpact : null;
    const decision = hasText(context?.recommendedDecisionLabel) ? context.recommendedDecisionLabel : null;
    const lifecycle = hasText(context?.currentLifecycleLabel) ? context.currentLifecycleLabel : null;
    const evidence = conciseEvidenceItems(context, 2);
    const facts = [
      risk ? (english ? `risk ${risk}` : `위험도 ${risk}`) : null,
      impact,
      decision ? (english ? `recommended action ${decision}` : `권고 조치 ${decision}`) : null,
      lifecycle ? (english ? `current step ${lifecycle}` : `현재 단계 ${lifecycle}`) : null,
      evidence.length ? evidence.join(english ? "; " : " · ") : null,
    ].filter((value): value is string => Boolean(value));
    if (summary) {
      return english
        ? `${summary} ${valueFrame ?? ""} Executive reporting basis: ${facts.join("; ")}.`
        : `${summary} ${valueFrame ?? ""} 경영 보고 기준으로 보면 ${facts.join(" · ")}입니다.`;
    }
    return english
      ? `${asset}: ${facts.join("; ")}. ${valueFrame ?? ""} This draft converts the connected operational evidence into value-realization language and should be reviewed before sharing.`
      : `${asset}은(는) ${facts.join(" · ")} 상태입니다. ${valueFrame ?? ""} 연결된 운영 근거를 가치 실현 관점의 경영 언어로 변환한 초안이며 공유 전 확인이 필요합니다.`;
  }

  if (includesAny(normalized, ["우선", "priority", "prioritized", "왜 이 설비"])) {
    const evidenceItems = conciseEvidenceItems(context);
    const decision = context?.recommendedDecisionLabel?.trim();
    const evidenceSentence = evidenceItems.length
      ? (english
          ? `The clearest connected evidence is ${evidenceItems.join(" and ")}.`
          : `현재 사람이 확인할 핵심 근거는 ${evidenceItems.join(" · ")}입니다.`)
      : "";

    if (monitoringOnly) {
      return english
        ? `The current evidence does not confirm ${asset} as a failed or abnormal asset. ${risk ? `The current risk is ${risk}` : "Risk remains low"}${decision ? ` and the recommended action is “${decision}”` : ""}. The practical decision is to keep watching the early signal rather than trigger unnecessary maintenance. ${evidenceSentence}${valueFrame ? ` ${valueFrame}` : ""}`
        : `현재 근거만 보면 ${asset}를 고장 이상으로 확정한 상태는 아닙니다. ${risk ? `현재 위험도는 ${risk}` : "현재 위험도는 낮은 편"}${decision ? `이고 권고 조치는 “${decision}”` : ""}입니다. 즉 지금은 즉시 수리보다 조기 징후를 계속 관찰하면서 불필요한 정비를 피하는 단계입니다.${evidenceSentence ? ` ${evidenceSentence}` : ""}${valueFrame ? ` ${valueFrame}` : ""}`;
    }

    return english
      ? `${asset}${risk ? ` is at ${risk} risk` : ""}${decision ? `, with “${decision}” as the current recommended action` : ""}. That makes it a priority for human review, not a confirmed failure. ${evidenceSentence}${valueFrame ? ` ${valueFrame}` : ""}`
      : `${asset}${risk ? `의 현재 위험도는 ${risk}` : ""}${decision ? `이며 현재 권고 조치는 “${decision}”` : ""}입니다. 그래서 우선 확인 대상이지만 아직 고장 확정은 아닙니다.${evidenceSentence ? ` ${evidenceSentence}` : ""}${valueFrame ? ` ${valueFrame}` : ""}`;
  }

  if (includesAny(normalized, ["근거", "evidence", "요인", "factor"])) {
    const items = conciseEvidenceItems(context, 4);
    if (items.length) {
      return english
        ? `The main evidence for ${asset} is ${items.join("; ")}. These are decision-support signals, not a confirmed physical root cause.${context?.retrievalCount ? ` ${context.retrievalCount} governed SOP guidance result(s) are also linked.` : ""}`
        : `${asset}에서 지금 확인할 핵심 근거는 ${items.join(" · ")}입니다. 이 값들은 판단을 돕는 근거이지 물리적 고장 원인이 확정됐다는 뜻은 아닙니다.${context?.retrievalCount ? ` 검증된 SOP 안내 ${context.retrievalCount}건도 함께 연결되어 있습니다.` : ""}`;
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
      ? (english ? "grounded operational evidence summary" : "운영 근거 기반 요약")
      : (english ? "validated operational evidence summary" : "검증된 운영 근거 요약");
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
    return workspaceReliabilityAssistantAnswer(context, "", locale);
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
