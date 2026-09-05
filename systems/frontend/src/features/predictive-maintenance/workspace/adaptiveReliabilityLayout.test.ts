import { describe, expect, it } from "vitest";
import {
  applyReliabilityPlannerOrder,
  adaptiveReliabilityRowSpan,
  preferredAdaptiveReliabilitySpan,
  reliabilityLayoutIntent,
} from "./adaptiveReliabilityLayout";

describe("adaptive reliability layout", () => {
  it("keeps action heroes and semantic full-width blocks stable", () => {
    expect(preferredAdaptiveReliabilitySpan({
      declaredSpan: 6,
      empty: false,
      actionHero: true,
      textLength: 240,
      controlCount: 1,
      hasWideVisualization: false,
    })).toBe(12);
    expect(preferredAdaptiveReliabilitySpan({
      declaredSpan: 12,
      empty: false,
      actionHero: false,
      textLength: 240,
      controlCount: 1,
      hasWideVisualization: false,
    })).toBe(12);
  });

  it("lets compact and empty blocks participate in dense packing", () => {
    expect(preferredAdaptiveReliabilitySpan({
      declaredSpan: 12,
      empty: true,
      actionHero: false,
      textLength: 80,
      controlCount: 0,
      hasWideVisualization: false,
    })).toBe(6);
    expect(preferredAdaptiveReliabilitySpan({
      declaredSpan: 6,
      empty: false,
      actionHero: false,
      textLength: 180,
      controlCount: 1,
      hasWideVisualization: false,
    })).toBe(4);
  });

  it("widens dense interaction blocks without widening charts arbitrarily", () => {
    expect(preferredAdaptiveReliabilitySpan({
      declaredSpan: 6,
      empty: false,
      actionHero: false,
      textLength: 1900,
      controlCount: 7,
      hasWideVisualization: false,
    })).toBe(8);
    expect(preferredAdaptiveReliabilitySpan({
      declaredSpan: 6,
      empty: false,
      actionHero: false,
      textLength: 1900,
      controlCount: 0,
      hasWideVisualization: true,
    })).toBe(6);
  });

  it("converts measured content height into stable masonry row spans", () => {
    expect(adaptiveReliabilityRowSpan(180, 10)).toBe(11);
    expect(adaptiveReliabilityRowSpan(0, 10)).toBe(1);
  });

  it("uses LLM layout types to reprioritize evidence without moving governed actions", () => {
    expect(applyReliabilityPlannerOrder(
      ["workflow-actions", "inspection-targets", "feature-trend", "evidence-factors"],
      ["FactorContribution", "EngineerChecklist"],
    )).toEqual(["workflow-actions", "evidence-factors", "inspection-targets", "feature-trend"]);
    expect(applyReliabilityPlannerOrder(
      ["evidence-factors", "inspection-targets", "sensor-signals", "feature-trend"],
      ["SensorLineChart", "EngineerChecklist", "FactorContribution"],
    )).toEqual(["feature-trend", "sensor-signals", "inspection-targets", "evidence-factors"]);
  });

  it("maps reliability surfaces to bounded legacy layout intents", () => {
    expect(reliabilityLayoutIntent("assets")).toBe("explain-risk");
    expect(reliabilityLayoutIntent("inspection")).toBe("recommend-check");
    expect(reliabilityLayoutIntent("executive-brief")).toBe("summarize-manager");
  });
});
