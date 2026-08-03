CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    subject_object_type TEXT NOT NULL,
    subject_object_id TEXT NOT NULL,
    prediction_status TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    UNIQUE (project_id, prediction_id)
);
CREATE INDEX IF NOT EXISTS idx_prediction_results_scope
    ON prediction_results(organization_id, project_id, workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_prediction_results_subject
    ON prediction_results(organization_id, project_id, workspace_id, subject_object_type, subject_object_id, created_at);
