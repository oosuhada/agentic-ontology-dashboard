-- Add the Operations-owned post-inspection recommendation while preserving
-- the Product Result/Evidence lineage required by Maintenance.

ALTER TABLE closed_loop_recommendations
  DROP CONSTRAINT IF EXISTS closed_loop_recommendations_recommendation_origin_check;

ALTER TABLE closed_loop_recommendations
  ADD COLUMN IF NOT EXISTS asset_type text NOT NULL DEFAULT 'legacy_unknown',
  ADD COLUMN IF NOT EXISTS source_inspection_work_order_id text,
  ADD COLUMN IF NOT EXISTS source_inspection_reference text,
  ADD COLUMN IF NOT EXISTS action_code text,
  ADD COLUMN IF NOT EXISTS authored_by text,
  ADD COLUMN IF NOT EXISTS authored_at timestamptz;

ALTER TABLE closed_loop_recommendations
  ADD CONSTRAINT closed_loop_recommendations_recommendation_origin_check
    CHECK(recommendation_origin IN ('product_result_projection','operations_manual')),
  ADD CONSTRAINT closed_loop_recommendations_action_code_check
    CHECK(action_code IS NULL OR action_code='TOOL_REPLACEMENT'),
  ADD CONSTRAINT closed_loop_recommendations_origin_lineage_check
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
        AND requires_human_approval
        AND kind=action_code
      )
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_closed_loop_operations_manual_source
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,
    source_inspection_work_order_id,source_inspection_reference,action_code
  )
  WHERE recommendation_origin='operations_manual';
