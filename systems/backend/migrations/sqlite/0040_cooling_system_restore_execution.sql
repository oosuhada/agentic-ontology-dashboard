-- Extend Operations recommendation and execution persistence for the cooling
-- slice while preserving existing foreign-key targets during table rebuilds.

PRAGMA foreign_keys=OFF;
PRAGMA legacy_alter_table=ON;

DROP INDEX IF EXISTS idx_closed_loop_recommendations_event;
DROP INDEX IF EXISTS uq_closed_loop_operations_manual_source;
DROP INDEX IF EXISTS idx_closed_loop_recommendations_cost_source;
DROP TRIGGER IF EXISTS closed_loop_recommendation_cost_lineage_insert;
DROP TRIGGER IF EXISTS closed_loop_recommendation_cost_lineage_update;

ALTER TABLE closed_loop_recommendations
  RENAME TO closed_loop_recommendations_legacy;

CREATE TABLE closed_loop_recommendations (
  recommendation_id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  equipment_id TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  recommendation_origin TEXT NOT NULL CHECK(
    recommendation_origin IN ('product_result_projection','operations_manual')
  ),
  status TEXT NOT NULL CHECK(
    status IN ('proposed','accepted','rejected','deferred','superseded')
  ),
  materialization_strategy TEXT NOT NULL DEFAULT 'runtime_generated' CHECK(
    materialization_strategy IN ('runtime_generated','imported_precomputed')
  ),
  source_action_id TEXT NOT NULL,
  source_product_result_id TEXT NOT NULL,
  source_evidence_id TEXT NOT NULL,
  source_schema_version TEXT NOT NULL,
  source_policy_version TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  requires_human_approval INTEGER NOT NULL CHECK(requires_human_approval IN (0,1)),
  basis_json TEXT NOT NULL,
  source_inspection_work_order_id TEXT,
  source_inspection_reference TEXT,
  action_code TEXT CHECK(
    action_code IS NULL OR action_code IN (
      'TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE'
    )
  ),
  authored_by TEXT,
  authored_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  source_cost_analysis_id TEXT REFERENCES closed_loop_maintenance_cost_analyses(analysis_id),
  source_cost_option_id TEXT,
  source_action_candidate_id TEXT,
  CHECK(asset_id=equipment_id),
  CHECK(
    (
      recommendation_origin='product_result_projection'
      AND source_inspection_work_order_id IS NULL
      AND source_inspection_reference IS NULL
      AND action_code IS NULL
      AND authored_by IS NULL
      AND authored_at IS NULL
    ) OR (
      recommendation_origin='operations_manual'
      AND source_inspection_work_order_id IS NOT NULL
      AND source_inspection_reference IS NOT NULL
      AND action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE')
      AND authored_by IS NOT NULL
      AND authored_at IS NOT NULL
      AND requires_human_approval=1
      AND kind=action_code
    )
  ),
  UNIQUE(organization_id,project_id,workspace_id,source_product_result_id,source_action_id)
);

INSERT INTO closed_loop_recommendations (
  recommendation_id,organization_id,project_id,workspace_id,event_id,
  asset_id,equipment_id,asset_type,recommendation_origin,status,
  materialization_strategy,source_action_id,source_product_result_id,
  source_evidence_id,source_schema_version,source_policy_version,label,kind,
  requires_human_approval,basis_json,source_inspection_work_order_id,
  source_inspection_reference,action_code,authored_by,authored_at,created_at,
  updated_at,source_cost_analysis_id,source_cost_option_id,
  source_action_candidate_id
)
SELECT
  recommendation_id,organization_id,project_id,workspace_id,event_id,
  asset_id,equipment_id,asset_type,recommendation_origin,status,
  materialization_strategy,source_action_id,source_product_result_id,
  source_evidence_id,source_schema_version,source_policy_version,label,kind,
  requires_human_approval,basis_json,source_inspection_work_order_id,
  source_inspection_reference,action_code,authored_by,authored_at,created_at,
  updated_at,source_cost_analysis_id,source_cost_option_id,
  source_action_candidate_id
FROM closed_loop_recommendations_legacy;

DROP TABLE closed_loop_recommendations_legacy;

