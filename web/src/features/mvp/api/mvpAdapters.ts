import type { Evidence, EventSummary, Report } from "../../../types";
import type { GovernedProductResultSummary } from "../../predictive-maintenance/types";
import type {
  MvpActivityItem,
  MvpAsset,
  MvpConfidence,
  MvpDecision,
  MvpEvent,
  MvpEventDetailModel,
  MvpFactor,
  MvpLineRisk,
  MvpMetrics,
  MvpProvenance,
  MvpReportModel,
  MvpRiskStatus,
  MvpSensorValue,
} from "./mvpContracts";

const STATUS_PRIORITY: Record<MvpRiskStatus, number> = {
  critical: 5,
  warning: 4,
  attention: 3,
  data_quality_hold: 2,
  normal: 1,
};

export function normalizeRiskStatus(value: unknown, probability?: number | null): MvpRiskStatus {
  const status = String(value ?? "").toLowerCase();
  if (status === "critical" || status === "danger") return "critical";
  if (status === "warning" || status === "warn") return "warning";
  if (status === "attention" || status === "caution") return "attention";
  if (status === "data_quality_hold" || status === "quality_hold" || status === "blocked") return "data_quality_hold";
  if (status === "normal" || status === "healthy" || status === "ok") return "normal";
  if (probability === null || probability === undefined) return "data_quality_hold";
  if (probability >= 0.85) return "critical";
  if (probability >= 0.6) return "warning";
  if (probability >= 0.35) return "attention";
  return "normal";
}

export function normalizeConfidence(value: unknown): { level: MvpConfidence; score: number | null } {
  if (typeof value === "number" && Number.isFinite(value)) {
    if (value >= 0.8) return { level: "high", score: value };
    if (value >= 0.6) return { level: "medium", score: value };
    return { level: "low", score: value };
  }
  const normalized = String(value ?? "").toLowerCase();
  if (["high", "높음"].includes(normalized)) return { level: "high", score: null };
  if (["medium", "moderate", "중간"].includes(normalized)) return { level: "medium", score: null };
  if (["low", "낮음"].includes(normalized)) return { level: "low", score: null };
  return { level: "unavailable", score: null };
}

export function normalizeDecision(value: unknown): MvpDecision {
  const decision = String(value ?? "").toLowerCase();
  if (decision === "continue_monitoring") return "continue_monitoring";
  if (decision === "request_inspection") return "request_inspection";
  if (decision === "review_shutdown") return "review_shutdown";
  if (decision === "hold_for_data_check") return "hold_for_data_check";
  if (decision.includes("data") || decision.includes("quality") || decision.includes("hold")) return "hold_for_data_check";
  if (decision.includes("stop") || decision.includes("shutdown")) return "review_shutdown";
  if (decision.includes("inspect") || decision.includes("check")) return "request_inspection";
  return "continue_monitoring";
}

export function sortRisk<T extends { status: MvpRiskStatus; failureProbability: number | null; criticality: "low" | "medium" | "high"; observedAt?: string | null }>(items: T[]): T[] {
  const criticality = { high: 3, medium: 2, low: 1 } as const;
  return [...items].sort((left, right) => (
    STATUS_PRIORITY[right.status] - STATUS_PRIORITY[left.status]
    || (right.failureProbability ?? -1) - (left.failureProbability ?? -1)
    || criticality[right.criticality] - criticality[left.criticality]
    || String(right.observedAt ?? "").localeCompare(String(left.observedAt ?? ""))
  ));
}

function fallbackProvenance(datasetVersionId: string): MvpProvenance {
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
export function adaptEvent(event: EventSummary): MvpEvent {
  const status = normalizeRiskStatus(event.status, event.failure_probability);
  return {
    eventId: event.event_id,
    scenarioId: event.scenario_id,
    assetId: event.equipment.equipment_id,
    assetName: event.equipment.display_name,
    line: event.equipment.line || "미지정 라인",
    status,
    failureProbability: status === "data_quality_hold" ? null : event.failure_probability,
    confidence: normalizeConfidence(event.confidence).level,
    predictedFailureType: event.predicted_failure_type || "unavailable",
    recommendedDecision: status === "data_quality_hold"
      ? "hold_for_data_check"
      : normalizeDecision(event.recommended_decision),
    criticality: event.equipment.criticality,
    assignedEngineer: event.equipment.assigned_engineer || null,
    estimatedDowntimeMinutes: event.equipment.estimated_downtime_minutes ?? 0,
    sparePartAvailable: event.equipment.spare_part_available ?? null,
    observedAt: event.observed_at ?? null,
    datasetVersionId: event.dataset_version_id ?? "dsv-canonical-v3-1",
    ontologyObjectId: event.ontology_object_id ?? null,
  };
}

function eventAsset(event: MvpEvent): MvpAsset {
  return {
    assetId: event.assetId,
    displayName: event.assetName,
    assetType: event.assetId.toLowerCase().includes("cnc") || event.assetId.startsWith("M-") ? "cnc" : "equipment",
    site: "Manufacturing Demo",
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

function adaptResultFactor(item: GovernedProductResultSummary["top_factors"][number]): MvpFactor {
  return {
    id: `${item.feature}:${item.rank}`,
    feature: item.feature,
    label: item.feature.replaceAll("_", " "),
    value: item.feature_value,
    unit: null,
    contribution: Math.abs(item.signed_contribution),
    direction: item.direction,
    explanationMethod: item.explanation_method,
  };
}

export function mergeAssets(results: GovernedProductResultSummary[], events: MvpEvent[]): MvpAsset[] {
  const byAsset = new Map(events.map((event) => [event.assetId, event]));
  const latestResultByAsset = new Map<string, GovernedProductResultSummary>();
  for (const result of results) {
    const current = latestResultByAsset.get(result.asset_id);
    if (!current || result.observed_at.localeCompare(current.observed_at) > 0) {
      latestResultByAsset.set(result.asset_id, result);
    }
  }
  const assets = [...latestResultByAsset.values()].map((result): MvpAsset => {
    const related = byAsset.get(result.asset_id);
    const confidence = normalizeConfidence(result.confidence);
    const status = normalizeRiskStatus(result.status_grade, result.failure_probability);
    return {
      assetId: result.asset_id,
      displayName: related?.assetName ?? result.asset_id,
      assetType: result.asset_type,
      site: result.site_id,
      line: related?.line ?? result.site_id,
      cell: result.cell_id,
      status,
      failureProbability: result.failure_probability,
      confidence: confidence.level,
      confidenceScore: confidence.score,
      criticality: related?.criticality ?? (status === "critical" ? "high" : "medium"),
      assignedEngineer: related?.assignedEngineer ?? null,
      estimatedDowntimeMinutes: related?.estimatedDowntimeMinutes ?? 0,
      sparePartAvailable: related?.sparePartAvailable ?? null,
      predictedFailureType: result.predicted_failure_type,
      recommendedDecision: related?.recommendedDecision ?? normalizeDecision(result.recommended_action?.action),
      observedAt: result.observed_at,
      eventId: related?.eventId ?? null,
      topFactors: result.top_factors.map(adaptResultFactor),
      provenance: {
        datasetId: result.provenance.dataset_id,
        datasetVersionId: result.provenance.dataset_version_id,
        datasetLabel: "Canonical V3.1",
        sourceVersion: result.provenance.source_version,
        modelVersion: result.provenance.model_version,
        policyVersion: null,
        schemaVersion: result.provenance.schema_version,
        promptVersion: null,
        sourceRefs: result.artifact_id ? [`result-artifact://${result.artifact_id}`] : [],
      },
    };
  });
  const seen = new Set(assets.map((asset) => asset.assetId));
  for (const event of events) {
    if (!seen.has(event.assetId)) {
      assets.push(eventAsset(event));
      seen.add(event.assetId);
    }
  }
  return sortRisk(assets);
}

export function computeMetrics(assets: MvpAsset[], events: MvpEvent[]): MvpMetrics {
  const probabilities = assets
    .map((asset) => asset.failureProbability)
    .filter((value): value is number => value !== null);
  const counts = {
    normal: assets.filter((asset) => asset.status === "normal").length,
    attention: assets.filter((asset) => asset.status === "attention").length,
    warning: assets.filter((asset) => asset.status === "warning").length,
    critical: assets.filter((asset) => asset.status === "critical").length,
    dataQualityHold: assets.filter((asset) => asset.status === "data_quality_hold").length,
  };
  return {
    totalAssets: assets.length,
    ...counts,
    averageRisk: probabilities.length ? probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length : null,
    estimatedDowntimeMinutes: events.reduce((sum, event) => sum + event.estimatedDowntimeMinutes, 0),
    pendingDecisions: events.filter((event) => event.recommendedDecision !== "continue_monitoring").length,
  };
}

export function computeLineRisk(assets: MvpAsset[]): MvpLineRisk[] {
  const grouped = new Map<string, MvpAsset[]>();
  for (const asset of assets) {
    const rows = grouped.get(asset.line) ?? [];
    rows.push(asset);
    grouped.set(asset.line, rows);
  }
  return [...grouped.entries()].map(([line, rows]) => {
    const probabilities = rows.map((row) => row.failureProbability).filter((value): value is number => value !== null);
    return {
      line,
      total: rows.length,
      critical: rows.filter((row) => row.status === "critical").length,
      warning: rows.filter((row) => row.status === "warning").length,
      attention: rows.filter((row) => row.status === "attention").length,
      dataQualityHold: rows.filter((row) => row.status === "data_quality_hold").length,
      averageRisk: probabilities.length ? probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length : null,
    };
  }).sort((left, right) => (
    right.critical - left.critical
    || right.warning - left.warning
    || (right.averageRisk ?? -1) - (left.averageRisk ?? -1)
  ));
}

function evidenceFactors(evidence: Evidence | null): MvpFactor[] {
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

function evidenceSensors(evidence: Evidence | null): MvpSensorValue[] {
  if (!evidence) return [];
  const rows: MvpSensorValue[] = [
    { id: "air_temperature_k", label: "공기 온도", value: evidence.observation.air_temperature_k, unit: "K" },
    { id: "process_temperature_k", label: "공정 온도", value: evidence.observation.process_temperature_k, unit: "K" },
    { id: "rotational_speed_rpm", label: "회전 속도", value: evidence.observation.rotational_speed_rpm, unit: "rpm" },
    { id: "torque_nm", label: "토크", value: evidence.observation.torque_nm, unit: "N·m" },
    { id: "tool_wear_min", label: "공구 마모", value: evidence.observation.tool_wear_min, unit: "분" },
    { id: "product_type", label: "제품 유형", value: evidence.observation.product_type, unit: null },
  ];
  return rows;
}

function provenanceFromEvidence(event: MvpEvent, evidence: Evidence | null): MvpProvenance {
  return {
    datasetId: null,
    datasetVersionId: evidence?.lineage.dataset_version_id ?? event.datasetVersionId,
    datasetLabel: "Canonical V3.1",
    sourceVersion: evidence?.lineage.source_version ?? "Canonical V3.1",
    modelVersion: evidence?.model.model_version ?? null,
    policyVersion: evidence?.model.policy_version ?? null,
    schemaVersion: evidence?.lineage.schema_version ?? null,
    promptVersion: null,
    sourceRefs: evidence?.maintenance_context.source_refs ?? [],
  };
}

export function normalizeActivity(payload: unknown): MvpActivityItem[] {
  const source = payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
  const direct = Array.isArray(source.items) ? source.items as Array<Record<string, unknown>> : [];
  const decisions = Array.isArray(source.decisions) ? source.decisions as Array<Record<string, unknown>> : [];
  const notes = Array.isArray(source.notes) ? source.notes as Array<Record<string, unknown>> : [];
  const conversations = Array.isArray(source.conversations) ? source.conversations as Array<Record<string, unknown>> : [];
  const mapped: MvpActivityItem[] = [];
  for (const row of direct) {
    mapped.push({
      id: String(row.id ?? crypto.randomUUID()),
      kind: String(row.activity_type ?? row.action ?? "system").includes("decision") ? "decision" : "system",
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
  return mapped.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

function reportMode(report: Report): MvpReportModel["mode"] {
  const mode = report.mode.toLowerCase();
  if (mode.includes("llm") || mode.includes("grounded")) return "llm";
  return "deterministic-fallback";
}

export function adaptReport(report: Report, revision = 0): MvpReportModel {
  return {
    reportId: report.report_id,
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

export function buildTemplateReport(event: MvpEvent, metrics?: MvpMetrics): MvpReportModel {
  const probability = event.failureProbability === null ? "예측 사용 불가" : `${Math.round(event.failureProbability * 100)}%`;
  const qualityText = event.status === "data_quality_hold"
    ? "데이터 품질 문제로 판단을 보류하고 원천 데이터 확인이 필요합니다."
    : `현재 실패 위험은 ${probability}이며, 이는 고장 확정이 아닌 운영 우선순위 판단을 위한 모델 결과입니다.`;
  return {
    reportId: `template-${event.eventId}`,
    revision: 0,
    mode: "template-fallback",
    headline: `${event.assetName} 설비 위험 대응 보고`,
    summary: `${event.line}의 ${event.assetName}을 우선 검토 중입니다. 권장 판단은 ${event.recommendedDecision}이며 예상 생산 영향은 ${event.estimatedDowntimeMinutes}분입니다.`,
    sections: [
      {
        id: "executive-summary",
        title: "임원 의사결정 요약",
        body: metrics
          ? `현재 ${metrics.totalAssets}개 설비 중 위험 ${metrics.critical}개, 경고 ${metrics.warning}개가 확인됐습니다. ${event.assetName}을 우선 대응 대상으로 관리합니다.`
          : `${event.assetName}을 우선 대응 대상으로 관리합니다.`,
        evidenceFieldIds: ["status", "failure_probability", "equipment.estimated_downtime_minutes"],
      },
      {
        id: "risk-and-impact",
        title: "위험과 생산 영향",
        body: qualityText,
        evidenceFieldIds: ["failure_probability", "confidence", "equipment.criticality"],
      },
      {
        id: "response-status",
        title: "대응 현황",
        body: `${event.assignedEngineer ?? "미배정 담당자"} 기준으로 ${event.recommendedDecision} 검토가 필요합니다. review_shutdown은 실제 정지 명령이 아니라 권한자의 검토 요청입니다.`,
        evidenceFieldIds: ["recommended_decision", "equipment.assigned_engineer"],
      },
    ],
    actions: [event.recommendedDecision],
    limitations: [
      "모델 확률은 실제 고장 발생을 확정하지 않습니다.",
      "미탐·오탐 비용 가정에 따라 운영 임계값은 달라질 수 있습니다.",
    ],
    generatedAt: new Date().toISOString(),
    promptVersion: "mvp-template-v1",
  };
}

export function composeEventDetail(input: {
  event: MvpEvent;
  evidence: Evidence | null;
  report: Report | null;
  activity: unknown;
  metrics?: MvpMetrics;
  reportRevision?: number;
  warnings?: string[];
}): MvpEventDetailModel {
  const provenance = provenanceFromEvidence(input.event, input.evidence);
  const report = input.report
    ? adaptReport(input.report, input.reportRevision)
    : buildTemplateReport(input.event, input.metrics);
  report.promptVersion = input.evidence?.lineage.prompt_version ?? report.promptVersion;
  provenance.promptVersion = report.promptVersion;
  return {
    event: input.event,
    sensors: evidenceSensors(input.evidence),
    topFactors: evidenceFactors(input.evidence),
    threshold: input.evidence?.threshold ?? null,
    dataQualityWarnings: input.evidence?.data_quality_warnings ?? [],
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
