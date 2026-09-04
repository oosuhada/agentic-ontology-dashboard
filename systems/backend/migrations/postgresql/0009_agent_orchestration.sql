CREATE TABLE IF NOT EXISTS agent_runs (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    user_id text NOT NULL REFERENCES users(id),
    question text NOT NULL,
    route text NOT NULL,
    status text NOT NULL CHECK (status IN ('running','succeeded','failed','awaiting_approval')),
    state_json jsonb NOT NULL,
    answer text NOT NULL DEFAULT '',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_scope
    ON agent_runs(organization_id, project_id, workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_checkpoints (
    id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    sequence integer NOT NULL,
    node_name text NOT NULL,
    state_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_run
    ON agent_checkpoints(organization_id, project_id, run_id, sequence DESC);

CREATE TABLE IF NOT EXISTS agent_traces (
    id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    step_name text NOT NULL,
    store_kind text,
    status text NOT NULL,
    input_json jsonb NOT NULL,
    output_json jsonb NOT NULL,
    latency_ms integer,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_traces_run
    ON agent_traces(organization_id, project_id, run_id, created_at, id);

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_traces ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_runs_scope_policy ON agent_runs;
CREATE POLICY agent_runs_scope_policy ON agent_runs
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS agent_checkpoints_scope_policy ON agent_checkpoints;
CREATE POLICY agent_checkpoints_scope_policy ON agent_checkpoints
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS agent_traces_scope_policy ON agent_traces;
CREATE POLICY agent_traces_scope_policy ON agent_traces
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
