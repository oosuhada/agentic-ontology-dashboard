CREATE TABLE IF NOT EXISTS pipeline_definitions (
  id text NOT NULL, version integer NOT NULL, organization_id text NOT NULL,
  project_id text NOT NULL, branch_id text NOT NULL, status text NOT NULL,
  graph_json jsonb NOT NULL, created_at timestamptz NOT NULL,
  PRIMARY KEY(organization_id,project_id,id,version,branch_id)
);
CREATE TABLE IF NOT EXISTS pipeline_materializations (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  pipeline_id text NOT NULL, pipeline_version integer NOT NULL, state text NOT NULL,
  output_dataset_version_id text, rows_written bigint NOT NULL, quality_state text NOT NULL,
  created_at timestamptz NOT NULL
);
ALTER TABLE pipeline_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_materializations ENABLE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['pipeline_definitions','pipeline_materializations'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_tenant ON %I',t,t);
    EXECUTE format($p$CREATE POLICY %I_tenant ON %I USING (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true)) WITH CHECK (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true))$p$,t,t);
  END LOOP;
END $$;

