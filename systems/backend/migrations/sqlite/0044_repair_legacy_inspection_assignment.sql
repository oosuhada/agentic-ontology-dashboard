-- SQLite equivalent of PostgreSQL 0046. Preserve truthful historical identity
-- and reopen active legacy work rather than leaving an impossible assignee.

INSERT OR IGNORE INTO closed_loop_activities(
  activity_id, organization_id, project_id, workspace_id, event_id,
  equipment_id, work_order_id, aggregate_type, aggregate_id, activity_type,
  actor_user_id, actor_display_name, before_status, after_status,
  timeline_order, payload_json, created_at
)
SELECT
  'migration-0044-reopen-' || work_order.work_order_id,
  work_order.organization_id,
  work_order.project_id,
  work_order.workspace_id,
  work_order.event_id,
  work_order.equipment_id,
  work_order.work_order_id,
  'work_order',
  work_order.work_order_id,
  'work_order.reverted_to_requested',
  'migration:0044',
  'Assignment repair migration',
  'in_progress',
  'requested',
  COALESCE((
    SELECT MAX(activity.timeline_order) + 1
    FROM closed_loop_activities AS activity
    WHERE activity.organization_id = work_order.organization_id
      AND activity.project_id = work_order.project_id
      AND activity.workspace_id = work_order.workspace_id
      AND activity.event_id = work_order.event_id
  ), 1),
  '{"reason":"legacy_unassigned_repair","previous_assigned_to":"legacy-unassigned"}',
  CURRENT_TIMESTAMP
FROM closed_loop_work_orders AS work_order
WHERE work_order.work_type = 'inspection'
  AND work_order.status = 'in_progress'
  AND work_order.assigned_to = 'legacy-unassigned';

UPDATE closed_loop_work_orders
SET status = 'requested',
    assigned_to = NULL,
    assigned_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE work_type = 'inspection'
  AND status = 'in_progress'
  AND assigned_to = 'legacy-unassigned';

UPDATE closed_loop_work_orders
SET assigned_to = NULL,
    assigned_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE work_type = 'inspection'
  AND status IN ('completed', 'blocked', 'failed', 'cancelled')
  AND assigned_to = 'legacy-unassigned';
