import { Database } from "lucide-react";

export function InputObjectSetBoard() {
  return <span className="analysis-catalog-icon"><Database size={13} /></span>;
}

export const INPUT_OBJECT_SET_CONFIG = { source: "risk_event", version: "latest_published" };
