import { describe, expect, it } from "vitest";
import { safeArtifactUri } from "./DatasetDetailInspector";

describe("safeArtifactUri", () => {
  it("hides a local workstation file path", () => {
    const result = safeArtifactUri(
      "file:///Users/example/private/project/data/manufacturing-equipment.jsonl",
      "dsv-001",
    );
    expect(result).toBe("artifact://datasets/dsv-001/manufacturing-equipment.jsonl");
    expect(result).not.toContain("/Users/example");
  });

  it("preserves governed non-file artifact URIs", () => {
    expect(safeArtifactUri("s3://bucket/dataset.jsonl", "dsv-001")).toBe("s3://bucket/dataset.jsonl");
  });
});
