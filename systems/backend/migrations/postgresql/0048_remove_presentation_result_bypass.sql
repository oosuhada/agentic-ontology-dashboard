-- Remove the retired browser-driven presentation Result path.
--
-- presentation-live-v1 observations and predictions bypassed gen_data and
-- Generator Runtime, so they are not valid Product Result lineage.  The
-- production UI now reads only the canonical source/runtime path and this
-- migration removes previously accumulated bypass rows.

DELETE FROM pm_prediction_timeline
WHERE model_version = 'presentation-live-v1';

DELETE FROM pm_result_artifacts
WHERE model_version = 'presentation-live-v1';

DELETE FROM pm_prediction_snapshots
WHERE model_version = 'presentation-live-v1';

DELETE FROM prediction_results
WHERE model_version = 'presentation-live-v1';

DELETE FROM pm_cnc_observations
WHERE generator_version = 'presentation-live-v1';

DELETE FROM pm_prediction_result_inbox_batches
WHERE raw_payload::text LIKE '%"model_version":"presentation-live-v1"%'
   OR raw_payload::text LIKE '%"model_version": "presentation-live-v1"%';
