-- Stored read-only Agent Review Summary records.

CREATE TABLE IF NOT EXISTS agent_review_summaries (
    summary_id TEXT PRIMARY KEY,
    summary_key TEXT NOT NULL UNIQUE,
    workflow_run_id TEXT,
    organization_id TEXT NOT NULL DEFAULT 'org-ontology-demo',
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'manufacturing-demo',
    asset_id TEXT NOT NULL,
    event_id TEXT,
    dataset_version_id TEXT,
    history_window TEXT NOT NULL,
    packet_schema_version TEXT NOT NULL,
    summary_schema_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready','fallback','failed','stale')),
    fallback_reason TEXT,
    snapshot_basis_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    trace_json TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_review_summaries_lookup
  ON agent_review_summaries (
    organization_id, project_id, workspace_id, asset_id, event_id, dataset_version_id, updated_at
  );
