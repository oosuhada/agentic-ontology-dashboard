-- Additive identity parity for the PostgreSQL runtime.
-- SQLite bootstrap has carried these user-level permission and display preference
-- tables since the original identity implementation; PostgreSQL must expose the
-- same contract before IdentityService principal resolution runs.

CREATE TABLE IF NOT EXISTS user_permission_overrides (
    user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_code text NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    allowed integer NOT NULL CHECK (allowed IN (0, 1)),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, permission_code)
);

CREATE INDEX IF NOT EXISTS idx_user_permission_overrides_user
    ON user_permission_overrides(user_id, permission_code);

CREATE TABLE IF NOT EXISTS user_display_preferences (
    user_id text PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE user_permission_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_display_preferences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_scope_policy ON user_permission_overrides;
CREATE POLICY identity_scope_policy ON user_permission_overrides
    USING (
        current_setting('app.identity_access', true) = 'on'
        OR EXISTS (
            SELECT 1
            FROM users
            WHERE users.id = user_permission_overrides.user_id
              AND users.organization_id = current_setting('app.organization_id', true)
        )
    )
    WITH CHECK (
        current_setting('app.identity_access', true) = 'on'
        OR EXISTS (
            SELECT 1
            FROM users
            WHERE users.id = user_permission_overrides.user_id
              AND users.organization_id = current_setting('app.organization_id', true)
        )
    );

DROP POLICY IF EXISTS identity_scope_policy ON user_display_preferences;
CREATE POLICY identity_scope_policy ON user_display_preferences
    USING (
        current_setting('app.identity_access', true) = 'on'
        OR EXISTS (
            SELECT 1
            FROM users
            WHERE users.id = user_display_preferences.user_id
              AND users.organization_id = current_setting('app.organization_id', true)
        )
    )
    WITH CHECK (
        current_setting('app.identity_access', true) = 'on'
        OR EXISTS (
            SELECT 1
            FROM users
            WHERE users.id = user_display_preferences.user_id
              AND users.organization_id = current_setting('app.organization_id', true)
        )
    );
