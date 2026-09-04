-- Idempotent presentation scenario for the Team DB Reliability demo.
-- Run with psql against the authoritative Team DB after live result artifacts exist.
-- It selects a high-risk CNC RESULT# that already has a later, lower-risk
-- Product Result for the same asset. The completed proof asset is therefore
-- separate from the still-actionable live demo asset and Before/After never
-- invents a post-maintenance prediction.

DO $$
DECLARE
  v_org text := 'org-ontology-demo';
  v_project text := 'manufacturing-demo-project';
  v_workspace text := 'manufacturing-demo';
  v_event text;
  v_asset text;
  v_asset_type text;
  v_prediction_result text;
  v_schema text;
  v_policy text;
  v_observed timestamptz;
  v_after_event text;
  v_after_observed timestamptz;
  v_before_risk numeric;
  v_after_risk numeric;
  v_active_event text;
  v_active_asset text;
  v_reco text;
  v_decision text;
  v_inspection_wo text;
  v_inspection_result text;
  v_maintenance_wo text;
  v_action text;
  v_maintenance_event text;
  v_t_decision timestamptz;
  v_t_inspection_requested timestamptz;
  v_t_inspection_completed timestamptz;
  v_t_reco timestamptz;
  v_t_approved timestamptz;
  v_t_started timestamptz;
  v_t_completed timestamptz;
