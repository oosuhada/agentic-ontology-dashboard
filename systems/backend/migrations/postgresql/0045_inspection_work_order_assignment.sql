ALTER TABLE closed_loop_work_orders
  ADD COLUMN IF NOT EXISTS assigned_to text;

ALTER TABLE closed_loop_work_orders
  ADD COLUMN IF NOT EXISTS assigned_at timestamptz;

UPDATE closed_loop_work_orders AS work_order
SET assigned_to = COALESCE(
      (
        SELECT activity.actor_user_id
        FROM closed_loop_activities AS activity
        WHERE activity.organization_id = work_order.organization_id
          AND activity.project_id = work_order.project_id
          AND activity.workspace_id = work_order.workspace_id
          AND activity.work_order_id = work_order.work_order_id
          AND activity.activity_type IN (
            'work_order.assigned',
            'work_order.in_progress',
            'inspection.result_recorded',
            'work_order.completed'
          )
        ORDER BY activity.created_at, activity.activity_id
        LIMIT 1
      ),
      'legacy-unassigned'
    ),
    assigned_at = COALESCE(
      (
        SELECT activity.created_at
        FROM closed_loop_activities AS activity
        WHERE activity.organization_id = work_order.organization_id
          AND activity.project_id = work_order.project_id
          AND activity.workspace_id = work_order.workspace_id
          AND activity.work_order_id = work_order.work_order_id
          AND activity.activity_type IN (
            'work_order.assigned',
            'work_order.in_progress',
            'inspection.result_recorded',
            'work_order.completed'
          )
        ORDER BY activity.created_at, activity.activity_id
        LIMIT 1
      ),
      work_order.updated_at
    )
WHERE work_order.work_type = 'inspection'
  AND work_order.status NOT IN ('requested', 'approved')
  AND work_order.assigned_to IS NULL;

-- Legacy `approved` meant a manager had approved the request; it did not name
-- a field assignee. Under the new lifecycle `approved` means accepted and
-- assigned, so legacy rows return to the unassigned request queue.
UPDATE closed_loop_work_orders
SET status = 'requested',
    assigned_to = NULL,
    assigned_at = NULL
WHERE work_type = 'inspection'
  AND status = 'approved';

CREATE INDEX IF NOT EXISTS idx_closed_loop_work_orders_assignment
  ON closed_loop_work_orders(
    organization_id, project_id, workspace_id, work_type, status, assigned_to
  );
