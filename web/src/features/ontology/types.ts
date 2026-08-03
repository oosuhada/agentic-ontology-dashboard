export type OntologyValueType = "string" | "number" | "integer" | "boolean" | "datetime" | "object" | "array";

export interface OntologyProperty {
  id: string;
  display_name: string;
  value_type: OntologyValueType;
  required: boolean;
  unit: string | null;
  description: string | null;
}

export interface ObjectTypeDefinition {
  id: string;
  display_name: string;
  description: string;
  properties: OntologyProperty[];
  interfaces: string[];
  domain_pack: string;
}

export interface ObjectRecord {
  id: string;
  object_type: string;
  workspace_id: string;
  properties: Record<string, unknown>;
  source_refs: string[];
  version: number;
}

export interface LinkTypeDefinition {
  id: string;
  display_name: string;
  source_type: string;
  target_type: string;
  cardinality: "one-to-one" | "one-to-many" | "many-to-one" | "many-to-many";
  domain_pack: string;
}

export interface LinkRecord {
  id: string;
  link_type: string;
  source_object_id: string;
  target_object_id: string;
  workspace_id: string;
  properties: Record<string, unknown>;
  version: number;
}

export interface ActionParameter {
  id: string;
  display_name: string;
  value_type: OntologyValueType;
  required: boolean;
}

export interface ActionTypeDefinition {
  id: string;
  display_name: string;
  description: string;
  object_type: string;
  parameters: ActionParameter[];
  required_permissions: string[];
  requires_human_approval: boolean;
  domain_pack: string;
}

export interface ActionInvocation {
  action_type: string;
  object_id: string;
  workspace_id: string;
  parameters: Record<string, unknown>;
  idempotency_key: string;
}

export interface ActionExecutionResult {
  invocation_id: string;
  action_type: string;
  object_id: string;
  workspace_id: string;
  state: "succeeded";
  replayed: boolean;
  result: Record<string, unknown>;
  audit_id: string;
  created_at: string;
  completed_at: string;
}

export interface OntologyObjectQueryResult {
  workspace_id: string;
  domain_pack: string;
  object_type: string | null;
  search: string | null;
  offset: number;
  limit: number;
  total: number;
  items: ObjectRecord[];
}

export interface OntologyTraversal {
  root: ObjectRecord;
  nodes: ObjectRecord[];
  edges: LinkRecord[];
  direction: "outgoing" | "incoming" | "both";
  depth: number;
}

export interface OntologyAggregateResult {
  workspace_id: string;
  object_type: string;
  group_by: string[];
  metrics: string[];
  source_rows: number;
  row_count: number;
  rows: Array<Record<string, unknown>>;
  generated_at: string;
}

export interface EvidenceReference {
  id: string;
  evidence_type: string;
  object_id: string;
  source_refs: string[];
  generated_at: string;
  version: number;
}

export interface BoardDefinition {
  id: string;
  display_name: string;
  category: "suggested" | "observe" | "explore" | "explain" | "act" | "audit" | "build";
  object_types: string[];
  emits: string[];
  accepts: string[];
  allowed_roles: string[];
  minimum_width: number;
  maximum_width: number;
}

export interface DashboardDefinition {
  id: string;
  display_name: string;
  workspace_id: string;
  role_code: string;
  tabs: string[];
  mandatory_board_ids: string[];
  version: number;
}

export interface OntologyRegistry {
  domain_packs: Array<{
    id: string;
    display_name: string;
    description: string;
    workspace_ids: string[];
    object_type_ids: string[];
    link_type_ids: string[];
    action_type_ids: string[];
    status: "active" | "draft" | "disabled";
  }>;
  object_types: ObjectTypeDefinition[];
  link_types: LinkTypeDefinition[];
  action_types: ActionTypeDefinition[];
}
