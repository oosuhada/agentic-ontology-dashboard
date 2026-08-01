import type { AppRole } from "../../types";

export type BoardCategory = "suggested" | "observe" | "explore" | "explain" | "act" | "audit" | "build";
export type BoardWidth = number;
export type DashboardMode = "view" | "edit";
export type VersionPolicy = "pinned" | "latest_published";
export type SelectionOperator = "eq" | "in" | "gte" | "lte" | "between";
export type RenderKind = "metric" | "bar" | "line" | "pie" | "histogram" | "table" | "ontology" | "activity";

export interface SelectionFilter {
  id: string;
  source_board_id: string;
  field: string;
  operator: SelectionOperator;
  values: Array<string | number | boolean>;
  object_type?: string;
  created_at: string;
}

export interface DataBinding {
  source: "object_set" | "analysis_board" | "inline";
  object_type?: string;
  analysis_id?: string;
  analysis_node_id?: string;
  fields?: string[];
  version_policy?: VersionPolicy;
  version?: number | null;
}

export interface RenderSpec {
  kind: RenderKind;
  title?: string;
  x_field?: string;
  y_field?: string;
  value_field?: string;
  group_field?: string;
  aggregation?: "count" | "sum" | "avg" | "min" | "max";
  selectable?: boolean;
  brushable?: boolean;
  page_size?: number;
}

export interface BoardSourceReference {
  kind: "analysis_board";
  analysis_id: string;
  analysis_node_id: string;
  version_policy: VersionPolicy;
  version?: number | null;
}

export interface DashboardParameterDefinition {
  id: string;
  display_name: string;
  value_type: "string" | "number" | "integer" | "boolean" | "datetime" | "object" | "array";
  scope: "dashboard" | "tab" | "board";
  default_value: unknown;
  options: unknown[];
  description: string | null;
}

export interface BoardCatalogDefinition {
  id: string;
  display_name: string;
  description: string;
  category: BoardCategory;
  renderer: string;
  allowed_roles: AppRole[];
  object_types: string[];
  emits: string[];
  accepts: string[];
  binding_schema: Record<string, string>;
  default_bindings: Record<string, unknown>;
  default_settings: Record<string, unknown>;
  default_data_binding?: DataBinding | null;
  default_render_spec?: RenderSpec | null;
  default_width: BoardWidth;
  minimum_width: BoardWidth;
  maximum_width: BoardWidth;
  allow_multiple: boolean;
}

export interface DashboardBoardLayout {
  x: number;
  y: number;
  w: number;
  h: number;
  min_w?: number | null;
  min_h?: number | null;
  max_w?: number | null;
  max_h?: number | null;
}

export interface DashboardBoard {
  id: string;
  definition_id: string;
  title: string;
  width: BoardWidth;
  order: number;
  layout?: DashboardBoardLayout | null;
  source?: BoardSourceReference | null;
  hidden: boolean;
  mandatory: boolean;
  custom: boolean;
  bindings: Record<string, unknown>;
  settings: Record<string, unknown>;
}

export interface DashboardTab {
  id: string;
  title: string;
  order: number;
  hidden: boolean;
  custom: boolean;
  parameter_ids: string[];
  boards: DashboardBoard[];
}

export interface DependencyEdge {
  source_board_id: string;
  target_board_id: string;
  parameter_ids: string[];
}

export interface ResolvedDashboard {
  dashboard_id: string;
  template_id: string;
  template_version: number;
  preference_revision: number;
  preference_template_version: number | null;
  workspace_id: string;
  role_code: AppRole;
  display_name: string;
  tabs: DashboardTab[];
  active_tab_id: string;
  parameter_state: Record<string, unknown>;
  parameter_definitions: DashboardParameterDefinition[];
  dependency_graph: DependencyEdge[];
  merge_notices: string[];
}

export interface SavedView {
  id: string;
  user_id: string;
  workspace_id: string;
  name: string;
  active_tab_id: string;
  tabs: DashboardTab[];
  parameter_state: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DashboardShareCreated {
  token: string;
  path: string;
  workspace_id: string;
  active_tab_id: string;
  parameter_state: Record<string, unknown>;
  expires_at: string;
}

export interface DashboardSharePayload {
  workspace_id: string;
  active_tab_id: string;
  parameter_state: Record<string, unknown>;
  owner_user_id: string;
  created_at: string;
  expires_at: string;
}

export interface DashboardTemplateVersion {
  template_id: string;
  display_name: string;
  current_version: number;
  version: number;
  status: "draft" | "published" | "archived";
  created_by: string | null;
  created_at: string;
}
