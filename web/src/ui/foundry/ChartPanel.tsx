import type { ReactNode } from "react";
import { EmptyState } from "./WorkbenchState";

interface ChartPanelProps {
  children: ReactNode;
  empty?: boolean;
  emptyTitle?: string;
  emptyDetail?: string;
  className?: string;
  toolbar?: ReactNode;
}

export function ChartPanel({
  children,
  empty = false,
  emptyTitle = "No chart data",
  emptyDetail = "현재 filter scope에 표시할 값이 없습니다.",
  className = "",
  toolbar,
}: ChartPanelProps) {
  return (
    <section className={`fd-chart-panel ${className}`.trim()}>
      {toolbar ? <header className="fd-chart-panel__toolbar">{toolbar}</header> : null}
      <div className="fd-chart-panel__canvas">
        {empty ? <EmptyState title={emptyTitle} detail={emptyDetail} /> : children}
      </div>
    </section>
  );
}
