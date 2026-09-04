CREATE TABLE IF NOT EXISTS modeling_intake_profiles (
    profile_id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
    workspace_id text NOT NULL, dataset_version_id text, parent_id text, checksum_sha256 text,
    artifact_uri text, status text NOT NULL, revision integer NOT NULL DEFAULT 1,
    idempotency_key text, payload_json jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id,project_id,workspace_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS modeling_manifest_drafts (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_manifest_drafts RENAME COLUMN profile_id TO draft_id;
CREATE TABLE IF NOT EXISTS modeling_mapping_sets (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_mapping_sets RENAME COLUMN profile_id TO mapping_set_id;
CREATE TABLE IF NOT EXISTS modeling_feature_recipe_sets (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_feature_recipe_sets RENAME COLUMN profile_id TO recipe_set_id;
CREATE TABLE IF NOT EXISTS modeling_feature_dataset_versions (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_feature_dataset_versions RENAME COLUMN profile_id TO feature_dataset_version_id;
CREATE TABLE IF NOT EXISTS modeling_experiment_runs (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_experiment_runs RENAME COLUMN profile_id TO experiment_id;
CREATE TABLE IF NOT EXISTS modeling_model_versions (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_model_versions RENAME COLUMN profile_id TO model_version_id;
CREATE TABLE IF NOT EXISTS modeling_explanation_artifacts (LIKE modeling_intake_profiles INCLUDING ALL);
ALTER TABLE modeling_explanation_artifacts RENAME COLUMN profile_id TO explanation_id;

CREATE TABLE IF NOT EXISTS modeling_audit_log (
    id bigserial PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
    workspace_id text NOT NULL, actor_id text NOT NULL, action text NOT NULL,
    aggregate_type text NOT NULL, aggregate_id text NOT NULL, payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'modeling_intake_profiles','modeling_manifest_drafts','modeling_mapping_sets',
        'modeling_feature_recipe_sets','modeling_feature_dataset_versions',
        'modeling_experiment_runs','modeling_model_versions','modeling_explanation_artifacts',
        'modeling_audit_log'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('DROP POLICY IF EXISTS project_scope_policy ON %I',table_name);
        EXECUTE format(
            'CREATE POLICY project_scope_policy ON %I USING (' ||
            'organization_id=current_setting(''app.organization_id'',true) AND ' ||
            'project_id=current_setting(''app.project_id'',true)) WITH CHECK (' ||
            'organization_id=current_setting(''app.organization_id'',true) AND ' ||
            'project_id=current_setting(''app.project_id'',true))',table_name
        );
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_modeling_profiles_scope ON modeling_intake_profiles(organization_id,project_id,workspace_id,created_at);
CREATE INDEX IF NOT EXISTS idx_modeling_mapping_dataset ON modeling_mapping_sets(organization_id,project_id,dataset_version_id,status);
CREATE INDEX IF NOT EXISTS idx_modeling_recipe_dataset ON modeling_feature_recipe_sets(organization_id,project_id,dataset_version_id,status);
CREATE INDEX IF NOT EXISTS idx_modeling_experiments_scope ON modeling_experiment_runs(organization_id,project_id,workspace_id,status,created_at);
CREATE INDEX IF NOT EXISTS idx_modeling_models_scope ON modeling_model_versions(organization_id,project_id,workspace_id,status,created_at);
