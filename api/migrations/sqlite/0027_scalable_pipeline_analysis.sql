CREATE TABLE IF NOT EXISTS pipeline_definitions (
  id TEXT NOT NULL, version INTEGER NOT NULL, organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL, branch_id TEXT NOT NULL, status TEXT NOT NULL,
  graph_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(organization_id,project_id,id,version,branch_id)
);
CREATE TABLE IF NOT EXISTS pipeline_materializations (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  pipeline_id TEXT NOT NULL, pipeline_version INTEGER NOT NULL, state TEXT NOT NULL,
  output_dataset_version_id TEXT, rows_written INTEGER NOT NULL, quality_state TEXT NOT NULL,
  created_at TEXT NOT NULL
);

