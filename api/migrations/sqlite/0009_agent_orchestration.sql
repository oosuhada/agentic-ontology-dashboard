CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    route TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','awaiting_approval')),
    state_json TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_scope
    ON agent_runs(organization_id, project_id, workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_checkpoints (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    node_name TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_run
    ON agent_checkpoints(organization_id, project_id, run_id, sequence DESC);

CREATE TABLE IF NOT EXISTS agent_traces (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    store_kind TEXT,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL,
    latency_ms INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agent_traces_run
    ON agent_traces(organization_id, project_id, run_id, created_at, id);
