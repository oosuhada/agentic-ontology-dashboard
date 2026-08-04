-- Predictive Maintenance Canonical v3 compatibility and ontology lineage.
-- Additive only: 0011 remains immutable for already-migrated environments.

CREATE TABLE IF NOT EXISTS pm_result_artifacts (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    artifact_id text NOT NULL,
    prediction_id text NOT NULL,
    prediction_result_id text NOT NULL REFERENCES prediction_results(prediction_id) ON DELETE CASCADE,
    asset_id text NOT NULL,
    asset_type text NOT NULL CHECK (asset_type IN ('compressor','cnc')),
    observed_at timestamptz NOT NULL,
    prediction_horizon_hours integer NOT NULL CHECK (prediction_horizon_hours > 0),
    prediction_task text NOT NULL CHECK (prediction_task = 'binary_failure_within_horizon'),
    failure_probability double precision NOT NULL CHECK (failure_probability BETWEEN 0 AND 1),
    predicted_failure_type text NOT NULL CHECK (
        predicted_failure_type IN ('failure_risk','no_significant_risk')
    ),
    status_grade text NOT NULL CHECK (
        status_grade IN ('normal','attention','warning','critical')
    ),
    confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    top_factors jsonb NOT NULL,
    recommended_action jsonb NOT NULL,
    provenance jsonb NOT NULL,
    schema_version text NOT NULL CHECK (schema_version = 'result-artifact-v1.0'),
    model_version text NOT NULL,
    source_sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, artifact_id),
    UNIQUE (dataset_version_id, asset_id),
    FOREIGN KEY (dataset_version_id, asset_id)
        REFERENCES pm_assets(dataset_version_id, asset_id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_version_id, prediction_id)
        REFERENCES pm_prediction_snapshots(dataset_version_id, prediction_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_result_artifacts_scope_status
    ON pm_result_artifacts(
        organization_id,project_id,workspace_id,dataset_version_id,status_grade,
        failure_probability DESC,observed_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_pm_result_artifacts_asset_time
    ON pm_result_artifacts(project_id,dataset_version_id,asset_id,observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_result_artifacts_payload
    ON pm_result_artifacts USING gin(top_factors,recommended_action,provenance);

ALTER TABLE ontology_objects ADD COLUMN IF NOT EXISTS dataset_id text REFERENCES datasets(id) ON DELETE CASCADE;
ALTER TABLE ontology_objects ADD COLUMN IF NOT EXISTS dataset_version_id text REFERENCES dataset_versions(id) ON DELETE CASCADE;
ALTER TABLE ontology_objects ADD COLUMN IF NOT EXISTS source_sha256 text;
ALTER TABLE ontology_links ADD COLUMN IF NOT EXISTS dataset_id text REFERENCES datasets(id) ON DELETE CASCADE;
ALTER TABLE ontology_links ADD COLUMN IF NOT EXISTS dataset_version_id text REFERENCES dataset_versions(id) ON DELETE CASCADE;
ALTER TABLE ontology_links ADD COLUMN IF NOT EXISTS source_sha256 text;
ALTER TABLE ontology_ingestion_runs ADD COLUMN IF NOT EXISTS dataset_id text REFERENCES datasets(id) ON DELETE CASCADE;
ALTER TABLE ontology_ingestion_runs ADD COLUMN IF NOT EXISTS dataset_version_id text REFERENCES dataset_versions(id) ON DELETE CASCADE;
ALTER TABLE ontology_ingestion_runs ADD COLUMN IF NOT EXISTS mapping_version text;
ALTER TABLE ontology_ingestion_runs ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'completed';
ALTER TABLE ontology_ingestion_runs ADD COLUMN IF NOT EXISTS materialization_checksum_sha256 text;

CREATE INDEX IF NOT EXISTS idx_ontology_objects_dataset_version
    ON ontology_objects(organization_id,project_id,workspace_id,dataset_version_id,object_type,object_id);
CREATE INDEX IF NOT EXISTS idx_ontology_links_dataset_version
    ON ontology_links(organization_id,project_id,workspace_id,dataset_version_id,link_type,link_id);
CREATE INDEX IF NOT EXISTS idx_ontology_ingestion_dataset_version
    ON ontology_ingestion_runs(organization_id,project_id,workspace_id,dataset_version_id,completed_at DESC);

CREATE TABLE IF NOT EXISTS ontology_materialization_mappings (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    mapping_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft','approved','superseded')),
    mapping_json jsonb NOT NULL,
    approved_by text,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(dataset_version_id,mapping_version)
);
CREATE INDEX IF NOT EXISTS idx_ontology_materialization_mapping_scope
    ON ontology_materialization_mappings(
        organization_id,project_id,workspace_id,dataset_version_id,status,updated_at DESC
    );

ALTER TABLE pm_result_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pm_result_artifacts FORCE ROW LEVEL SECURITY;
ALTER TABLE ontology_materialization_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_materialization_mappings FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_scope_policy ON pm_result_artifacts;
CREATE POLICY project_scope_policy ON pm_result_artifacts
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );

DROP POLICY IF EXISTS project_scope_policy ON ontology_materialization_mappings;
CREATE POLICY project_scope_policy ON ontology_materialization_mappings
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );

-- End of migration 0012.
