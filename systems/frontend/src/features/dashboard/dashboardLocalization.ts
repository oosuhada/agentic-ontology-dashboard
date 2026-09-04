import type { MessageKey } from "../../ui/i18n/messages";
import type { DashboardBoard } from "./types";

type Translate = (key: MessageKey, values?: Record<string, string | number>) => string;

const BOARD_TITLE_KEYS: Record<string, MessageKey> = {
  "operations-kpi": "board.operations-kpi",
  "risk-trend-workbench": "board.risk-trend-workbench",
  "event-data-grid": "board.event-data-grid",
  "ontology-relationship": "board.ontology-relationship",
  "activity-stream": "board.activity-stream",
  "status-summary": "board.status-summary",
  "risk-kpi": "board.risk-kpi",
  "priority-list": "board.priority-list",
  "impact-summary": "board.impact-summary",
  "manager-decision": "board.manager-decision",
  "sensor-line-chart": "board.sensor-line-chart",
  "anomaly-timeline": "board.anomaly-timeline",
  "factor-contribution": "board.factor-contribution",
  "evidence-table": "board.evidence-table",
  "recommended-actions": "board.recommended-actions",
  "engineer-checklist": "board.engineer-checklist",
  "data-quality-warning": "board.data-quality-warning",
  "model-details": "board.model-details",
  "conversation-thread": "board.conversation-thread",
  "planner-assistant": "board.planner-assistant",
  "analysis-reference": "board.analysis-reference",
  "object-context": "board.object-context",
  "parameter-summary": "board.parameter-summary",
  "audit-trace": "board.audit-trace",
  "integration-health": "board.integration-health",
  "model-health": "board.model-health",
  "text-board": "board.text-board",
};

export function localizedBoardTitle(board: DashboardBoard, t: Translate): string {
  if (board.custom) return board.title;
  const key = BOARD_TITLE_KEYS[board.definition_id];
  return key ? t(key) : board.title;
}
