import { describe, expect, it } from "vitest";
import { dashboardArrangeReducer, isArrangeInteractiveTarget } from "./dashboardArrange";

describe("Dashboard arrange state", () => {
  it("moves through long-press, drag, resize, save, and exit states", () => {
    expect(dashboardArrangeReducer("view", { type: "ARM" })).toBe("press-armed");
    expect(dashboardArrangeReducer("press-armed", { type: "ENTER" })).toBe("arranging");
    expect(dashboardArrangeReducer("arranging", { type: "DRAG_START" })).toBe("dragging");
    expect(dashboardArrangeReducer("dragging", { type: "DRAG_STOP" })).toBe("arranging");
    expect(dashboardArrangeReducer("arranging", { type: "RESIZE_START" })).toBe("resizing");
    expect(dashboardArrangeReducer("resizing", { type: "RESIZE_STOP" })).toBe("arranging");
    expect(dashboardArrangeReducer("arranging", { type: "SAVE_START" })).toBe("saving");
    expect(dashboardArrangeReducer("saving", { type: "SAVE_END" })).toBe("arranging");
    expect(dashboardArrangeReducer("arranging", { type: "EXIT" })).toBe("view");
  });

  it("cancels only an armed press", () => {
    expect(dashboardArrangeReducer("press-armed", { type: "CANCEL" })).toBe("view");
    expect(dashboardArrangeReducer("arranging", { type: "CANCEL" })).toBe("arranging");
  });

  it("does not arm from interactive descendants", () => {
    const article = document.createElement("article");
    const button = document.createElement("button");
    const chart = document.createElement("div");
    article.append(button, chart);
    expect(isArrangeInteractiveTarget(button)).toBe(true);
    expect(isArrangeInteractiveTarget(chart)).toBe(false);
    chart.setAttribute("role", "button");
    expect(isArrangeInteractiveTarget(chart)).toBe(true);
  });
});
