CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS organizations (
    id text PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspaces (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    slug text NOT NULL,
    display_name text NOT NULL,
    domain_pack text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, slug)
);

CREATE TABLE IF NOT EXISTS ontology_objects (
    organization_id text NOT NULL REFERENCES organizations(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    object_id text NOT NULL,
    object_type text NOT NULL,
    payload_json jsonb NOT NULL,
    source_system text NOT NULL,
    source_revision text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, object_id)
);
CREATE INDEX IF NOT EXISTS idx_ontology_objects_type
    ON ontology_objects(organization_id, workspace_id, object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_ontology_objects_payload
    ON ontology_objects USING gin(payload_json);

CREATE TABLE IF NOT EXISTS ontology_links (
    organization_id text NOT NULL REFERENCES organizations(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    link_id text NOT NULL,
    link_type text NOT NULL,
    source_object_id text NOT NULL,
    target_object_id text NOT NULL,
    payload_json jsonb NOT NULL,
    source_system text NOT NULL,
    source_revision text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, link_id),
    FOREIGN KEY (workspace_id, source_object_id)
        REFERENCES ontology_objects(workspace_id, object_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (workspace_id, target_object_id)
        REFERENCES ontology_objects(workspace_id, object_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS idx_ontology_links_source
    ON ontology_links(organization_id, workspace_id, source_object_id, link_type);
CREATE INDEX IF NOT EXISTS idx_ontology_links_target
    ON ontology_links(organization_id, workspace_id, target_object_id, link_type);

CREATE TABLE IF NOT EXISTS ontology_ingestion_runs (
    id uuid PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    source_system text NOT NULL,
    source_revision text,
    object_count integer NOT NULL,
    link_count integer NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ontology_schema_versions (
    id uuid PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    domain_pack text NOT NULL,
    version integer NOT NULL,
    status text NOT NULL,
    schema_json jsonb NOT NULL,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, domain_pack, version)
);

CREATE TABLE IF NOT EXISTS ontology_source_mappings (
    id uuid PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    source_system text NOT NULL,
    source_entity text NOT NULL,
    object_type text NOT NULL,
    mapping_json jsonb NOT NULL,
    schema_version_id uuid REFERENCES ontology_schema_versions(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, source_system, source_entity)
);

CREATE TABLE IF NOT EXISTS transactional_outbox (
    id uuid PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    workspace_id text REFERENCES workspaces(id),
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    event_type text NOT NULL,
    payload_json jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempt_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    last_error text
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON transactional_outbox(status, available_at, created_at)
    WHERE status = 'pending';

ALTER TABLE ontology_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_ingestion_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_schema_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ontology_source_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactional_outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ontology_objects_tenant_policy ON ontology_objects;
CREATE POLICY ontology_objects_tenant_policy ON ontology_objects
    USING (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS ontology_links_tenant_policy ON ontology_links;
CREATE POLICY ontology_links_tenant_policy ON ontology_links
    USING (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS ontology_ingestion_tenant_policy ON ontology_ingestion_runs;
CREATE POLICY ontology_ingestion_tenant_policy ON ontology_ingestion_runs
    USING (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS ontology_schema_tenant_policy ON ontology_schema_versions;
CREATE POLICY ontology_schema_tenant_policy ON ontology_schema_versions
    USING (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS ontology_mapping_tenant_policy ON ontology_source_mappings;
CREATE POLICY ontology_mapping_tenant_policy ON ontology_source_mappings
    USING (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS outbox_tenant_policy ON transactional_outbox;
CREATE POLICY outbox_tenant_policy ON transactional_outbox
    USING (organization_id = current_setting('app.organization_id', true));
