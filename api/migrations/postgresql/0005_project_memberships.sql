CREATE TABLE IF NOT EXISTS project_memberships (
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(user_id,project_id),
    CHECK(status IN ('active','suspended'))
);
CREATE INDEX IF NOT EXISTS idx_project_memberships_scope
    ON project_memberships(organization_id,project_id,status,user_id);

CREATE TABLE IF NOT EXISTS project_membership_roles (
    user_id text NOT NULL,
    organization_id text NOT NULL REFERENCES organizations(id),
    project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role_code text NOT NULL REFERENCES roles(code),
    PRIMARY KEY(user_id,project_id,role_code),
    FOREIGN KEY(user_id,project_id)
        REFERENCES project_memberships(user_id,project_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_project_membership_roles_scope
    ON project_membership_roles(organization_id,project_id,role_code,user_id);

CREATE OR REPLACE FUNCTION fill_project_membership_scope()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path=public
AS $$
BEGIN
    IF TG_TABLE_NAME='project_memberships' THEN
        SELECT organization_id INTO NEW.organization_id FROM projects WHERE id=NEW.project_id;
    ELSE
        SELECT organization_id INTO NEW.organization_id
          FROM project_memberships
         WHERE user_id=NEW.user_id AND project_id=NEW.project_id;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_project_memberships_scope ON project_memberships;
CREATE TRIGGER trg_project_memberships_scope
BEFORE INSERT OR UPDATE ON project_memberships
FOR EACH ROW EXECUTE FUNCTION fill_project_membership_scope();
DROP TRIGGER IF EXISTS trg_project_membership_roles_scope ON project_membership_roles;
CREATE TRIGGER trg_project_membership_roles_scope
BEFORE INSERT OR UPDATE ON project_membership_roles
FOR EACH ROW EXECUTE FUNCTION fill_project_membership_scope();

ALTER TABLE project_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_membership_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_scope_policy ON project_memberships
    USING (
        current_setting('app.identity_access',true)='on'
        OR (
            organization_id=current_setting('app.organization_id',true)
            AND (
                nullif(current_setting('app.project_id',true),'') IS NULL
                OR project_id=current_setting('app.project_id',true)
            )
        )
    )
    WITH CHECK (
        current_setting('app.identity_access',true)='on'
        OR (
            organization_id=current_setting('app.organization_id',true)
            AND project_id=current_setting('app.project_id',true)
        )
    );
CREATE POLICY project_scope_policy ON project_membership_roles
    USING (
        current_setting('app.identity_access',true)='on'
        OR (
            organization_id=current_setting('app.organization_id',true)
            AND (
                nullif(current_setting('app.project_id',true),'') IS NULL
                OR project_id=current_setting('app.project_id',true)
            )
        )
    )
    WITH CHECK (
        current_setting('app.identity_access',true)='on'
        OR (
            organization_id=current_setting('app.organization_id',true)
            AND project_id=current_setting('app.project_id',true)
        )
    );

-- Backfill active membership and Project role assignments from the compatibility
-- scope/global-role tables. New admin writes target these canonical tables.
INSERT INTO project_memberships(user_id,organization_id,project_id,status,created_at,updated_at)
SELECT ups.user_id,ups.organization_id,ups.project_id,'active',now(),now()
  FROM user_project_scopes ups
ON CONFLICT(user_id,project_id) DO NOTHING;

INSERT INTO project_membership_roles(user_id,organization_id,project_id,role_code)
SELECT pm.user_id,pm.organization_id,pm.project_id,ur.role_code
  FROM project_memberships pm
  JOIN user_roles ur ON ur.user_id=pm.user_id
ON CONFLICT(user_id,project_id,role_code) DO NOTHING;
