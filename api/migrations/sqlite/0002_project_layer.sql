CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    domain_pack_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    default_workspace_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    UNIQUE (organization_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_projects_organization_status
    ON projects(organization_id, status, display_name);

CREATE TABLE IF NOT EXISTS user_project_scopes (
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
