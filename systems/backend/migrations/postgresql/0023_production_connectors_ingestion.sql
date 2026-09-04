CREATE TABLE IF NOT EXISTS connector_definitions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    name text NOT NULL,
    connector_type text NOT NULL CHECK (connector_type IN (
        'fixture','postgresql','mysql','sqlserver','s3','http','kafka','mqtt'
    )),
    config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    credential_reference text,
    schema_contract_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    checkpoint_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    freshness_policy_seconds integer NOT NULL DEFAULT 300,
    max_batch_records integer NOT NULL DEFAULT 10000,
    max_inflight_batches integer NOT NULL DEFAULT 4,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft','ready','paused','blocked','error','disabled'
    )),
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id,project_id,name)
);

CREATE TABLE IF NOT EXISTS connector_checkpoints (
    connector_id text PRIMARY KEY REFERENCES connector_definitions(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    checkpoint_json jsonb NOT NULL,
    source_schema_hash text,
    records_committed bigint NOT NULL DEFAULT 0,
    watermark_at timestamptz,
    committed_at timestamptz NOT NULL DEFAULT now(),
    committed_run_id text
);

CREATE TABLE IF NOT EXISTS connector_ingestion_runs (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    connector_id text NOT NULL REFERENCES connector_definitions(id),
    durable_job_id text REFERENCES durable_jobs(id),
    state text NOT NULL CHECK (state IN (
        'queued','running','succeeded','failed','cancelled','quarantined','blocked'
    )),
    checkpoint_before_json jsonb,
    checkpoint_after_json jsonb,
    schema_hash text,
    schema_drift_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    records_read bigint NOT NULL DEFAULT 0,
    records_committed bigint NOT NULL DEFAULT 0,
    records_quarantined bigint NOT NULL DEFAULT 0,
    bytes_read bigint NOT NULL DEFAULT 0,
    backpressure_events integer NOT NULL DEFAULT 0,
    error_code text,
    error_message text,
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS connector_quarantine_records (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    connector_id text NOT NULL REFERENCES connector_definitions(id),
    ingestion_run_id text NOT NULL REFERENCES connector_ingestion_runs(id),
    source_record_key text,
    reason_code text NOT NULL,
    reason_detail text,
    payload_json jsonb NOT NULL,
    replay_state text NOT NULL DEFAULT 'pending' CHECK (replay_state IN (
        'pending','approved','replayed','discarded'
    )),
    created_at timestamptz NOT NULL DEFAULT now(),
    replayed_at timestamptz
);

CREATE TABLE IF NOT EXISTS connector_committed_records (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    connector_id text NOT NULL REFERENCES connector_definitions(id),
    ingestion_run_id text NOT NULL REFERENCES connector_ingestion_runs(id),
    source_record_key text NOT NULL,
    source_checkpoint_json jsonb NOT NULL,
    payload_json jsonb NOT NULL,
    payload_checksum_sha256 text NOT NULL CHECK (payload_checksum_sha256 ~ '^[a-f0-9]{64}$'),
    committed_at timestamptz NOT NULL DEFAULT now(),
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

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'connector_definitions','connector_checkpoints','connector_ingestion_runs',
        'connector_quarantine_records','connector_committed_records'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS connector_scope_policy ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY connector_scope_policy ON %I USING (' ||
            'organization_id = nullif(current_setting(''app.organization_id'', true), '''') AND ' ||
            'project_id = nullif(current_setting(''app.project_id'', true), '''')' ||
            ') WITH CHECK (' ||
            'organization_id = nullif(current_setting(''app.organization_id'', true), '''') AND ' ||
            'project_id = nullif(current_setting(''app.project_id'', true), '''')' ||
            ')', table_name
        );
    END LOOP;
END $$;
