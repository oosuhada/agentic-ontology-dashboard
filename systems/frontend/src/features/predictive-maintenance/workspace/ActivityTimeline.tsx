import {
  Ban,
  CheckCircle2,
  Circle,
  CircleDot,
  TriangleAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import "./lifecycle-instrument.css";

export type ActivityTimelineStatus = "completed" | "current" | "pending" | "blocked" | "failed";

export interface ActivityTimelineItem {
  id: string;
  label: string;
  status: ActivityTimelineStatus;
  actor?: string | null;
  occurredAt?: string | null;
  occurredAtLabel?: string | null;
  detail?: string | null;
}

export interface ActivityTimelineProps {
  items: ActivityTimelineItem[];
  locale?: "ko-KR" | "en-US";
  emptyLabel?: string;
}

const STATUS_LABELS: Record<ActivityTimelineStatus, { ko: string; en: string }> = {
  completed: { ko: "완료", en: "Completed" },
  current: { ko: "현재", en: "Current" },
  pending: { ko: "대기", en: "Pending" },
  blocked: { ko: "차단됨", en: "Blocked" },
  failed: { ko: "실패", en: "Failed" },
};

function statusLabel(status: ActivityTimelineStatus, locale: "ko-KR" | "en-US") {
  return locale === "ko-KR" ? STATUS_LABELS[status].ko : STATUS_LABELS[status].en;
}

function StatusIcon({ status }: { status: ActivityTimelineStatus }): ReactNode {
  if (status === "completed") return <CheckCircle2 aria-hidden="true" size={14} />;
  if (status === "current") return <CircleDot aria-hidden="true" size={14} />;
  if (status === "blocked") return <Ban aria-hidden="true" size={14} />;
  if (status === "failed") return <TriangleAlert aria-hidden="true" size={14} />;
  return <Circle aria-hidden="true" size={14} />;
}

export function ActivityTimeline({
  items,
  locale = "ko-KR",
  emptyLabel,
}: ActivityTimelineProps) {
  if (!items.length) {
    return (
      <div className="activity-timeline-empty" role="status">
        {emptyLabel ?? (locale === "ko-KR" ? "아직 기록된 활동이 없습니다." : "No activity has been recorded yet.")}
      </div>
    );
  }

  return (
    <ol className="activity-timeline" aria-label={locale === "ko-KR" ? "Lifecycle 활동 이력" : "Lifecycle activity history"}>
      {items.map((item) => {
        const label = statusLabel(item.status, locale);
        return (
          <li key={item.id} className={`activity-timeline-item is-${item.status}`} data-status={item.status}>
            <div className="activity-timeline-marker" aria-label={label}>
              <StatusIcon status={item.status} />
            </div>
            <div className="activity-timeline-content">
              <div className="activity-timeline-heading">
                <strong>{item.label}</strong>
                <span className="activity-timeline-status">{label}</span>
              </div>
              {item.detail ? <p>{item.detail}</p> : null}
              {item.actor || item.occurredAt ? (
                <div className="activity-timeline-meta">
                  {item.actor ? <span>{item.actor}</span> : null}
                  {item.occurredAt ? (
                    <time dateTime={item.occurredAt}>{item.occurredAtLabel ?? item.occurredAt}</time>
                  ) : null}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
