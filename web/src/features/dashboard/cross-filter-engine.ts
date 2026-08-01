import type { EventSummary } from "../../types";
import type { DependencyEdge, SelectionFilter } from "./types";

export function downstreamBoardIds(
  graph: DependencyEdge[],
  sourceBoardId: string,
  parameterId?: string,
): string[] {
  if (sourceBoardId === "context-panel" || sourceBoardId === "analysis-path") {
    return Array.from(new Set(graph.map((edge) => edge.target_board_id)));
  }
  const visited = new Set<string>();
  const queue = [sourceBoardId];
  while (queue.length) {
    const source = queue.shift()!;
    for (const edge of graph) {
      if (edge.source_board_id !== source) continue;
      if (parameterId && source === sourceBoardId && !edge.parameter_ids.includes(parameterId)) continue;
      if (visited.has(edge.target_board_id)) continue;
      visited.add(edge.target_board_id);
      queue.push(edge.target_board_id);
    }
  }
  return Array.from(visited);
}

export function upsertSelectionFilter(filters: SelectionFilter[], next: SelectionFilter): SelectionFilter[] {
  return [
    ...filters.filter((filter) => !(filter.source_board_id === next.source_board_id && filter.field === next.field)),
    next,
  ];
}

export function clearSelectionFilters(filters: SelectionFilter[], sourceBoardId?: string): SelectionFilter[] {
  return sourceBoardId ? filters.filter((filter) => filter.source_board_id !== sourceBoardId) : [];
}

function eventField(event: EventSummary, field: string): string | number | boolean | null {
  if (field === "event_id") return event.event_id;
  if (field === "scenario_id") return event.scenario_id;
  if (field === "equipment" || field === "equipment_name") return event.equipment.display_name;
  if (field === "equipment_id") return event.equipment.equipment_id;
  if (field === "line") return event.equipment.line;
  if (field === "status") return event.status;
  if (field === "risk" || field === "failure_probability") return event.failure_probability ?? 0;
  if (field === "downtime") return event.equipment.estimated_downtime_minutes;
  if (field === "confidence") return event.confidence;
  if (field === "failure_type") return event.predicted_failure_type;
  return null;
}

function matches(event: EventSummary, filter: SelectionFilter): boolean {
  const value = eventField(event, filter.field);
  if (value === null) return true;
  const values = filter.values;
  if (filter.operator === "eq") return String(value) === String(values[0]);
  if (filter.operator === "in") return values.some((candidate) => String(candidate) === String(value));
  if (filter.operator === "gte") return Number(value) >= Number(values[0]);
  if (filter.operator === "lte") return Number(value) <= Number(values[0]);
  if (filter.operator === "between") return Number(value) >= Number(values[0]) && Number(value) <= Number(values[1]);
  return true;
}

export function filtersForBoard(
  filters: SelectionFilter[],
  targetBoardId: string,
  graph: DependencyEdge[],
): SelectionFilter[] {
  return filters.filter((filter) => {
    if (filter.source_board_id === "context-panel" || filter.source_board_id === "analysis-path") return true;
    return downstreamBoardIds(graph, filter.source_board_id).includes(targetBoardId);
  });
}

export function filterEventsForBoard(
  events: EventSummary[],
  filters: SelectionFilter[],
  targetBoardId: string,
  graph: DependencyEdge[],
): EventSummary[] {
  const applicable = filtersForBoard(filters, targetBoardId, graph);
  if (!applicable.length) return events;
  return events.filter((event) => applicable.every((filter) => matches(event, filter)));
}

export function selectionFilterFromEvent(sourceBoardId: string, event: EventSummary): SelectionFilter {
  return {
    id: crypto.randomUUID(),
    source_board_id: sourceBoardId,
    field: "event_id",
    operator: "eq",
    values: [event.event_id],
    object_type: "risk_event",
    created_at: new Date().toISOString(),
  };
}
