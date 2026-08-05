CREATE TABLE IF NOT EXISTS ontology_action_invocations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    actor_display_name TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    request_json TEXT NOT NULL,
    state TEXT NOT NULL,
    result_json TEXT,
    error_json TEXT,
    audit_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    recovery_state TEXT NOT NULL DEFAULT 'none'
        CHECK (recovery_state IN ('none','retryable','compensation_required','reconciled','dead_letter')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_at TEXT,
    outbox_event_id TEXT,
    UNIQUE (workspace_id, actor_user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_ontology_actions_recovery
    ON ontology_action_invocations(
        organization_id,project_id,recovery_state,created_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_ontology_invocation_object
    ON ontology_action_invocations(workspace_id, object_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ontology_invocation_created
    ON ontology_action_invocations(created_at);
