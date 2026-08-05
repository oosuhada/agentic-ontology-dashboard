CREATE TABLE IF NOT EXISTS platform_branches (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  name text NOT NULL, base_branch_id text, status text NOT NULL, owner_user_id text NOT NULL,
  head_revision integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL, UNIQUE (organization_id, project_id, name)
);
CREATE TABLE IF NOT EXISTS platform_branch_resources (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  branch_id text NOT NULL, resource_type text NOT NULL, resource_id text NOT NULL,
  revision integer NOT NULL, payload_json jsonb NOT NULL, operation text NOT NULL,
  created_by text NOT NULL, created_at timestamptz NOT NULL,
  UNIQUE (organization_id, project_id, branch_id, resource_type, resource_id, revision)
);
CREATE TABLE IF NOT EXISTS platform_lineage_edges (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  branch_id text NOT NULL, source_type text NOT NULL, source_id text NOT NULL,
  target_type text NOT NULL, target_id text NOT NULL, relation text NOT NULL,
  source_field text, target_field text, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS platform_markings (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  resource_type text NOT NULL, resource_id text NOT NULL, field_name text,
  marking text NOT NULL, inherited_from text, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS platform_policy_decisions (
  id text PRIMARY KEY, organization_id text NOT NULL, project_id text NOT NULL,
  actor_user_id text NOT NULL, resource_type text NOT NULL, resource_id text NOT NULL,
  purpose text NOT NULL, decision text NOT NULL, reason_code text NOT NULL,
  created_at timestamptz NOT NULL
);

ALTER TABLE platform_branches ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_branch_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_lineage_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_markings ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform_policy_decisions ENABLE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['platform_branches','platform_branch_resources','platform_lineage_edges','platform_markings','platform_policy_decisions']
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_tenant ON %I', t, t);
    EXECUTE format($policy$CREATE POLICY %I_tenant ON %I USING (
      organization_id = current_setting('app.organization_id', true)
      AND project_id = current_setting('app.project_id', true)
    ) WITH CHECK (
      organization_id = current_setting('app.organization_id', true)
      AND project_id = current_setting('app.project_id', true)
    )$policy$, t, t);
  END LOOP;
END $$;
