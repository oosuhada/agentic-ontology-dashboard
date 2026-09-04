ALTER TABLE closed_loop_work_orders
  ADD COLUMN asset_type TEXT NOT NULL DEFAULT 'legacy_unknown';

CREATE TABLE closed_loop_inspection_results (
  inspection_result_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL UNIQUE,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK(
    outcome IN ('no_action_required','maintenance_recommended','data_check_required')
  ),
  checklist_json TEXT NOT NULL,
  measurements_json TEXT NOT NULL,
  findings_json TEXT NOT NULL,
  note TEXT NOT NULL,
  recorded_by TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  FOREIGN KEY(work_order_id) REFERENCES closed_loop_work_orders(work_order_id)
);

CREATE INDEX idx_closed_loop_inspection_results_event
  ON closed_loop_inspection_results(
    organization_id,project_id,workspace_id,event_id,recorded_at
  );
