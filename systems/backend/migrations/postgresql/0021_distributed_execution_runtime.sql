CREATE TABLE IF NOT EXISTS durable_jobs (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    job_type text NOT NULL CHECK (job_type IN (
        'analysis','modeling_experiment','projection','export','automation','connector_ingestion'
    )),
    idempotency_key text NOT NULL,
    payload_json jsonb NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN (
        'queued','running','retry','succeeded','failed','cancel_requested','cancelled','dead_letter'
    )),
    priority integer NOT NULL DEFAULT 100,
    attempt_count integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_owner text,
    lease_token text,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    worker_version text,
    runtime_checksum text,
    cancellation_reason text,
    failure_class text CHECK (failure_class IN ('transient','permanent','validation','cancelled')),
    last_error text,
    result_json jsonb,
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id,project_id,job_type,idempotency_key)
);

ALTER TABLE transactional_outbox
    ADD COLUMN IF NOT EXISTS lease_owner text;
ALTER TABLE transactional_outbox
    ADD COLUMN IF NOT EXISTS lease_token text;
ALTER TABLE transactional_outbox
    ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;
ALTER TABLE transactional_outbox
    ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_outbox_processing_lease
    ON transactional_outbox(status,lease_expires_at)
    WHERE status='processing';

CREATE TABLE IF NOT EXISTS durable_job_events (
    cursor bigserial PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    job_id text NOT NULL REFERENCES durable_jobs(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id text PRIMARY KEY,
    organization_id text,
    project_id text,
    worker_type text NOT NULL,
    worker_version text NOT NULL,
    runtime_checksum text NOT NULL,
    state text NOT NULL CHECK (state IN ('starting','ready','draining','stopped','error')),
    current_job_id text,
    queue_names_json jsonb NOT NULL,
    metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    heartbeat_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_durable_jobs_claim
    ON durable_jobs(organization_id,project_id,state,available_at,priority,created_at)
    WHERE state IN ('queued','retry');
CREATE INDEX IF NOT EXISTS idx_durable_jobs_lease
    ON durable_jobs(state,lease_expires_at)
    WHERE state IN ('running','cancel_requested');
CREATE INDEX IF NOT EXISTS idx_durable_job_events_cursor
    ON durable_job_events(organization_id,project_id,cursor);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeat_stale
    ON worker_heartbeats(worker_type,state,heartbeat_at);

ALTER TABLE durable_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE durable_job_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_heartbeats ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS durable_jobs_project_scope ON durable_jobs;
CREATE POLICY durable_jobs_project_scope ON durable_jobs
    USING (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    )
    WITH CHECK (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    );
DROP POLICY IF EXISTS durable_job_events_project_scope ON durable_job_events;
CREATE POLICY durable_job_events_project_scope ON durable_job_events
    USING (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    )
    WITH CHECK (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    );
DROP POLICY IF EXISTS worker_heartbeats_scope ON worker_heartbeats;
CREATE POLICY worker_heartbeats_scope ON worker_heartbeats
    USING (
        organization_id IS NULL
        OR organization_id = nullif(current_setting('app.organization_id', true), '')
    )
    WITH CHECK (
        organization_id IS NULL
        OR organization_id = nullif(current_setting('app.organization_id', true), '')
    );
