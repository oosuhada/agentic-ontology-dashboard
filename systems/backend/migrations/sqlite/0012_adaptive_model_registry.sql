CREATE TABLE IF NOT EXISTS modeling_model_release_requests (
    release_request_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    model_version_id TEXT NOT NULL,
    status TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    requested_by TEXT NOT NULL,
    request_rationale TEXT NOT NULL,
    decided_by TEXT,
    decision_rationale TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    UNIQUE (organization_id, project_id, workspace_id, model_version_id, status)
);
CREATE INDEX IF NOT EXISTS idx_model_release_requests_scope
    ON modeling_model_release_requests(organization_id,project_id,workspace_id,status,created_at);
