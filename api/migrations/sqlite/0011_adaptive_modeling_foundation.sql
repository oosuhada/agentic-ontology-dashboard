CREATE TABLE IF NOT EXISTS modeling_intake_profiles (
    profile_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT, parent_id TEXT, checksum_sha256 TEXT, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_manifest_drafts (
    draft_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT, parent_id TEXT, checksum_sha256 TEXT, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_mapping_sets (
    mapping_set_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL, parent_id TEXT, checksum_sha256 TEXT NOT NULL, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_feature_recipe_sets (
    recipe_set_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL, parent_id TEXT, checksum_sha256 TEXT NOT NULL, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_feature_dataset_versions (
    feature_dataset_version_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL, parent_id TEXT, checksum_sha256 TEXT NOT NULL, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_experiment_runs (
    experiment_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL, parent_id TEXT, checksum_sha256 TEXT, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_model_versions (
    model_version_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL, parent_id TEXT, checksum_sha256 TEXT NOT NULL, artifact_uri TEXT NOT NULL,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_explanation_artifacts (
    explanation_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    dataset_version_id TEXT, parent_id TEXT NOT NULL, checksum_sha256 TEXT NOT NULL, artifact_uri TEXT,
    status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, idempotency_key TEXT,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id TEXT NOT NULL, project_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
    actor_id TEXT NOT NULL, action TEXT NOT NULL, aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_modeling_profiles_scope ON modeling_intake_profiles(organization_id,project_id,workspace_id,created_at);
CREATE INDEX IF NOT EXISTS idx_modeling_mapping_dataset ON modeling_mapping_sets(organization_id,project_id,dataset_version_id,status);
CREATE INDEX IF NOT EXISTS idx_modeling_recipe_dataset ON modeling_feature_recipe_sets(organization_id,project_id,dataset_version_id,status);
CREATE INDEX IF NOT EXISTS idx_modeling_experiments_scope ON modeling_experiment_runs(organization_id,project_id,workspace_id,status,created_at);
CREATE INDEX IF NOT EXISTS idx_modeling_models_scope ON modeling_model_versions(organization_id,project_id,workspace_id,status,created_at);
