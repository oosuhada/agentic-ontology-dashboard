export type Role = "manager" | "engineer";
export type Intent =
  | "overview"
  | "explain-risk"
  | "compare"
  | "summarize-manager"
  | "detail-engineer"
  | "recommend-check"
  | "show-model-details";

export interface Equipment {
  equipment_id: string;
  display_name: string;
  line: string;
  criticality: "low" | "medium" | "high";
  assigned_engineer: string;
  last_maintenance_date: string;
  estimated_downtime_minutes: number;
  spare_part_available?: boolean;
}

export interface EventSummary {
  event_id: string;
  scenario_id: string;
  equipment: Equipment;
  status: string;
  failure_probability: number | null;
  confidence: string;
  predicted_failure_type: string;
  recommended_decision: string;
}

export interface Factor {
  evidence_field_id: string;
  feature: string;
  display_name: string;
  value: number;
  unit: string;
  normal_range: string;
  direction: "risk_up" | "risk_down";
  contribution: number;
  source_type: string;
}

export interface SensorPoint {
  timestamp: string;
  product_type: string;
  air_temperature_k: number | null;
  process_temperature_k: number | null;
  rotational_speed_rpm: number | null;
  torque_nm: number | null;
  tool_wear_min: number | null;
}

export interface Evidence {
  evidence_id: string;
  event_id: string;
  scenario_id: string;
  equipment: Equipment;
  model: { model_version: string; policy_version: string; mode: string };
  status: string;
  recommended_decision: string;
  confidence: string;
  failure_probability: number | null;
  threshold: number;
  predicted_failure_type: string;
  observation: SensorPoint & Record<string, unknown>;
  history: SensorPoint[];
  detected_interval: { start: string; end: string };
  top_factors: Factor[];
  maintenance_context: {
    provider: string;
    version: string;
    source_type: string;
    source_refs: string[];
    checklist: string[];
    recommended_actions: string[];
  };
  data_quality_warnings: Array<{ code: string; field: string; message: string; severity: string }>;
  lineage: Record<string, string>;
  generated_at: string;
}

export interface Report {
  report_id: string;
  event_id: string;
  role: Role;
  mode: string;
  headline: string;
  summary: string;
  status: string;
  confidence: string;
  recommended_decision: string;
  sections: Array<{ section_id: string; title: string; body: string; evidence_field_ids: string[] }>;
  actions: Array<{ action_id: string; label: string; kind: string; requires_human_approval: boolean; source_refs: string[] }>;
  citations: string[];
  limitations: string[];
  generated_at: string;
}

export type BlockType =
  | "StatusSummary"
  | "RiskKpi"
  | "PriorityList"
  | "ImpactSummary"
  | "ManagerDecisionCard"
  | "SensorLineChart"
  | "AnomalyTimeline"
  | "FactorContribution"
  | "EvidenceTable"
  | "RecommendedActions"
  | "EngineerChecklist"
  | "DataQualityWarning"
  | "ModelDetails"
  | "ConversationThread";

export interface UIBlock {
  block_id: string;
  type: BlockType;
  title: string;
  order: number;
  emphasis: "primary" | "secondary" | "detail";
  data_fields: string[];
  collapsed: boolean;
}

export interface Layout {
  layout_id: string;
  event_id: string;
  role: Role;
  intent: Intent;
  mode: string;
  blocks: UIBlock[];
  generated_at: string;
}

export interface FollowUp {
  thread_id: string;
  event_id: string;
  role: Role;
  intent: Intent;
  answer: string;
  report: Report;
  layout: Layout;
  supported: boolean;
  audit: Record<string, unknown>;
}
