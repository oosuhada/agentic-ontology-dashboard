-- Generation counters prevent an ingestion that arrives during a long index
-- build from being accidentally marked ready by the older build.

ALTER TABLE knowledge_index_state
    ADD COLUMN IF NOT EXISTS requested_generation bigint NOT NULL DEFAULT 0;

ALTER TABLE knowledge_index_state
    ADD COLUMN IF NOT EXISTS indexed_generation bigint NOT NULL DEFAULT 0;
