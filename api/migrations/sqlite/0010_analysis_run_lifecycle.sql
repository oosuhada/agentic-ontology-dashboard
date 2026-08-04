PRAGMA foreign_keys = OFF;

CREATE TABLE analysis_runs_lifecycle_v2 (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    analysis_version INTEGER NOT NULL CHECK (analysis_version >= 1),
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
    parameters_json TEXT NOT NULL,
    node_results_json TEXT NOT NULL,
    error_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
    current_node_id TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0,1)),
    cache_key TEXT,
    cache_hit INTEGER NOT NULL DEFAULT 0 CHECK (cache_hit IN (0,1)),
    rows_scanned INTEGER NOT NULL DEFAULT 0 CHECK (rows_scanned >= 0),
    updated_at TEXT
);

INSERT INTO analysis_runs_lifecycle_v2 (
    id,organization_id,project_id,workspace_id,analysis_id,analysis_version,
    requested_by,status,parameters_json,node_results_json,error_json,started_at,finished_at,
    progress_percent,current_node_id,cancel_requested,cache_key,cache_hit,rows_scanned,updated_at
)
SELECT
    id,organization_id,project_id,workspace_id,analysis_id,analysis_version,
    requested_by,status,parameters_json,node_results_json,error_json,started_at,finished_at,
    CASE WHEN status IN ('succeeded','failed') THEN 100 ELSE 0 END,
    NULL,0,NULL,0,0,COALESCE(finished_at,started_at)
FROM analysis_runs;

DROP TABLE analysis_runs;
ALTER TABLE analysis_runs_lifecycle_v2 RENAME TO analysis_runs;

CREATE INDEX IF NOT EXISTS idx_analysis_runs_latest
    ON analysis_runs(organization_id, project_id, workspace_id, analysis_id, analysis_version, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_cache
    ON analysis_runs(organization_id, project_id, workspace_id, analysis_id, analysis_version, cache_key, status, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_lifecycle
    ON analysis_runs(organization_id, project_id, workspace_id, status, updated_at DESC);

PRAGMA foreign_keys = ON;
