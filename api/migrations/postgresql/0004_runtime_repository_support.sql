-- Runtime repository support: trusted identity access, scope resolution,
-- compatibility triggers and manufacturing regression persistence.

CREATE TABLE IF NOT EXISTS admin_audit (
    id text PRIMARY KEY,
    organization_id text REFERENCES organizations(id),
    project_id text REFERENCES projects(id),
    actor_user_id text NOT NULL REFERENCES users(id),
    target_user_id text REFERENCES users(id),
    action text NOT NULL,
    before_json jsonb NOT NULL,
    after_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_scope
    ON admin_audit(organization_id,created_at DESC);

CREATE OR REPLACE FUNCTION fill_identity_scope_columns()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    resolved_org text;
    resolved_project text;
BEGIN
    IF TG_TABLE_NAME = 'password_credentials' THEN
        SELECT organization_id INTO resolved_org FROM users WHERE id=NEW.user_id;
        NEW.organization_id := COALESCE(NEW.organization_id,resolved_org);
    ELSIF TG_TABLE_NAME = 'user_roles' THEN
        SELECT organization_id INTO resolved_org FROM users WHERE id=NEW.user_id;
        NEW.organization_id := COALESCE(NEW.organization_id,resolved_org);
    ELSIF TG_TABLE_NAME = 'user_scopes' THEN
        SELECT u.organization_id,w.project_id
          INTO resolved_org,resolved_project
          FROM users u CROSS JOIN workspaces w
         WHERE u.id=NEW.user_id AND w.id=NEW.workspace_id;
        NEW.organization_id := COALESCE(NEW.organization_id,resolved_org);
        NEW.project_id := COALESCE(NEW.project_id,resolved_project);
    ELSIF TG_TABLE_NAME = 'user_project_scopes' THEN
        SELECT u.organization_id INTO resolved_org FROM users u WHERE u.id=NEW.user_id;
        NEW.organization_id := COALESCE(NEW.organization_id,resolved_org);
    ELSIF TG_TABLE_NAME = 'sessions' THEN
        SELECT organization_id INTO resolved_org FROM users WHERE id=NEW.user_id;
        NEW.organization_id := COALESCE(NEW.organization_id,resolved_org);
    ELSIF TG_TABLE_NAME = 'admin_audit' THEN
        SELECT organization_id INTO resolved_org FROM users WHERE id=NEW.actor_user_id;
        NEW.organization_id := COALESCE(NEW.organization_id,resolved_org);
        IF NEW.project_id IS NULL THEN
            SELECT active_project_id INTO resolved_project
              FROM sessions
             WHERE user_id=NEW.actor_user_id AND revoked_at IS NULL
             ORDER BY last_seen_at DESC LIMIT 1;
            NEW.project_id := resolved_project;
        END IF;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_password_credentials_scope ON password_credentials;
CREATE TRIGGER trg_password_credentials_scope
BEFORE INSERT OR UPDATE ON password_credentials
FOR EACH ROW EXECUTE FUNCTION fill_identity_scope_columns();
DROP TRIGGER IF EXISTS trg_user_roles_scope ON user_roles;
CREATE TRIGGER trg_user_roles_scope
BEFORE INSERT OR UPDATE ON user_roles
FOR EACH ROW EXECUTE FUNCTION fill_identity_scope_columns();
DROP TRIGGER IF EXISTS trg_user_scopes_scope ON user_scopes;
CREATE TRIGGER trg_user_scopes_scope
BEFORE INSERT OR UPDATE ON user_scopes
FOR EACH ROW EXECUTE FUNCTION fill_identity_scope_columns();
DROP TRIGGER IF EXISTS trg_user_project_scopes_scope ON user_project_scopes;
CREATE TRIGGER trg_user_project_scopes_scope
BEFORE INSERT OR UPDATE ON user_project_scopes
FOR EACH ROW EXECUTE FUNCTION fill_identity_scope_columns();
DROP TRIGGER IF EXISTS trg_sessions_scope ON sessions;
CREATE TRIGGER trg_sessions_scope
BEFORE INSERT OR UPDATE ON sessions
FOR EACH ROW EXECUTE FUNCTION fill_identity_scope_columns();
DROP TRIGGER IF EXISTS trg_admin_audit_scope ON admin_audit;
CREATE TRIGGER trg_admin_audit_scope
BEFORE INSERT OR UPDATE ON admin_audit
FOR EACH ROW EXECUTE FUNCTION fill_identity_scope_columns();

CREATE OR REPLACE FUNCTION resolve_workspace_scope(p_workspace_id text)
RETURNS TABLE(organization_id text,project_id text,workspace_id text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT w.organization_id,w.project_id,w.id
      FROM workspaces w
     WHERE w.id=p_workspace_id AND w.project_id IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION resolve_project_scope(p_project_id text)
RETURNS TABLE(organization_id text,project_id text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT p.organization_id,p.id
      FROM projects p
     WHERE p.id=p_project_id
$$;

CREATE OR REPLACE FUNCTION resolve_dashboard_share_scope(p_token_hash text)
RETURNS TABLE(organization_id text,project_id text,workspace_id text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT s.organization_id,s.project_id,s.workspace_id
      FROM dashboard_shares s
     WHERE s.token_hash=p_token_hash
$$;

-- Identity repository calls are a trusted service boundary. Every query still
-- applies explicit organization/user predicates, while this flag lets login,
-- registration and session lookup discover the tenant before request RLS is bound.
DROP POLICY IF EXISTS organization_scope_policy ON users;
CREATE POLICY organization_scope_policy ON users
    USING (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
        OR (organization_id IS NULL AND current_setting('app.identity_access', true)='on')
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
        OR organization_id IS NULL
    );
DROP POLICY IF EXISTS organization_scope_policy ON password_credentials;
CREATE POLICY organization_scope_policy ON password_credentials
    USING (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
        OR organization_id IS NULL
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
        OR organization_id IS NULL
    );
DROP POLICY IF EXISTS organization_scope_policy ON user_roles;
CREATE POLICY organization_scope_policy ON user_roles
    USING (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
    );
DROP POLICY IF EXISTS organization_scope_policy ON sessions;
CREATE POLICY organization_scope_policy ON sessions
    USING (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
        OR current_setting('app.identity_access', true)='on'
    );

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['user_scopes','user_project_scopes','admin_audit']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('DROP POLICY IF EXISTS project_scope_policy ON %I',table_name);
        EXECUTE format(
          'CREATE POLICY project_scope_policy ON %I USING (' ||
          'current_setting(''app.identity_access'', true)=''on'' OR (' ||
          'organization_id=current_setting(''app.organization_id'', true) AND (' ||
          'nullif(current_setting(''app.project_id'', true),'''') IS NULL OR ' ||
          'project_id=current_setting(''app.project_id'', true)))) ' ||
          'WITH CHECK (current_setting(''app.identity_access'', true)=''on'' OR (' ||
          'organization_id=current_setting(''app.organization_id'', true) AND (' ||
          'nullif(current_setting(''app.project_id'', true),'''') IS NULL OR ' ||
          'project_id=current_setting(''app.project_id'', true))))',
          table_name
        );
    END LOOP;
END $$;

DROP POLICY IF EXISTS projects_scope_policy ON projects;
CREATE POLICY projects_scope_policy ON projects
    USING (
        current_setting('app.identity_access', true)='on'
        OR (
            organization_id=current_setting('app.organization_id', true)
            AND (
                nullif(current_setting('app.project_id', true),'') IS NULL
                OR id=current_setting('app.project_id', true)
            )
        )
    )
    WITH CHECK (
        current_setting('app.identity_access', true)='on'
        OR organization_id=current_setting('app.organization_id', true)
    );
DROP POLICY IF EXISTS workspaces_scope_policy ON workspaces;
CREATE POLICY workspaces_scope_policy ON workspaces
    USING (
        current_setting('app.identity_access', true)='on'
        OR (
            organization_id=current_setting('app.organization_id', true)
            AND (
                nullif(current_setting('app.project_id', true),'') IS NULL
                OR project_id=current_setting('app.project_id', true)
            )
        )
    )
    WITH CHECK (
        current_setting('app.identity_access', true)='on'
        OR (
            organization_id=current_setting('app.organization_id', true)
            AND (
                nullif(current_setting('app.project_id', true),'') IS NULL
                OR project_id=current_setting('app.project_id', true)
            )
        )
    );

CREATE TABLE IF NOT EXISTS decisions (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    event_id text NOT NULL,
    actor text NOT NULL,
    decision text NOT NULL,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notes (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    event_id text NOT NULL,
    actor text NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversations (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    thread_id text NOT NULL,
    event_id text NOT NULL,
    role text NOT NULL,
    question text NOT NULL,
    intent text NOT NULL,
    answer text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_log (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    event_id text,
    run_id text NOT NULL,
    action text NOT NULL,
    model_version text,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_decisions_scope ON decisions(organization_id,project_id,workspace_id,event_id,created_at);
CREATE INDEX IF NOT EXISTS idx_notes_scope ON notes(organization_id,project_id,workspace_id,event_id,created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_scope ON conversations(organization_id,project_id,workspace_id,event_id,created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_scope ON audit_log(organization_id,project_id,workspace_id,event_id,created_at);

CREATE OR REPLACE FUNCTION fill_dashboard_template_version_scope()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    SELECT t.organization_id,t.project_id,t.workspace_id
      INTO NEW.organization_id,NEW.project_id,NEW.workspace_id
      FROM dashboard_templates t
     WHERE t.id=NEW.template_id;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_dashboard_template_version_scope ON dashboard_template_versions;
CREATE TRIGGER trg_dashboard_template_version_scope
BEFORE INSERT OR UPDATE ON dashboard_template_versions
FOR EACH ROW EXECUTE FUNCTION fill_dashboard_template_version_scope();

CREATE OR REPLACE FUNCTION fill_runtime_project_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.organization_id := COALESCE(NEW.organization_id,current_setting('app.organization_id', true));
    NEW.project_id := COALESCE(NEW.project_id,current_setting('app.project_id', true));
    NEW.workspace_id := COALESCE(NEW.workspace_id,'manufacturing-demo');
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_decisions_runtime_scope ON decisions;
CREATE TRIGGER trg_decisions_runtime_scope BEFORE INSERT OR UPDATE ON decisions
FOR EACH ROW EXECUTE FUNCTION fill_runtime_project_scope();
DROP TRIGGER IF EXISTS trg_notes_runtime_scope ON notes;
CREATE TRIGGER trg_notes_runtime_scope BEFORE INSERT OR UPDATE ON notes
FOR EACH ROW EXECUTE FUNCTION fill_runtime_project_scope();
DROP TRIGGER IF EXISTS trg_conversations_runtime_scope ON conversations;
CREATE TRIGGER trg_conversations_runtime_scope BEFORE INSERT OR UPDATE ON conversations
FOR EACH ROW EXECUTE FUNCTION fill_runtime_project_scope();
DROP TRIGGER IF EXISTS trg_audit_log_runtime_scope ON audit_log;
CREATE TRIGGER trg_audit_log_runtime_scope BEFORE INSERT OR UPDATE ON audit_log
FOR EACH ROW EXECUTE FUNCTION fill_runtime_project_scope();

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['decisions','notes','conversations','audit_log']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format(
          'CREATE POLICY project_scope_policy ON %I USING (' ||
          'organization_id=current_setting(''app.organization_id'', true) AND ' ||
          'project_id=current_setting(''app.project_id'', true)) ' ||
          'WITH CHECK (organization_id=current_setting(''app.organization_id'', true) AND ' ||
          'project_id=current_setting(''app.project_id'', true))',
          table_name
        );
    END LOOP;
END $$;
