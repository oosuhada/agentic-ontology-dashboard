CREATE TABLE IF NOT EXISTS outbox_delivery_log (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    outbox_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    handler_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    FOREIGN KEY (outbox_id) REFERENCES transactional_outbox(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_outbox_delivery_scope
    ON outbox_delivery_log(organization_id, project_id, delivered_at);
