-- Preserve the human-selected cost snapshot and option on an Operations-owned
-- recommendation. Cost analysis remains decision support and never records an
-- approval or creates a Work Order by itself.

ALTER TABLE closed_loop_recommendations
  ADD COLUMN source_cost_analysis_id TEXT
    REFERENCES closed_loop_maintenance_cost_analyses(analysis_id);
ALTER TABLE closed_loop_recommendations
  ADD COLUMN source_cost_option_id TEXT;
ALTER TABLE closed_loop_recommendations
  ADD COLUMN source_action_candidate_id TEXT;

CREATE TRIGGER closed_loop_recommendation_cost_lineage_insert
BEFORE INSERT ON closed_loop_recommendations
WHEN
  (
    NEW.recommendation_origin='product_result_projection'
    AND (
      NEW.source_cost_analysis_id IS NOT NULL
      OR NEW.source_cost_option_id IS NOT NULL
      OR NEW.source_action_candidate_id IS NOT NULL
    )
  )
  OR
  (
    NEW.recommendation_origin='operations_manual'
    AND (
      (
        NEW.source_cost_analysis_id IS NOT NULL
        OR NEW.source_cost_option_id IS NOT NULL
        OR NEW.source_action_candidate_id IS NOT NULL
      )
      AND NOT (
        NEW.source_cost_analysis_id IS NOT NULL
        AND NEW.source_cost_option_id IS NOT NULL
        AND NEW.source_action_candidate_id IS NOT NULL
      )
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'invalid recommendation cost lineage');
END;

CREATE TRIGGER closed_loop_recommendation_cost_lineage_update
BEFORE UPDATE ON closed_loop_recommendations
WHEN
  (
    NEW.recommendation_origin='product_result_projection'
    AND (
      NEW.source_cost_analysis_id IS NOT NULL
      OR NEW.source_cost_option_id IS NOT NULL
      OR NEW.source_action_candidate_id IS NOT NULL
    )
  )
  OR
  (
    NEW.recommendation_origin='operations_manual'
    AND (
      (
        NEW.source_cost_analysis_id IS NOT NULL
        OR NEW.source_cost_option_id IS NOT NULL
        OR NEW.source_action_candidate_id IS NOT NULL
      )
      AND NOT (
        NEW.source_cost_analysis_id IS NOT NULL
        AND NEW.source_cost_option_id IS NOT NULL
        AND NEW.source_action_candidate_id IS NOT NULL
      )
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'invalid recommendation cost lineage');
END;

CREATE INDEX idx_closed_loop_recommendations_cost_source
  ON closed_loop_recommendations(
    organization_id,project_id,workspace_id,source_cost_analysis_id,
    source_cost_option_id
  );
