import type { Evidence, EventSummary, Report } from "../../../types";
import type { GovernedProductResultSummary } from "../../predictive-maintenance/types";
import type {
  OperationsActivityItem,
  AssetDetailViewModel,
  OperationsAsset,
  OperationsConfidence,
  OperationsDecision,
  OperationsEquipmentHistoryItem,
  OperationsEvent,
  OperationsEventDetailModel,
  OperationsEvidenceGap,
  OperationsEvidenceSnapshotBasis,
  OperationsFactor,
  OperationsInspectionTarget,
  OperationsLineRisk,
  OperationsMetrics,
  OperationsClosedLoopSummary,
  OperationsOperationContext,
  OperationsProvenance,
  OperationsReportModel,
  OperationsRiskStatus,
  OperationsSensorValue,
} from "./operationsContracts";

const STATUS_PRIORITY: Record<OperationsRiskStatus, number> = {
  critical: 5,
  warning: 4,
  attention: 3,
  data_quality_hold: 2,
  normal: 1,
};

function snapshotBasisFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsEvidenceSnapshotBasis {
  return {
    artifactId: viewModel.snapshot_basis.artifact_id,
    evidencePayloadReference:
      viewModel.snapshot_basis.evidence_payload_reference,
    assetId: viewModel.snapshot_basis.asset_id,
    eventId: viewModel.snapshot_basis.event_id,
    observedAt: viewModel.snapshot_basis.observed_at,
    modelVersion: viewModel.snapshot_basis.model_version,
    datasetVersion: viewModel.snapshot_basis.dataset_version,
    sourceSha256: viewModel.snapshot_basis.source_sha256,
  };
}

export function normalizeRiskStatus(value: unknown): OperationsRiskStatus {
  const status = String(value ?? "").toLowerCase();
  if (status === "critical" || status === "danger") return "critical";
  if (status === "warning" || status === "warn") return "warning";
  if (status === "attention" || status === "caution") return "attention";
  if (
    status === "data_quality_hold" ||
    status === "quality_hold" ||
    status === "blocked"
  )
    return "data_quality_hold";
  if (status === "normal" || status === "healthy" || status === "ok")
    return "normal";
  return "data_quality_hold";
}

export function normalizeConfidence(value: unknown): {
  level: OperationsConfidence;
  score: number | null;
} {
  if (typeof value === "number" && Number.isFinite(value)) {
    if (value >= 0.8) return { level: "high", score: value };
    if (value >= 0.6) return { level: "medium", score: value };
    return { level: "low", score: value };
  }
  const normalized = String(value ?? "").toLowerCase();
  if (["high", "높음"].includes(normalized))
    return { level: "high", score: null };
  if (["medium", "moderate", "중간"].includes(normalized))
    return { level: "medium", score: null };
  if (["low", "낮음"].includes(normalized))
    return { level: "low", score: null };
  return { level: "unavailable", score: null };
}

export function normalizeDecision(value: unknown): OperationsDecision {
  const decision = String(value ?? "").toLowerCase();
  if (decision === "continue_monitoring") return "continue_monitoring";
  if (decision === "request_inspection") return "request_inspection";
  if (decision === "review_shutdown") return "review_shutdown";
  if (decision === "hold_for_data_check") return "hold_for_data_check";
  if (
    decision.includes("data") ||
    decision.includes("quality") ||
    decision.includes("hold")
  )
    return "hold_for_data_check";
  if (decision.includes("stop") || decision.includes("shutdown"))
    return "review_shutdown";
  if (decision.includes("inspect") || decision.includes("check"))
    return "request_inspection";
  return "continue_monitoring";
}

export function sortRisk<
  T extends {
    status: OperationsRiskStatus;
    failureProbability: number | null;
    observedAt?: string | null;
  },
>(items: T[]): T[] {
  return [...items].sort(
    (left, right) =>
      STATUS_PRIORITY[right.status] - STATUS_PRIORITY[left.status] ||
      (right.failureProbability ?? -1) - (left.failureProbability ?? -1) ||
      String(right.observedAt ?? "").localeCompare(
        String(left.observedAt ?? ""),
      ),
  );
}

function fallbackProvenance(datasetVersionId: string): OperationsProvenance {
  return {
    datasetId: null,
    datasetVersionId,
    datasetLabel: "Canonical V3.1",
    sourceVersion: "Canonical V3.1",
    modelVersion: null,
    policyVersion: null,
    schemaVersion: null,
    promptVersion: null,
    sourceRefs: [],
  };
}
export function adaptEvent(event: EventSummary): OperationsEvent {
  const status = normalizeRiskStatus(event.status);
  const line = event.equipment.line ?? event.equipment.cell_id ?? "미지정 라인";
  return {
    eventId: event.event_id,
    scenarioId: event.scenario_id,
    assetId: event.equipment.equipment_id,
    assetName: event.equipment.display_name,
    line,
    status,
    failureProbability:
      status === "data_quality_hold" ? null : event.failure_probability,
    confidence: normalizeConfidence(event.confidence).level,
    predictedFailureType: event.predicted_failure_type || "unavailable",
    recommendedDecision:
      status === "data_quality_hold"
        ? "hold_for_data_check"
        : normalizeDecision(event.recommended_decision),
    criticality: event.equipment.criticality ?? null,
    assignedEngineer: event.equipment.assigned_engineer || null,
    estimatedDowntimeMinutes:
      event.equipment.estimated_downtime_minutes ?? null,
    sparePartAvailable: event.equipment.spare_part_available ?? null,
    observedAt: event.observed_at ?? null,
    datasetVersionId: event.dataset_version_id ?? "dsv-canonical-v3-1",
    ontologyObjectId: event.ontology_object_id ?? null,
  };
}

