import type { AppRole } from "../../types";
import type {
  DashboardTab,
  ResolvedDashboard,
  VisualizationCandidate,
  VisualizationFieldProfile,
  VisualizationKind,
} from "../dashboard/types";

export interface ObjectQueryIntent {
  object_type: string;
  search: string | null;
  filters: Array<{
    field: string;
    operator: "eq" | "contains" | "gte" | "lte";
    value: string | number | boolean;
  }>;
  limit: number;
  rationale: string;
  source_terms: string[];
}

export interface ObjectQueryPlanResponse {
  mode: "deterministic" | "llm" | "deterministic_fallback";
  provider: string;
  fallback_reason: string | null;
  intent: ObjectQueryIntent;
  preview_total: number;
  preview_items: Array<{
    id: string;
    object_type: string;
    workspace_id: string;
    properties: Record<string, unknown>;
  }>;
  validation: Record<string, boolean>;
  requires_approval: boolean;
}

export interface BoardRecommendationItem {
  definition_id: string;
  display_name: string;
  category: string;
  score: number;
  reason: string;
  already_present: boolean;
  preference_signals: string[];
}

export interface BoardRecommendationResponse {
  mode: "deterministic" | "llm" | "deterministic_fallback";
  provider: string;
  fallback_reason: string | null;
  role_code: AppRole;
  goal: string;
  recommendations: BoardRecommendationItem[];
  current_board_ids: string[];
  requires_approval: true;
  persisted: false;
}

export interface DashboardDraftResponse {
  mode: "deterministic" | "llm" | "deterministic_fallback";
  provider: string;
  fallback_reason: string | null;
  workspace_id: string;
  target_role: AppRole;
  display_name: string;
  tabs: DashboardTab[];
  parameter_definitions: ResolvedDashboard["parameter_definitions"];
  recommended_definition_ids: string[];
  validation: Record<string, boolean>;
  requires_approval: true;
  persisted: false;
}

export interface VisualizationPlannerResponse {
  mode: "deterministic" | "llm" | "deterministic_fallback";
  provider: string;
  fallback_reason: string | null;
  workspace_id: string;
  dashboard_id: string;
  board_id: string;
  goal: string;
  recommended: VisualizationCandidate;
  alternatives: VisualizationCandidate[];
  validation: Record<string, boolean>;
  requires_approval: false;
}

export type SemanticSourceRole =
  | "cnc_sensor_observation"
  | "compressor_sensor_observation"
  | "prediction_timeline"
  | "result_artifact";
export type SemanticVisualizationIntent =
  | "comparison"
  | "trend"
  | "composition"
  | "distribution"
  | "relationship"
  | "detail"
  | "summary";
export type SemanticAggregation = "none" | "count" | "count_distinct" | "sum" | "avg" | "min" | "max";

export interface GovernedVisualizationSource {
  organization_id: string;
  project_id: string;
  workspace_id: string;
  dataset_id: string;
  dataset_version_id: string;
  source_role: SemanticSourceRole;
  dataset_version: string;
  source_version: string;
  bundle_checksum_sha256: string;
  model_version?: string;
  result_artifact_schema_version?: string;
  release_gates?: Record<string, unknown>;
  graph_readiness: "pending" | "indexing" | "ready" | "degraded" | "failed" | "unavailable";
  relational_fallback_capability: boolean;
}

export interface SemanticMeasure {
  field_id: string;
  aggregation: SemanticAggregation;
  alias?: string;
}

export interface SemanticChannelMapping {
  x?: string;
  y?: string;
  value?: string;
  series?: string;
  row?: string;
  column?: string;
  threshold?: string;
}

export interface SemanticVisualizationPlanInput {
  source: GovernedVisualizationSource;
  goal: string;
  intent: SemanticVisualizationIntent;
  dimensions?: string[];
  measures?: SemanticMeasure[];
  time?: {
    field_id: string;
    grain: "raw" | "10m" | "1h" | "1d";
    window: { start: string; end: string };
  };
  filters?: Array<{
    field_id: string;
    operator: "eq" | "in" | "gte" | "lte" | "between";
    value: string | number | boolean | Array<string | number | boolean>;
  }>;
  order?: Array<{ field_id: string; direction: "asc" | "desc" }>;
  limit?: number;
  chart_kind?: VisualizationKind;
  field_cardinalities?: Record<string, number>;
  result_profile?: VisualizationFieldProfile[];
  saved_override?: {
    version: 2;
    catalog_version: string;
    dataset_version: string;
    source_version: string;
    chart_kind: VisualizationKind;
    dimensions: string[];
    measures: SemanticMeasure[];
    channel_mapping: SemanticChannelMapping;
  };
  clamp_limits?: boolean;
  use_llm?: boolean;
}

export interface SemanticFieldCatalogEntry {
  field_id: string;
  semantic_role: "identifier" | "dimension" | "measure" | "timestamp" | "status" | "text";
  domain_concept: string;
  physical_type: string;
  unit: string | null;
  unit_status: "known" | "unitless" | "source_raw_unspecified";
  allowed_aggregations: SemanticAggregation[];
  grain: string;
  timezone: string | null;
  allowed_filters: Array<"eq" | "in" | "gte" | "lte" | "between">;
  cardinality_limit: number | null;
  source_roles: SemanticSourceRole[];
  source_role: string;
  dataset_version: string;
  source_version: string;
  bundle_checksum_sha256: string;
  model_version: string | null;
  result_artifact_schema_version: string | null;
  graph_readiness: "pending" | "indexing" | "ready" | "degraded" | "failed" | "unavailable";
  relational_fallback_capability: boolean;
  derived_expression_id: string | null;
  ordered_values: string[];
  queryable: boolean;
  runtime_allowed: boolean;
  governance_only: boolean;
}

export interface SemanticVisualizationPlanResponse {
  mode: "deterministic" | "llm" | "deterministic_fallback";
  provider: string;
  fallback_reason: string | null;
  plan: {
    catalog_version: string;
    source: GovernedVisualizationSource;
    intent: SemanticVisualizationIntent;
    dimensions: string[];
    measures: SemanticMeasure[];
    time: SemanticVisualizationPlanInput["time"] | null;
    filters: NonNullable<SemanticVisualizationPlanInput["filters"]>;
    order: NonNullable<SemanticVisualizationPlanInput["order"]>;
    limit: number;
    chart_kind: VisualizationKind;
    channel_mapping: SemanticChannelMapping;
    annotations: Array<{ kind: "threshold" | "range"; field_id: string; values: number[]; label: string }>;
    selection_reason: string;
    fallback_reason: string | null;
    profile_hash: string;
  };
  compiled_query: {
    sql: string;
    params: unknown[];
    query_hash: string;
    selected_fields: string[];
    units: Record<string, string | null>;
    clamped: boolean;
    warnings: string[];
  };
  candidates: VisualizationCandidate[];
  semantic_fields: SemanticFieldCatalogEntry[];
  override_compatibility: {
    status: "compatible" | "migration_required" | "incompatible" | "not_provided";
    reasons: string[];
  };
  validation: Record<string, unknown>;
}

export interface GroundedNarrativeResponse {
  mode: "deterministic" | "llm" | "deterministic_fallback";
  provider: string;
  fallback_reason: string | null;
  event_id: string;
  goal: string;
  headline: string;
  summary: string;
  claims: Array<{ text: string; evidence_field_ids: string[] }>;
  citations: string[];
  grounded: true;
  requires_approval: false;
}

export interface ExportArtifact {
  blob: Blob;
  filename: string;
  checkpointId: string;
  contentHash: string;
  snapshotHash: string;
}
