CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    document_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    allowed_roles_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id, project_id, workspace_id, source_ref)
);

CREATE TABLE IF NOT EXISTS knowledge_document_versions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    source_updated_at TEXT,
    effective_from TEXT,
    effective_to TEXT,
    status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('draft','approved','superseded','retired')),
    created_by TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (document_id, version_number),
    UNIQUE (document_id, checksum_sha256)
);

CREATE TABLE IF NOT EXISTS knowledge_index_state (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    dataset_id TEXT,
    dataset_version_id TEXT,
    embedding_provider TEXT NOT NULL DEFAULT 'unindexed',
    corpus_checksum_sha256 TEXT,
    document_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'dirty' CHECK (status IN ('dirty','indexing','ready','failed')),
    last_indexed_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (organization_id, project_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS knowledge_retrieval_audit (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    actor_user_id TEXT,
    query_sha256 TEXT NOT NULL,
    retrieval_mode TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    result_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_scope
    ON knowledge_documents (organization_id, project_id, workspace_id, document_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_versions_active
    ON knowledge_document_versions (organization_id, project_id, workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_audit_scope
    ON knowledge_retrieval_audit (organization_id, project_id, workspace_id, created_at DESC);
