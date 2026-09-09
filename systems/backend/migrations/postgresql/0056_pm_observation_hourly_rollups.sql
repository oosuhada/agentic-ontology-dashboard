CREATE TABLE IF NOT EXISTS pm_observation_hourly_rollups (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    asset_id text NOT NULL,
    asset_type text NOT NULL CHECK (asset_type IN ('compressor','cnc')),
    bucket_start timestamptz NOT NULL,
    site_id text NOT NULL,
    cell_id text NOT NULL,
    is_operating boolean NOT NULL,
    sample_count integer NOT NULL CHECK (sample_count > 0),
    source_sha256 text NOT NULL,
    measurements_json jsonb NOT NULL,
    derived_measures_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    refreshed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id,asset_id,asset_type,bucket_start),
    FOREIGN KEY (
        organization_id,project_id,workspace_id,dataset_version_id,asset_id
    ) REFERENCES pm_assets(
        organization_id,project_id,workspace_id,dataset_version_id,asset_id
    ) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_observation_hourly_rollups_scope_time
    ON pm_observation_hourly_rollups(
        project_id,dataset_version_id,asset_type,bucket_start DESC,asset_id
    );

ALTER TABLE pm_observation_hourly_rollups ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_scope_policy ON pm_observation_hourly_rollups;
CREATE POLICY project_scope_policy ON pm_observation_hourly_rollups
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );

COMMENT ON TABLE pm_observation_hourly_rollups IS
    'Persistent one-hour observation rollups used for 30-90 day Reliability history queries. Raw observations remain authoritative.';
