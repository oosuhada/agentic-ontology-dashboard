CREATE TABLE IF NOT EXISTS maintenance_runtime_delivery_receipts (
    outbox_id uuid PRIMARY KEY REFERENCES transactional_outbox(id) ON DELETE CASCADE,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text,
    event_id text NOT NULL,
    event_type text NOT NULL,
    equipment_id text NOT NULL,
    maintenance_action_id text NOT NULL,
    maintenance_event_id text,
    state_version integer NOT NULL CHECK (state_version > 0),
    transport text NOT NULL,
    payload_sha256 text NOT NULL,
    external_delivery_id text,
    overlay_branch_id text,
    history_segment_id text,
    response_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    delivered_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_maintenance_runtime_delivery_scope
    ON maintenance_runtime_delivery_receipts(
        organization_id,project_id,workspace_id,event_id,state_version
    );

ALTER TABLE maintenance_runtime_delivery_receipts ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_scope_policy ON maintenance_runtime_delivery_receipts
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );

CREATE TABLE IF NOT EXISTS maintenance_value_realizations (
    realization_id uuid PRIMARY KEY,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    event_id text NOT NULL,
    equipment_id text NOT NULL,
    maintenance_event_id text NOT NULL,
    source_product_result_id text NOT NULL,
    post_product_result_id text NOT NULL,
    predicted_downtime_minutes double precision,
    actual_downtime_minutes double precision,
    predicted_loss_exposure_minor bigint,
    realized_avoided_exposure_minor bigint,
    currency text NOT NULL DEFAULT 'KRW',
    before_risk_score double precision,
    after_risk_score double precision,
    recurrence_observed boolean,
    basis_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    measured_at timestamptz NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id,project_id,workspace_id,maintenance_event_id,post_product_result_id)
);

CREATE INDEX IF NOT EXISTS idx_maintenance_value_realization_scope
    ON maintenance_value_realizations(
        organization_id,project_id,workspace_id,event_id,measured_at DESC
    );

ALTER TABLE maintenance_value_realizations ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_scope_policy ON maintenance_value_realizations
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
