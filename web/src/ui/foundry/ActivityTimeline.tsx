import type { ReactNode } from "react";
import { StatusPill, type StatusPillIntent } from "./StatusPill";

export interface ActivityItem {
  id: string;
  title: string;
  detail?: ReactNode;
  meta?: ReactNode;
  status?: { label: string; intent?: StatusPillIntent };
  selected?: boolean;
  onSelect?: () => void;
  expandable?: ReactNode;
}

interface ActivityTimelineProps {
  items: ActivityItem[];
  emptyMessage?: string;
  className?: string;
}

export function ActivityTimeline({ items, emptyMessage = "No activity", className = "" }: ActivityTimelineProps) {
  return (
    <div className={`fd-activity-timeline ${className}`.trim()}>
      {items.length ? items.map((item, index) => {
        const Wrapper = item.onSelect ? "button" : "article";
        return (
          <Wrapper
            key={item.id}
            className={`fd-activity-item ${item.selected ? "selected" : ""}`.trim()}
            {...(item.onSelect ? { type: "button" as const, onClick: item.onSelect } : {})}
          >
            <span className="fd-activity-item__marker">{index + 1}</span>
            <div className="fd-activity-item__copy">
              <div className="fd-activity-item__title"><strong>{item.title}</strong>{item.status ? <StatusPill intent={item.status.intent}>{item.status.label}</StatusPill> : null}</div>
              {item.detail ? <div className="fd-activity-item__detail">{item.detail}</div> : null}
              {item.meta ? <small>{item.meta}</small> : null}
              {item.expandable}
            </div>
          </Wrapper>
        );
      }) : <div className="fd-activity-timeline__empty">{emptyMessage}</div>}
    </div>
  );
}
