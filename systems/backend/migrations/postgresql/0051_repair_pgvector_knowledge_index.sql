-- Older production volumes may have applied the Dataset Projection migration
-- before the database image exposed pgvector.  Re-assert the extension and
-- physical vector column/index now that Enterprise Knowledge depends on them.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE vector_document_chunks
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_vector_chunks_embedding
    ON vector_document_chunks USING hnsw (embedding vector_cosine_ops);
