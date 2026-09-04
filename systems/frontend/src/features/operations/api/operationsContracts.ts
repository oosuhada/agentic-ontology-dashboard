export type OperationsDecisionBriefRole =
  | "process_manager"
  | "process_engineer"
  | "maintenance_technician"
  | "system_admin";

export interface OperationsDecisionSupportBrief {
  schema_version: string;
  frame: {
    evidence_snapshot_id: string;
    decision_as_of: string;
    actor_role: OperationsDecisionBriefRole;
    risk_status: string;
    asset_id: string;
    active_constraints: string[];
    context_version_set: Record<string, string>;
  };
  why_now: {
    order_ids: string[];
    wip_units: number | null;
    lot_ids: string[];
    earliest_due_at: string | null;
    decision_blockers: string[];
    source_refs: string[];
  };
  relationships: Array<{
    relationship_type: string;
    from_ref: string;
    to_ref: string;
    status: string;
    source_refs: string[];
  }>;
  readiness: Record<string, unknown>;
  option_comparison: Array<{
    option: string;
    calculation_state: string;
    assumptions: Record<string, unknown>;
    formula: string | null;
    source_refs: string[];
  }>;
  gaps: Array<{
    state: string;
    owner_domain: string;
    blocks_options: string[];
    detail: Record<string, unknown>;
  }>;
  source_classifications: Record<string, string>;
  source_refs: string[];
  limitations: string[];
  mutation_available: false;
  recommendation: null;
}

export interface OperationsDecisionSupportResponse {
  brief: OperationsDecisionSupportBrief | null;
  trace: {
    status: string;
    reason: string | null;
    reused: boolean;
    workflow_run_id: string | null;
    context_version_set: Record<string, string>;
    temporal_validation: string;
  };
}

export type OperationsView =
  "overview" | "objects" | "operations" | "reports" | "system";
export type OperationsDashboardMode = "workflow" | "classic";
export type OperationsReportTab =
  "status-map" | "inspection-request" | "summary-report" | "executive-brief";
export type OperationsRoleLens = "process_manager" | "field_operator";
export type OperationsRiskStatus =
  "normal" | "attention" | "warning" | "critical" | "data_quality_hold";
export type OperationsConfidence = "high" | "medium" | "low" | "unavailable";
export type OperationsCriticality = "low" | "medium" | "high" | null;
export type OperationsDecision =
  | "continue_monitoring"
  | "request_inspection"
  | "review_shutdown"
  | "hold_for_data_check";

export type OperationsSourceMode =
  "canonical-runtime" | "gold-fixture-fallback";
export type OperationsSensorWindowId = "1h" | "3h" | "6h" | "12h" | "24h" | "7d" | "30d";
export type OperationsSensorWindowCoverage =
  "complete" | "partial" | "empty" | "unknown";

export interface OperationsProvenance {
  datasetId: string | null;
  datasetVersionId: string;
  datasetLabel: string;
  sourceVersion: string | null;
  modelVersion: string | null;
  policyVersion: string | null;
  schemaVersion: string | null;
  promptVersion: string | null;
  sourceRefs: string[];
}

export interface OperationsEvidenceSnapshotBasis {
  artifactId: string | null;
  evidencePayloadReference: string;
  assetId: string | null;
  eventId: string | null;
  observedAt: string | null;
  modelVersion: string | null;
  datasetVersion: string | null;
  sourceSha256: string | null;
}

export interface EvidenceSnapshotBasisWire {
  artifact_id: string | null;
  evidence_payload_reference: string;
  asset_id: string | null;
  event_id: string | null;
  observed_at: string | null;
  model_version: string | null;
  dataset_version: string | null;
  source_sha256: string | null;
}

export interface OperationsFactor {
  id: string;
  feature: string;
  label: string;
  value: number | null;
  unit: string | null;
  contribution: number;
  direction: "risk_up" | "risk_down";
  explanationMethod: string | null;
}

export interface OperationsAsset {
  assetId: string;
  displayName: string;
  assetType: string;
  site: string;
  line: string;
  cell: string;
  status: OperationsRiskStatus;
  failureProbability: number | null;
  confidence: OperationsConfidence;
  confidenceScore: number | null;
  criticality: OperationsCriticality;
  assignedEngineer: string | null;
  estimatedDowntimeMinutes: number | null;
  sparePartAvailable: boolean | null;
  predictedFailureType: string;
  recommendedDecision: OperationsDecision;
  observedAt: string | null;
  eventId: string | null;
  topFactors: OperationsFactor[];
  provenance: OperationsProvenance;
}

