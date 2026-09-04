import { Sigma } from "lucide-react";
import type { AnalysisBoardDefinition } from "../types";

export function AggregateBoard() {
  return <span className="analysis-catalog-icon"><Sigma size={13} /></span>;
}

export const AGGREGATE_BOARD: AnalysisBoardDefinition = {
  kind: "aggregate",
  title: "Aggregate metrics",
  description: "count, average risk, downtime 합계를 계산합니다.",
  input: "rows/groups",
  output: "aggregate",
};
