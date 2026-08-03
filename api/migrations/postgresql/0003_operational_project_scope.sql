-- Project-scoped operational runtime schema.
-- NOT VALID constraints preserve legacy rows while enforcing project_id for all
-- new and updated records after this migration.

ALTER TABLE workspaces
    ADD CONSTRAINT workspaces_project_required CHECK (project_id IS NOT NULL) NOT VALID;
ALTER TABLE ontology_objects
    ADD CONSTRAINT ontology_objects_project_required CHECK (project_id IS NOT NULL) NOT VALID;
ALTER TABLE ontology_links
    ADD CONSTRAINT ontology_links_project_required CHECK (project_id IS NOT NULL) NOT VALID;
ALTER TABLE ontology_ingestion_runs
    ADD CONSTRAINT ontology_ingestion_runs_project_required CHECK (project_id IS NOT NULL) NOT VALID;
ALTER TABLE ontology_source_mappings
    ADD CONSTRAINT ontology_source_mappings_project_required CHECK (project_id IS NOT NULL) NOT VALID;
ALTER TABLE transactional_outbox
    ADD CONSTRAINT transactional_outbox_project_required CHECK (project_id IS NOT NULL) NOT VALID;

CREATE TABLE IF NOT EXISTS users (
    id text PRIMARY KEY,
    organization_id text REFERENCES organizations(id),
    email text NOT NULL UNIQUE,
    display_name text NOT NULL,
    status text NOT NULL,
    requested_organization_name text,
    terms_accepted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_users_organization_status
    ON users(organization_id,status,email);

CREATE TABLE IF NOT EXISTS password_credentials (
    user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    organization_id text REFERENCES organizations(id),
    password_hash text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS roles (
    code text PRIMARY KEY,
    display_name text NOT NULL,
    description text NOT NULL
);
CREATE TABLE IF NOT EXISTS permissions (
    code text PRIMARY KEY,
    description text NOT NULL
);
CREATE TABLE IF NOT EXISTS role_permissions (
    role_code text NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission_code text NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    PRIMARY KEY(role_code,permission_code)
);
CREATE TABLE IF NOT EXISTS user_roles (
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id text REFERENCES organizations(id),
    role_code text NOT NULL REFERENCES roles(code),
    PRIMARY KEY(user_id,role_code)
);
CREATE TABLE IF NOT EXISTS user_scopes (
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    PRIMARY KEY(user_id,workspace_id)
);
CREATE TABLE IF NOT EXISTS user_project_scopes (
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    PRIMARY KEY(user_id,project_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    token_hash text NOT NULL UNIQUE,
    active_project_id text REFERENCES projects(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    user_agent_hash text,
    ip_hash text,
    rotated_from text,
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_active
    ON sessions(organization_id,user_id,expires_at) WHERE revoked_at IS NULL;
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text REFERENCES projects(id),
    actor_user_id text NOT NULL REFERENCES users(id),
    target_user_id text REFERENCES users(id),
    action text NOT NULL,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dashboard_templates (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    role_code text NOT NULL,
    display_name text NOT NULL,
    current_version integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id,workspace_id,role_code)
);
CREATE TABLE IF NOT EXISTS dashboard_template_versions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    template_id text NOT NULL REFERENCES dashboard_templates(id) ON DELETE CASCADE,
    version integer NOT NULL,
    status text NOT NULL,
    payload_json jsonb NOT NULL,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(template_id,version)
);
CREATE TABLE IF NOT EXISTS dashboard_user_preferences (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id text NOT NULL REFERENCES dashboard_templates(id) ON DELETE CASCADE,
    template_version integer NOT NULL,
    revision integer NOT NULL,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id,user_id,workspace_id,template_id)
);
CREATE TABLE IF NOT EXISTS dashboard_saved_views (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS dashboard_shares (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    token_hash text NOT NULL UNIQUE,
    owner_user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_dashboard_saved_views_scope
    ON dashboard_saved_views(organization_id,project_id,workspace_id,user_id,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dashboard_shares_scope
    ON dashboard_shares(organization_id,project_id,workspace_id,expires_at);

CREATE TABLE IF NOT EXISTS ontology_action_invocations (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    idempotency_key text NOT NULL,
    action_type text NOT NULL,
    object_id text NOT NULL,
    actor_user_id text NOT NULL REFERENCES users(id),
    actor_display_name text NOT NULL,
    request_hash text NOT NULL,
    request_json jsonb NOT NULL,
    state text NOT NULL,
    result_json jsonb,
    error_json jsonb,
    audit_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE(project_id,workspace_id,actor_user_id,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_ontology_actions_scope
    ON ontology_action_invocations(organization_id,project_id,workspace_id,object_id,created_at DESC);

CREATE TABLE IF NOT EXISTS audit_export_checkpoints (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    event_id text NOT NULL,
    export_format text NOT NULL,
    reason text NOT NULL,
    content_hash text NOT NULL,
    requested_by text NOT NULL REFERENCES users(id),
    requested_by_name text NOT NULL,
    snapshot_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS field_task_actions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    event_id text NOT NULL,
    action text NOT NULL,
    status text NOT NULL,
    actor_user_id text NOT NULL REFERENCES users(id),
    actor_display_name text NOT NULL,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS template_publish_requests (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    target_role text NOT NULL,
    status text NOT NULL,
    requested_by text NOT NULL REFERENCES users(id),
    requested_by_name text NOT NULL,
    payload_json jsonb NOT NULL,
    decision_by text,
    decision_by_name text,
    decision_note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS model_release_requests (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    status text NOT NULL,
    requested_by text NOT NULL REFERENCES users(id),
    requested_by_name text NOT NULL,
    payload_json jsonb NOT NULL,
    decision_by text,
    decision_by_name text,
    decision_note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_field_task_actions_scope
    ON field_task_actions(organization_id,project_id,workspace_id,event_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_template_publish_scope
    ON template_publish_requests(organization_id,project_id,workspace_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_model_release_scope
    ON model_release_requests(organization_id,project_id,workspace_id,status,created_at DESC);

CREATE TABLE IF NOT EXISTS export_checkpoints (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    scope text NOT NULL,
    format text NOT NULL,
    event_id text,
    filename text NOT NULL,
    media_type text NOT NULL,
    content_bytes integer NOT NULL,
    snapshot_hash text NOT NULL,
    content_hash text NOT NULL,
    requested_by text NOT NULL REFERENCES users(id),
    requested_by_name text NOT NULL,
    snapshot_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_export_checkpoints_scope
    ON export_checkpoints(organization_id,project_id,workspace_id,created_at DESC);

CREATE TABLE IF NOT EXISTS dataset_manifests (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    adapter_code text NOT NULL,
    dataset_name text NOT NULL,
    dataset_version text NOT NULL,
    source_uri text NOT NULL,
    source_checksum text NOT NULL,
    media_type text NOT NULL,
    manifest_json jsonb NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id,dataset_version,source_checksum)
);
CREATE TABLE IF NOT EXISTS adapter_ingestion_runs (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    manifest_id text NOT NULL REFERENCES dataset_manifests(id),
    adapter_code text NOT NULL,
    status text NOT NULL,
    source_record_count integer NOT NULL DEFAULT 0,
    accepted_record_count integer NOT NULL DEFAULT 0,
    quarantined_record_count integer NOT NULL DEFAULT 0,
    error_message text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE TABLE IF NOT EXISTS adapter_quarantine_records (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    ingestion_run_id text NOT NULL REFERENCES adapter_ingestion_runs(id) ON DELETE CASCADE,
    source_row_number integer,
    error_code text NOT NULL,
    error_message text NOT NULL,
    record_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    subject_object_type text NOT NULL,
    subject_object_id text NOT NULL,
    prediction_status text NOT NULL,
    model_version text NOT NULL,
    dataset_version text NOT NULL,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id,prediction_id)
);
CREATE INDEX IF NOT EXISTS idx_dataset_manifests_scope
    ON dataset_manifests(organization_id,project_id,workspace_id,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_adapter_runs_scope
    ON adapter_ingestion_runs(organization_id,project_id,workspace_id,started_at DESC);
CREATE INDEX IF NOT EXISTS idx_prediction_results_scope
    ON prediction_results(organization_id,project_id,workspace_id,created_at DESC);

-- Every operational table carries organization_id and project_id, so one
-- reusable policy expression can be applied consistently.
DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'user_scopes','user_project_scopes','admin_audit_log',
        'dashboard_templates','dashboard_template_versions',
        'dashboard_user_preferences','dashboard_saved_views','dashboard_shares',
        'ontology_action_invocations','audit_export_checkpoints','field_task_actions',
        'template_publish_requests','model_release_requests','export_checkpoints',
        'dataset_manifests','adapter_ingestion_runs','adapter_quarantine_records',
        'prediction_results'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS project_scope_policy ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY project_scope_policy ON %I USING (' ||
            'organization_id = current_setting(''app.organization_id'', true) ' ||
            'AND (nullif(current_setting(''app.project_id'', true), '''') IS NULL ' ||
            'OR project_id = current_setting(''app.project_id'', true))) ' ||
            'WITH CHECK (organization_id = current_setting(''app.organization_id'', true) ' ||
            'AND project_id = current_setting(''app.project_id'', true))',
            table_name
        );
    END LOOP;
END $$;

-- Users and credentials can be read before a Project is selected. They use
-- organization-only RLS while session.active_project_id carries UI context.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_scope_policy ON users;
CREATE POLICY organization_scope_policy ON users
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS project_scope_policy ON password_credentials;
CREATE POLICY organization_scope_policy ON password_credentials
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS project_scope_policy ON user_roles;
CREATE POLICY organization_scope_policy ON user_roles
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
DROP POLICY IF EXISTS project_scope_policy ON sessions;
CREATE POLICY organization_scope_policy ON sessions
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
