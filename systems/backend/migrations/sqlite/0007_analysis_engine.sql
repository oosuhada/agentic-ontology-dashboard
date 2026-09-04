-- Versioned Analysis definitions, board snapshots and execution results.

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','published','archived')),
    current_version INTEGER NOT NULL CHECK (current_version >= 1),
    published_version INTEGER CHECK (published_version IS NULL OR published_version >= 1),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_boards (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version >= 1),
    node_id TEXT NOT NULL,
    node_json TEXT NOT NULL,
    edges_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (analysis_id, version, node_id)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    analysis_id TEXT NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    analysis_version INTEGER NOT NULL CHECK (analysis_version >= 1),
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
    parameters_json TEXT NOT NULL,
    node_results_json TEXT NOT NULL,
    error_json TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_analyses_scope
    ON analyses(organization_id, project_id, workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_boards_version
    ON analysis_boards(organization_id, project_id, workspace_id, analysis_id, version, node_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_latest
    ON analysis_runs(organization_id, project_id, workspace_id, analysis_id, analysis_version, finished_at DESC);
