const STATUS_LABEL: Record<string, string> = {
  normal: "정상",
  attention: "관심",
  warning: "경고",
  critical: "긴급 검토",
  data_quality_hold: "데이터 확인",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge status-${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}
