ALTER TABLE knowledge_index_state
    ADD COLUMN requested_generation INTEGER NOT NULL DEFAULT 0;

ALTER TABLE knowledge_index_state
    ADD COLUMN indexed_generation INTEGER NOT NULL DEFAULT 0;
