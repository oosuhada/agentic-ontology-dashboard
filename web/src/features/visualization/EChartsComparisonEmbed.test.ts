import { describe, expect, it } from "vitest";
import { buildComparisonChartOption, parseComparisonPayload } from "./EChartsComparisonEmbed";

describe("parseComparisonPayload", () => {
  it("accepts the shared comparison payload", () => {
    const payload = encodeURIComponent(JSON.stringify({
      kind: "line",
      title: "Latency",
      unit: "ms",
      rows: [{ category: "1", value: 125 }, { category: "2", value: 98 }],
    }));
    expect(parseComparisonPayload(`?payload=${payload}`)).toMatchObject({
      kind: "line",
      title: "Latency",
      rows: [{ category: "1", value: 125 }, { category: "2", value: 98 }],
    });
  });

  it("falls back when the payload is invalid", () => {
    expect(parseComparisonPayload("?payload=not-json").rows.length).toBeGreaterThan(0);
  });

  it("removes redundant numeric ticks from compact horizontal bars", () => {
    const option = buildComparisonChartOption({
      kind: "bar",
      title: "Node count",
      rows: [{ category: "QualityMeasurement", value: 7570 }],
    }, true);

    expect((option.xAxis as { axisLabel?: { show?: boolean } }).axisLabel?.show).toBe(false);
    expect((option.yAxis as { axisLabel?: { width?: number } }).axisLabel?.width).toBe(112);
  });
});
