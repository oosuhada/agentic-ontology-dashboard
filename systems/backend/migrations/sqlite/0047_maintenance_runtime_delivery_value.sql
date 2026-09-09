CREATE TABLE IF NOT EXISTS maintenance_runtime_delivery_receipts (
    outbox_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    maintenance_action_id TEXT NOT NULL,
    maintenance_event_id TEXT,
    state_version INTEGER NOT NULL,
    transport TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    external_delivery_id TEXT,
    overlay_branch_id TEXT,
    history_segment_id TEXT,
    response_json TEXT NOT NULL DEFAULT '{}',
    delivered_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (outbox_id) REFERENCES transactional_outbox(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_maintenance_runtime_delivery_scope
    ON maintenance_runtime_delivery_receipts(
        organization_id,project_id,workspace_id,event_id,state_version
    );

CREATE TABLE IF NOT EXISTS maintenance_value_realizations (
    realization_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    equipment_id TEXT NOT NULL,
    maintenance_event_id TEXT NOT NULL,
    source_product_result_id TEXT NOT NULL,
    post_product_result_id TEXT NOT NULL,
    predicted_downtime_minutes REAL,
    actual_downtime_minutes REAL,
    predicted_loss_exposure_minor INTEGER,
    realized_avoided_exposure_minor INTEGER,
    currency TEXT NOT NULL DEFAULT 'KRW',
    before_risk_score REAL,
    after_risk_score REAL,
    recurrence_observed INTEGER,
    basis_json TEXT NOT NULL DEFAULT '{}',
    measured_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,workspace_id,maintenance_event_id,post_product_result_id)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_value_realization_scope
    ON maintenance_value_realizations(
        organization_id,project_id,workspace_id,event_id,measured_at
    );
