CREATE TABLE IF NOT EXISTS identity_providers (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    issuer TEXT,
    client_id TEXT,
    audience TEXT,
    verified_domains_json TEXT NOT NULL DEFAULT '[]',
    jit_policy TEXT NOT NULL DEFAULT 'invite_only',
    status TEXT NOT NULL DEFAULT 'not_configured',
    secret_reference TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id, provider_type, issuer)
);
CREATE TABLE IF NOT EXISTS identity_group_mappings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    external_group TEXT NOT NULL,
    organization_role TEXT,
    project_id TEXT,
    project_role TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    approved_by TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (organization_id, provider_id, external_group, project_id)
);
CREATE TABLE IF NOT EXISTS identity_invitations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    email TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    project_roles_json TEXT NOT NULL DEFAULT '{}',
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    revoked_at TEXT,
    invited_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scim_resources (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (organization_id, resource_type, external_id)
);
CREATE TABLE IF NOT EXISTS service_accounts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    project_scopes_json TEXT NOT NULL,
    permissions_json TEXT NOT NULL,
    credential_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    rotated_at TEXT,
    revoked_at TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enterprise_access_audit (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target_id TEXT,
    incident_reason TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scim_resources_scope
    ON scim_resources(organization_id,resource_type,active,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_accounts_scope
    ON service_accounts(organization_id,expires_at,revoked_at);
