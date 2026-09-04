import {
  AreaChart,
  BarChart2,
  BarChart3,
  Grid3X3,
  Hash,
  Layers3,
  LineChart,
  PieChart,
  ScatterChart,
  Table2,
  type LucideIcon,
} from "lucide-react";
import type { VisualizationKind } from "../types";

const ICON_BY_KIND: Record<VisualizationKind, LucideIcon> = {
  metric: Hash,
  table: Table2,
  bar: BarChart3,
  stacked_bar: Layers3,
  line: LineChart,
  area: AreaChart,
  pie: PieChart,
  histogram: BarChart2,
  scatter: ScatterChart,
  heatmap: Grid3X3,
};

interface VisualizationKindMarkProps {
  kind: VisualizationKind;
  variant?: "icon" | "preview";
  className?: string;
}

export function VisualizationKindMark({ kind, variant = "preview", className = "" }: VisualizationKindMarkProps) {
  const Icon = ICON_BY_KIND[kind];
  return (
    <span
      className={`visualization-kind-mark is-${variant} ${className}`.trim()}
      data-kind={kind}
      aria-hidden="true"
    >
      <Icon size={variant === "icon" ? 12 : 11} strokeWidth={2} />
      {variant === "preview" ? <i /> : null}
    </span>
  );
}
