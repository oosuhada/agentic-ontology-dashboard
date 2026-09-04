-- Add the Operations-owned post-inspection recommendation without weakening
-- the existing Product Result projection lineage contract.

CREATE TABLE closed_loop_recommendations_v2 (
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
  status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected','deferred','superseded')),
  materialization_strategy TEXT NOT NULL DEFAULT 'runtime_generated'
    CHECK(materialization_strategy IN ('runtime_generated','imported_precomputed')),
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
  action_code TEXT CHECK(action_code IS NULL OR action_code='TOOL_REPLACEMENT'),
  authored_by TEXT,
  authored_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
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
      AND action_code='TOOL_REPLACEMENT'
      AND authored_by IS NOT NULL
      AND authored_at IS NOT NULL
      AND requires_human_approval=1
      AND kind=action_code
    )
  ),
  UNIQUE(organization_id,project_id,workspace_id,source_product_result_id,source_action_id)
);

INSERT INTO closed_loop_recommendations_v2 (
  recommendation_id,organization_id,project_id,workspace_id,event_id,
  asset_id,equipment_id,asset_type,recommendation_origin,status,materialization_strategy,
  source_action_id,source_product_result_id,source_evidence_id,source_schema_version,
  source_policy_version,label,kind,requires_human_approval,basis_json,
  source_inspection_work_order_id,source_inspection_reference,action_code,
  authored_by,authored_at,created_at,updated_at
)
SELECT
  recommendation_id,organization_id,project_id,workspace_id,event_id,
  asset_id,equipment_id,'legacy_unknown',recommendation_origin,status,materialization_strategy,
  source_action_id,source_product_result_id,source_evidence_id,source_schema_version,
  source_policy_version,label,kind,requires_human_approval,basis_json,
  NULL,NULL,NULL,NULL,NULL,created_at,updated_at
FROM closed_loop_recommendations;

DROP TABLE closed_loop_recommendations;
ALTER TABLE closed_loop_recommendations_v2 RENAME TO closed_loop_recommendations;

CREATE INDEX idx_closed_loop_recommendations_event
  ON closed_loop_recommendations(organization_id,project_id,workspace_id,event_id,created_at);
CREATE UNIQUE INDEX uq_closed_loop_operations_manual_source
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,
    source_inspection_work_order_id,source_inspection_reference,action_code
  )
  WHERE recommendation_origin='operations_manual';
