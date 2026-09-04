-- Closed-loop Runtime Overlay persistence for post-maintenance observations.
-- Additive only: Canonical/live sensor tables remain unchanged.

CREATE TABLE IF NOT EXISTS pm_runtime_overlay_observations (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    simulation_session_id text NOT NULL,
    overlay_branch_id text NOT NULL,
    history_segment_id text NOT NULL,
    maintenance_action_id text NOT NULL,
    maintenance_event_id text NOT NULL,
    asset_id text NOT NULL,
    asset_type text NOT NULL CHECK (asset_type IN ('compressor','cnc')),
    site_id text NOT NULL,
    cell_id text NOT NULL,
    observed_at timestamptz NOT NULL,
    state_version integer NOT NULL CHECK (state_version > 0),
    source_kind text NOT NULL CHECK (source_kind='maintenance_replay_overlay'),
    observation_json jsonb NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id,overlay_branch_id,observed_at),
    FOREIGN KEY (dataset_version_id,asset_id)
        REFERENCES pm_assets(dataset_version_id,asset_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_runtime_overlay_observations_branch_time
    ON pm_runtime_overlay_observations(
        organization_id,project_id,workspace_id,dataset_version_id,
        overlay_branch_id,observed_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_pm_runtime_overlay_observations_asset_time
    ON pm_runtime_overlay_observations(
        project_id,dataset_version_id,asset_id,observed_at DESC
    );

CREATE TABLE IF NOT EXISTS pm_runtime_overlay_events (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    event_id text NOT NULL,
    event_type text NOT NULL CHECK (event_type='runtime_overlay.observations.available'),
    simulation_session_id text NOT NULL,
    overlay_branch_id text NOT NULL,
    history_segment_id text NOT NULL,
    maintenance_action_id text NOT NULL,
    maintenance_event_id text NOT NULL,
    asset_id text NOT NULL,
    state_version integer NOT NULL CHECK (state_version > 0),
    batch_rows integer NOT NULL CHECK (batch_rows > 0),
    generated_rows integer NOT NULL CHECK (generated_rows >= batch_rows),
    observed_from timestamptz NOT NULL,
    observed_to timestamptz NOT NULL,
    payload_json jsonb NOT NULL,
    source_sha256 text NOT NULL,
    consumed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id,event_id),
    CHECK (observed_to >= observed_from)
);

CREATE INDEX IF NOT EXISTS idx_pm_runtime_overlay_events_branch
    ON pm_runtime_overlay_events(
        organization_id,project_id,workspace_id,dataset_version_id,
        overlay_branch_id,observed_to DESC
    );

CREATE TABLE IF NOT EXISTS pm_runtime_overlay_state (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    overlay_branch_id text NOT NULL,
    simulation_session_id text NOT NULL,
    history_segment_id text NOT NULL,
    maintenance_action_id text NOT NULL,
    maintenance_event_id text NOT NULL,
    asset_id text NOT NULL,
    asset_type text NOT NULL CHECK (asset_type IN ('compressor','cnc')),
    runtime_status text NOT NULL CHECK (
        runtime_status IN ('warming_up','history_insufficient','ready','predicted')
    ),
    generated_rows integer NOT NULL DEFAULT 0 CHECK (generated_rows >= 0),
    required_prior_rows integer NOT NULL DEFAULT 0 CHECK (required_prior_rows >= 0),
    latest_observed_at timestamptz,
    model_version text,
    prediction_id text,
    latest_result_json jsonb,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id,overlay_branch_id),
    FOREIGN KEY (dataset_version_id,asset_id)
        REFERENCES pm_assets(dataset_version_id,asset_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_runtime_overlay_state_scope
    ON pm_runtime_overlay_state(
        organization_id,project_id,workspace_id,dataset_version_id,
        runtime_status,updated_at DESC
    );

ALTER TABLE pm_runtime_overlay_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pm_runtime_overlay_observations FORCE ROW LEVEL SECURITY;
ALTER TABLE pm_runtime_overlay_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pm_runtime_overlay_events FORCE ROW LEVEL SECURITY;
ALTER TABLE pm_runtime_overlay_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE pm_runtime_overlay_state FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_scope_policy ON pm_runtime_overlay_observations;
CREATE POLICY project_scope_policy ON pm_runtime_overlay_observations
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );

DROP POLICY IF EXISTS project_scope_policy ON pm_runtime_overlay_events;
CREATE POLICY project_scope_policy ON pm_runtime_overlay_events
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );

DROP POLICY IF EXISTS project_scope_policy ON pm_runtime_overlay_state;
CREATE POLICY project_scope_policy ON pm_runtime_overlay_state
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );

-- End of migration 0030.
