ALTER TABLE closed_loop_work_orders ADD COLUMN assigned_to TEXT;
ALTER TABLE closed_loop_work_orders ADD COLUMN assigned_at TEXT;

UPDATE closed_loop_work_orders
SET assigned_to = COALESCE(
      (
        SELECT activity.actor_user_id
        FROM closed_loop_activities AS activity
        WHERE activity.organization_id = closed_loop_work_orders.organization_id
          AND activity.project_id = closed_loop_work_orders.project_id
          AND activity.workspace_id = closed_loop_work_orders.workspace_id
          AND activity.work_order_id = closed_loop_work_orders.work_order_id
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
        WHERE activity.organization_id = closed_loop_work_orders.organization_id
          AND activity.project_id = closed_loop_work_orders.project_id
          AND activity.workspace_id = closed_loop_work_orders.workspace_id
          AND activity.work_order_id = closed_loop_work_orders.work_order_id
          AND activity.activity_type IN (
            'work_order.assigned',
            'work_order.in_progress',
            'inspection.result_recorded',
            'work_order.completed'
          )
        ORDER BY activity.created_at, activity.activity_id
        LIMIT 1
      ),
      updated_at
    )
WHERE work_type = 'inspection'
  AND status NOT IN ('requested', 'approved')
  AND assigned_to IS NULL;

-- Legacy `approved` did not carry a field assignee. In the new lifecycle the
-- same status means accepted-and-assigned, so put those rows back in the
-- request queue rather than attributing them to the former manager approver.
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
