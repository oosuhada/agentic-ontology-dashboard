import { GitMerge } from "lucide-react";
import type { AnalysisBoardDefinition } from "../types";

export const JOIN_RELATIONSHIPS = [
  { id: "risk_event_equipment", label: "RiskEvent ↔ Equipment" },
  { id: "risk_event_evidence", label: "RiskEvent ↔ Evidence" },
  { id: "equipment_work_order", label: "Equipment ↔ WorkOrder" },
] as const;

export function JoinBoardIcon() {
  return <span className="analysis-catalog-icon"><GitMerge size={13} /></span>;
}

export const JOIN_BOARD: AnalysisBoardDefinition = {
  kind: "join",
  title: "Join allowed relation",
  description: "Ontology Registry에 등록된 세 관계만 선택해 Object Set을 결합합니다.",
  input: "rows",
  output: "rows",
};
