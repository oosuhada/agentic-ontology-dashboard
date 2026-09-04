import { describe, expect, it } from "vitest";

import { profileRows } from "./visualizationProfile";

describe("profileRows", () => {
  it("serializes nested Result Artifact values into the scalar planner contract", () => {
    const profile = profileRows([
      {
        asset_id: "CMP-001",
        top_factors: [{ rank: 1, feature: "overstrain_load", contribution: 0.4 }],
      },
    ]);
    const factors = profile.find((field) => field.id === "top_factors");

    expect(factors?.physical_type).toBe("mixed");
    expect(factors?.sample_values).toHaveLength(1);
    expect(typeof factors?.sample_values[0]).toBe("string");
    expect(factors?.sample_values[0]).toContain("overstrain_load");
  });
});
