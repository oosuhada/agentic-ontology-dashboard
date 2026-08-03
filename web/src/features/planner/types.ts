import type { AppRole } from "../../types";
import type { DashboardTab, ResolvedDashboard } from "../dashboard/types";

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
