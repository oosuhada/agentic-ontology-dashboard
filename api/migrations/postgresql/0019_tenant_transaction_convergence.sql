-- Phase 20: additive Action recovery metadata used by transactional outbox recovery.
ALTER TABLE ontology_action_invocations
    ADD COLUMN IF NOT EXISTS recovery_state text NOT NULL DEFAULT 'none';
ALTER TABLE ontology_action_invocations
    ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0;
ALTER TABLE ontology_action_invocations
    ADD COLUMN IF NOT EXISTS last_error_at timestamptz;
ALTER TABLE ontology_action_invocations
    ADD COLUMN IF NOT EXISTS outbox_event_id uuid REFERENCES transactional_outbox(id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ontology_action_recovery_state_check'
    ) THEN
        ALTER TABLE ontology_action_invocations
            ADD CONSTRAINT ontology_action_recovery_state_check
            CHECK (recovery_state IN (
                'none','retryable','compensation_required','reconciled','dead_letter'
            ));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_ontology_actions_recovery
    ON ontology_action_invocations(
        organization_id,project_id,recovery_state,created_at DESC
    )
    WHERE recovery_state <> 'none';

-- Existing policy remains authoritative; restate the required enforcement flag
-- for upgraded databases without replacing or weakening the policy.
ALTER TABLE ontology_action_invocations ENABLE ROW LEVEL SECURITY;
