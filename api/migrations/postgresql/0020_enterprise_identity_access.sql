CREATE TABLE IF NOT EXISTS identity_providers (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    provider_type text NOT NULL CHECK (provider_type IN ('local','oidc')),
    issuer text,
    client_id text,
    audience text,
    verified_domains_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    jit_policy text NOT NULL DEFAULT 'invite_only'
        CHECK (jit_policy IN ('disabled','invite_only','approved_groups')),
    status text NOT NULL DEFAULT 'not_configured'
        CHECK (status IN ('active','disabled','not_configured','error')),
    secret_reference text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, provider_type, issuer)
);

CREATE TABLE IF NOT EXISTS identity_group_mappings (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    provider_id text NOT NULL REFERENCES identity_providers(id) ON DELETE CASCADE,
    external_group text NOT NULL,
    organization_role text,
    project_id text REFERENCES projects(id),
    project_role text,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','approved','disabled')),
    approved_by text REFERENCES users(id),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, provider_id, external_group, project_id)
);

CREATE TABLE IF NOT EXISTS identity_invitations (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    email text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    project_roles_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    revoked_at timestamptz,
    invited_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scim_resources (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    resource_type text NOT NULL CHECK (resource_type IN ('User','Group')),
    external_id text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, resource_type, external_id)
);

CREATE TABLE IF NOT EXISTS service_accounts (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    display_name text NOT NULL,
    project_scopes_json jsonb NOT NULL,
    permissions_json jsonb NOT NULL,
    credential_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    rotated_at timestamptz,
    revoked_at timestamptz,
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS enterprise_access_audit (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    actor_type text NOT NULL CHECK (actor_type IN ('user','service','system')),
    actor_id text NOT NULL,
    event_type text NOT NULL,
    target_id text,
    incident_reason text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'identity_providers','identity_group_mappings','identity_invitations',
        'scim_resources','service_accounts','enterprise_access_audit'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS organization_scope_policy ON %I', table_name);
        EXECUTE format(
            'CREATE POLICY organization_scope_policy ON %I USING (' ||
            'organization_id = nullif(current_setting(''app.organization_id'', true), '''')' ||
            ') WITH CHECK (' ||
            'organization_id = nullif(current_setting(''app.organization_id'', true), '''')' ||
            ')',
            table_name
        );
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_scim_resources_scope
    ON scim_resources(organization_id,resource_type,active,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_accounts_scope
    ON service_accounts(organization_id,expires_at,revoked_at);