export interface OperationsEvent {
  eventId: string;
  scenarioId: string;
  assetId: string;
  assetName: string;
  line: string;
  status: OperationsRiskStatus;
  failureProbability: number | null;
  confidence: OperationsConfidence;
  predictedFailureType: string;
  recommendedDecision: OperationsDecision;
  criticality: OperationsCriticality;
  assignedEngineer: string | null;
  estimatedDowntimeMinutes: number | null;
  sparePartAvailable: boolean | null;
  observedAt: string | null;
  datasetVersionId: string;
  ontologyObjectId: string | null;
}

export interface OperationsMetrics {
  totalAssets: number;
  normal: number;
  attention: number;
  warning: number;
  critical: number;
  dataQualityHold: number;
  averageRisk: number | null;
  estimatedDowntimeMinutes: number | null;
  pendingDecisions: number;
}

export interface OperationsLineRisk {
  line: string;
  total: number;
  normal: number;
  critical: number;
  warning: number;
  attention: number;
  dataQualityHold: number;
  averageRisk: number | null;
}

export interface OperationsContextModel {
  projectId: string;
  projectName: string;
  workspaceId: string;
  workspaceName: string;
  datasetVersionId: string;
  datasetLabel: string;
  sourceVersion: string | null;
  modelVersion: string | null;
  schemaVersion: string | null;
  sourceMode: OperationsSourceMode;
  sourceStatus: string;
  refreshedAt: string;
  observedAt: string | null;
  stale: boolean;
  warnings: string[];
}

export interface OperationsBootstrapModel {
  context: OperationsContextModel;
  assets: OperationsAsset[];
  events: OperationsEvent[];
  metrics: OperationsMetrics;
  lineRisk: OperationsLineRisk[];
  selectionRestoreError?: string | null;
}

export interface OperationsSensorValue {
  id: string;
  label: string;
  value: number | string | boolean | null;
  unit: string | null;
  observedAt?: string | null;
  qualityStatus?: "good" | "bad" | "unknown";
  historySourceRef?: string | null;
  historyPointCount?: number;
  historyWindow?: OperationsFeatureHistoryWindow | null;
  historyPoints?: OperationsFeatureHistoryPoint[];
}

export interface OperationsFeatureHistoryWindow {
  requested: OperationsSensorWindowId;
  anchorObservedAt: string | null;
  requestedStart: string | null;
  requestedEnd: string | null;
  actualStart: string | null;
  actualEnd: string | null;
  pointCount: number;
  coverageStatus: OperationsSensorWindowCoverage;
}

export interface OperationsFeatureHistoryPoint {
  observedAt: string;
  value: number | null;
  qualityStatus: "good" | "bad" | "unknown";
}

export interface OperationsRiskSeriesPoint {
  observedAt: string;
  failureProbability: number;
  status: "normal" | "attention" | "warning" | "critical" | null;
}

export interface OperationsActivityItem {
  id: string;
  kind: "decision" | "note" | "conversation" | "system";
  title: string;
  detail: string;
  actor: string;
  createdAt: string;
  decision: OperationsDecision | null;
}

export interface OperationsReportSection {
  id: string;
  title: string;
  body: string;
  evidenceFieldIds: string[];
}

export interface OperationsReportModel {
  reportId: string;
  reportType:
    | "inspection-summary"
    | "operations-decision"
    | "executive-brief"
    | "maintenance-effect"
    | "weekly-risk";
  snapshotId: string | null;
  artifactId: string | null;
  asOf: string | null;
  revision: number;
  mode: "llm" | "deterministic-fallback" | "template-fallback";
  headline: string;
  summary: string;
  sections: OperationsReportSection[];
  actions: string[];
  limitations: string[];
  generatedAt: string;
  promptVersion: string | null;
}

export interface OperationsEquipmentHistoryItem {
  occurredAt: string;
  kind: string;
  tone: "critical" | "warning" | "attention" | "normal" | "hold";
  description: string;
  source: string;
  memo: string | null;
}

export interface OperationsEvidenceGap {
  field: string;
  reason: string;
  ownerDomain: string;
}

export interface OperationsAssetDetailStatus {
  isStale: boolean | null;
  isDataQualityHold: boolean;
  lastUpdatedAt: string | null;
  source: "canonical" | "fallback";
}

