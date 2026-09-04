-- Persist each user's explicit predictive-maintenance Dataset Version selection.
-- Automatic defaults are derived at read time so a newly published canonical
-- release becomes active without copying mutable flags onto immutable versions.

CREATE TABLE IF NOT EXISTS pm_workspace_dataset_selections (
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id),
    workspace_id text NOT NULL REFERENCES workspaces(id),
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset_version_id text NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
    selection_mode text NOT NULL DEFAULT 'explicit'
        CHECK (selection_mode = 'explicit'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, project_id, workspace_id, user_id),
    FOREIGN KEY (dataset_version_id, organization_id, project_id, workspace_id)
        REFERENCES dataset_versions(id, organization_id, project_id, workspace_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pm_workspace_dataset_selection_version
    ON pm_workspace_dataset_selections(
        organization_id, project_id, workspace_id, dataset_version_id
    );

ALTER TABLE pm_workspace_dataset_selections ENABLE ROW LEVEL SECURITY;
ALTER TABLE pm_workspace_dataset_selections FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS project_scope_policy ON pm_workspace_dataset_selections;
CREATE POLICY project_scope_policy ON pm_workspace_dataset_selections
    USING (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    )
    WITH CHECK (
        organization_id = current_setting('app.organization_id', true)
        AND project_id = current_setting('app.project_id', true)
    );

COMMENT ON TABLE pm_workspace_dataset_selections IS
    'User-scoped explicit Dataset Version choice; automatic release defaults remain deterministic policy.';
