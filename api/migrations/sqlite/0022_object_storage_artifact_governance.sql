CREATE TABLE IF NOT EXISTS artifact_objects (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_version TEXT NOT NULL,
    object_key TEXT NOT NULL,
    uri TEXT NOT NULL,
    backend TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'available',
    retention_class TEXT NOT NULL DEFAULT 'standard',
    retain_until TEXT,
    legal_hold INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    deleted_at TEXT,
    UNIQUE (organization_id, project_id, object_key),
    UNIQUE (
        organization_id,project_id,workspace_id,resource_type,resource_id,
        resource_version,checksum_sha256
    )
);
CREATE TABLE IF NOT EXISTS artifact_access_audit (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    artifact_id TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    purpose TEXT,
    decision TEXT NOT NULL,
    signed_until TEXT,
    request_id TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_reconciliation_runs (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT,
    mode TEXT NOT NULL,
    state TEXT NOT NULL,
    catalog_count INTEGER NOT NULL DEFAULT 0,
    object_count INTEGER NOT NULL DEFAULT 0,
    verified_count INTEGER NOT NULL DEFAULT 0,
    missing_count INTEGER NOT NULL DEFAULT 0,
    mismatch_count INTEGER NOT NULL DEFAULT 0,
    orphan_count INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_artifact_objects_resource
    ON artifact_objects(organization_id,project_id,resource_type,resource_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_objects_retention
    ON artifact_objects(organization_id,project_id,state,retain_until);
CREATE INDEX IF NOT EXISTS idx_artifact_access_audit_scope
    ON artifact_access_audit(organization_id,project_id,artifact_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_reconciliation_scope
    ON artifact_reconciliation_runs(organization_id,project_id,created_at DESC);
