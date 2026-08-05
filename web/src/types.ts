export type Role = "manager" | "engineer";
export type AppRole =
  | "tenant_admin"
  | "executive_viewer"
  | "process_manager"
  | "process_engineer"
  | "maintenance_technician"
  | "quality_auditor"
  | "ml_validator"
  | "fde";
export type UserStatus = "pending_approval" | "active" | "disabled";

export interface AuthUser {
  user_id: string;
  email: string;
  display_name: string;
  status: UserStatus;
  roles: AppRole[];
  permissions: string[];
  workspace_scopes: string[];
  project_scopes: string[];
  project_roles: Record<string, string[]>;
  active_project_id: string | null;
  active_project_roles: string[];
  is_admin: boolean;
  default_path: "/app" | "/admin";
  landing_key: AppRole | "pending_approval";
}

export interface ProjectMembership {
  user_id: string;
  organization_id: string;
  project_id: string;
  status: "active" | "suspended";
  email: string;
  display_name: string;
  user_status: string;
  roles: string[];
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  organization_id: string;
  slug: string;
  display_name: string;
  description: string;
  domain_pack_code: string;
  status: "draft" | "active" | "archived";
  default_workspace_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Workspace {
  id: string;
  organization_id: string;
  project_id: string;
  slug: string;
  display_name: string;
  domain_pack: string;
}

export interface AdminUser {
  id: string;
  organization_id: string | null;
  organization_name: string | null;
  email: string;
  display_name: string;
  status: UserStatus;
  requested_organization_name: string | null;
  requested_role_code: AppRole | null;
  terms_accepted_at: string | null;
  created_at: string;
  updated_at: string;
  roles: AppRole[];
  permission_overrides: Record<string, boolean>;
  effective_permissions: string[];
  workspace_scopes: string[];
}

export interface RoleDefinition {
  code: AppRole;
  display_name: string;
  description: string;
  permissions: string[];
}

export interface AdminNotification {
  id: string;
  organization_id: string | null;
  notification_type: string;
  title: string;
  body: string;
  target_user_id: string | null;
  target_email: string | null;
  target_display_name: string | null;
  requested_role_code: AppRole | null;
  created_at: string;
  read_at: string | null;
}

export interface AdminAuditEntry {
  id: string;
  actor_user_id: string;
  target_user_id: string | null;
  actor_email: string;
  target_email: string | null;
  action: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  created_at: string;
}

export interface DomainPack {
  id: string;
  display_name: string;
  description: string;
  workspace_ids: string[];
  object_type_ids: string[];
  link_type_ids: string[];
  action_type_ids: string[];
  status: "active" | "draft" | "disabled";
}

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
  observed_at?: string;
  dataset_version_id?: string;
  ontology_object_id?: string | null;
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
  locale: "ko-KR" | "en-US";
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
