import { Braces, Calculator, Database } from "lucide-react";
import { AGGREGATE_BOARD } from "./boards/AggregateBoard";
import { CHART_BOARD } from "./boards/ChartBoard";
import { FILTER_BOARD } from "./boards/FilterBoard";
import { GROUP_BOARD } from "./boards/GroupBoard";
import { JOIN_BOARD } from "./boards/JoinBoard";
import { VERIFY_TABLE_BOARD } from "./boards/VerifyTableBoard";
import type { AnalysisBoardDefinition, AnalysisStepKind } from "./types";

export const ANALYSIS_BOARD_LIBRARY: AnalysisBoardDefinition[] = [
  FILTER_BOARD,
  GROUP_BOARD,
  AGGREGATE_BOARD,
  JOIN_BOARD,
  {
    kind: "formula",
    title: "Derived expression",
    description: "허용된 field와 연산자를 선택해 운영 점수를 계산합니다.",
    input: "rows",
    output: "rows",
  },
  CHART_BOARD,
  VERIFY_TABLE_BOARD,
  {
    kind: "evidence",
    title: "Join evidence",
    description: "event_id, equipment_id, model_version 중 허용 관계로 Evidence를 결합합니다.",
    input: "rows",
    output: "rows",
  },
];

export function defaultAnalysisConfig(kind: AnalysisStepKind): Record<string, string> {
  if (kind === "input") return { source: "risk_event", version: "latest_published" };
  if (kind === "filter") return { field: "status", operator: "equals", value: "critical" };
  if (kind === "group") return { field: "line" };
  if (kind === "aggregate") return { metric: "average_risk" };
  if (kind === "formula") return { left: "risk", operator: "multiply", right: "downtime", output: "priority_score" };
  if (kind === "join") return { relationship: "risk_event_equipment" };
  if (kind === "chart") return { chart: "bar", x: "line", y: "average_risk" };
  if (kind === "table") return { limit: "50" };
  return { relationship: "event_id", fields: "model,policy,evidence" };
}

export function outputKind(kind: AnalysisStepKind) {
  if (kind === "group") return "groups";
  if (kind === "aggregate") return "aggregate";
  if (kind === "join") return "rows";
  if (kind === "chart") return "chart";
  if (kind === "table") return "table";
  return "rows";
}

export function analysisNodeIcon(kind: AnalysisStepKind) {
  if (kind === "input" || kind === "evidence") return Database;
  if (kind === "formula") return Calculator;
  return Braces;
}