function runtimeEventFromResult(
  result: GovernedProductResultSummary,
): OperationsEvent | null {
  if (!result.artifact_id) return null;
  const status = normalizeRiskStatus(result.status_grade);
  return {
    eventId: result.artifact_id,
    scenarioId: "runtime-product-result",
    assetId: result.asset_id,
    assetName: result.asset_id,
    line: result.cell_id || result.site_id,
    status,
    failureProbability:
      status === "data_quality_hold" ? null : result.failure_probability,
    confidence: normalizeConfidence(result.confidence).level,
    predictedFailureType: result.predicted_failure_type,
    recommendedDecision: normalizeDecision(result.recommended_action?.action),
    criticality: null,
    assignedEngineer: null,
    estimatedDowntimeMinutes: null,
    sparePartAvailable: null,
    observedAt: result.observed_at,
    datasetVersionId: result.provenance.dataset_version_id,
    ontologyObjectId: null,
  };
}

export function promoteRuntimeProductResultsToEvents(
  results: GovernedProductResultSummary[],
  events: OperationsEvent[],
): OperationsEvent[] {
  const representedEvents = new Set(events.map((event) => event.eventId));
  const latestResultByAsset = new Map<string, GovernedProductResultSummary>();
  for (const result of results) {
    const current = latestResultByAsset.get(result.asset_id);
    if (!current || result.observed_at.localeCompare(current.observed_at) > 0) {
      latestResultByAsset.set(result.asset_id, result);
    }
  }

  const promoted = [...events];
  for (const result of latestResultByAsset.values()) {
    const event = runtimeEventFromResult(result);
    if (!event) continue;
    if (representedEvents.has(event.eventId)) continue;
    promoted.push(event);
    representedEvents.add(event.eventId);
  }
  return sortRisk(promoted);
}

function operationContextFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsOperationContext | null {
  const context = viewModel.operation_context;
  if (!context) return null;
  return {
    loadLevel: context.load_level,
    runtimeHours7d: context.runtime_hours_7d,
    productionImpact: context.production_impact,
    contextId: context.context_id,
    sourceType: context.source_type,
    temporalScope: context.temporal_scope
      ? {
          snapshotId: context.temporal_scope.snapshot_id,
          timezone: context.temporal_scope.timezone,
          validFrom: context.temporal_scope.valid_from,
          validTo: context.temporal_scope.valid_to,
          generatedAt: context.temporal_scope.generated_at,
        }
      : undefined,
    productionPlan: context.production_plan
      ? {
          planId: context.production_plan.plan_id,
          planDate: context.production_plan.plan_date,
          plannedUnits: context.production_plan.planned_units,
          productMix: context.production_plan.product_mix.map((item) => ({
            variant: item.variant,
            share: item.share,
            plannedUnits: item.planned_units,
          })),
        }
      : undefined,
    capacityModel: context.capacity_model
      ? {
          activeAssetCount: context.capacity_model.active_asset_count,
          plannedOperatingHours: context.capacity_model.planned_operating_hours,
          oee: context.capacity_model.oee,
          standardCycleMinutesPerUnit:
            context.capacity_model.standard_cycle_minutes_per_unit,
          assetUnitsPerHour: context.capacity_model.asset_units_per_hour,
          dailyCapacityUnits: context.capacity_model.daily_capacity_units,
          basis: context.capacity_model.basis,
        }
      : undefined,
    eventImpact: context.event_impact
      ? {
          eventId: context.event_impact.event_id,
          equipmentId: context.event_impact.equipment_id,
          line: context.event_impact.line,
          productVariant: context.event_impact.product_variant,
          screenPriority: context.event_impact.screen_priority,
          impactStatus: context.event_impact.impact_status,
          estimatedLostUnits: context.event_impact.estimated_lost_units,
          basis: {
            estimatedDowntimeMinutes:
              context.event_impact.basis.estimated_downtime_minutes,
            assetUnitsPerHour: context.event_impact.basis.asset_units_per_hour,
            formula: context.event_impact.basis.formula,
          },
        }
      : context.event_impact === null
        ? null
        : undefined,
    limitations: context.limitations,
  };
}

function closedLoopFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsClosedLoopSummary | null {
  const closedLoop = viewModel.closed_loop;
  if (!closedLoop) return null;
  return {
    workOrders: (closedLoop.work_orders ?? []).map((item) => ({
      workOrderId: item.work_order_id,
      workType: item.work_type,
      status: item.status,
      assignedTo: item.assigned_to ?? null,
      actorDisplayName: item.actor_display_name ?? null,
      createdAt: item.created_at ?? null,
      updatedAt: item.updated_at ?? null,
    })),
    inspectionResults: (closedLoop.inspection_results ?? []).map((item) => ({
      inspectionResultId: item.inspection_result_id,
      workOrderId: item.work_order_id,
      outcome: item.outcome,
      recordedBy: item.recorded_by ?? null,
      recordedAt: item.recorded_at ?? null,
      createdAt: item.created_at ?? null,
    })),
    maintenanceActions: (closedLoop.maintenance_actions ?? []).map((item) => ({
      maintenanceActionId: item.maintenance_action_id,
      workOrderId: item.work_order_id ?? null,
      status: item.status,
      actorDisplayName: item.actor_display_name ?? null,
      startedAt: item.started_at ?? null,
      completedAt: item.completed_at ?? null,
    })),
    maintenanceEvents: (closedLoop.maintenance_events ?? []).map((item) => ({
      maintenanceEventId: item.maintenance_event_id,
      maintenanceActionId: item.maintenance_action_id ?? null,
      workOrderId: item.work_order_id ?? null,
      completedAt: item.completed_at ?? null,
      actorDisplayName: item.actor_display_name ?? null,
    })),
    activities: (closedLoop.activities ?? []).map((item) => ({
      activityId: item.activity_id,
      activityType: item.activity_type,
      workType: item.work_type ?? null,
      actorDisplayName: item.actor_display_name ?? null,
      beforeStatus: item.before_status ?? null,
      afterStatus: item.after_status ?? null,
      createdAt: item.created_at ?? null,
      workOrderId: item.work_order_id ?? null,
      maintenanceActionId: item.maintenance_action_id ?? null,
      maintenanceEventId: item.maintenance_event_id ?? null,
    })),
    availableActions: (closedLoop.available_actions ?? []).map((item) => ({
      actionId: item.action_id,
      targetType: item.target_type,
      targetId: item.target_id ?? null,
      label: item.label,
      disabledReason: item.disabled_reason ?? null,
    })),
    lifecycleSummary: closedLoop.lifecycle_summary
      ? {
          currentStep: closedLoop.lifecycle_summary.current_step,
          currentStepLabel: closedLoop.lifecycle_summary.current_step_label,
          completedSteps: closedLoop.lifecycle_summary.completed_steps,
          nextStep: closedLoop.lifecycle_summary.next_step ?? null,
          source: closedLoop.lifecycle_summary.source,
        }
      : null,
    primaryAction: closedLoop.primary_action
      ? {
          actionId: closedLoop.primary_action.action_id,
          targetType: closedLoop.primary_action.target_type,
          targetId: closedLoop.primary_action.target_id ?? null,
          label: closedLoop.primary_action.label,
          disabledReason: closedLoop.primary_action.disabled_reason ?? null,
          ownerRole: closedLoop.primary_action.owner_role,
          ownerLabel: closedLoop.primary_action.owner_label,
          requiresInput: closedLoop.primary_action.requires_input,
        }
      : null,
    timeline: (closedLoop.timeline ?? []).map((item) => ({
      timelineId: item.timeline_id,
      eventType: item.event_type,
      label: item.label,
      status: item.status,
      actorDisplayName: item.actor_display_name ?? null,
      occurredAt: item.occurred_at ?? null,
      targetType: item.target_type ?? null,
      targetId: item.target_id ?? null,
    })),
    runtimeStatus: closedLoop.runtime_status ?? null,
  };
}

function eventAsset(event: OperationsEvent): OperationsAsset {
  return {
    assetId: event.assetId,
    displayName: event.assetName,
    assetType: event.assetId.toLowerCase().includes("cnc")
      ? "cnc"
      : event.assetId.toUpperCase().startsWith("CMP-")
        ? "compressor"
        : "equipment",
    site: event.assetId.match(/^[A-Z]+-(S\d+)-/)?.[1] ?? "Hanbit Tech Plant",
    line: event.line,
    cell: event.line,
    status: event.status,
    failureProbability: event.failureProbability,
    confidence: event.confidence,
    confidenceScore: null,
    criticality: event.criticality,
    assignedEngineer: event.assignedEngineer,
    estimatedDowntimeMinutes: event.estimatedDowntimeMinutes,
    sparePartAvailable: event.sparePartAvailable,
    predictedFailureType: event.predictedFailureType,
    recommendedDecision: event.recommendedDecision,
    observedAt: event.observedAt,
    eventId: event.eventId,
    topFactors: [],
    provenance: fallbackProvenance(event.datasetVersionId),
  };
}

function adaptResultFactor(
  item: GovernedProductResultSummary["top_factors"][number],
): OperationsFactor {
  return {
    id: `${item.feature}:${item.rank}`,
    feature: item.feature,
    label: item.display_name ?? item.feature.replaceAll("_", " "),
    value: item.feature_value,
    unit: item.unit ?? null,
    contribution: Math.abs(item.signed_contribution),
    direction: item.direction,
    explanationMethod: item.explanation_method,
  };
}

