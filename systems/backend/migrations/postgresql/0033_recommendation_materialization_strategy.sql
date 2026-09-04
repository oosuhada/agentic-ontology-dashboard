ALTER TABLE closed_loop_recommendations
  ADD COLUMN IF NOT EXISTS materialization_strategy text NOT NULL DEFAULT 'runtime_generated'
  CHECK(materialization_strategy IN ('runtime_generated','imported_precomputed'));
