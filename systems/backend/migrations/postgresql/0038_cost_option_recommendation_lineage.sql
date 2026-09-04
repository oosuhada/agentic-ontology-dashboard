-- Preserve the human-selected cost snapshot and option on an Operations-owned
-- recommendation without treating the analytical result as approval.

ALTER TABLE closed_loop_recommendations
  ADD COLUMN IF NOT EXISTS source_cost_analysis_id text
    REFERENCES closed_loop_maintenance_cost_analyses(analysis_id),
  ADD COLUMN IF NOT EXISTS source_cost_option_id text,
  ADD COLUMN IF NOT EXISTS source_action_candidate_id text;

ALTER TABLE closed_loop_recommendations
  DROP CONSTRAINT IF EXISTS closed_loop_recommendations_cost_lineage_check;
ALTER TABLE closed_loop_recommendations
  ADD CONSTRAINT closed_loop_recommendations_cost_lineage_check
  CHECK (
    (
      recommendation_origin='product_result_projection'
      AND source_cost_analysis_id IS NULL
      AND source_cost_option_id IS NULL
      AND source_action_candidate_id IS NULL
    )
    OR
    (
      recommendation_origin='operations_manual'
      AND (
        (
          source_cost_analysis_id IS NULL
          AND source_cost_option_id IS NULL
          AND source_action_candidate_id IS NULL
        )
        OR
        (
          source_cost_analysis_id IS NOT NULL
          AND source_cost_option_id IS NOT NULL
          AND source_action_candidate_id IS NOT NULL
        )
      )
    )
  );

CREATE INDEX IF NOT EXISTS idx_closed_loop_recommendations_cost_source
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,source_cost_analysis_id,
    source_cost_option_id
  );
