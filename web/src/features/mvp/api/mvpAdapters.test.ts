import { describe, expect, it } from "vitest";
import type { EventSummary } from "../../../types";
import {
  adaptEvent,
  buildTemplateReport,
  computeLineRisk,
  computeMetrics,
  mergeAssets,
  normalizeActivity,
  normalizeDecision,
  normalizeRiskStatus,
} from "./mvpAdapters";

const event: EventSummary = {
  event_id: "EVENT-001",
  scenario_id: "scenario-1",
  equipment: {
    equipment_id: "CNC-001",
    display_name: "CNC 001",
    line: "Line A",
    criticality: "high",
    assigned_engineer: "Engineer A",
    last_maintenance_date: "2026-08-01",
    estimated_downtime_minutes: 120,
    spare_part_available: false,
  },
  status: "critical",
  failure_probability: 0.92,
  confidence: "high",
  predicted_failure_type: "tool_wear",
  recommended_decision: "review_shutdown",
  observed_at: "2026-08-06T03:00:00Z",
  dataset_version_id: "dsv-canonical-v3-1",
};

describe("MVP adapter contract", () => {
  it("normalizes statuses and only uses the approved decision enum", () => {
    expect(normalizeRiskStatus("danger", 0.2)).toBe("critical");
    expect(normalizeRiskStatus("unknown", null)).toBe("data_quality_hold");
    expect(normalizeDecision("automatic shutdown")).toBe("review_shutdown");
    expect(normalizeDecision("inspect bearings")).toBe("request_inspection");
  });

  it("keeps data-quality hold out of failure probability presentation", () => {
    const adapted = adaptEvent({ ...event, status: "data_quality_hold", failure_probability: 0.98 });
    expect(adapted.status).toBe("data_quality_hold");
    expect(adapted.failureProbability).toBeNull();
    expect(adapted.recommendedDecision).toBe("hold_for_data_check");
  });

  it("merges Result Artifact fields with operational Event context", () => {
    const operational = adaptEvent(event);
    const assets = mergeAssets([{
      artifact_id: "RESULT#CNC-001",
      asset_id: "CNC-001",
      asset_type: "cnc",
      site_id: "SITE-1",
      cell_id: "CELL-1",
      observed_at: "2026-08-06T03:00:00Z",
      prediction_task: "binary_failure_within_horizon",
      failure_probability: 0.92,
      predicted_failure_type: "failure_risk",
      status_grade: "critical",
      confidence: 0.88,
      top_factors: [{ rank: 1, feature: "tool_wear_min", feature_value: 210, signed_contribution: 0.42, direction: "risk_up", explanation_method: "shap" }],
      recommended_action: { action: "review_shutdown", priority: "critical", semantic_type: "policy_recommendation", approval_state: "not_requested", execution_state: "not_executed", creates_work_order_automatically: false },
      provenance: { dataset_id: "dataset-1", dataset_version_id: "dsv-canonical-v3-1", source_version: "Canonical V3.1", bundle_checksum_sha256: "a".repeat(64), model_version: "model-1", schema_version: "result-artifact-v1.0", prediction_task: "binary_failure_within_horizon" },
    }], [operational]);

    expect(assets).toHaveLength(1);
    expect(assets[0]).toEqual(expect.objectContaining({
      displayName: "CNC 001",
      line: "Line A",
      eventId: "EVENT-001",
      confidence: "high",
    }));
    expect(assets[0].topFactors[0].feature).toBe("tool_wear_min");
    expect(assets[0].provenance.modelVersion).toBe("model-1");
  });

  it("derives the same metrics and line summary used by all four screens", () => {
    const events = [adaptEvent(event), adaptEvent({ ...event, event_id: "EVENT-002", equipment: { ...event.equipment, equipment_id: "CNC-002" }, status: "warning", failure_probability: 0.65 })];
    const assets = mergeAssets([], events);
    expect(computeMetrics(assets, events)).toEqual(expect.objectContaining({ critical: 1, warning: 1, estimatedDowntimeMinutes: 240 }));
    expect(computeLineRisk(assets)[0]).toEqual(expect.objectContaining({ line: "Line A", critical: 1, warning: 1 }));
  });

  it("keeps one asset row when multiple events reference the same equipment", () => {
    const events = [
      adaptEvent(event),
      adaptEvent({ ...event, event_id: "EVENT-002", observed_at: "2026-08-06T04:00:00Z" }),
    ];
    const assets = mergeAssets([], events);
    expect(assets).toHaveLength(1);
    expect(assets[0].assetId).toBe("CNC-001");
  });

  it("uses a verified template when report generation is unavailable", () => {
    const adapted = adaptEvent(event);
    const report = buildTemplateReport(adapted, computeMetrics(mergeAssets([], [adapted]), [adapted]));
    expect(report.mode).toBe("template-fallback");
    expect(report.sections.map((section) => section.id)).toContain("executive-summary");
    expect(report.limitations.join(" ")).toContain("고장");
  });

  it("normalizes decisions, notes, and conversations into one audit timeline", () => {
    const activity = normalizeActivity({
      decisions: [{ id: "d1", decision: "request_inspection", actor: "Manager", note: "Check tool", created_at: "2026-08-06T04:00:00Z" }],
      notes: [{ id: "n1", actor: "Engineer", body: "Tool checked", created_at: "2026-08-06T05:00:00Z" }],
      conversations: [],
    });
    expect(activity.map((item) => item.kind)).toEqual(["note", "decision"]);
    expect(activity[1].decision).toBe("request_inspection");
  });
});