export function mergeAssets(
  results: GovernedProductResultSummary[],
  events: OperationsEvent[],
): OperationsAsset[] {
  const byAsset = new Map(events.map((event) => [event.assetId, event]));
  const latestResultByAsset = new Map<string, GovernedProductResultSummary>();
  for (const result of results) {
    const current = latestResultByAsset.get(result.asset_id);
    if (!current || result.observed_at.localeCompare(current.observed_at) > 0) {
      latestResultByAsset.set(result.asset_id, result);
    }
  }
  const assets = [...latestResultByAsset.values()].map(
    (result): OperationsAsset => {
      const related = byAsset.get(result.asset_id);
      const confidence = normalizeConfidence(result.confidence);
      const status = normalizeRiskStatus(result.status_grade);
      return {
        assetId: result.asset_id,
        displayName: related?.assetName ?? result.asset_id,
        assetType: result.asset_type,
        site: result.site_id,
        // Runtime Product Results can exist before an Operations Event is
        // materialized.  In that case cell_id is the canonical factory-map
        // grouping key; using site_id collapses every cell in a site and makes
        // the real equipment look like an unconnected placeholder.
        line: related?.line ?? result.cell_id ?? result.site_id,
        cell: result.cell_id,
        status,
        failureProbability: result.failure_probability,
        confidence: confidence.level,
        confidenceScore: confidence.score,
        criticality: related?.criticality ?? null,
        assignedEngineer: related?.assignedEngineer ?? null,
        estimatedDowntimeMinutes: related?.estimatedDowntimeMinutes ?? null,
        sparePartAvailable: related?.sparePartAvailable ?? null,
        predictedFailureType: result.predicted_failure_type,
        recommendedDecision:
          related?.recommendedDecision ??
          normalizeDecision(result.recommended_action?.action),
        observedAt: result.observed_at,
        eventId: result.artifact_id ?? related?.eventId ?? null,
        topFactors: result.top_factors.map(adaptResultFactor),
        provenance: {
          datasetId: result.provenance.dataset_id,
          datasetVersionId: result.provenance.dataset_version_id,
          datasetLabel: result.provenance.source_version,
          sourceVersion: result.provenance.source_version,
          modelVersion: result.provenance.model_version,
          policyVersion: null,
          schemaVersion: result.provenance.schema_version,
          promptVersion: null,
          sourceRefs: result.artifact_id
            ? [`result-artifact://${result.artifact_id}`]
            : [],
        },
      };
    },
  );
  const seen = new Set(assets.map((asset) => asset.assetId));
  for (const event of events) {
    if (!seen.has(event.assetId)) {
      assets.push(eventAsset(event));
      seen.add(event.assetId);
    }
  }
  return sortRisk(assets);
}

export function computeMetrics(
  assets: OperationsAsset[],
  events: OperationsEvent[],
): OperationsMetrics {
  const probabilities = assets
    .map((asset) => asset.failureProbability)
    .filter((value): value is number => value !== null);
  const counts = {
    normal: assets.filter((asset) => asset.status === "normal").length,
    attention: assets.filter((asset) => asset.status === "attention").length,
    warning: assets.filter((asset) => asset.status === "warning").length,
    critical: assets.filter((asset) => asset.status === "critical").length,
    dataQualityHold: assets.filter(
      (asset) => asset.status === "data_quality_hold",
    ).length,
  };
  return {
    totalAssets: assets.length,
    ...counts,
    averageRisk: probabilities.length
      ? probabilities.reduce((sum, value) => sum + value, 0) /
        probabilities.length
      : null,
    estimatedDowntimeMinutes:
      assets.length > 0 &&
      assets.every((asset) => asset.estimatedDowntimeMinutes !== null)
        ? assets.reduce(
            (sum, asset) => sum + asset.estimatedDowntimeMinutes!,
            0,
          )
        : null,
    pendingDecisions: assets.filter(
      (asset) => asset.recommendedDecision !== "continue_monitoring",
    ).length,
  };
}

export function computeLineRisk(
  assets: OperationsAsset[],
): OperationsLineRisk[] {
  const grouped = new Map<string, OperationsAsset[]>();
  for (const asset of assets) {
    const rows = grouped.get(asset.line) ?? [];
    rows.push(asset);
    grouped.set(asset.line, rows);
  }
  return [...grouped.entries()]
    .map(([line, rows]) => {
      const probabilities = rows
        .map((row) => row.failureProbability)
        .filter((value): value is number => value !== null);
      return {
        line,
        total: rows.length,
        normal: rows.filter((row) => row.status === "normal").length,
        critical: rows.filter((row) => row.status === "critical").length,
        warning: rows.filter((row) => row.status === "warning").length,
        attention: rows.filter((row) => row.status === "attention").length,
        dataQualityHold: rows.filter(
          (row) => row.status === "data_quality_hold",
        ).length,
        averageRisk: probabilities.length
          ? probabilities.reduce((sum, value) => sum + value, 0) /
            probabilities.length
          : null,
      };
    })
    .sort(
      (left, right) =>
        right.critical - left.critical ||
        right.warning - left.warning ||
        (right.averageRisk ?? -1) - (left.averageRisk ?? -1),
    );
}

