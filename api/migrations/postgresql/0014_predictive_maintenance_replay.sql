-- Predictive Maintenance Result Artifact and PostgreSQL replay cursor.
-- Additive only: canonical observations and model outputs remain immutable.

CREATE TABLE IF NOT EXISTS pm_replay_sessions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    created_by text NOT NULL,
    state text NOT NULL CHECK (state IN ('stopped','running','paused','completed')),
    simulation_time timestamptz NOT NULL,
    dataset_start timestamptz NOT NULL,
    dataset_end timestamptz NOT NULL,
    source_freshness_at timestamptz NOT NULL,
    speed_minutes_per_second double precision NOT NULL
        CHECK (speed_minutes_per_second BETWEEN 0.1 AND 10080),
    sequence bigint NOT NULL DEFAULT 0 CHECK (sequence >= 0),
    last_advanced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (dataset_end >= dataset_start),
    CHECK (simulation_time BETWEEN dataset_start AND dataset_end)
);

CREATE INDEX IF NOT EXISTS idx_pm_replay_sessions_scope
    ON pm_replay_sessions(
        organization_id, project_id, workspace_id, dataset_version_id, updated_at DESC
    );

ALTER TABLE pm_replay_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pm_replay_sessions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_scope_policy ON pm_replay_sessions;
CREATE POLICY project_scope_policy ON pm_replay_sessions
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );

COMMENT ON TABLE pm_replay_sessions IS
    'Project-scoped simulation cursors over immutable PostgreSQL canonical observations and precomputed prediction timeline rows.';
COMMENT ON COLUMN pm_replay_sessions.simulation_time IS
    'Simulation clock. This is not wall-clock freshness and never causes model retraining.';
COMMENT ON COLUMN pm_replay_sessions.source_freshness_at IS
    'Maximum immutable canonical observation timestamp for the selected Dataset Version.';
