import type { ReactNode } from "react";
import { EmptyState, LoadingState } from "./WorkbenchState";

export type ChartPanelState = "ready" | "loading" | "empty" | "incompatible";

interface ChartPanelProps {
  children: ReactNode;
  empty?: boolean;
  emptyTitle?: string;
  emptyDetail?: string;
  state?: ChartPanelState;
  stateTitle?: string;
  stateDetail?: string;
  className?: string;
  toolbar?: ReactNode;
}

export function ChartPanel({
  children,
  empty = false,
  emptyTitle = "No chart data",
  emptyDetail = "현재 filter scope에 표시할 값이 없습니다.",
  state,
  stateTitle,
  stateDetail,
  className = "",
  toolbar,
}: ChartPanelProps) {
  const resolvedState = state ?? (empty ? "empty" : "ready");
  const fallback = resolvedState === "loading"
    ? <LoadingState title={stateTitle ?? "Chart data loading"} detail={stateDetail ?? "Query 결과와 field profile을 준비하고 있습니다."} />
    : resolvedState === "incompatible"
      ? <EmptyState className="is-incompatible" title={stateTitle ?? "Chart mapping unavailable"} detail={stateDetail ?? "현재 field mapping으로 이 chart를 표시할 수 없습니다."} />
      : resolvedState === "empty"
        ? <EmptyState title={stateTitle ?? emptyTitle} detail={stateDetail ?? emptyDetail} />
        : null;
  return (
    <section className={`fd-chart-panel ${className}`.trim()}>
      {toolbar ? <header className="fd-chart-panel__toolbar">{toolbar}</header> : null}
      <div className="fd-chart-panel__canvas">
        {fallback ?? children}
      </div>
    </section>
  );
}
