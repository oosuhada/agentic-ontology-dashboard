-- Runtime run records for read-only Agent Review Summary materialization.

CREATE TABLE IF NOT EXISTS agent_review_workflow_runs (
    workflow_run_id TEXT PRIMARY KEY,
    trigger TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','completed','partial','failed')),
    organization_id TEXT NOT NULL DEFAULT 'org-ontology-demo',
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL DEFAULT 'manufacturing-demo',
    asset_id TEXT NOT NULL,
    event_id TEXT,
    dataset_version_id TEXT,
    history_window TEXT NOT NULL,
    summary_key TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    context_sha256 TEXT NOT NULL,
    packet_schema_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    trace_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_review_workflow_runs_lookup
  ON agent_review_workflow_runs (
    organization_id, project_id, workspace_id, asset_id, event_id, dataset_version_id, updated_at
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_review_workflow_runs_running_summary
  ON agent_review_workflow_runs (
    organization_id, project_id, workspace_id, summary_key
  )
  WHERE status = 'running';
