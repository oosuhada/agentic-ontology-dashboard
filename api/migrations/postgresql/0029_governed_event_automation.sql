CREATE TABLE IF NOT EXISTS automation_definitions (
  id text NOT NULL, version integer NOT NULL, organization_id text NOT NULL,
  project_id text NOT NULL, status text NOT NULL, definition_json jsonb NOT NULL,
  created_at timestamptz NOT NULL, PRIMARY KEY(organization_id,project_id,id,version)
);
CREATE TABLE IF NOT EXISTS automation_runs (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  automation_id text NOT NULL, automation_version integer NOT NULL, event_id text NOT NULL,
  state text NOT NULL, simulation boolean NOT NULL, approval_state text NOT NULL,
  trace_json jsonb NOT NULL, created_at timestamptz NOT NULL,
  UNIQUE(organization_id,project_id,automation_id,event_id)
);
ALTER TABLE automation_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_runs ENABLE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['automation_definitions','automation_runs'] LOOP
EXECUTE format('DROP POLICY IF EXISTS %I_tenant ON %I',t,t);
EXECUTE format($p$CREATE POLICY %I_tenant ON %I USING (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true)) WITH CHECK (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true))$p$,t,t); END LOOP; END $$;

