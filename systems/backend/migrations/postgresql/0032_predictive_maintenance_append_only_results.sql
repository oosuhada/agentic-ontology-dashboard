-- Preserve every Product Result for an asset within an immutable Dataset Version.
-- Result identity remains (dataset_version_id, artifact_id); latest-state reads use
-- the ordered lookup index instead of enforcing one physical row per asset.

ALTER TABLE pm_result_artifacts
    DROP CONSTRAINT IF EXISTS pm_result_artifacts_dataset_version_id_asset_id_key;

CREATE INDEX IF NOT EXISTS idx_pm_result_artifacts_version_asset_latest
    ON pm_result_artifacts(dataset_version_id, asset_id, observed_at DESC, created_at DESC);

-- End of migration 0032.
