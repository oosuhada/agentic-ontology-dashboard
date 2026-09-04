ALTER TABLE closed_loop_work_orders
  ADD COLUMN IF NOT EXISTS asset_type text NOT NULL DEFAULT 'legacy_unknown';

CREATE TABLE IF NOT EXISTS closed_loop_inspection_results (
  inspection_result_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  work_order_id text NOT NULL UNIQUE REFERENCES closed_loop_work_orders(work_order_id),
  event_id text NOT NULL,
  asset_id text NOT NULL,
  equipment_id text NOT NULL,
  asset_type text NOT NULL,
  outcome text NOT NULL CHECK(
    outcome IN ('no_action_required','maintenance_recommended','data_check_required')
  ),
  checklist_json jsonb NOT NULL,
  measurements_json jsonb NOT NULL,
  findings_json jsonb NOT NULL,
  note text NOT NULL,
  recorded_by text NOT NULL,
  recorded_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL,
  CHECK(asset_id=equipment_id)
);

CREATE INDEX IF NOT EXISTS idx_closed_loop_inspection_results_event
  ON closed_loop_inspection_results(
    organization_id,project_id,workspace_id,event_id,recorded_at
  );

ALTER TABLE closed_loop_inspection_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS closed_loop_inspection_results_tenant
  ON closed_loop_inspection_results;
CREATE POLICY closed_loop_inspection_results_tenant
  ON closed_loop_inspection_results
  USING (
    organization_id=current_setting('app.organization_id',true)
    AND project_id=current_setting('app.project_id',true)
  )
  WITH CHECK (
    organization_id=current_setting('app.organization_id',true)
    AND project_id=current_setting('app.project_id',true)
  );
