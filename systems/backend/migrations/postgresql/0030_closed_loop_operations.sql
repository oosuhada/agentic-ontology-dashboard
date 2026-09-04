CREATE TABLE IF NOT EXISTS closed_loop_recommendations (
  recommendation_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  event_id text NOT NULL,
  asset_id text NOT NULL,
  equipment_id text NOT NULL,
  recommendation_origin text NOT NULL CHECK(recommendation_origin='product_result_projection'),
  status text NOT NULL CHECK(status IN ('proposed','accepted','rejected','deferred','superseded')),
  source_action_id text NOT NULL,
  source_product_result_id text NOT NULL,
  source_evidence_id text NOT NULL,
  source_schema_version text NOT NULL,
  source_policy_version text NOT NULL,
  label text NOT NULL,
  kind text NOT NULL,
  requires_human_approval boolean NOT NULL,
  basis_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,source_product_result_id,source_action_id)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_recommendations_event
  ON closed_loop_recommendations(organization_id,project_id,workspace_id,event_id,created_at);

CREATE TABLE IF NOT EXISTS closed_loop_recommendation_decisions (
  decision_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  event_id text NOT NULL,
  recommendation_id text NOT NULL REFERENCES closed_loop_recommendations(recommendation_id),
  disposition text NOT NULL CHECK(disposition IN ('accept','reject','defer')),
  actor_id text NOT NULL,
  note text NOT NULL DEFAULT '',
  decided_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_decisions_event
  ON closed_loop_recommendation_decisions(organization_id,project_id,workspace_id,event_id,decided_at);

CREATE TABLE IF NOT EXISTS closed_loop_work_orders (
  work_order_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  event_id text NOT NULL,
  asset_id text NOT NULL,
  equipment_id text NOT NULL,
  work_type text NOT NULL CHECK(work_type IN ('inspection','maintenance')),
  status text NOT NULL CHECK(status IN ('requested','approved','in_progress','completed','blocked','failed','cancelled')),
  idempotency_key text NOT NULL,
  authorization_json jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_work_orders_event
  ON closed_loop_work_orders(organization_id,project_id,workspace_id,event_id,created_at);

CREATE TABLE IF NOT EXISTS closed_loop_maintenance_actions (
  maintenance_action_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  work_order_id text NOT NULL REFERENCES closed_loop_work_orders(work_order_id),
  event_id text NOT NULL,
  asset_id text NOT NULL,
  equipment_id text NOT NULL,
  recommendation_id text NOT NULL REFERENCES closed_loop_recommendations(recommendation_id),
  recommendation_decision_id text NOT NULL REFERENCES closed_loop_recommendation_decisions(decision_id),
  simulation_session_id text NOT NULL,
  action_code text NOT NULL CHECK(action_code='TOOL_REPLACEMENT'),
  lifecycle_state_version integer NOT NULL DEFAULT 0 CHECK(lifecycle_state_version >= 0),
  status text NOT NULL CHECK(status IN ('planned','in_progress','completed','failed','cancelled')),
  idempotency_key text NOT NULL,
  started_at timestamptz,
  completed_at timestamptz,
  restart_at timestamptz,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK(asset_id=equipment_id),
  UNIQUE(organization_id,project_id,workspace_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_actions_event
  ON closed_loop_maintenance_actions(organization_id,project_id,workspace_id,event_id,created_at);

CREATE TABLE IF NOT EXISTS closed_loop_maintenance_events (
  maintenance_event_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  maintenance_action_id text NOT NULL UNIQUE REFERENCES closed_loop_maintenance_actions(maintenance_action_id),
  work_order_id text NOT NULL REFERENCES closed_loop_work_orders(work_order_id),
  event_id text NOT NULL,
  asset_id text NOT NULL,
  equipment_id text NOT NULL,
  recommendation_id text NOT NULL,
  recommendation_decision_id text NOT NULL,
  simulation_session_id text NOT NULL,
  action_code text NOT NULL CHECK(action_code='TOOL_REPLACEMENT'),
  state_patch_json jsonb NOT NULL,
  maintenance_started_at timestamptz NOT NULL,
  completed_at timestamptz NOT NULL,
  outcome text NOT NULL,
  created_at timestamptz NOT NULL,
  CHECK(asset_id=equipment_id)
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_maintenance_events_equipment
  ON closed_loop_maintenance_events(organization_id,project_id,workspace_id,equipment_id,completed_at);

CREATE TABLE IF NOT EXISTS closed_loop_equipment_state (
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  equipment_id text NOT NULL,
  state_version integer NOT NULL CHECK(state_version >= 1),
  state_json jsonb NOT NULL,
  last_maintenance_event_id text NOT NULL REFERENCES closed_loop_maintenance_events(maintenance_event_id),
  updated_at timestamptz NOT NULL,
  PRIMARY KEY(organization_id,project_id,workspace_id,equipment_id)
);

CREATE TABLE IF NOT EXISTS closed_loop_activities (
  activity_id text PRIMARY KEY,
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  event_id text NOT NULL,
  equipment_id text,
  recommendation_id text,
  work_order_id text,
  maintenance_action_id text,
  maintenance_event_id text,
  aggregate_type text NOT NULL,
  aggregate_id text NOT NULL,
  activity_type text NOT NULL,
  actor_user_id text NOT NULL,
  actor_display_name text NOT NULL,
  before_status text,
  after_status text,
  timeline_order integer NOT NULL,
  payload_json jsonb NOT NULL,
  created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_closed_loop_activities_event
  ON closed_loop_activities(organization_id,project_id,workspace_id,event_id,created_at,timeline_order);

CREATE TABLE IF NOT EXISTS closed_loop_idempotency_records (
  organization_id text NOT NULL,
  project_id text NOT NULL,
  workspace_id text NOT NULL,
  idempotency_key text NOT NULL,
  command_type text NOT NULL,
  request_fingerprint text NOT NULL,
  state text NOT NULL CHECK(state IN ('running','succeeded','failed')),
  response_json jsonb,
  last_error text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY(organization_id,project_id,workspace_id,idempotency_key)
);

ALTER TABLE closed_loop_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_recommendation_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_work_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_maintenance_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_maintenance_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_equipment_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE closed_loop_idempotency_records ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY[
  'closed_loop_recommendations',
  'closed_loop_recommendation_decisions',
  'closed_loop_work_orders',
  'closed_loop_maintenance_actions',
  'closed_loop_maintenance_events',
  'closed_loop_equipment_state',
  'closed_loop_activities',
  'closed_loop_idempotency_records'
] LOOP
EXECUTE format('DROP POLICY IF EXISTS %I_tenant ON %I',t,t);
EXECUTE format($p$CREATE POLICY %I_tenant ON %I USING (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true)) WITH CHECK (organization_id=current_setting('app.organization_id',true) AND project_id=current_setting('app.project_id',true))$p$,t,t); END LOOP; END $$;
