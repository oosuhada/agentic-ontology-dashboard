CREATE TABLE IF NOT EXISTS feature_views (
  id text NOT NULL, version integer NOT NULL, organization_id text NOT NULL,
  project_id text NOT NULL, status text NOT NULL, definition_json jsonb NOT NULL,
  created_at timestamptz NOT NULL, PRIMARY KEY(organization_id,project_id,id,version)
);
CREATE TABLE IF NOT EXISTS model_deployments (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  model_version_id text NOT NULL, mode text NOT NULL, traffic_percent double precision NOT NULL,
  state text NOT NULL, rollback_target_id text, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS model_drift_observations (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  model_version_id text NOT NULL, metric text NOT NULL, value double precision NOT NULL,
  threshold double precision NOT NULL, sample_size bigint NOT NULL, state text NOT NULL,
  observed_at timestamptz NOT NULL
);
ALTER TABLE feature_views ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_deployments ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_drift_observations ENABLE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['feature_views','model_deployments','model_drift_observations'] LOOP
EXECUTE format('DROP POLICY IF EXISTS %I_tenant ON %I',t,t);
EXECUTE format($p$CREATE POLICY %I_tenant ON %I USING (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true)) WITH CHECK (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true))$p$,t,t); END LOOP; END $$;
