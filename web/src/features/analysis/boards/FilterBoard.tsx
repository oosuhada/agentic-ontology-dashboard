import { Filter } from "lucide-react";
import type { AnalysisBoardDefinition } from "../types";

export function FilterBoard() {
  return <span className="analysis-catalog-icon"><Filter size={13} /></span>;
}

export const FILTER_BOARD: AnalysisBoardDefinition = {
  kind: "filter",
  title: "Filter rows",
  description: "상태, line, threshold 조건으로 Object row를 줄입니다.",
  input: "rows",
  output: "rows",
};
