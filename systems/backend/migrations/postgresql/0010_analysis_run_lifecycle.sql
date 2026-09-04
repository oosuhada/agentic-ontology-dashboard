ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS progress_percent integer NOT NULL DEFAULT 0;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS current_node_id text;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS cancel_requested boolean NOT NULL DEFAULT false;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS cache_key text;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS cache_hit boolean NOT NULL DEFAULT false;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS rows_scanned integer NOT NULL DEFAULT 0;
ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS updated_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_analysis_runs_cache
    ON analysis_runs(organization_id, project_id, workspace_id, analysis_id, analysis_version, cache_key, status, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_lifecycle
    ON analysis_runs(organization_id, project_id, workspace_id, status, updated_at DESC);
