-- Materialized read-only Agent Review Summary artifacts.
-- Summaries are regenerated from Product Result/Evidence snapshot diffs, not UI presentation events.

CREATE TABLE IF NOT EXISTS agent_review_summaries (
    summary_id text PRIMARY KEY,
    summary_key text NOT NULL UNIQUE,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    asset_id text NOT NULL,
    event_id text,
    dataset_version_id text,
    history_window text NOT NULL,
    packet_schema_version text NOT NULL,
    summary_schema_version text NOT NULL,
    prompt_version text NOT NULL,
    model_version text NOT NULL,
    source_sha256 text NOT NULL,
    status text NOT NULL CHECK (status IN ('ready','fallback','failed','stale')),
    fallback_reason text,
    snapshot_basis_json text NOT NULL,
    summary_json text NOT NULL,
    trace_json text NOT NULL,
    generated_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_review_summaries_lookup
  ON agent_review_summaries (
    organization_id,project_id,workspace_id,asset_id,event_id,dataset_version_id,updated_at DESC
  );

CREATE INDEX IF NOT EXISTS idx_agent_review_summaries_status
  ON agent_review_summaries (
    organization_id,project_id,workspace_id,status,updated_at DESC
  );

ALTER TABLE agent_review_summaries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_review_summaries_scope ON agent_review_summaries;
CREATE POLICY agent_review_summaries_scope
  ON agent_review_summaries
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );
