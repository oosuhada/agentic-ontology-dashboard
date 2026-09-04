import { describe, expect, it } from "vitest";
import {
  filtersForBoard,
  parameterIdForSelectionFilter,
} from "./cross-filter-engine";
import type { DependencyEdge, SelectionFilter } from "./types";

function selection(field: string, sourceBoardId = "source"): SelectionFilter {
  return {
    id: `${sourceBoardId}:${field}`,
    source_board_id: sourceBoardId,
    field,
    operator: "eq",
    values: [field === "event_id" ? "EVT-1" : "warning"],
    created_at: "2026-08-02T00:00:00Z",
  };
}

describe("cross-filter dependency scoping", () => {
  it("uses the explicit dependency graph when a downstream path exists", () => {
    const graph: DependencyEdge[] = [
      { source_board_id: "source", target_board_id: "middle", parameter_ids: ["selected_event_id"] },
      { source_board_id: "middle", target_board_id: "target", parameter_ids: ["selected_event_id"] },
    ];

    expect(filtersForBoard([selection("event_id")], "target", graph, [])).toHaveLength(1);
    expect(filtersForBoard([selection("event_id")], "other", graph, ["selected_event_id"])).toHaveLength(0);
  });

  it("falls back to accepted parameter bindings when the source has no graph edges", () => {
    const filter = selection("event_id", "unwired-grid");

    expect(filtersForBoard([filter], "decision", [], ["selected_event_id"])).toEqual([filter]);
    expect(filtersForBoard([filter], "status-only", [], ["status_filter"])).toEqual([]);
  });

  it("maps event, equipment, and status selections to canonical dashboard parameters", () => {
    expect(parameterIdForSelectionFilter(selection("event_id"))).toBe("selected_event_id");
    expect(parameterIdForSelectionFilter(selection("equipment_id"))).toBe("selected_equipment_id");
    expect(parameterIdForSelectionFilter(selection("status"))).toBe("status_filter");
    expect(parameterIdForSelectionFilter(selection("risk"))).toBeNull();
  });
});
