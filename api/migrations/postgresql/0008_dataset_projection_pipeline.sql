DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS datasets (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    slug text NOT NULL,
    display_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    source_type text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_datasets_scope
    ON datasets(organization_id, project_id, workspace_id, status, display_name);

CREATE TABLE IF NOT EXISTS dataset_versions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    version_label text NOT NULL,
    source_version text NOT NULL,
    manifest_id text REFERENCES dataset_manifests(id),
    checksum_sha256 text NOT NULL,
    schema_json jsonb NOT NULL,
    profile_json jsonb NOT NULL,
    record_count bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'registered',
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, version_number),
    UNIQUE (dataset_id, source_version)
);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_scope
    ON dataset_versions(organization_id, project_id, dataset_id, version_number DESC);

CREATE TABLE IF NOT EXISTS dataset_files (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    uri text NOT NULL,
    media_type text NOT NULL,
    checksum_sha256 text NOT NULL,
    size_bytes bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_version_id, checksum_sha256)
);

CREATE TABLE IF NOT EXISTS ontology_mappings (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    object_type text NOT NULL,
    identity_field text NOT NULL,
    mapping_json jsonb NOT NULL,
    status text NOT NULL DEFAULT 'approved',
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_version_id, object_type)
);

CREATE TABLE IF NOT EXISTS store_projections (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    store_kind text NOT NULL CHECK (store_kind IN ('relational','graph','vector')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','indexing','ready','failed')),
    object_namespace text NOT NULL,
    source_version text NOT NULL,
    record_count bigint NOT NULL DEFAULT 0,
    attempt_count integer NOT NULL DEFAULT 0,
    last_error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_version_id, store_kind)
);
CREATE INDEX IF NOT EXISTS idx_store_projections_pending
    ON store_projections(status, updated_at, store_kind);

CREATE TABLE IF NOT EXISTS materializations (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    source_kind text NOT NULL,
    source_reference text NOT NULL,
    format text NOT NULL,
    artifact_uri text NOT NULL,
    checksum_sha256 text NOT NULL,
    record_count bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'ready',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_materializations_scope
    ON materializations(organization_id, project_id, dataset_id, created_at DESC);

CREATE TABLE IF NOT EXISTS vector_document_chunks (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    dataset_id text NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    object_id text NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    metadata_json jsonb NOT NULL,
    embedding_json jsonb,
    allowed_roles text[] NOT NULL DEFAULT ARRAY[]::text[],
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_version_id, object_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_vector_chunks_scope
    ON vector_document_chunks(organization_id, project_id, dataset_version_id, object_id);
DO $$
BEGIN
    IF to_regtype('vector') IS NOT NULL THEN
        ALTER TABLE vector_document_chunks
            ADD COLUMN IF NOT EXISTS embedding vector(1536);
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding '
             || 'ON vector_document_chunks USING hnsw (embedding vector_cosine_ops)';
    END IF;
END
$$;

ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE store_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE materializations ENABLE ROW LEVEL SECURITY;
ALTER TABLE vector_document_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS datasets_scope_policy ON datasets;
CREATE POLICY datasets_scope_policy ON datasets
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS dataset_versions_scope_policy ON dataset_versions;
CREATE POLICY dataset_versions_scope_policy ON dataset_versions
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS dataset_files_scope_policy ON dataset_files;
CREATE POLICY dataset_files_scope_policy ON dataset_files
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS ontology_mappings_scope_policy ON ontology_mappings;
CREATE POLICY ontology_mappings_scope_policy ON ontology_mappings
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS store_projections_scope_policy ON store_projections;
CREATE POLICY store_projections_scope_policy ON store_projections
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS materializations_scope_policy ON materializations;
CREATE POLICY materializations_scope_policy ON materializations
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
DROP POLICY IF EXISTS vector_chunks_scope_policy ON vector_document_chunks;
CREATE POLICY vector_chunks_scope_policy ON vector_document_chunks
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );
