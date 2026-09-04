-- Distinguish a user's explicit Dataset choice from a local runtime default.
-- Automatic rows may be written by demo/runtime orchestration, but the read
-- policy continues to treat only explicit rows as a user preference.

ALTER TABLE pm_workspace_dataset_selections
    DROP CONSTRAINT IF EXISTS pm_workspace_dataset_selections_selection_mode_check;

ALTER TABLE pm_workspace_dataset_selections
    ADD CONSTRAINT pm_workspace_dataset_selections_selection_mode_check
    CHECK (selection_mode IN ('explicit', 'automatic'));

COMMENT ON COLUMN pm_workspace_dataset_selections.selection_mode IS
    'explicit=user choice; automatic=runtime orchestration provenance and never a user preference';
