import type { AppLocale } from "../../ui/i18n/messages";

export type AgentDisplayOutcome =
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "partial"
  | "no_evidence"
  | "failed";

interface AgentOutcomeInput {
  status: string;
  evidenceCount: number;
  claimCount?: number;
  failedStepCount?: number;
  caveats?: string[];
}

export function deriveAgentOutcome({
  status,
  evidenceCount,
  claimCount = 0,
  failedStepCount = 0,
  caveats = [],
}: AgentOutcomeInput): AgentDisplayOutcome {
  if (status === "failed") return "failed";
  if (status === "running") return "running";
  if (status === "awaiting_approval") return "awaiting_approval";
  if (status === "succeeded" && evidenceCount === 0) return "no_evidence";
  if (
    status === "succeeded"
    && (failedStepCount > 0 || (evidenceCount > 0 && claimCount === 0) || caveats.some((item) => /unavailable|failed|제한|장애/i.test(item)))
  ) return "partial";
  return "succeeded";
}

export function agentOutcomeLabel(outcome: AgentDisplayOutcome, locale: AppLocale): string {
  const ko: Record<AgentDisplayOutcome, string> = {
    running: "실행 중",
    awaiting_approval: "승인 대기",
    succeeded: "근거 검증 완료",
    partial: "부분 완료",
    no_evidence: "근거 없음",
    failed: "실패",
  };
  const en: Record<AgentDisplayOutcome, string> = {
    running: "Running",
    awaiting_approval: "Awaiting approval",
    succeeded: "Grounded",
    partial: "Partial",
    no_evidence: "No evidence",
    failed: "Failed",
  };
  return (locale === "ko-KR" ? ko : en)[outcome];
}

export function agentOutcomeIntent(outcome: AgentDisplayOutcome): "success" | "danger" | "warning" | "neutral" {
  if (outcome === "succeeded") return "success";
  if (outcome === "failed") return "danger";
  if (outcome === "running" || outcome === "awaiting_approval" || outcome === "partial" || outcome === "no_evidence") return "warning";
  return "neutral";
}
