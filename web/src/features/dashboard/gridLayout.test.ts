import { describe, expect, it } from "vitest";
import { applyGridLayoutItem, backfillGridLayouts, legacyBoardToGridLayout } from "./gridLayout";
import type { DashboardBoard } from "./types";

function board(id: string, width: number, order: number): DashboardBoard {
  return {
    id,
    definition_id: "event-data-grid",
    title: id,
    width,
    order,
    layout: null,
    source: null,
    hidden: false,
    mandatory: false,
    custom: true,
    bindings: {},
    settings: {},
  };
}

describe("dashboard grid layout migration", () => {
  it("converts width/order boards into deterministic non-overlapping x/y/w/h layouts", () => {
    const migrated = backfillGridLayouts([
      board("a", 6, 0),
      board("b", 6, 1),
      board("c", 12, 2),
    ], new Map([["event-data-grid", "EventDataGrid"]]));

    expect(migrated.map((item) => item.layout)).toEqual([
      expect.objectContaining({ x: 0, y: 0, w: 6, h: 5 }),
      expect.objectContaining({ x: 6, y: 0, w: 6, h: 5 }),
      expect.objectContaining({ x: 0, y: 5, w: 12, h: 5 }),
    ]);
  });

  it("clamps persisted layout values and preserves resize changes", () => {
    const item = {
      ...board("a", 6, 0),
      layout: { x: 20, y: -2, w: 20, h: 0 },
    };
    expect(legacyBoardToGridLayout(item, 0)).toEqual(expect.objectContaining({ x: 11, y: 0, w: 12, h: 1 }));

    const resized = applyGridLayoutItem(item, { x: 2, y: 3, w: 8, h: 6 });
    expect(resized.layout).toEqual(expect.objectContaining({ x: 2, y: 3, w: 8, h: 6 }));
    expect(resized.width).toBe(8);
    expect(resized.settings.height_units).toBe("6");
  });
});
