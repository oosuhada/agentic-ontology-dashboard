import { describe, expect, it } from "vitest";
import { executiveBriefIsStale } from "./OperationsExecutiveReportPage";

const base = {
  snapshotEventId: "RESULT#A#1",
  snapshotAssetId: "CNC-A",
  snapshotContextObservedAt: "2026-09-02T08:00:00Z",
  selectedEventId: "RESULT#A#1",
  selectedAssetId: "CNC-A",
  currentContextObservedAt: "2026-09-02T08:00:00Z",
};

describe("Executive Brief snapshot freshness", () => {
  it("keeps a report current while Monitoring stays on the same snapshot", () => {
    expect(executiveBriefIsStale(base)).toBe(false);
  });

  it("marks the report stale when a new Product Result arrives for the same asset", () => {
    expect(executiveBriefIsStale({ ...base, selectedEventId: "RESULT#A#2" })).toBe(true);
  });

  it("marks the report stale when Monitoring has a newer observation", () => {
    expect(executiveBriefIsStale({ ...base, currentContextObservedAt: "2026-09-02T08:10:00Z" })).toBe(true);
  });

  it("does not mark the report stale merely because another asset is selected", () => {
    expect(executiveBriefIsStale({
      ...base,
      selectedEventId: "RESULT#B#1",
      selectedAssetId: "CNC-B",
    })).toBe(false);
  });
});
