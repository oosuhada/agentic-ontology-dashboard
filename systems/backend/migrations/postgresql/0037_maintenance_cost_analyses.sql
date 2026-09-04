-- Append-only decision-support snapshots. This table cannot authorize or create
-- Recommendations, Decisions, Work Orders, or Maintenance Actions.

CREATE TABLE IF NOT EXISTS closed_loop_maintenance_cost_analyses (
  analysis_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  event_id text NOT NULL,
  asset_id text NOT NULL,
  equipment_id text NOT NULL,
  inspection_work_order_id text NOT NULL
    REFERENCES closed_loop_work_orders(work_order_id),
  inspection_result_id text NOT NULL
    REFERENCES closed_loop_inspection_results(inspection_result_id),
  action_candidate_id text NOT NULL,
  action_code text NOT NULL CHECK(action_code='TOOL_REPLACEMENT'),
  calculation_status text NOT NULL CHECK(
    calculation_status IN ('calculated','insufficient')
  ),
  result_json jsonb NOT NULL,
  request_idempotency_key text NOT NULL,
  request_fingerprint text NOT NULL,
  created_by text NOT NULL,
  calculated_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,request_idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_closed_loop_cost_analyses_inspection
  ON closed_loop_maintenance_cost_analyses(
    organization_id,project_id,workspace_id,inspection_result_id,calculated_at
  );

CREATE INDEX IF NOT EXISTS idx_closed_loop_cost_analyses_event
  ON closed_loop_maintenance_cost_analyses(
    organization_id,project_id,workspace_id,event_id,calculated_at
  );

ALTER TABLE closed_loop_maintenance_cost_analyses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS closed_loop_maintenance_cost_analyses_scope
  ON closed_loop_maintenance_cost_analyses;
DROP POLICY IF EXISTS closed_loop_maintenance_cost_analyses_scope_select
  ON closed_loop_maintenance_cost_analyses;
DROP POLICY IF EXISTS closed_loop_maintenance_cost_analyses_scope_insert
  ON closed_loop_maintenance_cost_analyses;

CREATE POLICY closed_loop_maintenance_cost_analyses_scope_select
  ON closed_loop_maintenance_cost_analyses
  FOR SELECT
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

CREATE POLICY closed_loop_maintenance_cost_analyses_scope_insert
  ON closed_loop_maintenance_cost_analyses
  FOR INSERT
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

CREATE OR REPLACE FUNCTION reject_maintenance_cost_analysis_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'maintenance cost analysis snapshots are append-only';
END;
$$;

DROP TRIGGER IF EXISTS closed_loop_maintenance_cost_analyses_reject_mutation
  ON closed_loop_maintenance_cost_analyses;
CREATE TRIGGER closed_loop_maintenance_cost_analyses_reject_mutation
BEFORE UPDATE OR DELETE ON closed_loop_maintenance_cost_analyses
FOR EACH ROW
EXECUTE FUNCTION reject_maintenance_cost_analysis_mutation();
