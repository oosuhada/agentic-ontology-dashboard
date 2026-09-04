-- Extend only the analytical Action vocabulary. Maintenance execution remains
-- blocked until its state patch and Runtime Overlay contract are versioned.

ALTER TABLE closed_loop_maintenance_cost_analyses
  DROP CONSTRAINT IF EXISTS closed_loop_maintenance_cost_analyses_action_code_check;

ALTER TABLE closed_loop_maintenance_cost_analyses
  ADD CONSTRAINT closed_loop_maintenance_cost_analyses_action_code_check
  CHECK(action_code IN ('TOOL_REPLACEMENT','COOLING_SYSTEM_RESTORE'));
