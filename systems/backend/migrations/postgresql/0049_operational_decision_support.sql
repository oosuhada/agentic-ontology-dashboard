-- Persistent read-only Operational Decision Support briefs and workflow traces.

CREATE TABLE IF NOT EXISTS operational_context_snapshots (
    owner_domain text NOT NULL,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    asset_id text NOT NULL,
    source_version text NOT NULL,
    source_updated_at timestamptz NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz NOT NULL,
    source_ref text NOT NULL,
    payload_json jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (
        owner_domain, organization_id, project_id, workspace_id, asset_id,
        source_version
    )
);

CREATE INDEX IF NOT EXISTS idx_operational_context_snapshots_lookup
  ON operational_context_snapshots (
    organization_id, project_id, workspace_id, asset_id, owner_domain,
    valid_from, valid_to, source_updated_at DESC
  );

CREATE TABLE IF NOT EXISTS operational_decision_briefs (
    cache_key text PRIMARY KEY,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    asset_id text NOT NULL,
    snapshot_json text NOT NULL,
    stored_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operational_decision_briefs_lookup
  ON operational_decision_briefs (
    organization_id, project_id, workspace_id, asset_id, stored_at DESC
  );

CREATE TABLE IF NOT EXISTS operational_decision_workflow_runs (
    workflow_run_id text PRIMARY KEY,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    asset_id text NOT NULL,
    cache_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('running','completed','partial','failed')),
    reason text,
    run_json text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operational_decision_runs_lookup
  ON operational_decision_workflow_runs (
    organization_id, project_id, workspace_id, asset_id, status, recorded_at DESC
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_operational_decision_workflow_runs_running_key
  ON operational_decision_workflow_runs (
    organization_id, project_id, workspace_id, cache_key
  )
  WHERE status = 'running';

ALTER TABLE operational_decision_briefs ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_decision_workflow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_context_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS operational_context_snapshots_scope
  ON operational_context_snapshots;
CREATE POLICY operational_context_snapshots_scope
  ON operational_context_snapshots
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

DROP POLICY IF EXISTS operational_decision_briefs_scope ON operational_decision_briefs;
CREATE POLICY operational_decision_briefs_scope
  ON operational_decision_briefs
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

DROP POLICY IF EXISTS operational_decision_workflow_runs_scope
  ON operational_decision_workflow_runs;
CREATE POLICY operational_decision_workflow_runs_scope
  ON operational_decision_workflow_runs
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );
