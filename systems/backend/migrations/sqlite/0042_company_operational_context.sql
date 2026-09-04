CREATE TABLE IF NOT EXISTS company_context_records (
    record_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_updated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id, project_id, workspace_id, record_type, record_key)
);

CREATE INDEX IF NOT EXISTS idx_company_context_scope_type
  ON company_context_records (organization_id, project_id, workspace_id, record_type, updated_at DESC);
