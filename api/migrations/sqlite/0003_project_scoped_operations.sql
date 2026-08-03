-- Project Layer phase 2.
-- Existing operational tables are upgraded conditionally by migrations.py and
-- by their repository initializers because some compatibility tables are created
-- lazily after the migration runner executes.

CREATE TABLE IF NOT EXISTS dataset_manifests (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    adapter_code TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    source_checksum TEXT NOT NULL,
    media_type TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, dataset_version, source_checksum)
);
CREATE INDEX IF NOT EXISTS idx_dataset_manifests_scope
    ON dataset_manifests(organization_id, project_id, workspace_id, created_at);

CREATE TABLE IF NOT EXISTS adapter_ingestion_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    adapter_code TEXT NOT NULL,
    status TEXT NOT NULL,
    source_record_count INTEGER NOT NULL DEFAULT 0,
    accepted_record_count INTEGER NOT NULL DEFAULT 0,
    quarantined_record_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (manifest_id) REFERENCES dataset_manifests(id)
);
CREATE INDEX IF NOT EXISTS idx_adapter_ingestion_runs_scope
    ON adapter_ingestion_runs(organization_id, project_id, workspace_id, started_at);

CREATE TABLE IF NOT EXISTS adapter_quarantine_records (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    source_row_number INTEGER,
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (ingestion_run_id) REFERENCES adapter_ingestion_runs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_adapter_quarantine_scope
    ON adapter_quarantine_records(organization_id, project_id, workspace_id, ingestion_run_id);
