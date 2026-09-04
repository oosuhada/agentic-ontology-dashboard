-- Project/workspace-scoped operational context promoted from static reference data.
-- Dynamic records (materials, maintenance history, meetings, decisions, KPIs) can
-- be updated independently while stable company/product masters retain the same API.

CREATE TABLE IF NOT EXISTS company_context_records (
    record_id text PRIMARY KEY,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    record_type text NOT NULL,
    record_key text NOT NULL,
    payload_json text NOT NULL,
    source_ref text NOT NULL,
    source_updated_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (organization_id, project_id, workspace_id, record_type, record_key)
);

CREATE INDEX IF NOT EXISTS idx_company_context_scope_type
  ON company_context_records (organization_id, project_id, workspace_id, record_type, updated_at DESC);

ALTER TABLE company_context_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS company_context_records_scope ON company_context_records;
CREATE POLICY company_context_records_scope
  ON company_context_records
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );
