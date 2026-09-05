-- Versioned enterprise knowledge documents, active hybrid index state, and
-- bounded retrieval audit.  Vector payloads continue to live in the existing
-- dataset-scoped vector_document_chunks table so retrieval keeps dataset/version
-- lineage instead of introducing an ungoverned side store.

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    title text NOT NULL,
    document_type text NOT NULL,
    source_ref text NOT NULL,
    allowed_roles_json text NOT NULL DEFAULT '[]',
    metadata_json text NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (organization_id, project_id, workspace_id, source_ref)
);

CREATE TABLE IF NOT EXISTS knowledge_document_versions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    document_id text NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    content text NOT NULL,
    checksum_sha256 text NOT NULL,
    source_updated_at timestamptz,
    effective_from timestamptz,
    effective_to timestamptz,
    status text NOT NULL DEFAULT 'approved' CHECK (status IN ('draft','approved','superseded','retired')),
    created_by text,
    created_at timestamptz NOT NULL,
    UNIQUE (document_id, version_number),
    UNIQUE (document_id, checksum_sha256)
);

CREATE TABLE IF NOT EXISTS knowledge_index_state (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text REFERENCES datasets(id),
    dataset_version_id text REFERENCES dataset_versions(id),
    embedding_provider text NOT NULL DEFAULT 'unindexed',
    corpus_checksum_sha256 text,
    document_count integer NOT NULL DEFAULT 0,
    chunk_count integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'dirty' CHECK (status IN ('dirty','indexing','ready','failed')),
    last_indexed_at timestamptz,
    last_error text,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, project_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS knowledge_retrieval_audit (
    id text PRIMARY KEY,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    actor_user_id text,
    query_sha256 text NOT NULL,
    retrieval_mode text NOT NULL,
    result_count integer NOT NULL,
    latency_ms integer NOT NULL,
    result_refs_json text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_scope
    ON knowledge_documents (organization_id, project_id, workspace_id, document_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_versions_active
    ON knowledge_document_versions (organization_id, project_id, workspace_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_audit_scope
    ON knowledge_retrieval_audit (organization_id, project_id, workspace_id, created_at DESC);

ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_index_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_retrieval_audit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS knowledge_documents_scope ON knowledge_documents;
CREATE POLICY knowledge_documents_scope ON knowledge_documents
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

DROP POLICY IF EXISTS knowledge_document_versions_scope ON knowledge_document_versions;
CREATE POLICY knowledge_document_versions_scope ON knowledge_document_versions
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

DROP POLICY IF EXISTS knowledge_index_state_scope ON knowledge_index_state;
CREATE POLICY knowledge_index_state_scope ON knowledge_index_state
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );

DROP POLICY IF EXISTS knowledge_retrieval_audit_scope ON knowledge_retrieval_audit;
CREATE POLICY knowledge_retrieval_audit_scope ON knowledge_retrieval_audit
  USING (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  )
  WITH CHECK (
    organization_id = nullif(current_setting('app.organization_id', true), '')
    AND project_id = nullif(current_setting('app.project_id', true), '')
  );
