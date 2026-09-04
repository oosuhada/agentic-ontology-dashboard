CREATE TABLE IF NOT EXISTS platform_branches (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  name TEXT NOT NULL, base_branch_id TEXT, status TEXT NOT NULL, owner_user_id TEXT NOT NULL,
  head_revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (organization_id, project_id, name)
);
CREATE TABLE IF NOT EXISTS platform_branch_resources (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  branch_id TEXT NOT NULL, resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,
  revision INTEGER NOT NULL, payload_json TEXT NOT NULL, operation TEXT NOT NULL,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE (organization_id, project_id, branch_id, resource_type, resource_id, revision)
);
CREATE TABLE IF NOT EXISTS platform_lineage_edges (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  branch_id TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
  target_type TEXT NOT NULL, target_id TEXT NOT NULL, relation TEXT NOT NULL,
  source_field TEXT, target_field TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS platform_markings (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  resource_type TEXT NOT NULL, resource_id TEXT NOT NULL, field_name TEXT,
  marking TEXT NOT NULL, inherited_from TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS platform_policy_decisions (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  actor_user_id TEXT NOT NULL, resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,
  purpose TEXT NOT NULL, decision TEXT NOT NULL, reason_code TEXT NOT NULL,
  created_at TEXT NOT NULL
);
