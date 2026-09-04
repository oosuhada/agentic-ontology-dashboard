-- Repair rows created by the first inspection-assignment migration without
-- inventing a permanent actor identity. Historical terminal rows may remain
-- unassigned; active legacy rows return to the request queue and leave an
-- explicit compensating activity in the audit timeline.

INSERT INTO closed_loop_activities(
  activity_id, organization_id, project_id, workspace_id, event_id,
  equipment_id, work_order_id, aggregate_type, aggregate_id, activity_type,
  actor_user_id, actor_display_name, before_status, after_status,
  timeline_order, payload_json, created_at
)
SELECT
  'migration-0046-reopen-' || md5(
    work_order.organization_id || ':' || work_order.project_id || ':' ||
    work_order.workspace_id || ':' || work_order.work_order_id
  ),
  work_order.organization_id,
  work_order.project_id,
  work_order.workspace_id,
  work_order.event_id,
  work_order.equipment_id,
  work_order.work_order_id,
  'work_order',
  work_order.work_order_id,
  'work_order.reverted_to_requested',
  'migration:0046',
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
  jsonb_build_object(
    'reason', 'legacy_unassigned_repair',
    'previous_assigned_to', work_order.assigned_to
  ),
  now()
FROM closed_loop_work_orders AS work_order
WHERE work_order.work_type = 'inspection'
  AND work_order.status = 'in_progress'
  AND work_order.assigned_to = 'legacy-unassigned'
  AND NOT EXISTS (
    SELECT 1
    FROM closed_loop_activities AS existing
    WHERE existing.activity_id = 'migration-0046-reopen-' || md5(
      work_order.organization_id || ':' || work_order.project_id || ':' ||
      work_order.workspace_id || ':' || work_order.work_order_id
    )
  );

UPDATE closed_loop_work_orders
SET status = 'requested',
    assigned_to = NULL,
    assigned_at = NULL,
    updated_at = now()
WHERE work_type = 'inspection'
  AND status = 'in_progress'
  AND assigned_to = 'legacy-unassigned';

UPDATE closed_loop_work_orders
SET assigned_to = NULL,
    assigned_at = NULL,
    updated_at = now()
WHERE work_type = 'inspection'
  AND status IN ('completed', 'blocked', 'failed', 'cancelled')
  AND assigned_to = 'legacy-unassigned';
