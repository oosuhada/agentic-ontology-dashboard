export type StoreKind = "relational" | "graph" | "vector";
export type ProjectionStatus = "pending" | "indexing" | "ready" | "failed" | "missing";

export interface DatasetCatalogItem {
  id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  slug: string;
  display_name: string;
  description: string;
  source_type: string;
  status: "draft" | "active" | "archived";
  created_by: string | null;
  created_at: string;
  updated_at: string;
  latest_version_id: string | null;
  latest_version_label: string | null;
  latest_source_version: string | null;
  record_count: number;
  projection_health: Record<StoreKind, ProjectionStatus>;
}

export interface DatasetVersionItem {
  id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  dataset_id: string;
  version_number: number;
  version_label: string;
  source_version: string;
  manifest_id: string | null;
  checksum_sha256: string;
  schema: Record<string, unknown>;
  profile: Record<string, unknown>;
  record_count: number;
  status: "registered" | "profiling" | "projecting" | "ready" | "failed";
  created_by: string | null;
  created_at: string;
}

export interface DatasetProjectionItem {
  id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  dataset_id: string;
  dataset_version_id: string;
  store_kind: StoreKind;
  status: Exclude<ProjectionStatus, "missing">;
  object_namespace: string;
  source_version: string;
  record_count: number;
  attempt_count: number;
  last_error: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface DatasetMappingItem {
  id: string;
  object_type: string;
  identity_field: string;
  property_mapping: Record<string, string>;
  relationship_mapping: Array<Record<string, unknown>>;
  content_fields: string[];
  allowed_roles: string[];
  status: string;
  dataset_version_id: string;
  created_at: string;
  updated_at: string;
}

export interface DatasetMaterializationItem {
  id: string;
  source_kind: string;
  source_reference: string;
  format: string;
  artifact_uri: string;
  checksum_sha256: string;
  record_count: number;
  status: string;
  metadata: Record<string, unknown>;
  dataset_version_id: string;
  created_at: string;
}

export interface DatasetCatalogDetail {
  dataset: DatasetCatalogItem;
  versions: DatasetVersionItem[];
  projections: DatasetProjectionItem[];
  mappings: DatasetMappingItem[];
  materializations: DatasetMaterializationItem[];
}
