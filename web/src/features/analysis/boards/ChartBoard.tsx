import { BarChart3 } from "lucide-react";
import type { AnalysisBoardDefinition } from "../types";

export function ChartBoard() {
  return <span className="analysis-catalog-icon"><BarChart3 size={13} /></span>;
}

export const CHART_BOARD: AnalysisBoardDefinition = {
  kind: "chart",
  title: "Visualize",
  description: "현재 결과를 bar 또는 line chart로 검토합니다.",
  input: "rows/aggregate",
  output: "chart",
};
