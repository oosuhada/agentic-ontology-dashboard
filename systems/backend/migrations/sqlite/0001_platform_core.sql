CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    domain_pack TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    UNIQUE (organization_id, slug)
);

CREATE TABLE IF NOT EXISTS transactional_outbox (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    workspace_id TEXT,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    processed_at TEXT,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON transactional_outbox(status, available_at, created_at);

CREATE TABLE IF NOT EXISTS ontology_schema_versions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    domain_pack TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, domain_pack, version)
);

CREATE TABLE IF NOT EXISTS ontology_source_mappings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    object_type TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    schema_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, source_system, source_entity)
);
