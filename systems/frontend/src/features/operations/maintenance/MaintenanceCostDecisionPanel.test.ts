import { describe, expect, it } from "vitest";
import type {
  MaintenanceCostAnalysisReadModel,
  MaintenanceEventLineageReadModel,
  MaintenanceInspectionResultReadModel,
} from "../../../api";
import type { OperationsInspectionGuidance } from "../api/operationsContracts";
import {
  buildCostRequest,
  costOptionsForDisplay,
  isCostAnalysisStageOpen,
  latestCostAnalysisForInspection,
  latestEligibleInspection,
} from "./MaintenanceCostDecisionPanel";

const guidance: OperationsInspectionGuidance = {
  sourceType: "demo_sop_fixture",
  sopId: "SOP-CNC-TOOL-001",
  title: "CNC 공구 점검",
  version: "v1",
  referenceLocationLabel: "공구대",
  suggestedCheckMethod: "마모량 확인",
  checklistDraft: ["마모량 확인"],
  maintenanceReviewPrerequisites: {
    label: "정비 검토",
    reviewConditions: ["마모 확인"],
    requiredMeasurements: ["tool_wear_min"],
    humanReviewQuestions: ["교체가 필요한가?"],
    decisionBoundary: "사람이 판단하고 승인한다.",
  },
  safetyLevel: "caution",
  requiresHumanApproval: true,
  sourceRef: "fixture://sop-cnc-tool-001",
  disclaimer: "참고 절차이며 정비 승인이 아닙니다.",
};

function lineage(): MaintenanceEventLineageReadModel {
  return {
    event_id: "EVT-1",
    work_orders: [
      { work_order_id: "WO-DONE", work_type: "inspection", status: "completed" },
      { work_order_id: "WO-OPEN", work_type: "inspection", status: "in_progress" },
    ],
    inspection_results: [
      {
        inspection_result_id: "RESULT-DONE",
        work_order_id: "WO-DONE",
        event_id: "EVT-1",
        asset_id: "CNC-1",
        equipment_id: "CNC-1",
        outcome: "maintenance_recommended",
        recorded_at: "2026-08-31T01:00:00Z",
      },
      {
        inspection_result_id: "RESULT-OPEN",
        work_order_id: "WO-OPEN",
        event_id: "EVT-1",
        asset_id: "CNC-1",
        equipment_id: "CNC-1",
        outcome: "maintenance_recommended",
        recorded_at: "2026-08-31T02:00:00Z",
      },
    ],
    cost_analyses: [],
    recommendations: [],
  };
}

function inspection(
  inspectionResultId: string,
  workOrderId: string,
  recordedAt: string,
): MaintenanceInspectionResultReadModel {
  return {
    inspection_result_id: inspectionResultId,
    work_order_id: workOrderId,
    event_id: "EVT-1",
    asset_id: "CNC-1",
    equipment_id: "CNC-1",
    outcome: "maintenance_recommended",
    recorded_at: recordedAt,
  };
}

function costAnalysis(
  analysisId: string,
  inspectionResultId: string,
  workOrderId: string,
  calculatedAt: string,
): MaintenanceCostAnalysisReadModel {
  return {
    schema_version: "maintenance-cost-scenario-v1.0",
    analysis_id: analysisId,
    organization_id: "ORG-1",
    project_id: "PROJECT-1",
    workspace_id: "WORKSPACE-1",
    asset_id: "CNC-1",
    equipment_id: "CNC-1",
    calculated_at: calculatedAt,
    based_on: {
      product_result_id: "PRODUCT-RESULT-1",
      evidence_id: "EVIDENCE-1",
      inspection_work_order_id: workOrderId,
      inspection_result_id: inspectionResultId,
      sop_id: "SOP-CNC-TOOL-001",
      sop_version: "v1",
    },
    currency: "KRW",
    currency_minor_unit: 0,
    options: [],
    lowest_calculated_cost_option_id: null,
    assumptions: [],
    missing_inputs: [],
    price_version: "price-v1",
    calculation_policy_version: "maintenance-cost-policy-v1",
    limitations: [],
  };
}

