import { describe, expect, it } from "vitest";
import {
  buildInspectionCompletionPayload,
  buildOperationsManualRecommendationPayload,
  type InspectionCompletionFacts,
} from "../../../api";

function facts(overrides: Partial<InspectionCompletionFacts> = {}): InspectionCompletionFacts {
  return {
    outcome: "maintenance_recommended",
    toolWearStatus: "not_checked",
    toolWearMin: null,
    coolingPathStatus: "not_checked",
    coolantTemperatureC: null,
    inHouseStatus: "pass",
    sparePartAvailableStatus: "",
    vendorDispatchRequiredStatus: "fail",
    componentReplacementRequiredStatus: "",
    findings: "현장 점검 결과",
    note: "",
    ...overrides,
  };
}

describe("inspection completion payload", () => {
  it("serializes observed tool-wear facts without selecting an Action", () => {
    const payload = buildInspectionCompletionPayload(facts({
      toolWearStatus: "fail",
      toolWearMin: 220,
      sparePartAvailableStatus: "pass",
    }));

    expect(payload.checklist.map((item) => [item.item_id, item.status])).toEqual([
      ["tool-wear", "fail"],
      ["cooling-path", "not_checked"],
      ["cost-basis-in-house", "pass"],
      ["cost-basis-spare-part-available", "pass"],
      ["cost-basis-vendor-dispatch-required", "fail"],
    ]);
    expect(payload.measurements).toEqual([
      { name: "tool_wear_min", value: 220, unit: "min" },
    ]);
  });

  it("serializes observed cooling facts with the canonical identifiers", () => {
    const payload = buildInspectionCompletionPayload(facts({
      coolingPathStatus: "fail",
      coolantTemperatureC: 92,
      componentReplacementRequiredStatus: "fail",
      findings: "냉각 경로 막힘 확인",
    }));

    expect(payload.checklist.map((item) => [item.item_id, item.status])).toEqual([
      ["tool-wear", "not_checked"],
      ["cooling-path", "fail"],
      ["cost-basis-in-house", "pass"],
      ["cost-basis-vendor-dispatch-required", "fail"],
      ["cost-basis-component-replacement-required", "fail"],
    ]);
    expect(payload.measurements).toEqual([
      { name: "coolant_temperature_c", value: 92, unit: "C" },
    ]);
    expect(payload.findings).toEqual(["냉각 경로 막힘 확인"]);
  });

  it("never substitutes process temperature for a coolant inspection measurement", () => {
    const payload = buildInspectionCompletionPayload(facts({
      coolingPathStatus: "fail",
      coolantTemperatureC: 92,
    }));

    expect(payload.checklist.some((item) => item.item_id === "cooling-system-condition")).toBe(false);
    expect(payload.measurements.some((item) => item.name === "process_temperature_k")).toBe(false);
  });

  it("can preserve both failed checks so Backend derives both eligible candidates", () => {
    const payload = buildInspectionCompletionPayload(facts({
      toolWearStatus: "fail",
      toolWearMin: 220,
      coolingPathStatus: "fail",
      coolantTemperatureC: 92,
      sparePartAvailableStatus: "pass",
      componentReplacementRequiredStatus: "fail",
    }));

    expect(payload.checklist.filter((item) => item.status === "fail").map((item) => item.item_id)).toEqual([
      "tool-wear",
      "cooling-path",
      "cost-basis-vendor-dispatch-required",
      "cost-basis-component-replacement-required",
    ]);
    expect(payload).not.toHaveProperty("action_code");
  });
});

describe("operations manual recommendation payload", () => {
  it("preserves the consulted analysis and selected action without selecting a cost option", () => {
    const payload = buildOperationsManualRecommendationPayload(
      "inspection-result-001",
      "TOOL_REPLACEMENT",
      "cost-analysis-001",
      "action-candidate-001",
    );

    expect(payload).toEqual({
      action_code: "TOOL_REPLACEMENT",
      basis: ["inspection_result:inspection-result-001"],
      cost_analysis_id: "cost-analysis-001",
      action_candidate_id: "action-candidate-001",
    });
    expect(payload).not.toHaveProperty("cost_option_id");
  });
});
