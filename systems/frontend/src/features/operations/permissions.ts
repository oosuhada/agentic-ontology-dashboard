const AGENT_REVIEW_MATERIALIZE_PERMISSION = "agent.review.materialize";
const Operations_SYSTEM_LOG_READ_PERMISSION = "admin.audit.read";

export function canMaterializeAgentReviewSummary(
  permissions: readonly string[] | null | undefined,
): boolean {
  return Boolean(permissions?.includes(AGENT_REVIEW_MATERIALIZE_PERMISSION));
}

export function canReadOperationsSystemLogs(
  permissions: readonly string[] | null | undefined,
): boolean {
  return Boolean(permissions?.includes(Operations_SYSTEM_LOG_READ_PERMISSION));
}
