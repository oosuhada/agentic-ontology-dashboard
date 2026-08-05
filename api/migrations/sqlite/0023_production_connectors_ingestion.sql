CREATE TABLE IF NOT EXISTS connector_definitions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    name TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    credential_reference TEXT,
    schema_contract_json TEXT NOT NULL DEFAULT '{}',
    checkpoint_policy_json TEXT NOT NULL DEFAULT '{}',
    freshness_policy_seconds INTEGER NOT NULL DEFAULT 300,
    max_batch_records INTEGER NOT NULL DEFAULT 10000,
    max_inflight_batches INTEGER NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'draft',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,name)
);
CREATE TABLE IF NOT EXISTS connector_checkpoints (
    connector_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    source_schema_hash TEXT,
    records_committed INTEGER NOT NULL DEFAULT 0,
    watermark_at TEXT,
    committed_at TEXT NOT NULL,
    committed_run_id TEXT
);
CREATE TABLE IF NOT EXISTS connector_ingestion_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    connector_id TEXT NOT NULL,
    durable_job_id TEXT,
    state TEXT NOT NULL,
    checkpoint_before_json TEXT,
    checkpoint_after_json TEXT,
    schema_hash TEXT,
    schema_drift_json TEXT NOT NULL DEFAULT '{}',
    records_read INTEGER NOT NULL DEFAULT 0,
    records_committed INTEGER NOT NULL DEFAULT 0,
    records_quarantined INTEGER NOT NULL DEFAULT 0,
    bytes_read INTEGER NOT NULL DEFAULT 0,
    backpressure_events INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS connector_quarantine_records (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    connector_id TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    source_record_key TEXT,
    reason_code TEXT NOT NULL,
    reason_detail TEXT,
    payload_json TEXT NOT NULL,
    replay_state TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    replayed_at TEXT
);
CREATE TABLE IF NOT EXISTS connector_committed_records (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    connector_id TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    source_record_key TEXT NOT NULL,
    source_checkpoint_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_checksum_sha256 TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    UNIQUE (organization_id,project_id,connector_id,source_record_key,payload_checksum_sha256)
);
CREATE INDEX IF NOT EXISTS idx_connector_runs_scope
    ON connector_ingestion_runs(organization_id,project_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_connector_quarantine_scope
    ON connector_quarantine_records(organization_id,project_id,replay_state,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_connector_committed_scope
    ON connector_committed_records(organization_id,project_id,connector_id,committed_at DESC);
CREATE INDEX IF NOT EXISTS idx_connector_freshness
    ON connector_checkpoints(organization_id,project_id,watermark_at);
