CREATE TABLE IF NOT EXISTS object_view_definitions (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  object_type_id TEXT NOT NULL, interface_id TEXT, form_factor TEXT NOT NULL,
  status TEXT NOT NULL, branch_id TEXT NOT NULL, definition_json TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(organization_id,project_id,object_type_id,form_factor,branch_id)
);
CREATE TABLE IF NOT EXISTS saved_object_perspectives (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  owner_user_id TEXT NOT NULL, name TEXT NOT NULL, object_type_id TEXT NOT NULL,
  query_json TEXT NOT NULL, columns_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS application_runtime_definitions (
  id TEXT NOT NULL, version INTEGER NOT NULL, organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL, status TEXT NOT NULL, branch_id TEXT NOT NULL,
  definition_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(organization_id,project_id,id,version,branch_id)
);

