-- Append-only decision-support snapshots. Recommendation/approval/work commands
-- are deliberately stored in their existing Closed-loop tables, never here.

CREATE TABLE closed_loop_maintenance_cost_analyses (
  analysis_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  inspection_work_order_id TEXT NOT NULL,
  inspection_result_id TEXT NOT NULL,
  action_candidate_id TEXT NOT NULL,
  action_code TEXT NOT NULL CHECK(action_code='TOOL_REPLACEMENT'),
  calculation_status TEXT NOT NULL CHECK(
    calculation_status IN ('calculated','insufficient')
  ),
  result_json TEXT NOT NULL,
  request_idempotency_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  created_by TEXT NOT NULL,
  calculated_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,request_idempotency_key),
  FOREIGN KEY(inspection_work_order_id)
    REFERENCES closed_loop_work_orders(work_order_id),
  FOREIGN KEY(inspection_result_id)
    REFERENCES closed_loop_inspection_results(inspection_result_id)
);

CREATE INDEX idx_closed_loop_cost_analyses_inspection
  ON closed_loop_maintenance_cost_analyses(
    organization_id,project_id,workspace_id,inspection_result_id,calculated_at
  );

CREATE INDEX idx_closed_loop_cost_analyses_event
  ON closed_loop_maintenance_cost_analyses(
    organization_id,project_id,workspace_id,event_id,calculated_at
  );

CREATE TRIGGER closed_loop_maintenance_cost_analyses_reject_update
BEFORE UPDATE ON closed_loop_maintenance_cost_analyses
BEGIN
  SELECT RAISE(ABORT, 'maintenance cost analysis snapshots are append-only');
END;

CREATE TRIGGER closed_loop_maintenance_cost_analyses_reject_delete
BEFORE DELETE ON closed_loop_maintenance_cost_analyses
BEGIN
  SELECT RAISE(ABORT, 'maintenance cost analysis snapshots are append-only');
END;