describe("MaintenanceCostDecisionPanel helpers", () => {
  it("does not reuse an older completed inspection while the latest inspection is open", () => {
    expect(latestEligibleInspection(lineage())).toBeNull();
  });

  it("opens cost analysis only after the latest inspection is completed", () => {
    const completed = lineage();
    completed.work_orders[1].status = "completed";

    expect(latestEligibleInspection(completed)?.inspection_result_id).toBe("RESULT-OPEN");
    expect(
      isCostAnalysisStageOpen(completed, latestEligibleInspection(completed)),
    ).toBe(true);
  });

  it("closes the current cost-analysis stage after an operations recommendation exists", () => {
    const completed = lineage();
    completed.work_orders[1].status = "completed";
    completed.recommendations = [{
      recommendation_id: "REC-1",
      status: "proposed",
      source_inspection_work_order_id: "WO-OPEN",
      source_inspection_reference: "RESULT-OPEN",
    }];
    const latestInspection = latestEligibleInspection(completed);

    expect(latestInspection?.inspection_result_id).toBe("RESULT-OPEN");
    expect(isCostAnalysisStageOpen(completed, latestInspection)).toBe(false);
  });

  it("does not expose an older inspection's cost analysis for the latest inspection", () => {
    const olderInspection = inspection(
      "RESULT-A",
      "WO-A",
      "2026-08-31T01:00:00Z",
    );
    const latestInspection = inspection(
      "RESULT-B",
      "WO-B",
      "2026-08-31T02:00:00Z",
    );
    const analysisA = costAnalysis(
      "ANALYSIS-A",
      olderInspection.inspection_result_id,
      olderInspection.work_order_id,
      "2026-08-31T01:30:00Z",
    );

    expect(latestCostAnalysisForInspection([analysisA], latestInspection)).toBeNull();

    const analysisB = costAnalysis(
      "ANALYSIS-B",
      latestInspection.inspection_result_id,
      latestInspection.work_order_id,
      "2026-08-31T02:30:00Z",
    );
    expect(
      latestCostAnalysisForInspection([analysisA, analysisB], latestInspection)?.analysis_id,
    ).toBe("ANALYSIS-B");
  });

  it("sends only Action and consulted SOP for server-owned tool cost inputs", () => {
    const request = buildCostRequest(guidance);

    expect(request).toEqual({
      action_code: "TOOL_REPLACEMENT",
      sop_id: "SOP-CNC-TOOL-001",
      sop_version: "v1",
    });
  });

  it("sends only Action and consulted SOP for server-owned cooling cost inputs", () => {
    expect(buildCostRequest(guidance, "COOLING_SYSTEM_RESTORE")).toEqual({
      action_code: "COOLING_SYSTEM_RESTORE",
      sop_id: "SOP-CNC-TOOL-001",
      sop_version: "v1",
    });
  });

  it("shows cooling immediate only and hides tool reinspection from the product UI", () => {
    const analysis = costAnalysis(
      "ANALYSIS-COOLING",
      "RESULT-DONE",
      "WO-DONE",
      "2026-09-01T01:00:00Z",
    );
    analysis.options = [
      "immediate",
      "planned_window",
      "reinspect_after",
      "no_action_baseline",
    ].map((executionTiming, index) => ({
      option_id: `OPTION-${index}`,
      action_candidate_id: "ACTION-CANDIDATE-COOLING",
      action_code: "COOLING_SYSTEM_RESTORE",
      execution_timing: executionTiming as typeof analysis.options[number]["execution_timing"],
      calculation_status: executionTiming === "immediate" ? "calculated" : "insufficient",
      total_expected_cost: executionTiming === "immediate"
        ? { low_minor: 46830, base_minor: 76620, high_minor: 131730 }
        : null,
      expected_downtime: executionTiming === "immediate"
        ? { low_minutes: 45, base_minutes: 60, high_minutes: 90 }
        : null,
      confidence: executionTiming === "immediate" ? "low" : "insufficient",
      missing_inputs: executionTiming === "immediate" ? [] : ["expected_failure_loss"],
    }));

    expect(
      costOptionsForDisplay(analysis, "COOLING_SYSTEM_RESTORE")
        .map((option) => option.execution_timing),
    ).toEqual(["immediate"]);
    expect(
      costOptionsForDisplay(analysis, "TOOL_REPLACEMENT")
        .map((option) => option.execution_timing),
    ).toEqual(["immediate", "planned_window", "no_action_baseline"]);
  });
});
