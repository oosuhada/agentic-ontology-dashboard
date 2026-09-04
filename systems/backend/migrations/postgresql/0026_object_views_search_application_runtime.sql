CREATE TABLE IF NOT EXISTS object_view_definitions (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  object_type_id text NOT NULL, interface_id text, form_factor text NOT NULL,
  status text NOT NULL, branch_id text NOT NULL, definition_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  UNIQUE(organization_id,project_id,object_type_id,form_factor,branch_id)
);
CREATE TABLE IF NOT EXISTS saved_object_perspectives (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  owner_user_id text NOT NULL, name text NOT NULL, object_type_id text NOT NULL,
  query_json jsonb NOT NULL, columns_json jsonb NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS application_runtime_definitions (
  id text NOT NULL, version integer NOT NULL, organization_id text NOT NULL,
  project_id text NOT NULL, status text NOT NULL, branch_id text NOT NULL,
  definition_json jsonb NOT NULL, created_at timestamptz NOT NULL,
  PRIMARY KEY(organization_id,project_id,id,version,branch_id)
);
ALTER TABLE object_view_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_object_perspectives ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_runtime_definitions ENABLE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['object_view_definitions','saved_object_perspectives','application_runtime_definitions'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_tenant ON %I', t, t);
    EXECUTE format($p$CREATE POLICY %I_tenant ON %I USING (
      organization_id=current_setting('app.organization_id',true)
      AND project_id=current_setting('app.project_id',true)
    ) WITH CHECK (
      organization_id=current_setting('app.organization_id',true)
      AND project_id=current_setting('app.project_id',true)
    )$p$, t, t);
  END LOOP;
END $$;
