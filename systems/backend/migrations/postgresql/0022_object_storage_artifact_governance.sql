CREATE TABLE IF NOT EXISTS artifact_objects (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    resource_type text NOT NULL CHECK (resource_type IN (
        'dataset_file','materialization','model','evaluation','feature_manifest',
        'explanation','report','export','backup','pipeline','other'
    )),
    resource_id text NOT NULL,
    resource_version text NOT NULL,
    object_key text NOT NULL,
    uri text NOT NULL,
    backend text NOT NULL CHECK (backend IN ('local','s3','gcs','azure')),
    checksum_sha256 text NOT NULL CHECK (checksum_sha256 ~ '^[a-f0-9]{64}$'),
    media_type text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    state text NOT NULL DEFAULT 'available' CHECK (state IN (
        'available','missing','checksum_mismatch','quarantined','retention_pending','deleted'
    )),
    retention_class text NOT NULL DEFAULT 'standard' CHECK (retention_class IN (
        'ephemeral','standard','regulated','backup','legal_hold'
    )),
    retain_until timestamptz,
    legal_hold boolean NOT NULL DEFAULT false,
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    verified_at timestamptz,
    deleted_at timestamptz,
    UNIQUE (organization_id, project_id, object_key),
    UNIQUE (
        organization_id,project_id,workspace_id,resource_type,resource_id,
        resource_version,checksum_sha256
    )
);

CREATE TABLE IF NOT EXISTS artifact_access_audit (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    artifact_id text NOT NULL REFERENCES artifact_objects(id),
    actor_user_id text NOT NULL REFERENCES users(id),
    action text NOT NULL CHECK (action IN (
        'register','verify','download_sign','download','retention_preview',
        'retention_apply','reconcile','restore','quarantine','delete'
    )),
    purpose text,
    decision text NOT NULL CHECK (decision IN ('allowed','denied','completed','failed')),
    signed_until timestamptz,
    request_id text,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS artifact_reconciliation_runs (
    id text PRIMARY KEY,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text REFERENCES workspaces(id),
    mode text NOT NULL CHECK (mode IN ('dry_run','apply')),
    state text NOT NULL CHECK (state IN ('running','succeeded','failed')),
    catalog_count integer NOT NULL DEFAULT 0,
    object_count integer NOT NULL DEFAULT 0,
    verified_count integer NOT NULL DEFAULT 0,
    missing_count integer NOT NULL DEFAULT 0,
    mismatch_count integer NOT NULL DEFAULT 0,
    orphan_count integer NOT NULL DEFAULT 0,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by text NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_artifact_objects_resource
    ON artifact_objects(organization_id,project_id,resource_type,resource_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_objects_retention
    ON artifact_objects(organization_id,project_id,state,retain_until)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_artifact_access_audit_scope
    ON artifact_access_audit(organization_id,project_id,artifact_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_reconciliation_scope
    ON artifact_reconciliation_runs(organization_id,project_id,created_at DESC);

ALTER TABLE artifact_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_access_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact_reconciliation_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS artifact_objects_scope ON artifact_objects;
CREATE POLICY artifact_objects_scope ON artifact_objects
    USING (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    )
    WITH CHECK (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    );
DROP POLICY IF EXISTS artifact_access_audit_scope ON artifact_access_audit;
CREATE POLICY artifact_access_audit_scope ON artifact_access_audit
    USING (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    )
    WITH CHECK (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    );
DROP POLICY IF EXISTS artifact_reconciliation_scope ON artifact_reconciliation_runs;
CREATE POLICY artifact_reconciliation_scope ON artifact_reconciliation_runs
    USING (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    )
    WITH CHECK (
        organization_id = nullif(current_setting('app.organization_id', true), '')
        AND project_id = nullif(current_setting('app.project_id', true), '')
    );
