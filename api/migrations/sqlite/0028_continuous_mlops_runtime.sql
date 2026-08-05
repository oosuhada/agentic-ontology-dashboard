CREATE TABLE IF NOT EXISTS feature_views (
  id TEXT NOT NULL, version INTEGER NOT NULL, organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL, status TEXT NOT NULL, definition_json TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(organization_id,project_id,id,version)
);
CREATE TABLE IF NOT EXISTS model_deployments (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  model_version_id TEXT NOT NULL, mode TEXT NOT NULL, traffic_percent REAL NOT NULL,
  state TEXT NOT NULL, rollback_target_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_drift_observations (
  id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, project_id TEXT NOT NULL,
  model_version_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL,
  threshold REAL NOT NULL, sample_size INTEGER NOT NULL, state TEXT NOT NULL,
  observed_at TEXT NOT NULL
);

