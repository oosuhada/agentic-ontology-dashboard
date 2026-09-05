-- Candidate-level hybrid retrieval combines pgvector HNSW candidates with
-- PostgreSQL full-text candidates before reranking.

CREATE INDEX IF NOT EXISTS idx_vector_chunks_content_fts
    ON vector_document_chunks USING gin (to_tsvector('simple', content));