function evidenceFactors(evidence: Evidence | null): OperationsFactor[] {
  return (evidence?.top_factors ?? []).map((factor) => ({
    id: factor.evidence_field_id,
    feature: factor.feature,
    label: factor.display_name,
    value: factor.value,
    unit: factor.unit || null,
    contribution: Math.abs(factor.contribution),
    direction: factor.direction,
    explanationMethod: factor.source_type || null,
  }));
}

function evidenceSensors(evidence: Evidence | null): OperationsSensorValue[] {
  if (!evidence) return [];
  if (
    String(evidence.observation.asset_type ?? "").toLowerCase() === "compressor"
  ) {
    return [
      {
        id: "voltage_raw",
        label: "전압 신호",
        value: evidence.observation.voltage_raw as number | null,
        unit: "raw",
      },
      {
        id: "rotation_raw",
        label: "회전 신호",
        value: evidence.observation.rotation_raw as number | null,
        unit: "raw",
      },
      {
        id: "pressure_raw",
        label: "압력 신호",
        value: evidence.observation.pressure_raw as number | null,
        unit: "raw",
      },
      {
        id: "vibration_raw",
        label: "진동 신호",
        value: evidence.observation.vibration_raw as number | null,
        unit: "raw",
      },
      {
        id: "relative_vibration_z",
        label: "상대 진동 Z-score",
        value: evidence.observation.relative_vibration_z as number | null,
        unit: "z",
      },
      {
        id: "relative_vibration_zone",
        label: "진동 Zone",
        value: evidence.observation.relative_vibration_zone as string | null,
        unit: null,
      },
    ];
  }
  const rows: OperationsSensorValue[] = [
    {
      id: "air_temperature_k",
      label: "공기 온도",
      value: evidence.observation.air_temperature_k,
      unit: "K",
    },
    {
      id: "process_temperature_k",
      label: "공정 온도",
      value: evidence.observation.process_temperature_k,
      unit: "K",
    },
    {
      id: "rotational_speed_rpm",
      label: "회전 속도",
      value: evidence.observation.rotational_speed_rpm,
      unit: "rpm",
    },
    {
      id: "torque_nm",
      label: "토크",
      value: evidence.observation.torque_nm,
      unit: "N·m",
    },
    {
      id: "tool_wear_min",
      label: "공구 마모",
      value: evidence.observation.tool_wear_min,
      unit: "분",
    },
    {
      id: "product_type",
      label: "제품 유형",
      value: evidence.observation.product_type,
      unit: null,
    },
  ];
  return rows;
}

function provenanceFromEvidence(
  event: OperationsEvent,
  evidence: Evidence | null,
): OperationsProvenance {
  return {
    datasetId: null,
    datasetVersionId:
      evidence?.lineage.dataset_version_id ?? event.datasetVersionId,
    datasetLabel: "Canonical V3.1",
    sourceVersion: evidence?.lineage.source_version ?? "Canonical V3.1",
    modelVersion: evidence?.model.model_version ?? null,
    policyVersion: evidence?.model.policy_version ?? null,
    schemaVersion: evidence?.lineage.schema_version ?? null,
    promptVersion: null,
    sourceRefs: evidence?.maintenance_context.source_refs ?? [],
  };
}

function provenanceFromAssetDetailViewModel(
  event: OperationsEvent,
  viewModel: AssetDetailViewModel,
): OperationsProvenance {
  return {
    datasetId: null,
    datasetVersionId:
      viewModel.evidence.dataset_version ?? event.datasetVersionId,
    datasetLabel: "Canonical V3.1",
    sourceVersion: viewModel.evidence.source_kind,
    modelVersion: viewModel.evidence.model_version,
    policyVersion: null,
    schemaVersion: null,
    promptVersion: null,
    sourceRefs: [
      ...(viewModel.evidence.artifact_id
        ? [`result-artifact://${viewModel.evidence.artifact_id}`]
        : []),
      ...viewModel.risk_series
        .map((point) => point.source_ref)
        .filter((value): value is string => Boolean(value)),
    ],
  };
}

function sensorsFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsSensorValue[] {
  return viewModel.features.map((feature) => ({
    id: feature.key,
    label: feature.label,
    value: feature.current.value,
    unit: feature.unit || null,
    observedAt: feature.current.observed_at,
    qualityStatus: feature.current.quality_status,
    historySourceRef: feature.history.source_ref ?? null,
    historyPointCount: feature.history.points.length,
    historyWindow: feature.history.window
      ? {
          requested: feature.history.window.requested,
          anchorObservedAt: feature.history.window.anchor_observed_at,
          requestedStart: feature.history.window.requested_start,
          requestedEnd: feature.history.window.requested_end,
          actualStart: feature.history.window.actual_start,
          actualEnd: feature.history.window.actual_end,
          pointCount: feature.history.window.point_count,
          coverageStatus: feature.history.window.coverage_status,
        }
      : null,
    historyPoints: feature.history.points.map((point) => ({
      observedAt: point.observed_at,
      value: point.value,
      qualityStatus: point.quality_status,
    })),
  }));
}

