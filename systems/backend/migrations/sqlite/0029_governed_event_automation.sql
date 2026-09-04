CREATE TABLE IF NOT EXISTS automation_definitions (
  id TEXT NOT NULL, version INTEGER NOT NULL, organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL, status TEXT NOT NULL, definition_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(organization_id,project_id,id,version)
);
CREATE TABLE IF NOT EXISTS automation_runs (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  automation_id TEXT NOT NULL, automation_version INTEGER NOT NULL, event_id TEXT NOT NULL,
  state TEXT NOT NULL, simulation INTEGER NOT NULL, approval_state TEXT NOT NULL,
  trace_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(organization_id,project_id,automation_id,event_id)
);
