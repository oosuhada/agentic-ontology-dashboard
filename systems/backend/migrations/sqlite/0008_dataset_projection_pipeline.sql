CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (project_id, slug),
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
CREATE INDEX IF NOT EXISTS idx_datasets_scope
    ON datasets(organization_id, project_id, workspace_id, status, display_name);

CREATE TABLE IF NOT EXISTS dataset_versions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    version_label TEXT NOT NULL,
    source_version TEXT NOT NULL,
    manifest_id TEXT,
    checksum_sha256 TEXT NOT NULL,
    schema_json TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'registered',
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (dataset_id, version_number),
    UNIQUE (dataset_id, source_version),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (manifest_id) REFERENCES dataset_manifests(id)
);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_scope
    ON dataset_versions(organization_id, project_id, dataset_id, version_number DESC);

CREATE TABLE IF NOT EXISTS dataset_files (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL,
    uri TEXT NOT NULL,
    media_type TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    size_bytes INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (dataset_version_id, checksum_sha256),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_version_id) REFERENCES dataset_versions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ontology_mappings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    identity_field TEXT NOT NULL,
    mapping_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'approved',
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (dataset_version_id, object_type),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_version_id) REFERENCES dataset_versions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS store_projections (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL,
    store_kind TEXT NOT NULL CHECK (store_kind IN ('relational','graph','vector')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','indexing','ready','failed')),
    object_namespace TEXT NOT NULL,
    source_version TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (dataset_version_id, store_kind),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_version_id) REFERENCES dataset_versions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_store_projections_pending
    ON store_projections(status, updated_at, store_kind);

CREATE TABLE IF NOT EXISTS materializations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    format TEXT NOT NULL,
    artifact_uri TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ready',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_version_id) REFERENCES dataset_versions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_materializations_scope
    ON materializations(organization_id, project_id, dataset_id, created_at DESC);

CREATE TABLE IF NOT EXISTS vector_document_chunks (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    dataset_version_id TEXT NOT NULL,
    object_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    embedding_json TEXT,
    allowed_roles_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE (dataset_version_id, object_id, chunk_index),
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_version_id) REFERENCES dataset_versions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_vector_chunks_scope
    ON vector_document_chunks(organization_id, project_id, dataset_version_id, object_id);