function riskSeriesFromAssetDetailViewModel(viewModel: AssetDetailViewModel) {
  return viewModel.risk_series.map((point) => ({
    observedAt: point.observed_at,
    failureProbability: point.failure_probability,
    status: point.status_grade,
  }));
}

function equipmentHistoryFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsEquipmentHistoryItem[] {
  return viewModel.equipment_history.map((item) => ({
    occurredAt: item.occurred_at,
    kind: item.kind,
    tone: item.tone,
    description: item.description,
    source: item.source,
    memo: item.memo ?? null,
  }));
}

function evidenceGapsFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsEvidenceGap[] {
  return viewModel.evidence.gaps.map((gap) => ({
    field: gap.field,
    reason: gap.reason,
    ownerDomain: gap.owner_domain,
  }));
}

function inspectionTargetsFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsInspectionTarget[] {
  return (viewModel.inspection_targets ?? []).map((target) => ({
    targetId: target.target_id,
    componentId: target.component_id,
    componentLabel: target.component_label,
    association: target.association,
    locationLabel: target.location_label,
    inspectionMethod: target.inspection_method,
    locationContractId: target.location_contract_id,
    locationSourceRef: target.location_source_ref,
    locationMaturity: target.location_maturity,
    inspectionGuidance: target.inspection_guidance
      ? {
          sourceType: target.inspection_guidance.source_type,
          sopId: target.inspection_guidance.sop_id,
          title: target.inspection_guidance.title,
          version: target.inspection_guidance.version,
          referenceLocationLabel:
            target.inspection_guidance.reference_location_label,
          suggestedCheckMethod:
            target.inspection_guidance.suggested_check_method,
          checklistDraft: target.inspection_guidance.checklist_draft,
          maintenanceReviewPrerequisites: {
            label:
              target.inspection_guidance.maintenance_review_prerequisites.label,
            reviewConditions:
              target.inspection_guidance.maintenance_review_prerequisites
                .review_conditions,
            requiredMeasurements:
              target.inspection_guidance.maintenance_review_prerequisites
                .required_measurements,
            humanReviewQuestions:
              target.inspection_guidance.maintenance_review_prerequisites
                .human_review_questions,
            decisionBoundary:
              target.inspection_guidance.maintenance_review_prerequisites
                .decision_boundary,
          },
          safetyLevel: target.inspection_guidance.safety_level,
          requiresHumanApproval:
            target.inspection_guidance.requires_human_approval,
          sourceRef: target.inspection_guidance.source_ref,
          disclaimer: target.inspection_guidance.disclaimer,
        }
      : null,
    basisRefs: target.basis_refs,
    sourceRef: target.source_ref,
    unavailableReason: target.unavailable_reason,
  }));
}

function factorsFromAssetDetailViewModel(
  viewModel: AssetDetailViewModel,
): OperationsFactor[] {
  return viewModel.features
    .filter((feature) => feature.top_factor !== null)
    .sort(
      (left, right) =>
        (left.top_factor?.rank ?? 999) - (right.top_factor?.rank ?? 999),
    )
    .map((feature) => ({
      id:
        feature.top_factor?.evidence_field_id ??
        `${feature.key}:${feature.top_factor?.rank ?? "factor"}`,
      feature: feature.key,
      label: feature.label,
      value: feature.current.value,
      unit: feature.unit || null,
      contribution: Math.abs(feature.top_factor?.contribution ?? 0),
      direction: feature.top_factor?.direction ?? "risk_up",
      explanationMethod: feature.top_factor?.explanation_method ?? null,
    }));
}

export function normalizeActivity(payload: unknown): OperationsActivityItem[] {
  const source =
    payload && typeof payload === "object"
      ? (payload as Record<string, unknown>)
      : {};
  const direct = Array.isArray(source.items)
    ? (source.items as Array<Record<string, unknown>>)
    : [];
  const decisions = Array.isArray(source.decisions)
    ? (source.decisions as Array<Record<string, unknown>>)
    : [];
  const notes = Array.isArray(source.notes)
    ? (source.notes as Array<Record<string, unknown>>)
    : [];
  const conversations = Array.isArray(source.conversations)
    ? (source.conversations as Array<Record<string, unknown>>)
    : [];
  const mapped: OperationsActivityItem[] = [];
  for (const row of direct) {
    mapped.push({
      id: String(row.id ?? crypto.randomUUID()),
      kind: String(row.activity_type ?? row.action ?? "system").includes(
        "decision",
      )
        ? "decision"
        : "system",
      title: String(row.summary ?? row.action ?? "업무 활동"),
      detail: String(row.detail ?? row.note ?? ""),
      actor: String(row.actor_display_name ?? row.actor ?? "시스템"),
      createdAt: String(row.created_at ?? new Date(0).toISOString()),
      decision: row.decision ? normalizeDecision(row.decision) : null,
    });
  }
  for (const row of decisions) {
    const decision = normalizeDecision(row.decision);
    mapped.push({
      id: String(row.id ?? crypto.randomUUID()),
      kind: "decision",
      title: decision,
      detail: String(row.note ?? ""),
      actor: String(row.actor ?? "사용자"),
      createdAt: String(row.created_at ?? new Date(0).toISOString()),
      decision,
    });
  }
  for (const row of notes) {
    mapped.push({
      id: String(row.id ?? crypto.randomUUID()),
      kind: "note",
      title: "현장 메모",
      detail: String(row.body ?? row.note ?? ""),
      actor: String(row.actor ?? "사용자"),
      createdAt: String(row.created_at ?? new Date(0).toISOString()),
      decision: null,
    });
  }
  for (const row of conversations) {
    mapped.push({
      id: String(row.id ?? crypto.randomUUID()),
      kind: "conversation",
      title: "후속 질의",
      detail: String(row.answer ?? row.question ?? ""),
      actor: String(row.actor ?? "사용자"),
      createdAt: String(row.created_at ?? new Date(0).toISOString()),
      decision: null,
    });
  }
  return mapped.sort((left, right) =>
    right.createdAt.localeCompare(left.createdAt),
  );
}

