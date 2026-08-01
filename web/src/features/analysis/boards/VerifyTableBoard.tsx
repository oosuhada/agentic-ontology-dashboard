import { Table2 } from "lucide-react";
import type { AnalysisBoardDefinition } from "../types";

export function VerifyTableBoard() {
  return <span className="analysis-catalog-icon"><Table2 size={13} /></span>;
}

export const VERIFY_TABLE_BOARD: AnalysisBoardDefinition = {
  kind: "table",
  title: "Verify table",
  description: "샘플 row와 schema를 고밀도 표로 검증합니다.",
  input: "rows",
  output: "table",
};