CREATE INDEX idx_closed_loop_recommendations_event
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,event_id,created_at
  );
CREATE UNIQUE INDEX uq_closed_loop_operations_manual_source
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,
    source_inspection_work_order_id,source_inspection_reference,action_code
  ) WHERE recommendation_origin='operations_manual';
CREATE INDEX idx_closed_loop_recommendations_cost_source
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,source_cost_analysis_id,
    source_cost_option_id
  );

CREATE TRIGGER closed_loop_recommendation_cost_lineage_insert
BEFORE INSERT ON closed_loop_recommendations
WHEN
  (NEW.recommendation_origin='product_result_projection' AND (
    NEW.source_cost_analysis_id IS NOT NULL OR
    NEW.source_cost_option_id IS NOT NULL OR
    NEW.source_action_candidate_id IS NOT NULL
  )) OR
  (NEW.recommendation_origin='operations_manual' AND (
    (NEW.source_cost_analysis_id IS NOT NULL OR
     NEW.source_cost_option_id IS NOT NULL OR
     NEW.source_action_candidate_id IS NOT NULL)
    AND NOT (
      NEW.source_cost_analysis_id IS NOT NULL AND
      NEW.source_cost_option_id IS NOT NULL AND
      NEW.source_action_candidate_id IS NOT NULL
    )
  ))
BEGIN
  SELECT RAISE(ABORT, 'invalid recommendation cost lineage');
END;

CREATE TRIGGER closed_loop_recommendation_cost_lineage_update
BEFORE UPDATE ON closed_loop_recommendations
WHEN
  (NEW.recommendation_origin='product_result_projection' AND (
    NEW.source_cost_analysis_id IS NOT NULL OR
    NEW.source_cost_option_id IS NOT NULL OR
    NEW.source_action_candidate_id IS NOT NULL
  )) OR
  (NEW.recommendation_origin='operations_manual' AND (
    (NEW.source_cost_analysis_id IS NOT NULL OR
     NEW.source_cost_option_id IS NOT NULL OR
     NEW.source_action_candidate_id IS NOT NULL)
    AND NOT (
      NEW.source_cost_analysis_id IS NOT NULL AND
      NEW.source_cost_option_id IS NOT NULL AND
      NEW.source_action_candidate_id IS NOT NULL
    )
  ))
BEGIN
  SELECT RAISE(ABORT, 'invalid recommendation cost lineage');
END;

DROP INDEX IF EXISTS idx_closed_loop_actions_event;
ALTER TABLE closed_loop_maintenance_actions
  RENAME TO closed_loop_maintenance_actions_legacy;

CREATE TABLE closed_loop_maintenance_actions (
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
  action_code TEXT NOT NULL CHECK(
    action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE')
  ),
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

INSERT INTO closed_loop_maintenance_actions
SELECT * FROM closed_loop_maintenance_actions_legacy;
DROP TABLE closed_loop_maintenance_actions_legacy;
CREATE INDEX idx_closed_loop_actions_event
  ON closed_loop_maintenance_actions(
    organization_id,project_id,workspace_id,event_id,created_at
  );

DROP INDEX IF EXISTS idx_closed_loop_maintenance_events_equipment;
ALTER TABLE closed_loop_maintenance_events
  RENAME TO closed_loop_maintenance_events_legacy;

CREATE TABLE closed_loop_maintenance_events (
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
  action_code TEXT NOT NULL CHECK(
    action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE')
  ),
  state_patch_json TEXT NOT NULL,
  maintenance_started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK(asset_id=equipment_id),
  FOREIGN KEY(maintenance_action_id) REFERENCES closed_loop_maintenance_actions(maintenance_action_id),
  FOREIGN KEY(work_order_id) REFERENCES closed_loop_work_orders(work_order_id)
);

INSERT INTO closed_loop_maintenance_events
SELECT * FROM closed_loop_maintenance_events_legacy;
DROP TABLE closed_loop_maintenance_events_legacy;
CREATE INDEX idx_closed_loop_maintenance_events_equipment
  ON closed_loop_maintenance_events(
    organization_id,project_id,workspace_id,equipment_id,completed_at
  );

PRAGMA legacy_alter_table=OFF;
PRAGMA foreign_keys=ON;
