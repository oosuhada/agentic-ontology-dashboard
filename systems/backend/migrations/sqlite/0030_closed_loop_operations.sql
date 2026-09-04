CREATE TABLE IF NOT EXISTS closed_loop_recommendations (
  recommendation_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  recommendation_origin TEXT NOT NULL CHECK(recommendation_origin='product_result_projection'),
  status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected','deferred','superseded')),
  source_action_id TEXT NOT NULL,
  source_product_result_id TEXT NOT NULL,
  source_evidence_id TEXT NOT NULL,
  source_schema_version TEXT NOT NULL,
  source_policy_version TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  requires_human_approval INTEGER NOT NULL CHECK(requires_human_approval IN (0,1)),
  basis_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,source_product_result_id,source_action_id)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_recommendations_event
  ON closed_loop_recommendations(organization_id,project_id,workspace_id,event_id,created_at);

CREATE TABLE IF NOT EXISTS closed_loop_recommendation_decisions (
  decision_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  recommendation_id TEXT NOT NULL,
  disposition TEXT NOT NULL CHECK(disposition IN ('accept','reject','defer')),
  actor_id TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  decided_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(recommendation_id) REFERENCES closed_loop_recommendations(recommendation_id)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_decisions_event
  ON closed_loop_recommendation_decisions(organization_id,project_id,workspace_id,event_id,decided_at);

CREATE TABLE IF NOT EXISTS closed_loop_work_orders (
  work_order_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  work_type TEXT NOT NULL CHECK(work_type IN ('inspection','maintenance')),
  status TEXT NOT NULL CHECK(status IN ('requested','approved','in_progress','completed','blocked','failed','cancelled')),
  idempotency_key TEXT NOT NULL,
  authorization_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_work_orders_event
  ON closed_loop_work_orders(organization_id,project_id,workspace_id,event_id,created_at);

CREATE TABLE IF NOT EXISTS closed_loop_maintenance_actions (
  maintenance_action_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  work_order_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  recommendation_id TEXT NOT NULL,
  recommendation_decision_id TEXT NOT NULL,
  simulation_session_id TEXT NOT NULL,
  action_code TEXT NOT NULL CHECK(action_code='TOOL_REPLACEMENT'),
  lifecycle_state_version INTEGER NOT NULL DEFAULT 0 CHECK(lifecycle_state_version >= 0),
  status TEXT NOT NULL CHECK(status IN ('planned','in_progress','completed','failed','cancelled')),
  idempotency_key TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  restart_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,idempotency_key),
  FOREIGN KEY(work_order_id) REFERENCES closed_loop_work_orders(work_order_id),
  FOREIGN KEY(recommendation_id) REFERENCES closed_loop_recommendations(recommendation_id),
  FOREIGN KEY(recommendation_decision_id) REFERENCES closed_loop_recommendation_decisions(decision_id)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_actions_event
  ON closed_loop_maintenance_actions(organization_id,project_id,workspace_id,event_id,created_at);

CREATE TABLE IF NOT EXISTS closed_loop_maintenance_events (
  maintenance_event_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  maintenance_action_id TEXT NOT NULL UNIQUE,
  work_order_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  recommendation_id TEXT NOT NULL,
  recommendation_decision_id TEXT NOT NULL,
  simulation_session_id TEXT NOT NULL,
  action_code TEXT NOT NULL CHECK(action_code='TOOL_REPLACEMENT'),
  state_patch_json TEXT NOT NULL,
  maintenance_started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  FOREIGN KEY(maintenance_action_id) REFERENCES closed_loop_maintenance_actions(maintenance_action_id),
  FOREIGN KEY(work_order_id) REFERENCES closed_loop_work_orders(work_order_id)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_maintenance_events_equipment
  ON closed_loop_maintenance_events(organization_id,project_id,workspace_id,equipment_id,completed_at);

CREATE TABLE IF NOT EXISTS closed_loop_equipment_state (
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK(state_version >= 1),
  state_json TEXT NOT NULL,
  last_maintenance_event_id TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(organization_id,project_id,workspace_id,equipment_id),
  FOREIGN KEY(last_maintenance_event_id) REFERENCES closed_loop_maintenance_events(maintenance_event_id)
);

CREATE TABLE IF NOT EXISTS closed_loop_activities (
  activity_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  equipment_id TEXT,
  recommendation_id TEXT,
  work_order_id TEXT,
  maintenance_action_id TEXT,
  maintenance_event_id TEXT,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  actor_user_id TEXT NOT NULL,
  actor_display_name TEXT NOT NULL,
  before_status TEXT,
  after_status TEXT,
  timeline_order INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_activities_event
  ON closed_loop_activities(organization_id,project_id,workspace_id,event_id,created_at,timeline_order);

CREATE TABLE IF NOT EXISTS closed_loop_idempotency_records (
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  command_type TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('running','succeeded','failed')),
  response_json TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(organization_id,project_id,workspace_id,idempotency_key)
);