function reportMode(report: Report): OperationsReportModel["mode"] {
  const mode = report.mode.toLowerCase();
  if (mode.includes("llm") || mode.includes("grounded")) return "llm";
  return "deterministic-fallback";
}

export function adaptReport(
  report: Report,
  revision = 0,
): OperationsReportModel {
  return {
    reportId: report.report_id,
    reportType: report.report_type,
    snapshotId: null,
    artifactId: null,
    asOf: null,
    revision,
    mode: reportMode(report),
    headline: report.headline,
    summary: report.summary,
    sections: report.sections.map((section) => ({
      id: section.section_id,
      title: section.title,
      body: section.body,
      evidenceFieldIds: section.evidence_field_ids,
    })),
    actions: report.actions.map((action) => action.label),
    limitations: report.limitations,
    generatedAt: report.generated_at,
    promptVersion: null,
  };
}

export function buildTemplateReport(
  event: OperationsEvent,
  metrics?: OperationsMetrics,
): OperationsReportModel {
  const probability =
    event.failureProbability === null
      ? "예측 사용 불가"
      : `${Math.round(event.failureProbability * 100)}%`;
  const impact =
    event.estimatedDowntimeMinutes === null
      ? "영향 근거 부족"
      : `${event.estimatedDowntimeMinutes}분`;
  const qualityText =
    event.status === "data_quality_hold"
      ? "데이터 품질 문제로 판단을 보류하고 원천 데이터 확인이 필요합니다."
      : `현재 실패 위험은 ${probability}이며, 이는 고장 확정이 아닌 운영 우선순위 판단을 위한 모델 결과입니다.`;
  return {
    reportId: `template-${event.eventId}`,
    reportType: "operations-decision",
    snapshotId: `event:${event.eventId}`,
    artifactId: event.eventId,
    asOf: event.observedAt,
    revision: 0,
    mode: "template-fallback",
    headline: `${event.assetName} 생산 가치 보호 보고`,
    summary: `${event.line}의 ${event.assetName} 위험을 조기에 포착해 예상 정지 노출 ${impact}을 실제 생산 손실로 확정되기 전에 관리하는 Case입니다. 권장 판단은 ${event.recommendedDecision}이며, 현재 영향은 보호 대상 노출이지 확정된 비용 절감 실적이 아닙니다.`,
    sections: [
      {
        id: "executive-summary",
        title: "가치 기반 의사결정 요약",
        body: metrics
          ? `현재 ${metrics.totalAssets}개 설비 중 위험 ${metrics.critical}개, 경고 ${metrics.warning}개가 확인됐습니다. ${event.assetName}은 조기 대응을 통해 생산 연속성과 손실 노출을 보호해야 할 우선 Case입니다.`
          : `${event.assetName}은 조기 대응을 통해 생산 연속성과 손실 노출을 보호해야 할 우선 Case입니다.`,
        evidenceFieldIds: [
          "status",
          "failure_probability",
          "equipment.estimated_downtime_minutes",
        ],
      },
      {
        id: "risk-and-impact",
        title: "위험 · 보호 대상 가치",
        body: `${qualityText} 현재 생산 영향 ${impact}은 선제 대응이 보호하려는 운영 가치의 기준이며 실제 절감액은 후속 actual로 확정합니다.`,
        evidenceFieldIds: [
          "failure_probability",
          "confidence",
          "equipment.criticality",
        ],
      },
      {
        id: "response-status",
        title: "대응 현황",
        body: `${event.assignedEngineer ?? "미배정 담당자"} 기준으로 ${event.recommendedDecision} 검토가 필요합니다. review_shutdown은 실제 정지 명령이 아니라 권한자의 검토 요청입니다.`,
        evidenceFieldIds: [
          "recommended_decision",
          "equipment.assigned_engineer",
        ],
      },
    ],
    actions: [event.recommendedDecision],
    limitations: [
      "모델 확률은 실제 고장 발생을 확정하지 않습니다.",
      "미탐·오탐 비용 가정에 따라 운영 임계값은 달라질 수 있습니다.",
      "예상 정지·생산 노출은 보호 대상 가치이며 실제 비용 절감·KPI 기여 실적은 후속 운영 및 재무 actual로 확정합니다.",
    ],
    generatedAt: new Date().toISOString(),
    promptVersion: "operations-template-v1",
  };
}

