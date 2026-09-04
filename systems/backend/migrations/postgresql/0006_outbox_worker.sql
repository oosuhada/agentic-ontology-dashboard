CREATE TABLE IF NOT EXISTS outbox_delivery_log (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    outbox_id uuid NOT NULL UNIQUE REFERENCES transactional_outbox(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    handler_code text NOT NULL,
    payload_json jsonb NOT NULL,
    delivered_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outbox_delivery_scope
    ON outbox_delivery_log(organization_id,project_id,delivered_at DESC);
ALTER TABLE outbox_delivery_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_scope_policy ON outbox_delivery_log
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );
