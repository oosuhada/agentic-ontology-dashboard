import { useI18n } from "../ui/i18n/I18nProvider";
import type { MessageKey } from "../ui/i18n/messages";

const STATUS_LABEL: Record<string, MessageKey> = {
  normal: "status.normal",
  attention: "status.attention",
  warning: "status.warning",
  critical: "status.critical",
  data_quality_hold: "status.dataQualityHold",
};

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const key = STATUS_LABEL[status];
  return <span className={`status-badge status-${status}`}>{key ? t(key) : status}</span>;
}
