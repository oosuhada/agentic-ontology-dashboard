CREATE TABLE IF NOT EXISTS projects (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    slug text NOT NULL,
    display_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    domain_pack_code text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    default_workspace_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_projects_organization_status
    ON projects(organization_id, status, display_name);

ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
CREATE INDEX IF NOT EXISTS idx_workspaces_project
    ON workspaces(organization_id, project_id, display_name);

ALTER TABLE ontology_objects ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
ALTER TABLE ontology_links ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
ALTER TABLE ontology_ingestion_runs ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
ALTER TABLE ontology_schema_versions ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
ALTER TABLE ontology_source_mappings ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);
ALTER TABLE transactional_outbox ADD COLUMN IF NOT EXISTS project_id text REFERENCES projects(id);

CREATE INDEX IF NOT EXISTS idx_ontology_objects_project
    ON ontology_objects(organization_id, project_id, workspace_id, object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_ontology_links_project
    ON ontology_links(organization_id, project_id, workspace_id, link_type, link_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_project
    ON ontology_ingestion_runs(organization_id, project_id, workspace_id, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_project_pending
    ON transactional_outbox(organization_id, project_id, status, available_at, created_at)
    WHERE status = 'pending';

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS projects_scope_policy ON projects;
CREATE POLICY projects_scope_policy ON projects
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR id = current_setting('app.project_id', true)
        )
    );

DROP POLICY IF EXISTS workspaces_scope_policy ON workspaces;
CREATE POLICY workspaces_scope_policy ON workspaces
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );

DROP POLICY IF EXISTS ontology_objects_tenant_policy ON ontology_objects;
CREATE POLICY ontology_objects_tenant_policy ON ontology_objects
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );
DROP POLICY IF EXISTS ontology_links_tenant_policy ON ontology_links;
CREATE POLICY ontology_links_tenant_policy ON ontology_links
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );
DROP POLICY IF EXISTS ontology_ingestion_tenant_policy ON ontology_ingestion_runs;
CREATE POLICY ontology_ingestion_tenant_policy ON ontology_ingestion_runs
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );
DROP POLICY IF EXISTS ontology_schema_tenant_policy ON ontology_schema_versions;
CREATE POLICY ontology_schema_tenant_policy ON ontology_schema_versions
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );
DROP POLICY IF EXISTS ontology_mapping_tenant_policy ON ontology_source_mappings;
CREATE POLICY ontology_mapping_tenant_policy ON ontology_source_mappings
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );
DROP POLICY IF EXISTS outbox_tenant_policy ON transactional_outbox;
CREATE POLICY outbox_tenant_policy ON transactional_outbox
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND (
            nullif(current_setting('app.project_id', true), '') IS NULL
            OR project_id = current_setting('app.project_id', true)
        )
    );
