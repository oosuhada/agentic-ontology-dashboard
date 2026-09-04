import { describe, expect, it } from "vitest";
import type { EventSummary } from "../../../types";
import type { GovernedProductResultSummary } from "../../predictive-maintenance/types";
import {
  adaptEvent,
  applyAssetDetailViewModel,
  buildTemplateReport,
  composeEventDetail,
  computeLineRisk,
  computeMetrics,
  mergeAssets,
  normalizeActivity,
  normalizeDecision,
  normalizeRiskStatus,
  promoteRuntimeProductResultsToEvents,
} from "./operationsAdapters";

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

describe("Operations adapter contract", () => {
  it("normalizes statuses and only uses the approved decision enum", () => {
    expect(normalizeRiskStatus("danger")).toBe("critical");
    expect(normalizeRiskStatus("unknown")).toBe("data_quality_hold");
    expect(normalizeRiskStatus(undefined)).toBe("data_quality_hold");
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
      source_contract: "result_artifact",
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
      evidence_summary: null,
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

  it("does not synthesize criticality from risk when operational context is missing", () => {
    const result: GovernedProductResultSummary = {
      artifact_id: "RESULT#CNC-009",
      source_contract: "result_artifact",
      asset_id: "CNC-009",
      asset_type: "cnc",
      site_id: "SITE-1",
      cell_id: "CELL-1",
      observed_at: "2026-08-06T03:00:00Z",
      prediction_task: "binary_failure_within_horizon",
      failure_probability: 0.94,
      predicted_failure_type: "failure_risk",
      status_grade: "critical",
      confidence: 0.88,
      top_factors: [],
      recommended_action: { action: "review_shutdown", priority: "critical", semantic_type: "policy_recommendation", approval_state: "not_requested", execution_state: "not_executed", creates_work_order_automatically: false },
      evidence_summary: null,
      provenance: { dataset_id: "dataset-1", dataset_version_id: "dsv-canonical-v3-1", source_version: "Canonical V3.1", bundle_checksum_sha256: "a".repeat(64), model_version: "model-1", schema_version: "result-artifact-v1.0", prediction_task: "binary_failure_within_horizon" },
    };
    const events = promoteRuntimeProductResultsToEvents([result], []);
    const assets = mergeAssets([result], events);

    expect(assets[0].status).toBe("critical");
    expect(assets[0].criticality).toBeNull();
    expect(assets[0].eventId).toBe("RESULT#CNC-009");
    expect(events).toEqual([
      expect.objectContaining({
        eventId: "RESULT#CNC-009",
        assetId: "CNC-009",
        line: "CELL-1",
        recommendedDecision: "review_shutdown",
      }),
    ]);
  });

  it("keeps an existing operational event instead of replacing it with a runtime result event", () => {
    const operational = adaptEvent(event);
    const result: GovernedProductResultSummary = {
      artifact_id: "RESULT#CNC-001",
      source_contract: "result_artifact",
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
      top_factors: [],
      recommended_action: { action: "review_shutdown", priority: "critical", semantic_type: "policy_recommendation", approval_state: "not_requested", execution_state: "not_executed", creates_work_order_automatically: false },
      evidence_summary: null,
      provenance: { dataset_id: "dataset-1", dataset_version_id: "dsv-canonical-v3-1", source_version: "Canonical V3.1", bundle_checksum_sha256: "a".repeat(64), model_version: "model-1", schema_version: "result-artifact-v1.0", prediction_task: "binary_failure_within_horizon" },
    };

    expect(promoteRuntimeProductResultsToEvents([result], [operational])).toEqual([operational]);
  });

  it("does not synthesize downtime impact when operational context is missing", () => {
    const adapted = adaptEvent({
      ...event,
      equipment: {
        ...event.equipment,
        estimated_downtime_minutes: undefined,
      },
    } as unknown as EventSummary);

    expect(adapted.estimatedDowntimeMinutes).toBeNull();
  });

  it("derives the same metrics and line summary used by all four screens", () => {
    const events = [adaptEvent(event), adaptEvent({ ...event, event_id: "EVENT-002", equipment: { ...event.equipment, equipment_id: "CNC-002" }, status: "warning", failure_probability: 0.65 })];
    const assets = mergeAssets([], events);
    expect(computeMetrics(assets, events)).toEqual(expect.objectContaining({ critical: 1, warning: 1, estimatedDowntimeMinutes: 240 }));
    expect(computeLineRisk(assets)[0]).toEqual(expect.objectContaining({ line: "Line A", normal: 0, critical: 1, warning: 1 }));
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

  it("maps compressor evidence to compressor sensor fields", () => {
    const evidence = {
      observation: {
        asset_type: "compressor",
        voltage_raw: 171.2,
        rotation_raw: 448.4,
        pressure_raw: 101.5,
        vibration_raw: 42.1,
        relative_vibration_z: 1.2,
        relative_vibration_zone: "B",
      },
      top_factors: [],
      lineage: {},
      maintenance_context: { source_refs: [] },
      model: {},
    } as never;

    const event = adaptEvent({
      event_id: "compressor-event",
      equipment: { equipment_id: "CMP-001", display_name: "CMP-001", line: "S01 / L01", criticality: "medium" },
      status: "attention",
      failure_probability: 0.3,
      confidence: "70%",
      predicted_failure_type: "no_significant_risk",
      recommended_decision: "request_inspection",
      observed_at: "2026-08-01T00:00:00Z",
      dataset_version_id: "dsv-test",
    } as never);
    const detail = composeEventDetail({ event, evidence, report: null, activity: null });

    expect(detail.sensors.map((item) => item.id)).toEqual([
      "voltage_raw",
      "rotation_raw",
      "pressure_raw",
      "vibration_raw",
      "relative_vibration_z",
      "relative_vibration_zone",
    ]);
  });

  it("preserves AssetDetailViewModel current/history, gaps, and nullable freshness", () => {
    const adapted = adaptEvent({
      ...event,
      equipment: { ...event.equipment, criticality: undefined },
    } as never);
    const detail = composeEventDetail({ event: adapted, evidence: null, report: null, activity: null });
    const enriched = applyAssetDetailViewModel(detail, {
      snapshot_basis: {
        artifact_id: "RESULT#CNC-001",
        evidence_payload_reference: "RESULT#CNC-001",
        asset_id: "CNC-001",
        event_id: "EVT-CNC-001",
        observed_at: "2026-08-06T03:00:00Z",
        model_version: "model-1",
        dataset_version: "dsv-canonical-v3-1",
        source_sha256: null,
      },
      asset: {
        asset_id: "CNC-001",
        asset_type: "cnc",
        observed_at: "2026-08-06T03:00:00Z",
        criticality: null,
        criticality_basis: [],
        criticality_source: "unknown",
      },
      risk: {
        current: 0.92,
        threshold: 0.7,
        status_grade: "critical",
        prediction_horizon_hours: 24,
      },
      risk_series: [{
        observed_at: "2026-08-06T02:00:00Z",
        failure_probability: 0.84,
        status_grade: "warning",
        prediction_id: "pred-1",
        source_kind: "runtime_inference",
        source_ref: "prediction://pred-1",
      }],
      features: [{
        key: "tool_wear_min",
        label: "공구 마모",
        unit: "분",
        current: {
          observed_at: "2026-08-06T03:00:00Z",
          value: 210,
          quality_status: "good",
        },
        history: {
          source_ref: "observation-series://CNC-001/tool_wear_min",
          window: {
            requested: "24h",
            anchor_observed_at: "2026-08-06T03:00:00Z",
            requested_start: "2026-08-05T03:00:00Z",
            requested_end: "2026-08-06T03:00:00Z",
            actual_start: "2026-08-06T02:00:00Z",
            actual_end: "2026-08-06T02:00:00Z",
            point_count: 1,
            coverage_status: "partial",
          },
          points: [{
            observed_at: "2026-08-06T02:00:00Z",
            value: 200,
            quality_status: "good",
          }],
        },
        top_factor: {
          rank: 1,
          contribution: 0.42,
          direction: "risk_up",
          explanation_method: "shap",
          evidence_field_id: "features.tool_wear_min",
        },
      }],
      equipment_history: [{
        occurred_at: "2026-08-05T00:00:00Z",
        kind: "inspection",
        tone: "attention",
        description: "이전 점검 기록",
        source: "maintenance-read-model",
      }],
      maintenance_context: {
        last_maintenance_days_ago: null,
        similar_events_30d: null,
        open_work_order_exists: null,
      },
      inspection_targets: [{
        target_id: "inspection-target:RESULT#CNC-001:1",
        component_id: "rotating_assembly",
        component_label: "회전/진동 계통",
        association: "inspection_candidate",
        location_label: null,
        inspection_method: null,
        location_contract_id: null,
        location_source_ref: null,
        location_maturity: null,
        inspection_guidance: {
          source_type: "demo_sop_fixture",
          sop_id: "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
          title: "CNC 회전/구동 계통 점검 참고 절차",
          version: "demo-2026-08-28",
          reference_location_label: "SOP 기준 참고 위치",
          suggested_check_method: "회전/구동 계통의 체결, 마모, 이상 소음 여부를 확인합니다.",
          checklist_draft: ["점검 전 설비 상태를 확인합니다."],
          maintenance_review_prerequisites: {
            label: "정비 판단 전 확인사항",
            review_conditions: ["동일 부품 후보가 반복적으로 상위 위험 요인과 연결됩니다."],
            required_measurements: ["현재 센서 관측값과 최근 이력 비교"],
            human_review_questions: ["교체 전 생산 정지 가능 시간이 확인됐습니까?"],
            decision_boundary: "이 정보는 정비 판단 전 확인사항이며 정비 방법·시점 결정, 비용상 선호 대안, WorkOrder 생성 또는 정비 승인을 수행하지 않습니다.",
          },
          safety_level: "caution",
          requires_human_approval: true,
          source_ref: "data/fixtures/inspection_sop/demo-cnc-inspection-guidance-v1-1.json#SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
          disclaimer: "데모 SOP fixture 기반 참고 안내이며 Product Evidence가 확정한 점검 위치 또는 수리 지시가 아닙니다.",
        },
        basis_refs: ["factor.1.tool_wear_min", "sensor_evidence.sensors.tool_wear_min"],
        source_ref: "storage://result.json#component_hypotheses[0]",
        unavailable_reason: "field_inspection_location_reference_unavailable",
      }],
      operation_context: {
        load_level: null,
        runtime_hours_7d: null,
        production_impact: null,
      },
      review_priority: null,
      evidence: {
        artifact_id: "RESULT#CNC-001",
        model_version: "model-1",
        dataset_version: "dsv-canonical-v3-1",
        source_kind: "runtime_inference",
        gaps: [
          {
            field: "asset.criticality",
            reason: "criticality_missing_or_unresolved",
            owner_domain: "equipment",
          },
          {
            field: "review_priority",
            reason: "review_priority_inputs_missing_or_unresolved",
            owner_domain: "report",
          },
        ],
      },
      data_status: {
        source: "canonical",
        is_stale: null,
        is_data_quality_hold: false,
        warnings: [],
      },
      closed_loop: {
        work_orders: [{
          work_order_id: "WO-INS-001",
          work_type: "inspection",
          status: "requested",
          assigned_to: null,
          actor_display_name: "윤하린",
          created_at: "2026-08-06T03:10:00Z",
          updated_at: "2026-08-06T03:10:00Z",
        }],
        maintenance_actions: [],
        maintenance_events: [],
        activities: [{
          activity_id: "ACT-001",
          activity_type: "work_order.requested",
          work_type: "inspection",
          actor_display_name: "윤하린",
          before_status: null,
          after_status: "requested",
          created_at: "2026-08-06T03:10:00Z",
          work_order_id: "WO-INS-001",
        }],
        available_actions: [{
          action_id: "approve_inspection_work_order",
          target_type: "work_order",
          target_id: "WO-INS-001",
          label: "점검 승인",
          disabled_reason: null,
        }],
        lifecycle_summary: {
          current_step: "inspection_requested",
          current_step_label: "점검 승인 대기",
          completed_steps: ["prediction", "evidence", "decision"],
          next_step: "inspection_approved",
          source: "backend_closed_loop_policy",
        },
        primary_action: {
          action_id: "approve_inspection_work_order",
          target_type: "work_order",
          target_id: "WO-INS-001",
          label: "점검 승인",
          owner_role: "process_manager",
          owner_label: "생산 운영 의사결정자",
          disabled_reason: null,
          requires_input: false,
        },
        timeline: [{
          timeline_id: "ACT-001",
          event_type: "work_order.requested",
          label: "작업요청 생성",
          status: "completed",
          actor_display_name: "윤하린",
          occurred_at: "2026-08-06T03:10:00Z",
          target_type: "work_order",
          target_id: "WO-INS-001",
        }],
        runtime_status: null,
      },
    });

    expect(enriched.snapshotBasis).toEqual({
      artifactId: "RESULT#CNC-001",
      evidencePayloadReference: "RESULT#CNC-001",
      assetId: "CNC-001",
      eventId: "EVT-CNC-001",
      observedAt: "2026-08-06T03:00:00Z",
      modelVersion: "model-1",
      datasetVersion: "dsv-canonical-v3-1",
      sourceSha256: null,
    });
    expect(enriched.sensors[0]).toEqual(expect.objectContaining({
      observedAt: "2026-08-06T03:00:00Z",
      historySourceRef: "observation-series://CNC-001/tool_wear_min",
      historyPointCount: 1,
      historyWindow: {
        requested: "24h",
        anchorObservedAt: "2026-08-06T03:00:00Z",
        requestedStart: "2026-08-05T03:00:00Z",
        requestedEnd: "2026-08-06T03:00:00Z",
        actualStart: "2026-08-06T02:00:00Z",
        actualEnd: "2026-08-06T02:00:00Z",
        pointCount: 1,
        coverageStatus: "partial",
      },
      historyPoints: [{
        observedAt: "2026-08-06T02:00:00Z",
        value: 200,
        qualityStatus: "good",
      }],
    }));
    expect(enriched.predictionHorizonHours).toBe(24);
    expect(enriched.riskSeries[0]).toEqual(expect.objectContaining({
      observedAt: "2026-08-06T02:00:00Z",
      failureProbability: 0.84,
      status: "warning",
    }));
    expect(enriched.evidenceGaps[0]).toEqual(expect.objectContaining({ field: "asset.criticality" }));
    expect(enriched.assetDetailStatus?.isStale).toBeNull();
    expect(enriched.equipmentHistory[0].source).toBe("maintenance-read-model");
    expect(enriched.closedLoop?.workOrders[0]).toEqual(expect.objectContaining({
      workOrderId: "WO-INS-001",
      workType: "inspection",
      status: "requested",
      actorDisplayName: "윤하린",
    }));
    expect(enriched.closedLoop?.availableActions[0]).toEqual(expect.objectContaining({
      actionId: "approve_inspection_work_order",
      targetId: "WO-INS-001",
    }));
    expect(enriched.closedLoop?.lifecycleSummary).toEqual(expect.objectContaining({
      currentStep: "inspection_requested",
      currentStepLabel: "점검 승인 대기",
      nextStep: "inspection_approved",
    }));
    expect(enriched.closedLoop?.primaryAction).toEqual(expect.objectContaining({
      actionId: "approve_inspection_work_order",
      ownerRole: "process_manager",
      ownerLabel: "생산 운영 의사결정자",
      requiresInput: false,
    }));
    expect(enriched.closedLoop?.timeline[0]).toEqual(expect.objectContaining({
      timelineId: "ACT-001",
      label: "작업요청 생성",
      targetId: "WO-INS-001",
    }));
    expect(enriched.closedLoop?.activities[0]).toEqual(expect.objectContaining({
      activityType: "work_order.requested",
      afterStatus: "requested",
      workOrderId: "WO-INS-001",
    }));
    expect(enriched.inspectionTargets[0]).toEqual(expect.objectContaining({
      componentId: "rotating_assembly",
      componentLabel: "회전/진동 계통",
      locationLabel: null,
      inspectionGuidance: expect.objectContaining({
        sourceType: "demo_sop_fixture",
        sopId: "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
        referenceLocationLabel: "SOP 기준 참고 위치",
        suggestedCheckMethod: "회전/구동 계통의 체결, 마모, 이상 소음 여부를 확인합니다.",
        safetyLevel: "caution",
        requiresHumanApproval: true,
        maintenanceReviewPrerequisites: {
          label: "정비 판단 전 확인사항",
          reviewConditions: ["동일 부품 후보가 반복적으로 상위 위험 요인과 연결됩니다."],
          requiredMeasurements: ["현재 센서 관측값과 최근 이력 비교"],
          humanReviewQuestions: ["교체 전 생산 정지 가능 시간이 확인됐습니까?"],
          decisionBoundary: "이 정보는 정비 판단 전 확인사항이며 정비 방법·시점 결정, 비용상 선호 대안, WorkOrder 생성 또는 정비 승인을 수행하지 않습니다.",
        },
      }),
      unavailableReason: "field_inspection_location_reference_unavailable",
    }));
    expect(enriched.inspectionTargets[0].basisRefs).toEqual([
      "factor.1.tool_wear_min",
      "sensor_evidence.sensors.tool_wear_min",
    ]);
    expect(enriched.event.criticality).toBeNull();
    expect(enriched.assetCriticality).toBeNull();
    expect(enriched.reviewPriority).toBeNull();
    expect(enriched.warnings.join(" ")).toContain("asset.criticality");
  });
});