export function composeEventDetail(input: {
  event: OperationsEvent;
  evidence: Evidence | null;
  report: Report | null;
  activity: unknown;
  metrics?: OperationsMetrics;
  reportRevision?: number;
  warnings?: string[];
}): OperationsEventDetailModel {
  const provenance = provenanceFromEvidence(input.event, input.evidence);
  const report = input.report
    ? adaptReport(input.report, input.reportRevision)
    : buildTemplateReport(input.event, input.metrics);
  report.snapshotId = report.snapshotId ?? `event:${input.event.eventId}`;
  report.artifactId = report.artifactId ?? input.event.eventId;
  report.asOf = report.asOf ?? input.event.observedAt;
  report.promptVersion =
    input.evidence?.lineage.prompt_version ?? report.promptVersion;
  provenance.promptVersion = report.promptVersion;
  return {
    snapshotBasis: null,
    event: input.event,
    sensors: evidenceSensors(input.evidence),
    topFactors: evidenceFactors(input.evidence),
    riskSeries: [],
    predictionHorizonHours: null,
    threshold: input.evidence?.threshold ?? null,
    assetCriticality: input.event.criticality,
    criticalityBasis: [],
    criticalitySource: "unknown",
    maintenanceContext: null,
    inspectionTargets: [],
    dataQualityWarnings: input.evidence?.data_quality_warnings ?? [],
    equipmentHistory: [],
    evidenceGaps: [],
    assetDetailStatus: null,
    operationContext: null,
    closedLoop: null,
    reviewPriority: null,
    activity: normalizeActivity(input.activity),
    report,
    provenance,
    loadedSources: {
      evidence: Boolean(input.evidence),
      report: Boolean(input.report),
      activity: Boolean(input.activity),
    },
    warnings: input.warnings ?? [],
  };
}

export function applyAssetDetailViewModel(
  detail: OperationsEventDetailModel,
  viewModel: AssetDetailViewModel,
): OperationsEventDetailModel {
  const warnings = [
    ...detail.warnings,
    ...viewModel.data_status.warnings,
    ...viewModel.evidence.gaps.map(
      (gap) => `${gap.owner_domain}: ${gap.field} - ${gap.reason}`,
    ),
  ];
  const snapshotBasis = snapshotBasisFromAssetDetailViewModel(viewModel);
  const operationContext = operationContextFromAssetDetailViewModel(viewModel);
  const report = {
    ...detail.report,
    snapshotId:
      operationContext?.temporalScope?.snapshotId ?? detail.report.snapshotId,
    artifactId: snapshotBasis.artifactId ?? detail.report.artifactId,
    asOf: snapshotBasis.observedAt ?? detail.report.asOf,
  };
  return {
    ...detail,
    snapshotBasis,
    sensors: sensorsFromAssetDetailViewModel(viewModel),
    topFactors: factorsFromAssetDetailViewModel(viewModel),
    riskSeries: riskSeriesFromAssetDetailViewModel(viewModel),
    predictionHorizonHours: viewModel.risk.prediction_horizon_hours,
    threshold: viewModel.risk.threshold,
    event: {
      ...detail.event,
      criticality: viewModel.asset.criticality,
    },
    assetCriticality: viewModel.asset.criticality,
    criticalityBasis: viewModel.asset.criticality_basis,
    criticalitySource: viewModel.asset.criticality_source,
    maintenanceContext: {
      lastMaintenanceDaysAgo:
        viewModel.maintenance_context.last_maintenance_days_ago,
      similarEvents30d: viewModel.maintenance_context.similar_events_30d,
      openWorkOrderExists: viewModel.maintenance_context.open_work_order_exists,
    },
    inspectionTargets: inspectionTargetsFromAssetDetailViewModel(viewModel),
    equipmentHistory: equipmentHistoryFromAssetDetailViewModel(viewModel),
    evidenceGaps: evidenceGapsFromAssetDetailViewModel(viewModel),
    assetDetailStatus: {
      isStale: viewModel.data_status.is_stale,
      isDataQualityHold: viewModel.data_status.is_data_quality_hold,
      lastUpdatedAt: viewModel.data_status.last_updated_at ?? null,
      source: viewModel.data_status.source,
    },
    operationContext,
    closedLoop: closedLoopFromAssetDetailViewModel(viewModel),
    reviewPriority: viewModel.review_priority
      ? {
          level: viewModel.review_priority.level,
          reasons: viewModel.review_priority.reasons,
          sourceFields: viewModel.review_priority.source_fields,
        }
      : null,
    provenance: {
      ...provenanceFromAssetDetailViewModel(detail.event, viewModel),
      promptVersion: detail.provenance.promptVersion,
    },
    report,
    loadedSources: {
      ...detail.loadedSources,
      evidence: true,
    },
    warnings: [...new Set(warnings)],
  };
}
