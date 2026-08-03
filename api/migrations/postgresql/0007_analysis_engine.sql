-- Versioned Analysis definitions, board snapshots and execution results.

CREATE TABLE IF NOT EXISTS analyses (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    display_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft','published','archived')),
    current_version integer NOT NULL CHECK (current_version >= 1),
    published_version integer CHECK (published_version IS NULL OR published_version >= 1),
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analysis_boards (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    analysis_id text NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version >= 1),
    node_id text NOT NULL,
    node_json jsonb NOT NULL,
    edges_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (analysis_id, version, node_id)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    analysis_id text NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    analysis_version integer NOT NULL CHECK (analysis_version >= 1),
    requested_by text NOT NULL REFERENCES users(id),
    status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed')),
    parameters_json jsonb NOT NULL,
    node_results_json jsonb NOT NULL,
    error_json jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_analyses_scope
    ON analyses(organization_id, project_id, workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_boards_version
    ON analysis_boards(organization_id, project_id, workspace_id, analysis_id, version, node_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_latest
    ON analysis_runs(organization_id, project_id, workspace_id, analysis_id, analysis_version, finished_at DESC);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['analyses','analysis_boards','analysis_runs']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS project_scope_policy ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY project_scope_policy ON %I USING (' ||
            'organization_id = current_setting(''app.organization_id'', true) ' ||
            'AND project_id = current_setting(''app.project_id'', true)' ||
            ') WITH CHECK (' ||
            'organization_id = current_setting(''app.organization_id'', true) ' ||
            'AND project_id = current_setting(''app.project_id'', true)' ||
            ')',
            table_name
        );
    END LOOP;
END $$;
