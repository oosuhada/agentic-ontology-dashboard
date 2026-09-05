import { describe, expect, it } from "vitest";
import { baseReliabilityComposition, resolveReliabilityComposition } from "./roleComposition";

describe("role composed reliability workspace", () => {
  it("uses materially different first-screen blocks by role", () => {
    expect(baseReliabilityComposition("executive", "reports")).toEqual([
      "risk-metrics", "operational-kpis", "report-summary", "production-exposure", "decision-queue", "case-lineage", "business-kpis", "risk-portfolio", "context-evidence",
    ]);
    expect(baseReliabilityComposition("operations", "operations").slice(0, 4)).toEqual([
      "risk-metrics", "operational-kpis", "decision-queue", "production-exposure",
    ]);
    expect(baseReliabilityComposition("engineering", "overview").slice(0, 4)).toEqual([
      "risk-metrics", "factory-map", "risk-queue", "feature-trend",
    ]);
    expect(baseReliabilityComposition("maintenance", "operations").slice(0, 3)).toEqual([
      "risk-metrics", "case-lineage", "workflow-lifecycle",
    ]);
  });

  it("keeps the surface task invariant ahead of runtime promotion", () => {
    const result = resolveReliabilityComposition("executive", "reports", {
      hasCriticalRisk: true,
      hasDataQualityHold: true,
      hasOpenWorkflow: false,
      hasMaterialConstraint: true,
      hasDecisionBacklog: false,
      hasHighProductionExposure: true,
      hasMaintenanceOutcome: false,
    }, "executive-brief");
    expect(result.slice(0, 3)).toEqual(["risk-metrics", "production-exposure", "decision-bottleneck"]);
    expect(result.indexOf("data-quality")).toBeGreaterThanOrEqual(3);
    expect(result).toContain("material-context");
    expect(new Set(result).size).toBe(result.length);
  });

  it("keeps the governed action first and inspection context ahead of charts", () => {
    const result = resolveReliabilityComposition("engineering", "objects", {
      hasCriticalRisk: true,
      hasDataQualityHold: true,
      hasOpenWorkflow: true,
      hasMaterialConstraint: false,
      hasDecisionBacklog: false,
      hasHighProductionExposure: false,
      hasMaintenanceOutcome: false,
    }, "inspection");
    expect(result.slice(0, 3)).toEqual(["workflow-actions", "inspection-targets", "workflow-lifecycle"]);
    expect(result.indexOf("feature-trend")).toBeGreaterThanOrEqual(3);
  });

  it("keeps the bottleneck table first on the executive bottleneck surface", () => {
    const result = resolveReliabilityComposition("executive", "reports", {
      hasCriticalRisk: true,
      hasDataQualityHold: false,
      hasOpenWorkflow: true,
      hasMaterialConstraint: true,
      hasDecisionBacklog: true,
      hasHighProductionExposure: true,
      hasMaintenanceOutcome: false,
    }, "decision-bottleneck");
    expect(result[0]).toBe("decision-bottleneck");
  });

  it("promotes role-specific runtime signals without allowing arbitrary UI mutation", () => {
    const engineering = resolveReliabilityComposition("engineering", "overview", {
      hasCriticalRisk: true,
      hasDataQualityHold: false,
      hasOpenWorkflow: false,
      hasMaterialConstraint: false,
      hasDecisionBacklog: false,
      hasHighProductionExposure: false,
      hasMaintenanceOutcome: false,
    });
    expect(engineering.slice(0, 2)).toEqual(["feature-trend", "evidence-factors"]);

    const operations = resolveReliabilityComposition("operations", "operations", {
      hasCriticalRisk: false,
      hasDataQualityHold: false,
      hasOpenWorkflow: false,
      hasMaterialConstraint: false,
      hasDecisionBacklog: true,
      hasHighProductionExposure: false,
      hasMaintenanceOutcome: false,
    });
    expect(operations[0]).toBe("decision-queue");
  });

  it("keeps engineering maintenance effect focused on technical before-after evidence", () => {
    const engineering = resolveReliabilityComposition("engineering", "objects", {
      hasCriticalRisk: false,
      hasDataQualityHold: false,
      hasOpenWorkflow: false,
      hasMaterialConstraint: false,
      hasDecisionBacklog: false,
      hasHighProductionExposure: false,
      hasMaintenanceOutcome: false,
    }, "maintenance-effect");
    expect(engineering.slice(0, 4)).toEqual([
      "maintenance-effect", "feature-trend", "sensor-signals", "maintenance-history",
    ]);
    expect(engineering).not.toContain("business-kpis");
  });
});
