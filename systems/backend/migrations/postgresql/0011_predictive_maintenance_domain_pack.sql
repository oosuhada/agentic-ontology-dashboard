-- Predictive Maintenance Canonical v2 relational source-of-truth tables.
-- Raw sensor rows stay in typed, time-partitioned fact tables. They are not
-- materialized as ontology_objects and are not stored in a JSONB mega table.

ALTER TABLE dataset_versions
    DROP CONSTRAINT IF EXISTS dataset_versions_dataset_id_source_version_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_versions_dataset_checksum
    ON dataset_versions(dataset_id, checksum_sha256);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_source_version
    ON dataset_versions(dataset_id, source_version, version_number DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_versions_scoped_id
    ON dataset_versions(id, organization_id, project_id, workspace_id);

ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS role text;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS format text;
ALTER TABLE dataset_files ADD COLUMN IF NOT EXISTS schema_json jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dataset_files_version_role
    ON dataset_files(dataset_version_id, role)
    WHERE role IS NOT NULL;

ALTER TABLE adapter_ingestion_runs ADD COLUMN IF NOT EXISTS dataset_id text REFERENCES datasets(id);
ALTER TABLE adapter_ingestion_runs ADD COLUMN IF NOT EXISTS dataset_version_id text REFERENCES dataset_versions(id);
ALTER TABLE adapter_ingestion_runs ADD COLUMN IF NOT EXISTS bundle_checksum_sha256 text;
ALTER TABLE adapter_ingestion_runs ADD COLUMN IF NOT EXISTS validation_checksum_sha256 text;
ALTER TABLE adapter_ingestion_runs ADD COLUMN IF NOT EXISTS metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_adapter_runs_bundle
    ON adapter_ingestion_runs(project_id, bundle_checksum_sha256, started_at DESC);

CREATE TABLE IF NOT EXISTS pm_assets (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    asset_id text NOT NULL,
    asset_type text NOT NULL CHECK (asset_type IN ('compressor', 'cnc')),
    site_id text NOT NULL,
    cell_id text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, asset_id),
    UNIQUE (organization_id, project_id, workspace_id, dataset_version_id, asset_id),
    FOREIGN KEY (dataset_version_id, organization_id, project_id, workspace_id)
        REFERENCES dataset_versions(id, organization_id, project_id, workspace_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_assets_scope_type
    ON pm_assets(organization_id, project_id, dataset_version_id, asset_type, site_id, cell_id);

CREATE TABLE IF NOT EXISTS pm_asset_relations (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    from_asset_id text NOT NULL,
    relation_type text NOT NULL,
    to_asset_id text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, from_asset_id, relation_type, to_asset_id),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, from_asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE,
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, to_asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_relations_from
    ON pm_asset_relations(project_id, dataset_version_id, from_asset_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_pm_relations_to
    ON pm_asset_relations(project_id, dataset_version_id, to_asset_id, relation_type);

CREATE TABLE IF NOT EXISTS pm_compressor_observations (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    observed_at timestamptz NOT NULL,
    asset_id text NOT NULL,
    site_id text NOT NULL,
    cell_id text NOT NULL,
    is_operating boolean NOT NULL,
    operating_state text NOT NULL,
    voltage_raw double precision NOT NULL,
    rotation_raw double precision NOT NULL,
    pressure_raw double precision NOT NULL,
    vibration_raw double precision NOT NULL,
    relative_vibration_z double precision NOT NULL,
    relative_vibration_zone text NOT NULL,
    generator_version text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, asset_id, observed_at),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
) PARTITION BY RANGE (observed_at);
CREATE TABLE IF NOT EXISTS pm_compressor_observations_default
    PARTITION OF pm_compressor_observations DEFAULT;
CREATE INDEX IF NOT EXISTS idx_pm_compressor_asset_time
    ON pm_compressor_observations(project_id, dataset_version_id, asset_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_compressor_site_time
    ON pm_compressor_observations(project_id, dataset_version_id, site_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS pm_cnc_observations (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    observed_at timestamptz NOT NULL,
    asset_id text NOT NULL,
    site_id text NOT NULL,
    cell_id text NOT NULL,
    is_operating boolean NOT NULL,
    operating_state text NOT NULL,
    product_type text NOT NULL,
    air_temperature_k double precision NOT NULL,
    process_temperature_k double precision NOT NULL,
    rotational_speed_rpm double precision NOT NULL,
    torque_nm double precision NOT NULL,
    tool_wear_min double precision NOT NULL,
    generator_version text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, asset_id, observed_at),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
) PARTITION BY RANGE (observed_at);
CREATE TABLE IF NOT EXISTS pm_cnc_observations_default
    PARTITION OF pm_cnc_observations DEFAULT;
CREATE INDEX IF NOT EXISTS idx_pm_cnc_asset_time
    ON pm_cnc_observations(project_id, dataset_version_id, asset_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_cnc_site_time
    ON pm_cnc_observations(project_id, dataset_version_id, site_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS pm_production_cycles (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    product_id text NOT NULL,
    cnc_asset_id text NOT NULL,
    cycle_started_at timestamptz NOT NULL,
    cycle_completed_at timestamptz NOT NULL,
    product_type text NOT NULL,
    cutting_minutes double precision NOT NULL,
    tool_wear_increment_min double precision NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, product_id),
    CHECK (cycle_completed_at > cycle_started_at),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, cnc_asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_cycles_asset_time
    ON pm_production_cycles(project_id, dataset_version_id, cnc_asset_id, cycle_completed_at DESC);

CREATE TABLE IF NOT EXISTS pm_maintenance_events (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    maintenance_id text NOT NULL,
    asset_id text NOT NULL,
    maintenance_type text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    tool_replaced boolean NOT NULL,
    source_event_id text,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, maintenance_id),
    CHECK (completed_at > started_at),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_maintenance_asset_time
    ON pm_maintenance_events(project_id, dataset_version_id, asset_id, started_at DESC);

CREATE TABLE IF NOT EXISTS pm_prediction_snapshots (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    prediction_id text NOT NULL,
    prediction_result_id text NOT NULL REFERENCES prediction_results(prediction_id) ON DELETE CASCADE,
    asset_id text NOT NULL,
    asset_type text NOT NULL,
    observed_at timestamptz NOT NULL,
    prediction_horizon_hours integer NOT NULL,
    failure_probability double precision NOT NULL,
    predicted_failure_type text,
    confidence double precision NOT NULL,
    status text NOT NULL,
    model_version text NOT NULL,
    feature_scope jsonb NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, prediction_id),
    UNIQUE (prediction_result_id),
    CHECK (failure_probability >= 0 AND failure_probability <= 1),
    CHECK (confidence >= 0 AND confidence <= 1),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_snapshot_asset_time
    ON pm_prediction_snapshots(project_id, dataset_version_id, asset_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS pm_prediction_factors (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    prediction_id text NOT NULL,
    rank integer NOT NULL,
    feature text NOT NULL,
    feature_value double precision NOT NULL,
    signed_contribution double precision NOT NULL,
    absolute_contribution double precision NOT NULL,
    direction text NOT NULL,
    explanation_method text NOT NULL,
    source_type text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, prediction_id, rank),
    FOREIGN KEY (dataset_version_id, prediction_id)
        REFERENCES pm_prediction_snapshots(dataset_version_id, prediction_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_factors_prediction
    ON pm_prediction_factors(project_id, dataset_version_id, prediction_id, rank);

CREATE TABLE IF NOT EXISTS pm_prediction_timeline (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL,
    prediction_id text NOT NULL,
    asset_id text NOT NULL,
    asset_type text NOT NULL,
    observed_at timestamptz NOT NULL,
    prediction_horizon_hours integer NOT NULL,
    failure_probability double precision NOT NULL,
    status text NOT NULL,
    top_factors jsonb NOT NULL,
    model_version text NOT NULL,
    feature_scope jsonb NOT NULL,
    source_type text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, prediction_id),
    CHECK (failure_probability >= 0 AND failure_probability <= 1),
    FOREIGN KEY (
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) REFERENCES pm_assets(
        organization_id, project_id, workspace_id, dataset_version_id, asset_id
    ) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pm_timeline_asset_time
    ON pm_prediction_timeline(project_id, dataset_version_id, asset_id, observed_at DESC);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'pm_assets',
        'pm_asset_relations',
        'pm_compressor_observations',
        'pm_compressor_observations_default',
        'pm_cnc_observations',
        'pm_cnc_observations_default',
        'pm_production_cycles',
        'pm_maintenance_events',
        'pm_prediction_snapshots',
        'pm_prediction_factors',
        'pm_prediction_timeline'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS project_scope_policy ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY project_scope_policy ON %I USING (' ||
            'organization_id = current_setting(''app.organization_id'', true) ' ||
            'AND project_id = current_setting(''app.project_id'', true)) ' ||
            'WITH CHECK (organization_id = current_setting(''app.organization_id'', true) ' ||
            'AND project_id = current_setting(''app.project_id'', true))',
            table_name
        );
    END LOOP;
END $$;

COMMENT ON TABLE pm_compressor_observations IS
    'Typed compressor time-series facts. Monthly partitions are created by the bundle ingestor.';
COMMENT ON TABLE pm_cnc_observations IS
    'Typed CNC time-series facts. Monthly partitions are created by the bundle ingestor.';
COMMENT ON COLUMN pm_prediction_snapshots.prediction_result_id IS
    'Deterministic Project 2 Prediction Result Contract identity for this immutable Dataset Version.';
