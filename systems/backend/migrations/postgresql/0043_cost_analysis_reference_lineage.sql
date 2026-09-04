-- Distinguish a consulted cost-analysis snapshot from an explicitly selected
-- cost option. Analysis + action-candidate lineage is valid without an option.

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
          AND source_action_candidate_id IS NOT NULL
        )
      )
    )
  );
