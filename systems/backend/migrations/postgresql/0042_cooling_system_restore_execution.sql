-- Extend the approved Maintenance execution vocabulary for the cooling slice.

ALTER TABLE closed_loop_recommendations
  DROP CONSTRAINT IF EXISTS closed_loop_recommendations_action_code_check,
  DROP CONSTRAINT IF EXISTS closed_loop_recommendations_origin_lineage_check;

ALTER TABLE closed_loop_recommendations
  ADD CONSTRAINT closed_loop_recommendations_action_code_check
    CHECK(
      action_code IS NULL OR action_code IN (
        'TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE'
      )
    ),
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
        AND action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE')
        AND authored_by IS NOT NULL
        AND authored_at IS NOT NULL
        AND requires_human_approval
        AND kind=action_code
      )
    );

ALTER TABLE closed_loop_maintenance_actions
  DROP CONSTRAINT IF EXISTS closed_loop_maintenance_actions_action_code_check;
ALTER TABLE closed_loop_maintenance_actions
  ADD CONSTRAINT closed_loop_maintenance_actions_action_code_check
    CHECK(action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE'));

ALTER TABLE closed_loop_maintenance_events
  DROP CONSTRAINT IF EXISTS closed_loop_maintenance_events_action_code_check;
ALTER TABLE closed_loop_maintenance_events
  ADD CONSTRAINT closed_loop_maintenance_events_action_code_check
    CHECK(action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE'));