export type OperationsProductionImpact =
  "none" | "low" | "medium" | "high" | null;
export type OperationsOperationSourceType = "capacity_model";
export type OperationsScreenPriority =
  | "none"
  | "monitor"
  | "shift_inspection"
  | "plan_at_risk"
  | "data_check_required";
export type OperationsImpactStatus =
  "not_applicable" | "estimated" | "withheld_data_quality_hold";

export interface OperationsOperationTemporalScope {
  snapshotId: string;
  timezone: string;
  validFrom: string;
  validTo: string;
  generatedAt: string;
}

export interface OperationsProductionPlan {
  planId: string;
  planDate: string;
  plannedUnits: number;
  productMix: Array<{ variant: string; share: number; plannedUnits: number }>;
}

export interface OperationsCapacityModel {
  activeAssetCount: number;
  plannedOperatingHours: number;
  oee: number;
  standardCycleMinutesPerUnit: number;
  assetUnitsPerHour: number;
  dailyCapacityUnits: number;
  basis: string;
}

export interface OperationsEventImpact {
  eventId: string;
  equipmentId: string;
  line: string;
  productVariant: string;
  screenPriority: OperationsScreenPriority;
  impactStatus: OperationsImpactStatus;
  estimatedLostUnits: number | null;
  basis: {
    estimatedDowntimeMinutes: number;
    assetUnitsPerHour: number;
    formula: string;
  };
}

export interface OperationsOperationContext {
  loadLevel: "low" | "normal" | "high" | null;
  runtimeHours7d: number | null;
  productionImpact: OperationsProductionImpact;
  contextId?: string;
  sourceType?: OperationsOperationSourceType;
  temporalScope?: OperationsOperationTemporalScope;
  productionPlan?: OperationsProductionPlan;
  capacityModel?: OperationsCapacityModel;
  eventImpact?: OperationsEventImpact | null;
  limitations?: string[];
}

export interface OperationsCompanyContext {
  schema_version: string;
  context_kind: string;
  context_storage?: {
    mode: "team_db_overlay" | "reference_bootstrap";
    persisted_record_count: number;
  };
  project_id: string;
  workspace_id: string;
  company: {
    id: string;
    name: string;
    english_name: string;
    industry: string;
    headquarters: string;
    fiscal_year: number;
    currency: string;
    operating_principle: string;
  };
  organization_units: Array<{
    id: string;
    name: string;
    parent_id: string | null;
    leader: string;
    responsibilities: string[];
    persona_roles: string[];
  }>;
  plants: Array<Record<string, unknown>>;
  products: Array<{
    id: string;
    variant: string;
    name: string;
    unit_sales_price_krw: number;
    unit_material_cost_krw: number;
    unit_contribution_margin_krw: number;
    daily_plan_units: number;
  }>;
  materials: Array<{
    id: string;
    name: string;
    category: string;
    unit_cost_krw: number;
    on_hand_quantity: number;
    reorder_point: number;
    lead_time_days: number;
    related_asset_ids: string[];
  }>;
  business_metrics: Array<{
    id: string;
    name: string;
    period: string;
    value: number;
    unit: string;
    source_label: string;
  }>;
  maintenance_records: Array<{
    id: string;
    asset_id: string;
    occurred_at: string;
    work_type: string;
    component: string;
    symptom: string;
    action: string;
    result: string;
    downtime_minutes: number;
    material_ids: string[];
    source_ref: string;
  }>;
  meeting_minutes: Array<{
    id: string;
    title: string;
    occurred_at: string;
    attendees: string[];
    summary: string;
    decision_ids: string[];
    source_ref: string;
  }>;
  decisions: Array<{
    id: string;
    title: string;
    decided_at: string;
    owner_org_unit_id: string;
    decision: string;
    related_asset_ids: string[];
    source_ref: string;
  }>;
}

export type OperationsClosedLoopWorkType = "inspection" | "maintenance";
export type OperationsClosedLoopWorkOrderStatus =
  | "requested"
  | "approved"
  | "in_progress"
  | "completed"
  | "blocked"
  | "failed"
  | "cancelled";
export type OperationsClosedLoopMaintenanceActionStatus =
  "planned" | "in_progress" | "completed" | "failed" | "cancelled";
export type OperationsClosedLoopRuntimeStatus =
  | "equipment_under_maintenance"
  | "warming_up"
  | "history_insufficient"
  | "ready"
  | "predicted"
  | null;
