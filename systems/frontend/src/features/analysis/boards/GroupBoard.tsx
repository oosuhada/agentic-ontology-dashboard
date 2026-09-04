import { GitMerge } from "lucide-react";
import type { AnalysisBoardDefinition } from "../types";

export function GroupBoard() {
  return <span className="analysis-catalog-icon"><GitMerge size={13} /></span>;
}

export const GROUP_BOARD: AnalysisBoardDefinition = {
  kind: "group",
  title: "Group objects",
  description: "equipment, line, status 기준으로 Object set을 묶습니다.",
  input: "rows",
  output: "groups",
};
