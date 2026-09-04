-- Runtime run records for read-only Agent Review Summary materialization.

CREATE TABLE IF NOT EXISTS agent_review_workflow_runs (
    workflow_run_id text PRIMARY KEY,
    trigger text NOT NULL,
    engine text NOT NULL,
    status text NOT NULL CHECK (status IN ('running','completed','partial','failed')),
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    asset_id text NOT NULL,
    event_id text,
    dataset_version_id text,
    history_window text NOT NULL,
    summary_key text NOT NULL,
    source_sha256 text NOT NULL,
    context_sha256 text NOT NULL,
    packet_schema_version text NOT NULL,
    prompt_version text NOT NULL,
    model_version text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL,
    error_type text,
    error_message text,
    trace_json text NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_review_workflow_runs_lookup
  ON agent_review_workflow_runs (
    organization_id, project_id, workspace_id, asset_id, event_id, dataset_version_id, updated_at DESC
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_review_workflow_runs_running_summary
  ON agent_review_workflow_runs (
    organization_id, project_id, workspace_id, summary_key
  )
  WHERE status = 'running';

ALTER TABLE agent_review_summaries
  ADD COLUMN IF NOT EXISTS workflow_run_id text;

ALTER TABLE agent_review_workflow_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_review_workflow_runs_scope ON agent_review_workflow_runs;
CREATE POLICY agent_review_workflow_runs_scope
  ON agent_review_workflow_runs
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );
