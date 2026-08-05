import { describe, expect, it } from "vitest";
import { parseComparisonPayload } from "./EChartsComparisonEmbed";

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
});