export type OperationsClosedLoopLifecycleStep =
  | "prediction"
  | "evidence"
  | "decision"
  | "inspection_requested"
  | "inspection_approved"
  | "inspection_in_progress"
  | "inspection_completed"
  | "recommendation_proposed"
  | "maintenance_requested"
  | "maintenance_approved"
  | "maintenance_in_progress"
  | "maintenance_completed"
  | "post_maintenance_observation_pending"
  | "ready_for_reprediction";

export interface OperationsClosedLoopAvailableAction {
  actionId: string;
  targetType:
    | "recommendation"
    | "work_order"
    | "maintenance_action"
    | "inspection_result"
    | "event";
  targetId: string | null;
  label?: string;
  disabledReason?: string | null;
}

export interface OperationsClosedLoopWorkOrder {
  workOrderId: string;
  workType: OperationsClosedLoopWorkType;
  status: OperationsClosedLoopWorkOrderStatus;
  assignedTo?: string | null;
  actorDisplayName?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface OperationsClosedLoopInspectionResult {
  inspectionResultId: string;
  workOrderId: string;
  outcome: string;
  recordedBy?: string | null;
  recordedAt?: string | null;
  createdAt?: string | null;
}

export interface OperationsClosedLoopMaintenanceAction {
  maintenanceActionId: string;
  workOrderId: string | null;
  status: OperationsClosedLoopMaintenanceActionStatus;
  actorDisplayName?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface OperationsClosedLoopMaintenanceEvent {
  maintenanceEventId: string;
  maintenanceActionId: string | null;
  workOrderId: string | null;
  completedAt: string | null;
  actorDisplayName?: string | null;
}

export interface OperationsClosedLoopActivity {
  activityId: string;
  activityType: string;
  workType?: OperationsClosedLoopWorkType | null;
  actorDisplayName?: string | null;
  beforeStatus?: string | null;
  afterStatus?: string | null;
  createdAt?: string | null;
  workOrderId?: string | null;
  maintenanceActionId?: string | null;
  maintenanceEventId?: string | null;
}

export interface OperationsClosedLoopLifecycleSummary {
  currentStep: OperationsClosedLoopLifecycleStep;
  currentStepLabel: string;
  completedSteps: OperationsClosedLoopLifecycleStep[];
  nextStep: OperationsClosedLoopLifecycleStep | null;
  source: "backend_closed_loop_policy";
}

export interface OperationsClosedLoopPrimaryAction extends OperationsClosedLoopAvailableAction {
  label: string;
  ownerRole:
    | "process_manager"
    | "process_engineer"
    | "maintenance_technician"
    | "unassigned";
  ownerLabel: string;
  requiresInput: boolean;
}

export interface OperationsClosedLoopTimelineItem {
  timelineId: string;
  eventType: string;
  label: string;
  status: "completed" | "pending" | "blocked" | "failed";
  actorDisplayName?: string | null;
  occurredAt?: string | null;
  targetType?: string | null;
  targetId?: string | null;
}

export interface OperationsClosedLoopSummary {
  workOrders: OperationsClosedLoopWorkOrder[];
  inspectionResults: OperationsClosedLoopInspectionResult[];
  maintenanceActions: OperationsClosedLoopMaintenanceAction[];
  maintenanceEvents: OperationsClosedLoopMaintenanceEvent[];
  activities: OperationsClosedLoopActivity[];
  availableActions: OperationsClosedLoopAvailableAction[];
  lifecycleSummary: OperationsClosedLoopLifecycleSummary | null;
  primaryAction: OperationsClosedLoopPrimaryAction | null;
  timeline: OperationsClosedLoopTimelineItem[];
  runtimeStatus: OperationsClosedLoopRuntimeStatus;
}

export interface OperationsInspectionGuidance {
  sourceType: "demo_sop_fixture" | "site_sop";
  sopId: string;
  title: string;
  version: string;
  referenceLocationLabel: string;
  suggestedCheckMethod: string;
  checklistDraft: string[];
  maintenanceReviewPrerequisites: {
    label: string;
    reviewConditions: string[];
    requiredMeasurements: string[];
    humanReviewQuestions: string[];
    decisionBoundary: string;
  };
  safetyLevel: "none" | "caution" | "permit_required" | "shutdown_controlled";
  requiresHumanApproval: boolean;
  sourceRef: string;
  disclaimer: string;
}

export interface OperationsInspectionTarget {
  targetId: string;
  componentId: string;
  componentLabel: string;
  association: string;
  locationLabel: string | null;
  inspectionMethod: string | null;
  locationContractId: string | null;
  locationSourceRef: string | null;
  locationMaturity: "fixture" | "draft" | "approved" | "retired" | null;
  inspectionGuidance: OperationsInspectionGuidance | null;
  basisRefs: string[];
  sourceRef: string;
  unavailableReason: string | null;
}

export interface OperationsAgentReviewPacket {
  schema_version: "agent-review-packet-v1.0";
  project_id: string;
  asset_id: string;
  asset_label: string;
  generated_at: string;
  snapshot_basis: EvidenceSnapshotBasisWire;
  risk_summary: {
    status_grade: "normal" | "attention" | "warning" | "critical" | null;
    failure_probability: number | null;
    prediction_horizon_hours: number | null;
  };
  review_priority: {
    level: "immediate" | "high" | "medium" | "low";
    reasons: string[];
    source_fields: string[];
  } | null;
  review_draft: {
    title: string;
    summary: string;
    priority_label: string;
    recommended_next_step: string;
    checklist: string[];
    history_summary: string[];
    evidence_gap_count: number;
    boundary_note: string;
  };
  sop_retrieval: {
    provider: "local_sop_metadata_retriever";
    query: {
      asset_type: string;
      failure_mode: string;
      factor_keys: string[];
      component_ids: string[];
      risk_grade: string;
      criticality: string;
      production_impact: string;
    };
    top_k: number;
    returned_count: number;
    mutation_allowed: false;
  };
  sop_guidance: Array<{
    target_id: string;
    component_id: string;
    component_label: string;
    location_label: string | null;
    inspection_method: string | null;
    location_source_ref: string | null;
    sop_id: string;
    source_type: "demo_sop_fixture" | "site_sop";
    maturity: "fixture" | "draft" | "approved" | "retired";
    checklist_draft: string[];
    replacement_review_guidance: {
      review_label: string;
      review_triggers: string[];
      required_measurements: string[];
      operator_review_items: string[];
      decision_boundary: string;
    };
    sensor_judgment: Record<string, unknown> | null;
    retrieval_score: number;
    matched_fields: string[];
    disclaimer: string;
    source_ref: string;
  }>;
  inspection_targets: Array<{
    target_id: string;
    component_id: string;
    component_label: string;
    association: string;
    location_label: string | null;
    inspection_method: string | null;
    location_source_ref: string | null;
    basis_refs: string[];
    source_ref: string;
    unavailable_reason: string | null;
  }>;
  operation_context_summary?: {
    production_impact: "none" | "low" | "medium" | "high" | null;
    estimated_downtime_minutes: number | null;
    estimated_lost_units: number | null;
    product_variant: string | null;
    basis: string;
    limitations: string[];
    source_ref: string | null;
  } | null;
  model_expression_context: {
    source_type: string;
    model_version: string | null;
    dataset_version: string | null;
    failure_probability: number | null;
    threshold: number | null;
    confidence_label: string | null;
    top_factors: Array<{
      rank: number;
      feature: string;
      display_name: string;
      value: number | string | boolean | null;
      unit: string;
      contribution: number | null;
      direction: "positive" | "negative" | "risk_up" | "risk_down" | string;
      explanation_method: string;
      source_ref: string;
    }>;
    source_refs: string[];
  };
  maintenance_history_summary: {
    provider: string;
    mutation_allowed: false;
    open_work_order_exists: boolean | null;
    similar_events_30d: number | null;
    work_orders: Array<Record<string, unknown>>;
    inspection_results: Array<Record<string, unknown>>;
    maintenance_actions: Array<Record<string, unknown>>;
    maintenance_events: Array<Record<string, unknown>>;
    activities: Array<Record<string, unknown>>;
    equipment_history: Array<Record<string, unknown>>;
    similar_events: Array<Record<string, unknown>>;
    source_refs: string[];
  };
  ontology_context: {
    provider: string;
    mutation_allowed: false;
    traversals: Array<{
      component_id: string;
      component_label: string;
      factor_refs: string[];
      location_label: string | null;
      location_source_ref: string | null;
      sop_ids: string[];
      spare_parts: Array<{
        part_id: string;
        part_label: string;
        replacement_scope: string;
        availability:
          "available_from_fixture" | "unavailable_from_fixture" | "unknown";
        lead_time_days: number | null;
        replacement_window_minutes: number | null;
        assumption_level: string;
        source_ref: string;
      }>;
      similar_events: Array<{
        similar_event_id: string;
        asset_label: string;
        observed_at: string;
        matched_factor_keys: string[];
        action_taken: string;
        outcome: string;
        post_action_observation_window_hours: number | null;
        assumption_level: string;
        source_ref: string;
      }>;
      source_refs: string[];
    }>;
    source_refs: string[];
  };
  history_review_items: string[];
  evidence_gaps: Array<{ field: string; reason: string; owner_domain: string }>;
  source_refs: string[];
  closed_loop_boundary: {
    mutation_allowed: false;
    available_action_ids: string[];
    forbidden_actions: string[];
    note: string;
  };
  limitations: string[];
}

export interface OperationsAgentReviewSummary {
  schema_version: "agent-review-summary-v1.0";
  packet_schema_version: "agent-review-packet-v1.0";
  asset_id: string;
  generated_at: string;
  mode: "llm" | "deterministic_fallback";
  title: string;
  summary: string;
  role_summaries: Array<{
    role: "field_operator" | "process_manager";
    label: string;
    quote: string;
    source_refs: string[];
  }>;
  history_summary: string[];
  inspection_focus: Array<{
    component_id: string;
    component_label: string;
    location_label: string | null;
    basis_refs: string[];
    source_refs: string[];
  }>;
  evidence_gaps: Array<{ field: string; reason: string; owner_domain: string }>;
  data_footnotes: Array<{
    code: string;
    note: string;
    owner_domain: string;
    source_refs: string[];
  }>;
  source_refs: string[];
  boundary_note: string;
  confidence_label: "grounded" | "partial" | "fallback" | "data_quality_hold";
  limitations: string[];
}

export interface OperationsAgentReviewSummaryResponse {
  summary: OperationsAgentReviewSummary | null;
  trace: {
    provider: string;
    fallback: boolean;
    reason: string | null;
    validation_errors: string[];
    fallback_validation_errors?: string[];
    materialization?: {
      summary_id: string | null;
      summary_key: string;
      workflow_run_id: string | null;
      status: "ready" | "fallback" | "failed" | "stale" | "pending";
      reused: boolean;
      source_sha256: string;
      context_sha256: string | null;
      prompt_version: string;
      model_version: string;
      generated_at: string | null;
      created_at: string | null;
      updated_at: string | null;
      fallback_reason?: string | null;
    };
    workflow_run?: {
      workflow_run_id: string;
      trigger: string;
      engine: string;
      status: "running" | "completed" | "partial" | "failed";
      started_at: string;
      completed_at: string | null;
      updated_at: string;
      summary_key: string;
      source_sha256: string;
      context_sha256: string;
      error_type: string | null;
      error_message: string | null;
    };
  };
}

export interface OperationsAgentReviewWorkflowRun {
  workflow_run_id: string;
  trigger: string;
  engine: string;
  status: "running" | "completed" | "partial" | "failed";
  started_at: string;
  completed_at: string | null;
  updated_at: string;
  asset_id: string | null;
  event_id: string | null;
  dataset_version_id: string | null;
  history_window: string | null;
  summary_key: string;
  source_sha256: string;
  context_sha256: string;
  error_type: string | null;
  error_message: string | null;
  trace: {
    stage?: string;
    materialization?: Record<string, unknown>;
    provider?: string | null;
    fallback?: boolean | null;
    reason?: string | null;
    validation_errors?: string[];
  };
}

export interface OperationsAgentReviewWorkflowRunsResponse {
  project_id: string;
  workspace_id: string;
  items: OperationsAgentReviewWorkflowRun[];
}

export interface OperationsEventDetailModel {
  snapshotBasis: OperationsEvidenceSnapshotBasis | null;
  event: OperationsEvent;
  sensors: OperationsSensorValue[];
  topFactors: OperationsFactor[];
  riskSeries: OperationsRiskSeriesPoint[];
  predictionHorizonHours: number | null;
  threshold: number | null;
  assetCriticality: OperationsCriticality;
  criticalityBasis: string[];
  criticalitySource:
    | "manual_initial_assessment"
    | "equipment_master"
    | "project_context"
    | "unknown";
  maintenanceContext: {
    lastMaintenanceDaysAgo: number | null;
    similarEvents30d: number | null;
    openWorkOrderExists: boolean | null;
  } | null;
  inspectionTargets: OperationsInspectionTarget[];
  dataQualityWarnings: Array<{
    code: string;
    field: string;
    message: string;
    severity: string;
  }>;
  equipmentHistory: OperationsEquipmentHistoryItem[];
  evidenceGaps: OperationsEvidenceGap[];
  assetDetailStatus: OperationsAssetDetailStatus | null;
  operationContext: OperationsOperationContext | null;
  closedLoop: OperationsClosedLoopSummary | null;
  reviewPriority: {
    level: "immediate" | "high" | "medium" | "low";
    reasons: string[];
    sourceFields: string[];
  } | null;
  activity: OperationsActivityItem[];
  report: OperationsReportModel;
  provenance: OperationsProvenance;
  loadedSources: {
    evidence: boolean;
    report: boolean;
    activity: boolean;
  };
  warnings: string[];
}

export interface AssetDetailViewModel {
  snapshot_basis: EvidenceSnapshotBasisWire;
  asset: {
    asset_id: string;
    asset_type: "compressor" | "cnc";
    display_name?: string;
    site_id?: string;
    cell_id?: string;
    observed_at: string;
    criticality: OperationsCriticality;
    criticality_basis: string[];
    criticality_source:
      | "manual_initial_assessment"
      | "equipment_master"
      | "project_context"
      | "unknown";
  };
  risk: {
    current: number | null;
    threshold: number | null;
    status_grade: "normal" | "attention" | "warning" | "critical" | null;
    prediction_horizon_hours: number | null;
  };
  risk_series: Array<{
    observed_at: string;
    failure_probability: number;
    status_grade: "normal" | "attention" | "warning" | "critical" | null;
    prediction_id: string;
    source_kind: "runtime_inference" | "compatibility_fallback";
    source_ref?: string;
  }>;
  features: Array<{
    key: string;
    label: string;
    unit: string;
    current: {
      observed_at: string;
      value: number | null;
      quality_status: "good" | "bad" | "unknown";
    };
    history: {
      source_ref?: string;
      window?: {
        requested: OperationsSensorWindowId;
        anchor_observed_at: string | null;
        requested_start: string | null;
        requested_end: string | null;
        actual_start: string | null;
        actual_end: string | null;
        point_count: number;
        coverage_status: OperationsSensorWindowCoverage;
      };
      points: Array<{
        observed_at: string;
        value: number | null;
        quality_status: "good" | "bad" | "unknown";
      }>;
    };
    top_factor: {
      rank: number;
      contribution: number;
      direction: "risk_up" | "risk_down";
      explanation_method: string;
      evidence_field_id?: string;
    } | null;
  }>;
  equipment_history: Array<{
    occurred_at: string;
    kind: string;
    tone: "critical" | "warning" | "attention" | "normal" | "hold";
    description: string;
    source: string;
    memo?: string;
  }>;
  maintenance_context: {
    last_maintenance_days_ago: number | null;
    similar_events_30d: number | null;
    open_work_order_exists: boolean | null;
  };
  inspection_targets?: Array<{
    target_id: string;
    component_id: string;
    component_label: string;
    association: string;
    location_label: string | null;
    inspection_method: string | null;
    location_contract_id: string | null;
    location_source_ref: string | null;
    location_maturity: "fixture" | "draft" | "approved" | "retired" | null;
    inspection_guidance?: {
      source_type: "demo_sop_fixture" | "site_sop";
      sop_id: string;
      title: string;
      version: string;
      reference_location_label: string;
      suggested_check_method: string;
      checklist_draft: string[];
      maintenance_review_prerequisites: {
        label: string;
        review_conditions: string[];
        required_measurements: string[];
        human_review_questions: string[];
        decision_boundary: string;
      };
      safety_level:
        "none" | "caution" | "permit_required" | "shutdown_controlled";
      requires_human_approval: boolean;
      source_ref: string;
      disclaimer: string;
    };
    basis_refs: string[];
    source_ref: string;
    unavailable_reason: string | null;
  }>;
  operation_context: {
    load_level: "low" | "normal" | "high" | null;
    runtime_hours_7d: number | null;
    production_impact: OperationsProductionImpact;
    context_id?: string;
    source_type?: OperationsOperationSourceType;
    temporal_scope?: {
      snapshot_id: string;
      timezone: string;
      valid_from: string;
      valid_to: string;
      generated_at: string;
    };
    production_plan?: {
      plan_id: string;
      plan_date: string;
      planned_units: number;
      product_mix: Array<{
        variant: string;
        share: number;
        planned_units: number;
      }>;
    };
    capacity_model?: {
      active_asset_count: number;
      planned_operating_hours: number;
      oee: number;
      standard_cycle_minutes_per_unit: number;
      asset_units_per_hour: number;
      daily_capacity_units: number;
      basis: string;
    };
    event_impact?: {
      event_id: string;
      equipment_id: string;
      line: string;
      product_variant: string;
      screen_priority: OperationsScreenPriority;
      impact_status: OperationsImpactStatus;
      estimated_lost_units: number | null;
      basis: {
        estimated_downtime_minutes: number;
        asset_units_per_hour: number;
        formula: string;
      };
    } | null;
    limitations?: string[];
  };
  closed_loop?: {
    work_orders?: Array<{
      work_order_id: string;
      work_type: OperationsClosedLoopWorkType;
      status: OperationsClosedLoopWorkOrderStatus;
      assigned_to?: string | null;
      actor_display_name?: string | null;
      created_at?: string | null;
      updated_at?: string | null;
    }>;
    maintenance_actions?: Array<{
      maintenance_action_id: string;
      work_order_id?: string | null;
      status: OperationsClosedLoopMaintenanceActionStatus;
      actor_display_name?: string | null;
      started_at?: string | null;
      completed_at?: string | null;
    }>;
    maintenance_events?: Array<{
      maintenance_event_id: string;
      maintenance_action_id?: string | null;
      work_order_id?: string | null;
      completed_at?: string | null;
      actor_display_name?: string | null;
    }>;
    activities?: Array<{
      activity_id: string;
      activity_type: string;
      work_type?: OperationsClosedLoopWorkType | null;
      actor_display_name?: string | null;
      before_status?: string | null;
      after_status?: string | null;
      created_at?: string | null;
      work_order_id?: string | null;
      maintenance_action_id?: string | null;
      maintenance_event_id?: string | null;
    }>;
    inspection_results?: Array<{
      inspection_result_id: string;
      work_order_id: string;
      outcome: string;
      recorded_by?: string | null;
      recorded_at?: string | null;
      created_at?: string | null;
    }>;
    available_actions?: Array<{
      action_id: string;
      target_type:
        | "recommendation"
        | "work_order"
        | "maintenance_action"
        | "inspection_result"
        | "event";
      target_id?: string | null;
      label?: string;
      disabled_reason?: string | null;
    }>;
    lifecycle_summary?: {
      current_step: OperationsClosedLoopLifecycleStep;
      current_step_label: string;
      completed_steps: OperationsClosedLoopLifecycleStep[];
      next_step?: OperationsClosedLoopLifecycleStep | null;
      source: "backend_closed_loop_policy";
    } | null;
    primary_action?: {
      action_id: string;
      target_type:
        | "recommendation"
        | "work_order"
        | "maintenance_action"
        | "inspection_result"
        | "event";
      target_id?: string | null;
      label: string;
      owner_role:
        | "process_manager"
        | "process_engineer"
        | "maintenance_technician"
        | "unassigned";
      owner_label: string;
      disabled_reason?: string | null;
      requires_input: boolean;
    } | null;
    timeline?: Array<{
      timeline_id: string;
      event_type: string;
      label: string;
      status: "completed" | "pending" | "blocked" | "failed";
      actor_display_name?: string | null;
      occurred_at?: string | null;
      target_type?: string | null;
      target_id?: string | null;
    }>;
    runtime_status?: OperationsClosedLoopRuntimeStatus;
  } | null;
  review_priority: {
    level: "immediate" | "high" | "medium" | "low";
    reasons: string[];
    source_fields: string[];
  } | null;
  evidence: {
    artifact_id: string | null;
    model_version: string | null;
    dataset_version: string | null;
    source_kind: "runtime_inference" | "compatibility_fallback";
    gaps: Array<{ field: string; reason: string; owner_domain: string }>;
  };
  data_status: {
    source: "canonical" | "fallback";
    is_stale: boolean | null;
    is_data_quality_hold: boolean;
    last_updated_at?: string;
    warnings: string[];
  };
}

export interface OperationsSelection {
  view: OperationsView;
  surface: string | null;
  dashboard: OperationsDashboardMode;
  reportTab: OperationsReportTab;
  projectId: string;
  workspaceId: string | null;
  assetId: string | null;
  eventId: string | null;
  role: OperationsRoleLens;
}