BEGIN
  PERFORM set_config('app.organization_id', v_org, true);
  PERFORM set_config('app.project_id', v_project, true);

  SELECT before_result.artifact_id, before_result.asset_id, before_result.asset_type,
         before_result.prediction_result_id, before_result.schema_version,
         COALESCE(before_result.recommended_action->>'policy_version', 'recommendation-policy-v1'),
         before_result.observed_at, after_result.artifact_id, after_result.observed_at,
         before_result.failure_probability, after_result.failure_probability
    INTO v_event, v_asset, v_asset_type, v_prediction_result, v_schema, v_policy,
         v_observed, v_after_event, v_after_observed, v_before_risk, v_after_risk
  FROM pm_result_artifacts before_result
  JOIN LATERAL (
    SELECT candidate.artifact_id, candidate.observed_at, candidate.failure_probability
    FROM pm_result_artifacts candidate
    WHERE candidate.organization_id = before_result.organization_id
      AND candidate.project_id = before_result.project_id
      AND candidate.workspace_id = before_result.workspace_id
      AND candidate.asset_id = before_result.asset_id
      AND candidate.observed_at >= before_result.observed_at + interval '60 minutes'
      AND candidate.failure_probability < before_result.failure_probability
    ORDER BY candidate.observed_at ASC
    LIMIT 1
  ) after_result ON true
  WHERE before_result.organization_id = v_org
    AND before_result.project_id = v_project
    AND before_result.workspace_id = v_workspace
    AND before_result.artifact_id LIKE 'RESULT#%'
    AND before_result.asset_type = 'cnc'
    AND before_result.failure_probability >= 0.62
  ORDER BY before_result.observed_at DESC, before_result.failure_probability DESC
  LIMIT 1;

  IF v_event IS NULL THEN
    RAISE EXCEPTION 'No grounded CNC Before/After Result pair exists for %.%. Run the current runtime until a later lower-risk Result is available.', v_project, v_workspace;
  END IF;

  SELECT artifact_id, asset_id INTO v_active_event, v_active_asset
  FROM pm_result_artifacts
  WHERE organization_id = v_org AND project_id = v_project AND workspace_id = v_workspace
    AND asset_id <> v_asset AND status_grade IN ('critical', 'warning')
  ORDER BY observed_at DESC, failure_probability DESC
  LIMIT 1;
  IF v_active_event IS NULL THEN
    RAISE EXCEPTION 'A distinct actionable live demo asset is required; completed proof asset=%', v_asset;
  END IF;

  v_reco := 'team-demo-reco:' || v_event;
  v_decision := 'team-demo-decision:' || v_event;
  v_inspection_wo := 'team-demo-inspection-wo:' || v_event;
  v_inspection_result := 'team-demo-inspection-result:' || v_event;
  v_maintenance_wo := 'team-demo-maintenance-wo:' || v_event;
  v_action := 'team-demo-maintenance-action:' || v_event;
  v_maintenance_event := 'team-demo-maintenance-event:' || v_event;

  v_t_decision := v_observed + interval '6 minutes';
  v_t_inspection_requested := v_observed + interval '7 minutes';
  v_t_inspection_completed := v_observed + interval '17 minutes';
  v_t_reco := v_observed + interval '18 minutes';
  v_t_approved := v_observed + interval '22 minutes';
  v_t_completed := v_after_observed - interval '5 minutes';
  v_t_started := v_t_completed - interval '25 minutes';

  INSERT INTO decisions(id, organization_id, project_id, workspace_id, event_id, actor, decision, note, created_at)
  VALUES('team-demo-audit-decision:' || v_event, v_org, v_project, v_workspace, v_event, '김현우', 'request_inspection', '시연용 Case: 고위험 설비에 대한 현장 점검 요청을 기록했습니다.', v_t_decision)
  ON CONFLICT (id) DO UPDATE SET actor = EXCLUDED.actor, decision = EXCLUDED.decision, note = EXCLUDED.note, created_at = EXCLUDED.created_at;

  INSERT INTO closed_loop_work_orders(work_order_id, organization_id, project_id, workspace_id, event_id, asset_id, equipment_id, work_type, status, idempotency_key, authorization_json, created_at, updated_at, asset_type)
  VALUES(v_inspection_wo, v_org, v_project, v_workspace, v_event, v_asset, v_asset, 'inspection', 'completed', 'team-demo-inspection:' || v_event, jsonb_build_object('actor','김현우','scope','presentation-demo'), v_t_inspection_requested, v_t_inspection_completed, v_asset_type)
  ON CONFLICT (work_order_id) DO UPDATE SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at, authorization_json = EXCLUDED.authorization_json;

  INSERT INTO closed_loop_inspection_results(inspection_result_id, organization_id, project_id, workspace_id, work_order_id, event_id, asset_id, equipment_id, asset_type, outcome, checklist_json, measurements_json, findings_json, note, recorded_by, recorded_at, created_at)
  VALUES(v_inspection_result, v_org, v_project, v_workspace, v_inspection_wo, v_event, v_asset, v_asset, v_asset_type, 'maintenance_recommended',
    jsonb_build_array('주축 회전수 현재값 확인', '공구 마모 상태 확인', '절삭 부하음/진동 확인'),
    jsonb_build_object('spindle_rpm_review','abnormal_pattern_confirmed','tool_wear_visual','wear_confirmed'),
    jsonb_build_array('6시간 평균 대비 회전수 변동 확대', '공구 교체 권장'),
    '시연용 Case: 점검 결과 공구 교체 정비가 필요하다고 기록했습니다.', '박지민', v_t_inspection_completed, v_t_inspection_completed)
  ON CONFLICT (inspection_result_id) DO UPDATE SET outcome = EXCLUDED.outcome, checklist_json = EXCLUDED.checklist_json, measurements_json = EXCLUDED.measurements_json, findings_json = EXCLUDED.findings_json, note = EXCLUDED.note, recorded_by = EXCLUDED.recorded_by, recorded_at = EXCLUDED.recorded_at;

  INSERT INTO closed_loop_recommendations(recommendation_id, organization_id, project_id, workspace_id, event_id, asset_id, equipment_id, recommendation_origin, status, source_action_id, source_product_result_id, source_evidence_id, source_schema_version, source_policy_version, label, kind, requires_human_approval, basis_json, created_at, updated_at, materialization_strategy, asset_type, source_inspection_work_order_id, source_inspection_reference, action_code, authored_by, authored_at)
  VALUES(v_reco, v_org, v_project, v_workspace, v_event, v_asset, v_asset, 'operations_manual', 'accepted', 'team-demo-action:' || v_event, v_prediction_result, 'product-result-artifact://' || v_event, COALESCE(v_schema,'result-artifact-v1.0'), v_policy, '공구 교체 및 주축 상태 재확인', 'TOOL_REPLACEMENT', true,
    jsonb_build_array('점검 결과 공구 마모 확인', '고위험 RESULT snapshot', '정비 후 재관측 필요'), v_t_reco, v_t_approved, 'runtime_generated', v_asset_type, v_inspection_wo, v_inspection_result, 'TOOL_REPLACEMENT', '김현우', v_t_reco)
  ON CONFLICT (recommendation_id) DO UPDATE SET status = EXCLUDED.status, label = EXCLUDED.label, basis_json = EXCLUDED.basis_json, updated_at = EXCLUDED.updated_at, authored_at = EXCLUDED.authored_at;

  INSERT INTO closed_loop_recommendation_decisions(decision_id, organization_id, project_id, workspace_id, event_id, recommendation_id, disposition, actor_id, note, decided_at, created_at)
  VALUES(v_decision, v_org, v_project, v_workspace, v_event, v_reco, 'accept', 'kim-hyunwoo', '시연용 Case: 정비안을 승인했습니다.', v_t_approved, v_t_approved)
  ON CONFLICT (decision_id) DO UPDATE SET disposition = EXCLUDED.disposition, note = EXCLUDED.note, decided_at = EXCLUDED.decided_at, created_at = EXCLUDED.created_at;

  INSERT INTO closed_loop_work_orders(work_order_id, organization_id, project_id, workspace_id, event_id, asset_id, equipment_id, work_type, status, idempotency_key, authorization_json, created_at, updated_at, asset_type)
  VALUES(v_maintenance_wo, v_org, v_project, v_workspace, v_event, v_asset, v_asset, 'maintenance', 'completed', 'team-demo-maintenance:' || v_event, jsonb_build_object('actor','김현우','approved_at',v_t_approved,'scope','presentation-demo'), v_t_approved, v_t_completed, v_asset_type)
  ON CONFLICT (work_order_id) DO UPDATE SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at, authorization_json = EXCLUDED.authorization_json;

  INSERT INTO closed_loop_maintenance_actions(maintenance_action_id, organization_id, project_id, workspace_id, work_order_id, event_id, asset_id, equipment_id, recommendation_id, recommendation_decision_id, simulation_session_id, action_code, lifecycle_state_version, status, idempotency_key, started_at, completed_at, restart_at, created_at, updated_at)
  VALUES(v_action, v_org, v_project, v_workspace, v_maintenance_wo, v_event, v_asset, v_asset, v_reco, v_decision, 'team-demo-session', 'TOOL_REPLACEMENT', 2, 'completed', 'team-demo-action:' || v_event, v_t_started, v_t_completed, NULL, v_t_approved, v_t_completed)
  ON CONFLICT (maintenance_action_id) DO UPDATE SET status = EXCLUDED.status, lifecycle_state_version = EXCLUDED.lifecycle_state_version, started_at = EXCLUDED.started_at, completed_at = EXCLUDED.completed_at, updated_at = EXCLUDED.updated_at;

  INSERT INTO closed_loop_maintenance_events(maintenance_event_id, organization_id, project_id, workspace_id, maintenance_action_id, work_order_id, event_id, asset_id, equipment_id, recommendation_id, recommendation_decision_id, simulation_session_id, action_code, state_patch_json, maintenance_started_at, completed_at, outcome, created_at)
  VALUES(v_maintenance_event, v_org, v_project, v_workspace, v_action, v_maintenance_wo, v_event, v_asset, v_asset, v_reco, v_decision, 'team-demo-session', 'TOOL_REPLACEMENT', jsonb_build_object('demo','presentation','risk_before',v_before_risk,'risk_after',v_after_risk,'after_result_id',v_after_event), v_t_started, v_t_completed, 'completed', v_t_completed)
  ON CONFLICT (maintenance_event_id) DO UPDATE SET state_patch_json = EXCLUDED.state_patch_json, maintenance_started_at = EXCLUDED.maintenance_started_at, completed_at = EXCLUDED.completed_at, outcome = EXCLUDED.outcome;

  DELETE FROM closed_loop_activities WHERE event_id = v_event AND activity_id LIKE 'team-demo-activity:%';
  INSERT INTO closed_loop_activities(activity_id, organization_id, project_id, workspace_id, event_id, equipment_id, recommendation_id, work_order_id, maintenance_action_id, maintenance_event_id, aggregate_type, aggregate_id, activity_type, actor_user_id, actor_display_name, before_status, after_status, timeline_order, payload_json, created_at)
  VALUES
    ('team-demo-activity:001:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, NULL, v_inspection_wo, NULL, NULL, 'work_order', v_inspection_wo, 'work_order.requested', 'kim-hyunwoo', '김현우', NULL, 'requested', 1, '{}'::jsonb, v_t_inspection_requested),
    ('team-demo-activity:002:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, NULL, v_inspection_wo, NULL, NULL, 'work_order', v_inspection_wo, 'work_order.started', 'park-jimin', '박지민', 'requested', 'in_progress', 2, '{}'::jsonb, v_t_inspection_requested + interval '2 minutes'),
    ('team-demo-activity:003:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, NULL, v_inspection_wo, NULL, NULL, 'work_order', v_inspection_wo, 'inspection.completed', 'park-jimin', '박지민', 'in_progress', 'completed', 3, '{}'::jsonb, v_t_inspection_completed),
    ('team-demo-activity:004:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, v_reco, NULL, NULL, NULL, 'recommendation', v_reco, 'recommendation.proposed', 'kim-hyunwoo', '김현우', NULL, 'proposed', 4, '{}'::jsonb, v_t_reco),
    ('team-demo-activity:005:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, v_reco, NULL, NULL, NULL, 'recommendation', v_reco, 'recommendation.decided', 'kim-hyunwoo', '김현우', 'proposed', 'accepted', 5, '{}'::jsonb, v_t_approved),
    ('team-demo-activity:006:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, v_reco, v_maintenance_wo, NULL, NULL, 'work_order', v_maintenance_wo, 'work_order.approved', 'kim-hyunwoo', '김현우', 'requested', 'approved', 6, '{}'::jsonb, v_t_approved),
    ('team-demo-activity:007:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, v_reco, v_maintenance_wo, v_action, NULL, 'maintenance_action', v_action, 'maintenance.started', 'choi-minho', '최민호', 'planned', 'in_progress', 7, '{}'::jsonb, v_t_started),
    ('team-demo-activity:008:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, v_reco, v_maintenance_wo, v_action, v_maintenance_event, 'maintenance_event', v_maintenance_event, 'maintenance.completed', 'choi-minho', '최민호', 'in_progress', 'completed', 8, '{}'::jsonb, v_t_completed),
    ('team-demo-activity:009:' || v_event, v_org, v_project, v_workspace, v_event, v_asset, v_reco, v_maintenance_wo, v_action, v_maintenance_event, 'result_artifact', v_after_event, 'post_maintenance.predicted', 'generator-runtime', '예측 시스템', 'completed', 'ready_for_reprediction', 9, jsonb_build_object('before_result_id',v_event,'after_result_id',v_after_event,'risk_before',v_before_risk,'risk_after',v_after_risk), v_after_observed);

  RAISE NOTICE 'Completed proof: % % -> % (% -> %). Active demo: % %', v_asset, v_event, v_after_event, v_before_risk, v_after_risk, v_active_asset, v_active_event;
END $$;
