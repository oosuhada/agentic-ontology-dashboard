CREATE TABLE IF NOT EXISTS durable_jobs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    job_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 100,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    worker_version TEXT,
    runtime_checksum TEXT,
    cancellation_reason TEXT,
    failure_class TEXT,
    last_error TEXT,
    result_json TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,job_type,idempotency_key)
);

ALTER TABLE transactional_outbox ADD COLUMN lease_owner TEXT;
ALTER TABLE transactional_outbox ADD COLUMN lease_token TEXT;
ALTER TABLE transactional_outbox ADD COLUMN lease_expires_at TEXT;
ALTER TABLE transactional_outbox ADD COLUMN heartbeat_at TEXT;
CREATE INDEX IF NOT EXISTS idx_outbox_processing_lease
    ON transactional_outbox(status,lease_expires_at);

CREATE TABLE IF NOT EXISTS durable_job_events (
    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES durable_jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    organization_id TEXT,
    project_id TEXT,
    worker_type TEXT NOT NULL,
    worker_version TEXT NOT NULL,
    runtime_checksum TEXT NOT NULL,
    state TEXT NOT NULL,
    current_job_id TEXT,
    queue_names_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    heartbeat_at TEXT NOT NULL,
    started_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_durable_jobs_claim
    ON durable_jobs(organization_id,project_id,state,available_at,priority,created_at);
CREATE INDEX IF NOT EXISTS idx_durable_jobs_lease
    ON durable_jobs(state,lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_durable_job_events_cursor
    ON durable_job_events(organization_id,project_id,cursor);
CREATE INDEX IF NOT EXISTS idx_worker_heartbeat_stale
    ON worker_heartbeats(worker_type,state,heartbeat_at);
