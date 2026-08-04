-- Project 3 provider lineage for version-scoped graph projections.

ALTER TABLE store_projections
    ADD COLUMN IF NOT EXISTS provider_run_id text;

ALTER TABLE store_projections
    ADD COLUMN IF NOT EXISTS provider_metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_store_projections_graph_delivery
    ON store_projections(project_id,store_kind,status,updated_at)
    WHERE store_kind='graph';
