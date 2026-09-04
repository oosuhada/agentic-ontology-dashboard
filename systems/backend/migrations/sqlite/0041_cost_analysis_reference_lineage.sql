-- Distinguish a consulted cost-analysis snapshot from an explicitly selected
-- cost option. Operations may preserve analysis + action-candidate lineage
-- without claiming that a timing/cost option was selected.

DROP TRIGGER IF EXISTS closed_loop_recommendation_cost_lineage_insert;
DROP TRIGGER IF EXISTS closed_loop_recommendation_cost_lineage_update;

CREATE TRIGGER closed_loop_recommendation_cost_lineage_insert
BEFORE INSERT ON closed_loop_recommendations
WHEN
  (NEW.recommendation_origin='product_result_projection' AND (
    NEW.source_cost_analysis_id IS NOT NULL OR
    NEW.source_cost_option_id IS NOT NULL OR
    NEW.source_action_candidate_id IS NOT NULL
  )) OR
  (NEW.recommendation_origin='operations_manual' AND (
    (NEW.source_cost_analysis_id IS NULL AND
     NEW.source_action_candidate_id IS NOT NULL) OR
    (NEW.source_cost_analysis_id IS NOT NULL AND
     NEW.source_action_candidate_id IS NULL) OR
    (NEW.source_cost_option_id IS NOT NULL AND (
      NEW.source_cost_analysis_id IS NULL OR
      NEW.source_action_candidate_id IS NULL
    ))
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
    (NEW.source_cost_analysis_id IS NULL AND
     NEW.source_action_candidate_id IS NOT NULL) OR
    (NEW.source_cost_analysis_id IS NOT NULL AND
     NEW.source_action_candidate_id IS NULL) OR
    (NEW.source_cost_option_id IS NOT NULL AND (
      NEW.source_cost_analysis_id IS NULL OR
      NEW.source_action_candidate_id IS NULL
    ))
  ))
BEGIN
  SELECT RAISE(ABORT, 'invalid recommendation cost lineage');
END;
