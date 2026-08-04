CREATE TABLE IF NOT EXISTS modeling_model_release_requests (
    release_request_id text PRIMARY KEY,
    organization_id text NOT NULL,
    project_id text NOT NULL,
    workspace_id text NOT NULL,
    model_version_id text NOT NULL,
    status text NOT NULL,
    revision integer NOT NULL DEFAULT 1,
    requested_by text NOT NULL,
    request_rationale text NOT NULL,
    decided_by text,
    decision_rationale text,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    UNIQUE (organization_id, project_id, workspace_id, model_version_id, status)
);
ALTER TABLE modeling_model_release_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_scope_policy ON modeling_model_release_requests;
CREATE POLICY project_scope_policy ON modeling_model_release_requests
    USING (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    )
    WITH CHECK (
        organization_id=current_setting('app.organization_id',true)
        AND project_id=current_setting('app.project_id',true)
    );
CREATE INDEX IF NOT EXISTS idx_model_release_requests_scope
    ON modeling_model_release_requests(organization_id,project_id,workspace_id,status,created_at);
