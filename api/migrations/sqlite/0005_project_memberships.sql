CREATE TABLE IF NOT EXISTS project_memberships (
    user_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_project_memberships_scope
    ON project_memberships(organization_id, project_id, status, user_id);

CREATE TABLE IF NOT EXISTS project_membership_roles (
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    role_code TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id, role_code),
    FOREIGN KEY (user_id, project_id)
        REFERENCES project_memberships(user_id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (role_code) REFERENCES roles(code)
);
CREATE INDEX IF NOT EXISTS idx_project_membership_roles_project
    ON project_membership_roles(project_id, role_code, user_id);
