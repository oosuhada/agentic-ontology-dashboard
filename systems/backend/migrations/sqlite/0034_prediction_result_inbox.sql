-- Receive-only Backend Inbox for Generator Prediction Result Batch payloads.
-- SQLite keeps local migration and smoke-test schema parity with PostgreSQL.

CREATE TABLE IF NOT EXISTS pm_prediction_result_inbox_batches (
    receive_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 GLOB '[0-9a-f]*' AND length(payload_sha256)=64),
    validation_status TEXT NOT NULL CHECK (
        validation_status IN ('accepted','duplicate','conflict','rejected')
    ),
    rejection_reason TEXT,
    raw_payload TEXT NOT NULL,
    promotion_result_id TEXT,
    received_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pm_prediction_result_inbox_items (
    receive_item_id TEXT PRIMARY KEY,
    receive_id TEXT NOT NULL REFERENCES pm_prediction_result_inbox_batches(receive_id)
      ON DELETE CASCADE,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 GLOB '[0-9a-f]*' AND length(payload_sha256)=64),
    validation_status TEXT NOT NULL CHECK (
        validation_status IN ('accepted','duplicate','conflict','rejected')
    ),
    rejection_reason TEXT,
    raw_item TEXT NOT NULL,
    promotion_result_id TEXT,
    received_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pm_prediction_inbox_batches_status
  ON pm_prediction_result_inbox_batches(
    organization_id,project_id,workspace_id,validation_status,received_at DESC
  );

CREATE INDEX IF NOT EXISTS idx_pm_prediction_inbox_items_batch
  ON pm_prediction_result_inbox_items(
    organization_id,project_id,workspace_id,batch_id
  );

CREATE INDEX IF NOT EXISTS idx_pm_prediction_inbox_batches_identity
  ON pm_prediction_result_inbox_batches(
    organization_id,project_id,workspace_id,batch_id,payload_sha256
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_pm_prediction_inbox_batches_accepted_identity
  ON pm_prediction_result_inbox_batches(
    organization_id,project_id,workspace_id,batch_id
  )
  WHERE validation_status='accepted';

CREATE INDEX IF NOT EXISTS idx_pm_prediction_inbox_items_identity
  ON pm_prediction_result_inbox_items(
    organization_id,project_id,workspace_id,event_id,payload_sha256
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_pm_prediction_inbox_items_accepted_identity
  ON pm_prediction_result_inbox_items(
    organization_id,project_id,workspace_id,event_id
  )
  WHERE validation_status='accepted';
