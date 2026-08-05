import { describe, expect, it } from "vitest";
import { optimizeDashboardLayout, type BoardContentMetric } from "./layoutOptimizer";
import type { DashboardBoard } from "./types";

function board(
  id: string,
  definitionId: string,
  layout: { x: number; y: number; w: number; h: number },
  settings: Record<string, unknown> = {},
): DashboardBoard {
  return {
    id,
    definition_id: definitionId,
    title: id,
    width: layout.w,
    order: 0,
    layout: { ...layout, min_w: 2, min_h: 1, max_w: 12, max_h: 12 },
    source: null,
    hidden: false,
    mandatory: false,
    custom: false,
    bindings: {},
    settings,
  };
}

function metric(boardId: string, contentHeight: number, viewportHeight: number): BoardContentMetric {
  return { boardId, contentHeight, viewportHeight, contentWidth: 600 };
}

function overlaps(left: DashboardBoard, right: DashboardBoard) {
  const a = left.layout!;
  const b = right.layout!;
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

describe("dashboard layout optimizer", () => {
  it("shrinks empty space to the semantic renderer height when content does not overflow", () => {
    const result = optimizeDashboardLayout(
      [board("kpi", "operations-kpi", { x: 0, y: 0, w: 12, h: 8 })],
      [metric("kpi", 300, 300)],
      "content-fit",
      1440,
      new Map([["operations-kpi", "OperationsKpi"]]),
    );

    expect(result[0].layout).toEqual(expect.objectContaining({ w: 12, h: 2 }));
    expect(result[0].settings.layout_mode).toBe("auto");
  });

  it("expands a board when measured content overflows its viewport", () => {
    const result = optimizeDashboardLayout(
      [board("table", "evidence-table", { x: 0, y: 0, w: 8, h: 3 })],
      [metric("table", 700, 250)],
      "content-fit",
      1440,
      new Map([["evidence-table", "EvidenceTable"]]),
    );

    expect(result[0].layout?.h).toBeGreaterThanOrEqual(9);
  });

  it("uses renderer semantics to recommend widths and packs boards without overlap", () => {
    const result = optimizeDashboardLayout(
      [
        board("trend", "risk-trend", { x: 0, y: 0, w: 4, h: 4 }),
        board("graph", "ontology", { x: 4, y: 0, w: 8, h: 4 }),
      ],
      [],
      "ai-recommendation",
      1440,
      new Map([
        ["risk-trend", "RiskTrendWorkbench"],
        ["ontology", "OntologyRelationship"],
      ]),
    );

    expect(result[0].layout?.w).toBe(8);
    expect(result[1].layout?.w).toBe(4);
    expect(overlaps(result[0], result[1])).toBe(false);
    expect(result.every((item) => item.settings.layout_mode === "ai")).toBe(true);
  });

  it("preserves a manually locked board while packing automatic boards around it", () => {
    const locked = board("locked", "ontology", { x: 8, y: 0, w: 4, h: 4 }, { layout_mode: "manual", layout_lock: true });
    const automatic = board("trend", "risk-trend", { x: 0, y: 0, w: 6, h: 4 });
    const result = optimizeDashboardLayout(
      [locked, automatic],
      [],
      "ai-recommendation",
      1440,
      new Map([
        ["ontology", "OntologyRelationship"],
        ["risk-trend", "RiskTrendWorkbench"],
      ]),
    );

    expect(result[0].layout).toEqual(expect.objectContaining({ x: 8, y: 0, w: 4, h: 4 }));
    expect(result[0].settings.layout_mode).toBe("manual");
    expect(overlaps(result[0], result[1])).toBe(false);
  });
});
