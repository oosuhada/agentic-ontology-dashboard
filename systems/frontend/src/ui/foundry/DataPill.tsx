import {
  Activity,
  BarChart3,
  Braces,
  CircleDot,
  Database,
  FileCheck2,
  GitBranch,
  Hash,
  Table2,
} from "lucide-react";
import type { AnalysisDataKind } from "../../features/analysis/types";

const LABELS: Record<AnalysisDataKind, string> = {
  "object-set": "Object set",
  rows: "Rows",
  "grouped-rows": "Grouped rows",
  "transform-table": "Transform table",
  scalar: "Number",
  chart: "Chart",
  table: "Table",
  "evidence-set": "Evidence set",
  "time-series": "Time series",
  materialization: "Materialization",
  none: "None",
};

const ICONS = {
  "object-set": Braces,
  rows: Database,
  "grouped-rows": GitBranch,
  "transform-table": Table2,
  scalar: Hash,
  chart: BarChart3,
  table: Table2,
  "evidence-set": FileCheck2,
  "time-series": Activity,
  materialization: Database,
  none: CircleDot,
} as const;

interface DataPillProps {
  kind: AnalysisDataKind;
  compact?: boolean;
  label?: string;
}

export function DataPill({ kind, compact = false, label }: DataPillProps) {
  const Icon = ICONS[kind];
  return <span className={`fd-data-pill kind-${kind} ${compact ? "is-compact" : ""}`}><Icon size={10} />{compact ? null : label ?? LABELS[kind]}</span>;
}
