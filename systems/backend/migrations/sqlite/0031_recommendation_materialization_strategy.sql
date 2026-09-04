ALTER TABLE closed_loop_recommendations
  ADD COLUMN materialization_strategy TEXT NOT NULL DEFAULT 'runtime_generated'
  CHECK(materialization_strategy IN ('runtime_generated','imported_precomputed'));
