from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from ..contracts import AppLocale
from ..adapters.models import (
    DataQuality,
    EvidenceSource,
    PredictionEvidence,
    PredictionModel,
    PredictionResult,
    PredictionSubject,
    PredictionValue,
    RecommendedAction,
)
from .models import (
    DashboardDataSource,
    DashboardEquipment,
    DashboardEventDetail,
    DashboardEventSummary,
    DatasetVersionOption,
    DatasetVersionOptions,
    DatasetVersionRuntimeContext,
    GovernedProductResult,
    GovernanceProvenance,
    GraphReadiness,
    ObservationQueryResponse,
    PolicyRecommendation,
    PredictiveMaintenanceDashboardResponse,
    ProductFactor,
    ProductResultPage,
    ProductResultProvenance,
    PredictiveMaintenanceReleaseOverview,
    ReplayCursor,
    ReplaySessionRecord,
    ReplaySessionSnapshot,
    SemanticQueryCapability,
    SensorObservation,
    SnapshotDrilldown,
    TimelinePrediction,
)
from .repository import ALLOWED_DERIVED_MEASURES, PredictiveMaintenanceRuntimeRepository


V3_1_SOURCE_VERSION = "canonical-ai4i-physics-v3.1"
V3_1_MODEL_VERSION = "independent-logreg-v3.1"
V3_1_RESULT_SCHEMA = "result-artifact-v1.0"
PREDICTION_TASK = "binary_failure_within_horizon"

PM_STATUS_LABELS: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {"critical": "긴급 검토", "warning": "경고", "attention": "관찰", "normal": "정상"},
    "en-US": {"critical": "Critical", "warning": "Warning", "attention": "Attention", "normal": "Normal"},
}
PM_ACTION_LABELS: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {
        "continue_monitoring": "계속 모니터링",
        "request_inspection": "현장 점검 요청",
        "review_shutdown": "권한자 정지 검토",
        "hold_for_data_check": "데이터 확인 전 판단 보류",
        "Review governed prediction": "관리형 예측 결과 검토",
    },
    "en-US": {
        "continue_monitoring": "Continue monitoring",
        "request_inspection": "Request a field inspection",
        "review_shutdown": "Review a shutdown with an authorized operator",
        "hold_for_data_check": "Hold the decision until data is verified",
        "Review governed prediction": "Review the governed prediction",
    },
}
PM_FEATURE_LABELS: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {
        "air_temperature_k": "공기 온도",
        "process_temperature_k": "공정 온도",
        "rotational_speed_rpm": "회전속도",
        "torque_nm": "토크",
        "tool_wear_min": "공구 마모",
        "power_w": "기계 동력",
        "temperature_gap_k": "공정·공기 온도 차이",
        "overstrain_load": "공구 마모·토크 부하",
        "rotation_raw_6h_mean": "6시간 회전속도 평균",
        "rotation_raw_6h_abs_mean": "6시간 회전속도 절대평균",
        "rotation_raw_6h_std": "6시간 회전속도 표준편차",
    },
    "en-US": {
        "air_temperature_k": "Air temperature",
        "process_temperature_k": "Process temperature",
        "rotational_speed_rpm": "Rotational speed",
        "torque_nm": "Torque",
        "tool_wear_min": "Tool wear",
        "power_w": "Mechanical power",
        "temperature_gap_k": "Process-to-air temperature gap",
        "overstrain_load": "Tool-wear torque load",
        "rotation_raw_6h_mean": "6-hour rotational-speed mean",
        "rotation_raw_6h_abs_mean": "6-hour rotational-speed absolute mean",
        "rotation_raw_6h_std": "6-hour rotational-speed standard deviation",
    },
}
PM_LAYOUT_TITLES: dict[AppLocale, dict[str, str]] = {
    "ko-KR": {
        "StatusSummary": "상태 요약",
        "RiskKpi": "위험 KPI",
        "PriorityList": "점검 우선순위",
        "SensorLineChart": "센서 추세",
        "FactorContribution": "주요 위험 요인",
        "EvidenceTable": "근거 데이터",
        "RecommendedActions": "권장 조치",
        "EngineerChecklist": "엔지니어 점검표",
        "ModelDetails": "모델 상세",
        "ConversationThread": "업무 대화",
    },
    "en-US": {
        "StatusSummary": "Status Summary",
        "RiskKpi": "Risk KPI",
        "PriorityList": "Inspection Priority",
        "SensorLineChart": "Sensor Trend",
        "FactorContribution": "Factor Contribution",
        "EvidenceTable": "Evidence Data",
        "RecommendedActions": "Recommended Actions",
        "EngineerChecklist": "Engineer Checklist",
        "ModelDetails": "Model Details",
        "ConversationThread": "Work Conversation",
    },
}


def _pm_label(mapping: dict[AppLocale, dict[str, str]], locale: AppLocale, value: str) -> str:
    return mapping[locale].get(value, value.replace("_", " ").title() if locale == "en-US" else value)


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return []


class PredictiveMaintenanceRuntimeService:
    def __init__(self, repository: PredictiveMaintenanceRuntimeRepository) -> None:
        self.repository = repository

    @staticmethod
    def _safe_governance(profile: dict[str, Any]) -> GovernanceProvenance:
        release = _dict(profile.get("release_gates"))
        artifacts = [item for item in profile.get("governance_artifacts", []) if isinstance(item, dict)]
        package = next((item for item in artifacts if item.get("role") == "package_validation"), {})
        package_summary = _dict(package.get("summary"))
        continuity = _dict(release.get("tool_wear_continuity"))
        continuity_allowed = {
            key: continuity.get(key)
            for key in (
                "pass",
                "running_reset_count",
                "tool_replacement_event_count",
                "aligned_reset_transition_count",
                "reset_without_matching_maintenance_count",
                "replacement_without_reset_count",
            )
            if key in continuity
        }
        agent = _dict(release.get("agent_example_evaluation"))
        agent_allowed = {
            key: agent.get(key)
            for key in (
                "pass",
                "maintenance_evidence_accuracy",
                "false_upstream_claim_rate",
            )
            if key in agent
        }
        safe_artifacts = [
            {
                key: item.get(key)
                for key in ("role", "checksum_sha256", "media_type")
                if item.get(key) is not None
            }
            for item in artifacts
        ]
        return GovernanceProvenance(
            release_identity=_dict(release.get("release_identity")),
            tool_wear_continuity=continuity_allowed,
            agent_example_evaluation=agent_allowed,
            ai4i_physics=_dict(package_summary.get("ai4i_physics")),
            ai4i_contract=_dict(package_summary.get("ai4i_contract")),
            query_time_derived_measures={
                str(key): str(value)
                for key, value in _dict(
                    package_summary.get("query_time_derived_measures")
                ).items()
            },
            governance_artifacts=safe_artifacts,
        )

    @staticmethod
    def _graph(row: dict[str, Any]) -> GraphReadiness:
        status = str(row.get("graph_status") or "unavailable")
        if status not in {"pending", "indexing", "ready", "failed", "unavailable"}:
            status = "unavailable"
        return GraphReadiness(
            status=status,
            record_count=int(row.get("graph_record_count") or 0),
            provider_run_id=(
                None
                if row.get("graph_provider_run_id") is None
                else str(row["graph_provider_run_id"])
            ),
            last_error=(
                None if row.get("graph_last_error") is None else str(row["graph_last_error"])
            ),
            attempt_count=int(row.get("graph_attempt_count") or 0),
            updated_at=row.get("graph_updated_at"),
        )

    @staticmethod
    def _runtime_contract(row: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        model_version = (
            None
            if row.get("runtime_model_version") is None
            else str(row["runtime_model_version"])
        )
        schema_version = (
            None
            if row.get("result_artifact_schema_version") is None
            else str(row["result_artifact_schema_version"])
        )
        raw_task = (
            None
            if row.get("runtime_prediction_task") is None
            else str(row["runtime_prediction_task"])
        )
        prediction_task = raw_task if raw_task == PREDICTION_TASK else None
        return model_version, schema_version, prediction_task

    @classmethod
    def _release_ready(cls, row: dict[str, Any], governance: GovernanceProvenance) -> bool:
        if str(row.get("status")) == "failed":
            return False
        if str(row.get("source_version")) != V3_1_SOURCE_VERSION:
            return True
        agent = governance.agent_example_evaluation
        agent_ready = agent.get("pass") is True or (
            float(agent.get("maintenance_evidence_accuracy", -1)) == 1.0
            and float(agent.get("false_upstream_claim_rate", -1)) == 0.0
        )
        return bool(
            int(row.get("result_artifact_count") or 0) > 0
            and governance.tool_wear_continuity.get("pass") is True
            and agent_ready
        )

    def context(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
        user_id: str | None = None,
    ) -> DatasetVersionRuntimeContext:
        if dataset_version_id is None:
            selected = self.versions(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=user_id,
            ).default_dataset_version_id
            if selected is None:
                raise KeyError("default predictive-maintenance Dataset Version")
            dataset_version_id = selected
        row = self.repository.resolve_version(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        profile = _dict(row.get("profile_json"))
        source_version = str(row["source_version"])
        model_version, result_schema, prediction_task = self._runtime_contract(row)
        context = DatasetVersionRuntimeContext(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_id=str(row["dataset_id"]),
            dataset_version_id=str(row["id"]),
            source_version=source_version,
            bundle_checksum_sha256=str(row["checksum_sha256"]),
            version_number=int(row["version_number"]),
            record_count=int(row["record_count"]),
            dataset_status=str(row["status"]),
            row_counts={
                str(key): int(value)
                for key, value in _dict(profile.get("row_counts")).items()
            },
            source_contract=_dict(profile.get("source_contract")),
            model_version=model_version,
            result_artifact_schema_version=result_schema,
            prediction_task=prediction_task,
            relational_status=str(row.get("relational_status") or "unavailable"),
            relational_record_count=int(row.get("relational_record_count") or 0),
            semantic_catalog_version=(
                "predictive-maintenance-semantic-v3.1"
                if source_version == V3_1_SOURCE_VERSION
                else "predictive-maintenance-semantic-compat-v1"
            ),
            governance=self._safe_governance(profile),
            graph=self._graph(row),
            semantic_query=SemanticQueryCapability(
                dimensions=[
                    "asset_id",
                    "asset_type",
                    "site_id",
                    "cell_id",
                    "observed_at",
                    "operating_state",
                    "product_type",
                ],
                canonical_measures=[
                    "voltage_raw",
                    "rotation_raw",
                    "pressure_raw",
                    "vibration_raw",
                    "relative_vibration_z",
                    "air_temperature_k",
                    "process_temperature_k",
                    "rotational_speed_rpm",
                    "torque_nm",
                    "tool_wear_min",
                    "failure_probability",
                    "confidence",
                ],
                derived_measures={
                    "power_w": "torque_nm * rotational_speed_rpm * 2*pi/60",
                    "temperature_gap_k": (
                        "process_temperature_k - air_temperature_k"
                    ),
                    "overstrain_load": "tool_wear_min * torque_nm",
                },
                latest_result_contract=(
                    "result_artifact"
                    if int(row.get("result_artifact_count") or 0) > 0
                    else "prediction_snapshot_compatibility"
                ),
                supported_grains=["raw", "10m", "1h"],
            ),
        )
        if source_version == V3_1_SOURCE_VERSION:
            release = context.governance
            continuity = release.tool_wear_continuity
            agent = release.agent_example_evaluation
            if not continuity.get("pass") or not agent:
                raise ValueError("V3.1 Dataset Version is missing governed release evidence")
        return context

    def versions(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str | None = None,
    ) -> DatasetVersionOptions:
        rows = self.repository.list_versions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        items: list[DatasetVersionOption] = []
        for index, row in enumerate(rows):
            profile = _dict(row.get("profile_json"))
            governance = self._safe_governance(profile)
            model_version, result_schema, prediction_task = self._runtime_contract(row)
            items.append(
                DatasetVersionOption(
                    dataset_id=str(row["dataset_id"]),
                    dataset_name=str(row.get("dataset_name") or row["dataset_id"]),
                    dataset_version_id=str(row["id"]),
                    version_number=int(row["version_number"]),
                    source_version=str(row["source_version"]),
                    bundle_checksum_sha256=str(row["checksum_sha256"]),
                    dataset_status=str(row["status"]),
                    record_count=int(row["record_count"]),
                    row_counts={
                        str(key): int(value)
                        for key, value in _dict(profile.get("row_counts")).items()
                    },
                    result_artifact_count=int(row.get("result_artifact_count") or 0),
                    prediction_timeline_count=int(row.get("prediction_timeline_count") or 0),
                    relational_status=str(row.get("relational_status") or "unavailable"),
                    relational_record_count=int(row.get("relational_record_count") or 0),
                    model_version=model_version,
                    result_artifact_schema_version=result_schema,
                    prediction_task=prediction_task,
                    graph=self._graph(row),
                    release_ready=self._release_ready(row, governance),
                    is_latest=index == 0,
                    is_v3_1=str(row["source_version"]) == V3_1_SOURCE_VERSION,
                )
            )
        item_ids = {item.dataset_version_id for item in items}
        explicit = (
            self.repository.selected_version_for_user(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if user_id
            else None
        )
        if explicit in item_ids:
            selected_id = explicit
            selection_mode = "explicit"
            selection_reason = "explicit_user_selection"
        else:
            canonical = next(
                (
                    item
                    for item in items
                    if item.is_v3_1
                    and item.release_ready
                    and item.dataset_status == "published"
                ),
                None,
            )
            published = next(
                (item for item in items if item.dataset_status == "published"),
                None,
            )
            selected = canonical or published or (items[0] if items else None)
            selected_id = selected.dataset_version_id if selected else None
            selection_mode = "automatic"
            selection_reason = (
                "canonical_v3_1_release_ready"
                if canonical is not None
                else "latest_published_predictive_maintenance"
                if published is not None
                else "latest_predictive_maintenance"
                if selected is not None
                else "no_runtime_dataset"
            )
        return DatasetVersionOptions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            items=items,
            default_dataset_version_id=selected_id,
            selection_mode=selection_mode,
            selection_reason=selection_reason,
            rollback_supported=len(items) > 1,
        )

    def select_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
        dataset_version_id: str | None,
    ) -> DatasetVersionOptions:
        self.repository.save_selected_version(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
            dataset_version_id=dataset_version_id,
        )
        return self.versions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )

    def release_overview(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
        user_id: str | None = None,
    ) -> PredictiveMaintenanceReleaseOverview:
        active = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
            user_id=user_id,
        )
        versions = self.versions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        active_option = next(
            (item for item in versions.items if item.dataset_version_id == active.dataset_version_id),
            None,
        )
        same_dataset = [item for item in versions.items if item.dataset_id == active.dataset_id]
        if len(same_dataset) < 2 and active_option is not None:
            same_dataset = [
                item for item in versions.items if item.dataset_name == active_option.dataset_name
            ]
        if len(same_dataset) < 2:
            has_v3 = any(item.is_v3_1 for item in versions.items)
            has_compatibility_version = any(not item.is_v3_1 for item in versions.items)
            if has_v3 and has_compatibility_version:
                same_dataset = versions.items
        immutable_upgrade_verified = len(
            {
                (item.dataset_version_id, item.source_version, item.bundle_checksum_sha256)
                for item in same_dataset
            }
        ) == len(same_dataset) and len(same_dataset) > 1
        safe_gates = {
            "tool_wear_continuity": active.governance.tool_wear_continuity,
            "agent_example_evaluation": active.governance.agent_example_evaluation,
            "ai4i_physics": active.governance.ai4i_physics,
        }
        return PredictiveMaintenanceReleaseOverview(
            active=active,
            versions=versions,
            immutable_upgrade_verified=immutable_upgrade_verified,
            result_artifact_coverage=(
                active_option.result_artifact_count if active_option is not None else 0
            ),
            projection_status=active.graph,
            safe_release_gates=safe_gates,
            limitations=[
                "The canonical predictive-maintenance dataset is synthetic.",
                "Replay uses stored observations and precomputed predictions; it is not a live sensor server.",
                "The active model predicts binary failure risk and is not an AI4I failure-mode classifier.",
                "Policy recommendations are not approved or executed WorkOrders.",
                "SUPPLIES_AIR_TO is topology evidence and does not establish causality.",
            ],
        )

    @staticmethod
    def _factor_models(raw: Any) -> list[ProductFactor]:
        factors = _list(raw)
        result: list[ProductFactor] = []
        for item in factors[:3]:
            if not isinstance(item, dict):
                continue
            raw_direction = str(item["direction"])
            direction = {
                "positive": "risk_up",
                "negative": "risk_down",
                "risk_up": "risk_up",
                "risk_down": "risk_down",
            }.get(raw_direction)
            if direction is None:
                raise ValueError(f"unsupported factor direction: {raw_direction}")
            result.append(
                ProductFactor(
                    rank=int(item["rank"]),
                    feature=str(item["feature"]),
                    feature_value=float(item["feature_value"]),
                    signed_contribution=float(item["signed_contribution"]),
                    direction=direction,
                    explanation_method=str(item["explanation_method"]),
                )
            )
        return result

    @staticmethod
    def _prediction_result(
        *,
        context: DatasetVersionRuntimeContext,
        row: dict[str, Any],
        factors: list[ProductFactor],
        recommendation: PolicyRecommendation | None,
        source_contract: str,
        source_checksum: str,
        prediction_task: str,
        model_version: str,
    ) -> PredictionResult:
        prediction_result_id = str(row["prediction_result_id"])
        prediction_id = str(row["prediction_id"])
        evidence: list[PredictionEvidence] = [
            PredictionEvidence(
                evidence_id=f"artifact:{row.get('artifact_id') or prediction_id}",
                kind="artifact",
                label=(
                    "Governed Result Artifact"
                    if source_contract == "result_artifact"
                    else "Prediction Snapshot Compatibility"
                ),
                value={
                    "source_contract": source_contract,
                    "prediction_task": prediction_task,
                    "predicted_failure_type_semantics": (
                        "generic_binary_risk_not_ai4i_failure_mode"
                    ),
                },
                source=EvidenceSource(
                    system="predictive-maintenance-postgresql",
                    reference=(
                        f"dataset:{context.dataset_id}:version:{context.dataset_version_id}:"
                        f"role:{source_contract}:sha256:{source_checksum}"
                    ),
                    checksum=source_checksum,
                ),
            )
        ]
        for factor in factors:
            evidence.append(
                PredictionEvidence(
                    evidence_id=f"factor:{prediction_id}:{factor.rank}",
                    kind="feature",
                    label=factor.feature,
                    value=factor.feature_value,
                    contribution=factor.signed_contribution,
                    source=EvidenceSource(
                        system="predictive-maintenance-postgresql",
                        reference=(
                            f"dataset:{context.dataset_id}:version:{context.dataset_version_id}:"
                            f"prediction:{prediction_id}:factor:{factor.rank}"
                        ),
                    ),
                )
            )
        actions: list[RecommendedAction] = []
        if recommendation is not None:
            actions.append(
                RecommendedAction(
                    action_type=recommendation.action,
                    label=recommendation.action,
                    reason="Policy recommendation only; approval and execution have not occurred.",
                    requires_approval=True,
                    parameters={
                        "priority": recommendation.priority,
                        "semantic_type": "policy_recommendation",
                        "execution_state": "not_executed",
                        "creates_work_order_automatically": False,
                    },
                )
            )
        status = str(row.get("status_grade") or row.get("status") or "normal")
        return PredictionResult(
            prediction_id=prediction_result_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            workspace_id=context.workspace_id,
            source_run_id=(
                str(row["artifact_id"]) if row.get("artifact_id") is not None else prediction_id
            ),
            subject=PredictionSubject(
                object_type="equipment",
                object_id=str(row["asset_id"]),
                observed_at=row["observed_at"],
            ),
            prediction=PredictionValue(
                task="classification",
                status=status,
                label=str(row.get("predicted_failure_type") or "no_significant_risk"),
                score=float(row["failure_probability"]),
                confidence=float(row["confidence"]),
                horizon=f"{int(row['prediction_horizon_hours'])}h",
                value=str(row.get("predicted_failure_type") or "no_significant_risk"),
            ),
            evidence=evidence,
            recommended_actions=actions,
            model=PredictionModel(
                provider="canonical-predictive-maintenance",
                model_name=(
                    "independent-logreg"
                    if model_version.startswith("independent-logreg")
                    else model_version
                ),
                model_version=model_version,
                dataset_version=context.source_version,
                policy_version=(
                    "result-artifact-policy-v1"
                    if recommendation is not None
                    else "snapshot-compatibility"
                ),
            ),
            data_quality=DataQuality(status="pass", issues=[]),
            created_at=row.get("prediction_result_created_at") or row["observed_at"],
        )

    def _product_result(
        self,
        *,
        context: DatasetVersionRuntimeContext,
        row: dict[str, Any],
        source_contract: str,
    ) -> GovernedProductResult:
        factors = self._factor_models(row.get("top_factors"))
        if source_contract == "result_artifact":
            provenance = _dict(row.get("provenance"))
            recommendation_raw = _dict(row.get("recommended_action"))
            prediction_task = str(row["prediction_task"])
            model_version = str(row["model_version"])
            schema_version = str(row["schema_version"])
            source_checksum = str(row["source_sha256"])
            recommendation = PolicyRecommendation(
                action=str(recommendation_raw["action"]),
                priority=str(recommendation_raw["priority"]),
            )
            canonical_mutated = provenance.get("canonical_source_mutated")
            if canonical_mutated is not False:
                raise ValueError("Result Artifact provenance must assert canonical_source_mutated=false")
            if prediction_task != PREDICTION_TASK:
                raise ValueError("Result Artifact prediction task mismatch")
            if context.source_version == V3_1_SOURCE_VERSION:
                if model_version != V3_1_MODEL_VERSION or schema_version != V3_1_RESULT_SCHEMA:
                    raise ValueError("V3.1 Result Artifact model/schema provenance mismatch")
            source_type = str(provenance.get("source_type") or "derived_result_artifact")
        else:
            prediction_task = PREDICTION_TASK
            model_version = str(row["model_version"])
            schema_version = "prediction-snapshot-compat-v1"
            source_checksum = str(row["source_sha256"])
            recommendation = None
            source_type = "prediction_snapshot_compatibility"

        predicted_type = str(row.get("predicted_failure_type") or "")
        if source_contract == "prediction_snapshot_compatibility" and predicted_type not in {
            "failure_risk",
            "no_significant_risk",
        }:
            predicted_type = (
                "failure_risk"
                if float(row["failure_probability"]) >= 0.5
                else "no_significant_risk"
            )
        if predicted_type not in {"failure_risk", "no_significant_risk"}:
            raise ValueError("snapshot/result predicted_failure_type is not a binary risk class")
        prediction_result = self._prediction_result(
            context=context,
            row=row,
            factors=factors,
            recommendation=recommendation,
            source_contract=source_contract,
            source_checksum=source_checksum,
            prediction_task=prediction_task,
            model_version=model_version,
        )
        return GovernedProductResult(
            source_contract=source_contract,
            artifact_id=(
                str(row["artifact_id"]) if row.get("artifact_id") is not None else None
            ),
            asset_id=str(row["asset_id"]),
            asset_type=str(row["asset_type"]),
            site_id=str(row["site_id"]),
            cell_id=str(row["cell_id"]),
            observed_at=row["observed_at"],
            prediction_horizon_hours=int(row["prediction_horizon_hours"]),
            prediction_task=prediction_task,
            failure_probability=float(row["failure_probability"]),
            predicted_failure_type=predicted_type,
            status_grade=str(row.get("status_grade") or row.get("status")),
            confidence=float(row["confidence"]),
            top_factors=factors,
            recommended_action=recommendation,
            provenance=ProductResultProvenance(
                dataset_id=context.dataset_id,
                dataset_version_id=context.dataset_version_id,
                source_version=context.source_version,
                bundle_checksum_sha256=context.bundle_checksum_sha256,
                result_artifact_source_sha256=(
                    source_checksum if source_contract == "result_artifact" else None
                ),
                prediction_id=str(row["prediction_id"]),
                prediction_result_id=str(row["prediction_result_id"]),
                model_version=model_version,
                schema_version=schema_version,
                prediction_task=prediction_task,
                source_type=source_type,
                canonical_source_mutated=False,
            ),
            governance=context.governance,
            graph=context.graph,
            prediction_result=prediction_result,
        )

    def latest_results(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
        asset_id: str | None = None,
        site_id: str | None = None,
        cell_id: str | None = None,
        asset_type: str | None = None,
        status_grade: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> ProductResultPage:
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        source_contract, total, rows = self.repository.latest_result_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            asset_id=asset_id,
            site_id=site_id,
            cell_id=cell_id,
            asset_type=asset_type,
            status_grade=status_grade,
            offset=offset,
            limit=limit,
        )
        items = [
            self._product_result(
                context=context,
                row=row,
                source_contract=source_contract,
            )
            for row in rows
        ]
        return ProductResultPage(
            context=context,
            items=items,
            total=total,
            offset=offset,
            limit=limit,
            latest_product_contract=source_contract,
        )

    @staticmethod
    def _dashboard_event_id(result: GovernedProductResult) -> str:
        return result.artifact_id or result.provenance.prediction_id

    @staticmethod
    def _dashboard_equipment(
        result: GovernedProductResult,
        maintenance: list[dict[str, Any]],
    ) -> DashboardEquipment:
        last_maintenance = maintenance[0]["completed_at"] if maintenance else None
        downtime_by_status = {
            "critical": 240,
            "warning": 120,
            "attention": 60,
            "normal": 30,
        }
        criticality = (
            "high"
            if result.status_grade in {"critical", "warning"}
            else "medium"
            if result.status_grade == "attention"
            else "low"
        )
        return DashboardEquipment(
            equipment_id=result.asset_id,
            display_name=f"{result.asset_type.upper()} · {result.asset_id}",
            line=f"{result.site_id} / {result.cell_id}",
            criticality=criticality,
            assigned_engineer="Unassigned · policy review",
            last_maintenance_date=(
                last_maintenance.isoformat() if last_maintenance else "No recorded maintenance"
            ),
            estimated_downtime_minutes=downtime_by_status[result.status_grade],
            spare_part_available=None,
        )

    @staticmethod
    def _dashboard_observation_payload(observation: SensorObservation) -> dict[str, Any]:
        measurements = observation.measurements
        return {
            "timestamp": observation.observed_at.isoformat(),
            "product_type": str(measurements.get("product_type") or observation.asset_type),
            "air_temperature_k": measurements.get("air_temperature_k"),
            "process_temperature_k": measurements.get("process_temperature_k"),
            "rotational_speed_rpm": measurements.get("rotational_speed_rpm"),
            "torque_nm": measurements.get("torque_nm"),
            "tool_wear_min": measurements.get("tool_wear_min"),
            "asset_id": observation.asset_id,
            "asset_type": observation.asset_type,
            "site_id": observation.site_id,
            "cell_id": observation.cell_id,
            "is_operating": observation.is_operating,
            "operating_state": observation.operating_state,
            **measurements,
            **observation.derived_measures,
        }

    def _dashboard_detail(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        context: DatasetVersionRuntimeContext,
        result: GovernedProductResult,
        equipment: DashboardEquipment,
        maintenance: list[dict[str, Any]],
        role: str,
        intent: str,
        locale: AppLocale,
    ) -> DashboardEventDetail:
        event_id = self._dashboard_event_id(result)
        window_start = result.observed_at - timedelta(hours=6)
        observation_response = self.observations(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            start=window_start,
            end=result.observed_at,
            asset_id=result.asset_id,
            site_id=None,
            cell_id=None,
            asset_type=None,
            grain="10m",
            derived_measures=ALLOWED_DERIVED_MEASURES,
            limit=72,
        )
        history = [
            self._dashboard_observation_payload(item)
            for item in observation_response.observations
        ]
        observation = history[-1] if history else {
            "timestamp": result.observed_at.isoformat(),
            "product_type": result.asset_type,
            "air_temperature_k": None,
            "process_temperature_k": None,
            "rotational_speed_rpm": None,
            "torque_nm": None,
            "tool_wear_min": None,
        }
        recommendation = result.recommended_action
        action = recommendation.action if recommendation else "Review governed prediction"
        action_label = _pm_label(PM_ACTION_LABELS, locale, action)
        status_label = _pm_label(PM_STATUS_LABELS, locale, result.status_grade)
        confidence = (
            f"{result.confidence * 100:.1f}% · 보정됨"
            if locale == "ko-KR"
            else f"{result.confidence * 100:.1f}% · calibrated"
        )
        factor_units = {
            "air_temperature_k": "K",
            "process_temperature_k": "K",
            "rotational_speed_rpm": "rpm",
            "torque_nm": "Nm",
            "tool_wear_min": "min",
        }
        factors = [
            {
                "evidence_field_id": f"factor:{item.feature}",
                "feature": item.feature,
                "display_name": _pm_label(PM_FEATURE_LABELS, locale, item.feature),
                "value": item.feature_value,
                "unit": factor_units.get(item.feature, "model unit"),
                "normal_range": "관리형 모델 계약 참조" if locale == "ko-KR" else "See governed model contract",
                "direction": item.direction,
                "contribution": item.signed_contribution,
                "source_type": "result_artifact_factor",
            }
            for item in result.top_factors
        ]
        maintenance_payload = [
            {
                **item,
                "started_at": item["started_at"].isoformat(),
                "completed_at": item["completed_at"].isoformat(),
            }
            for item in maintenance
        ]
        source_refs = [
            f"dataset-version:{context.dataset_version_id}",
            f"result-artifact:{event_id}",
            *[f"maintenance:{item['maintenance_id']}" for item in maintenance[:5]],
        ]
        evidence = {
            "evidence_id": f"pm-evidence:{event_id}",
            "event_id": event_id,
            "scenario_id": f"{result.asset_type}:{result.site_id}:{result.cell_id}",
            "equipment": equipment.model_dump(mode="json"),
            "model": {
                "model_version": result.provenance.model_version,
                "policy_version": "result-artifact-policy-v1",
                "mode": "postgresql_result_artifact",
            },
            "status": result.status_grade,
            "recommended_decision": action,
            "confidence": confidence,
            "failure_probability": result.failure_probability,
            "threshold": 0.5,
            "predicted_failure_type": result.predicted_failure_type,
            "observation": observation,
            "history": history,
            "detected_interval": {
                "start": window_start.isoformat(),
                "end": result.observed_at.isoformat(),
            },
            "top_factors": factors,
            "maintenance_context": {
                "provider": "PostgreSQL Canonical 정비 이력" if locale == "ko-KR" else "PostgreSQL canonical maintenance events",
                "version": context.source_version,
                "source_type": "canonical_maintenance_evidence",
                "source_refs": source_refs,
                "checklist": (
                    [
                        "관리형 상위 3개 위험 요인을 검토합니다",
                        "최신 Canonical 센서 구간을 확인합니다",
                        "승인 전에 정비 근거를 확인합니다",
                    ]
                    if locale == "ko-KR"
                    else [
                        "Review the governed Top-3 factors",
                        "Confirm the latest canonical sensor window",
                        "Check maintenance evidence before approval",
                    ]
                ),
                "recommended_actions": [action_label],
            },
            "data_quality_warnings": [],
            "lineage": {
                "project_id": project_id,
                "workspace_id": workspace_id,
                "dataset_id": context.dataset_id,
                "dataset_version_id": context.dataset_version_id,
                "source_version": context.source_version,
                "bundle_checksum_sha256": context.bundle_checksum_sha256,
                "model_version": result.provenance.model_version,
                "result_schema": result.provenance.schema_version,
                "prediction_task": result.provenance.prediction_task,
                "prediction_id": result.provenance.prediction_id,
                "prediction_result_id": result.provenance.prediction_result_id,
                "replay_timestamp": result.observed_at.isoformat(),
            },
            "generated_at": result.observed_at.isoformat(),
        }
        report = {
            "report_id": f"pm-report:{event_id}:{role}:{locale}",
            "event_id": event_id,
            "role": role,
            "locale": locale,
            "mode": "deterministic_result_artifact",
            "headline": (
                f"{result.asset_id} · {status_label} · 고장 위험"
                if locale == "ko-KR"
                else f"{result.asset_id} · {status_label} failure risk"
            ),
            "summary": (
                f"관리형 Result Artifact는 {result.prediction_horizon_hours}시간 이내 이진 고장 위험을 "
                f"{result.failure_probability * 100:.1f}%로 산출했습니다. 정책 권장 조치는 실행 전에 사람이 검토해야 합니다."
                if locale == "ko-KR"
                else (
                    f"The governed Result Artifact reports {result.failure_probability * 100:.1f}% "
                    f"binary failure risk within {result.prediction_horizon_hours} hours. "
                    "A human must review the policy recommendation before execution."
                )
            ),
            "status": result.status_grade,
            "confidence": confidence,
            "recommended_decision": action,
            "sections": [
                {
                    "section_id": "risk",
                    "title": "위험도와 주요 요인" if locale == "ko-KR" else "Risk and factors",
                    "body": ", ".join(
                        (
                            f"{_pm_label(PM_FEATURE_LABELS, locale, item.feature)} "
                            f"{'위험 증가' if item.direction == 'risk_up' else '위험 감소'}"
                            if locale == "ko-KR"
                            else f"{_pm_label(PM_FEATURE_LABELS, locale, item.feature)} {item.direction.replace('_', ' ')}"
                        )
                        for item in result.top_factors
                    ),
                    "evidence_field_ids": [item["evidence_field_id"] for item in factors],
                },
                {
                    "section_id": "maintenance",
                    "title": "정비 이력" if locale == "ko-KR" else "Maintenance history",
                    "body": (
                        f"이 자산에는 Canonical 정비 이벤트 {len(maintenance)}건이 연결되어 있습니다."
                        if locale == "ko-KR"
                        else f"{len(maintenance)} canonical maintenance events are linked to this asset."
                    ),
                    "evidence_field_ids": source_refs[2:],
                },
                {
                    "section_id": "provenance",
                    "title": "Release 출처" if locale == "ko-KR" else "Release provenance",
                    "body": (
                        f"{context.source_version} · {result.provenance.model_version} · "
                        f"{result.provenance.schema_version}"
                    ),
                    "evidence_field_ids": source_refs[:2],
                },
            ],
            "actions": [{
                "action_id": f"review:{event_id}",
                "label": action_label,
                "kind": "policy_recommendation",
                "requires_human_approval": True,
                "source_refs": source_refs,
            }],
            "citations": source_refs,
            "limitations": (
                [
                    "이 모델은 AI4I 고장 모드가 아니라 일반 이진 고장 위험을 예측합니다.",
                    "정책 권장 조치는 승인되거나 실행된 WorkOrder가 아닙니다.",
                    "Replay는 변경 불가능한 관측값과 사전 계산된 예측을 사용합니다.",
                ]
                if locale == "ko-KR"
                else [
                    "The model predicts generic binary failure risk, not an AI4I failure mode.",
                    "Policy recommendations are not approved or executed WorkOrders.",
                    "Replay uses immutable observations and precomputed predictions.",
                ]
            ),
            "generated_at": result.observed_at.isoformat(),
        }
        block_types = [
            "StatusSummary",
            "RiskKpi",
            "PriorityList",
            "SensorLineChart",
            "FactorContribution",
            "EvidenceTable",
            "RecommendedActions",
            "EngineerChecklist",
            "ModelDetails",
            "ConversationThread",
        ]
        layout = {
            "layout_id": f"pm-layout:{event_id}:{role}:{intent}:{locale}",
            "event_id": event_id,
            "role": role,
            "intent": intent,
            "mode": "dataset_version_aware_server_adapter",
            "blocks": [
                {
                    "block_id": f"pm:{index}:{block_type}",
                    "type": block_type,
                    "title": _pm_label(PM_LAYOUT_TITLES, locale, block_type),
                    "order": index,
                    "emphasis": "primary" if index < 3 else "secondary",
                    "data_fields": [],
                    "collapsed": False,
                }
                for index, block_type in enumerate(block_types)
            ],
            "generated_at": result.observed_at.isoformat(),
        }
        return DashboardEventDetail(
            event_id=event_id,
            evidence=evidence,
            report=report,
            layout=layout,
            maintenance_events=maintenance_payload,
        )

    def dashboard(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
        dataset_version_id: str | None,
        selected_event_id: str | None,
        role: str,
        intent: str,
        locale: AppLocale = "ko-KR",
    ) -> PredictiveMaintenanceDashboardResponse:
        versions = self.versions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        active_id = dataset_version_id or versions.default_dataset_version_id
        if active_id is None:
            raise KeyError("default predictive-maintenance Dataset Version")
        results = self.latest_results(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=active_id,
            limit=500,
        )
        context = results.context
        option = next(
            item for item in versions.items if item.dataset_version_id == context.dataset_version_id
        )
        maintenance_by_asset, ontology_by_asset = self.repository.dashboard_support_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
        )
        events: list[DashboardEventSummary] = []
        equipment_by_event: dict[str, DashboardEquipment] = {}
        result_by_event: dict[str, GovernedProductResult] = {}
        for result in results.items:
            event_id = self._dashboard_event_id(result)
            maintenance = maintenance_by_asset.get(result.asset_id, [])
            equipment = self._dashboard_equipment(result, maintenance)
            events.append(
                DashboardEventSummary(
                    event_id=event_id,
                    scenario_id=f"{result.asset_type}:{result.site_id}:{result.cell_id}",
                    ontology_object_id=ontology_by_asset.get(result.asset_id),
                    equipment=equipment,
                    status=result.status_grade,
                    failure_probability=result.failure_probability,
                    confidence=f"{result.confidence * 100:.1f}% · calibrated",
                    predicted_failure_type=result.predicted_failure_type,
                    recommended_decision=(
                        result.recommended_action.action
                        if result.recommended_action
                        else "Review governed prediction"
                    ),
                    observed_at=result.observed_at,
                    dataset_version_id=context.dataset_version_id,
                )
            )
            equipment_by_event[event_id] = equipment
            result_by_event[event_id] = result
        events.sort(
            key=lambda item: (
                {"critical": 0, "warning": 1, "attention": 2, "normal": 3}.get(
                    item.status, 4
                ),
                -(item.failure_probability or 0),
            )
        )
        selected_id = (
            selected_event_id
            if selected_event_id in result_by_event
            else events[0].event_id
            if events
            else None
        )
        detail = None
        if selected_id:
            selected_result = result_by_event[selected_id]
            detail = self._dashboard_detail(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                context=context,
                result=selected_result,
                equipment=equipment_by_event[selected_id],
                maintenance=maintenance_by_asset.get(selected_result.asset_id, []),
                role=role,
                intent=intent,
                locale=locale,
            )
        return PredictiveMaintenanceDashboardResponse(
            data_source=DashboardDataSource(
                dataset_id=context.dataset_id,
                dataset_name=option.dataset_name,
                dataset_version_id=context.dataset_version_id,
                source_version=context.source_version,
                model_version=context.model_version,
                result_artifact_schema_version=context.result_artifact_schema_version,
                prediction_task=context.prediction_task,
                bundle_checksum_sha256=context.bundle_checksum_sha256,
                record_count=context.record_count,
                row_counts=context.row_counts,
                result_artifact_count=option.result_artifact_count,
                prediction_timeline_count=option.prediction_timeline_count,
                relational_status=context.relational_status,
                relational_record_count=context.relational_record_count,
                dataset_status=context.dataset_status,
                release_ready=option.release_ready,
                selection_mode=(
                    versions.selection_mode
                    if context.dataset_version_id == versions.default_dataset_version_id
                    else "explicit"
                ),
                selection_reason=(
                    versions.selection_reason
                    if context.dataset_version_id == versions.default_dataset_version_id
                    else "request_dataset_version"
                ),
                graph=context.graph,
            ),
            context=context,
            versions=versions,
            events=events,
            selected_event_id=selected_id,
            selected_event_detail=detail,
        )

    def snapshot_drilldown(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
        prediction_id: str,
    ) -> SnapshotDrilldown:
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        row = self.repository.snapshot_drilldown(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            prediction_id=prediction_id,
        )
        if row is None:
            raise KeyError(prediction_id)
        return SnapshotDrilldown.model_validate(row)

    @staticmethod
    def _timeline(row: dict[str, Any]) -> TimelinePrediction:
        return TimelinePrediction(
            prediction_id=str(row["prediction_id"]),
            asset_id=str(row["asset_id"]),
            asset_type=str(row["asset_type"]),
            observed_at=row["observed_at"],
            prediction_horizon_hours=int(row["prediction_horizon_hours"]),
            failure_probability=float(row["failure_probability"]),
            status=str(row["status"]),
            top_factors=[item for item in _list(row.get("top_factors")) if isinstance(item, dict)],
            model_version=str(row["model_version"]),
            feature_scope=row.get("feature_scope"),
            source_type=str(row["source_type"]),
            source_sha256=str(row["source_sha256"]),
        )

    def timeline(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
        asset_id: str | None,
        start: datetime | None,
        end: datetime | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        total, rows = self.repository.timeline_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            asset_id=asset_id,
            start=start,
            end=end,
            offset=offset,
            limit=limit,
        )
        return {
            "context": context.model_dump(mode="json"),
            "items": [self._timeline(row).model_dump(mode="json") for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
            "source": "precomputed_prediction_timeline",
            "model_retrained": False,
        }

    @staticmethod
    def _sensor(row: dict[str, Any]) -> SensorObservation:
        measurements = _dict(row.get("measurements"))
        derived = {
            str(key): float(value)
            for key, value in _dict(row.get("derived_measures")).items()
        }
        return SensorObservation(
            observed_at=row["observed_at"],
            asset_id=str(row["asset_id"]),
            asset_type=str(row["asset_type"]),
            site_id=str(row["site_id"]),
            cell_id=str(row["cell_id"]),
            is_operating=bool(row["is_operating"]),
            operating_state=str(row["operating_state"]),
            source_sha256=str(row["source_sha256"]),
            measurements=measurements,
            derived_measures=derived,
        )

    def observations(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
        start: datetime,
        end: datetime,
        asset_id: str | None,
        site_id: str | None,
        cell_id: str | None,
        asset_type: str | None,
        grain: str,
        derived_measures: set[str],
        limit: int,
    ) -> ObservationQueryResponse:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("time-window timestamps must include timezone")
        if end < start:
            raise ValueError("window_end must not precede window_start")
        maximum = 7 * 24 if grain in {"raw", "10m"} else 31 * 24
        if (end - start).total_seconds() > maximum * 3600:
            raise ValueError(
                f"{grain} query window exceeds safe maximum of {maximum} hours"
            )
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        rows = self.repository.observation_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            start=start,
            end=end,
            asset_id=asset_id,
            site_id=site_id,
            cell_id=cell_id,
            asset_type=asset_type,
            grain=grain,
            derived_measures=derived_measures,
            limit=limit,
        )
        truncated = len(rows) > limit
        visible = rows[:limit]
        assets = sorted({str(row["asset_id"]) for row in visible})
        predictions = self.repository.nearest_timeline_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            at_or_before=end,
            asset_ids=assets,
        )
        return ObservationQueryResponse(
            context=context,
            window_start=start,
            window_end=end,
            grain=grain,
            observations=[self._sensor(row) for row in visible],
            nearest_predictions=[self._timeline(row) for row in predictions],
            returned_observation_count=len(visible),
            limit=limit,
            truncated=truncated,
        )

    def create_replay(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        user_id: str,
        dataset_version_id: str | None,
        start_time: datetime | None,
        speed: float,
    ) -> ReplaySessionSnapshot:
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        dataset_start, dataset_end = self.repository.observation_bounds(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
        )
        requested = start_time or dataset_start
        if requested.tzinfo is None:
            raise ValueError("replay start_time must include timezone")
        if requested < dataset_start or requested > dataset_end:
            raise ValueError("replay start_time is outside Dataset Version bounds")
        canonical_start = self.repository.nearest_sensor_time(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=context.dataset_version_id,
            at_or_before=requested,
        )
        row = self.repository.create_session(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_id=context.dataset_id,
            dataset_version_id=context.dataset_version_id,
            created_by=user_id,
            dataset_start=dataset_start,
            dataset_end=dataset_end,
            start_time=canonical_start,
            speed=speed,
        )
        return self.replay_snapshot(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=str(row["id"]),
        )

    @staticmethod
    def _cursor(record: ReplaySessionRecord) -> ReplayCursor:
        span = max(1.0, (record.dataset_end - record.dataset_start).total_seconds())
        progress = min(
            1.0,
            max(
                0.0,
                (record.simulation_time - record.dataset_start).total_seconds() / span,
            ),
        )
        return ReplayCursor(
            session_id=record.id,
            state=record.state,
            sequence=record.sequence,
            simulation_time=record.simulation_time,
            wall_clock_observed_at=datetime.now(timezone.utc),
            source_freshness_at=record.source_freshness_at,
            speed_minutes_per_second=record.speed_minutes_per_second,
            dataset_start=record.dataset_start,
            dataset_end=record.dataset_end,
            progress=round(progress, 6),
        )

    def replay_snapshot(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        session_id: str,
    ) -> ReplaySessionSnapshot:
        row = self.repository.session(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=session_id,
            advance=True,
        )
        record = ReplaySessionRecord.model_validate(row)
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=record.dataset_version_id,
        )
        sensor_time = self.repository.nearest_sensor_time(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=record.dataset_version_id,
            at_or_before=record.simulation_time,
        )
        observations = [
            self._sensor(item)
            for item in self.repository.observations_at(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                dataset_version_id=record.dataset_version_id,
                observed_at=sensor_time,
            )
        ]
        prediction_rows = self.repository.nearest_timeline_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=record.dataset_version_id,
            at_or_before=sensor_time,
        )
        predictions = [self._timeline(item) for item in prediction_rows]
        prediction_time = max((item.observed_at for item in predictions), default=None)
        references = self.repository.latest_artifact_references(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=record.dataset_version_id,
        )
        return ReplaySessionSnapshot(
            context=context,
            cursor=self._cursor(record),
            canonical_sensor_time=sensor_time,
            compressor_observations=[
                item for item in observations if item.asset_type == "compressor"
            ],
            cnc_observations=[item for item in observations if item.asset_type == "cnc"],
            nearest_prediction_time=prediction_time,
            predictions=predictions,
            latest_result_artifact_references=references,
            graph=context.graph,
        )

    def control_replay(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        session_id: str,
        action: str,
        time_value: datetime | None = None,
        speed: float | None = None,
    ) -> ReplaySessionSnapshot:
        self.repository.update_session(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=session_id,
            action=action,
            time_value=time_value,
            speed=speed,
        )
        return self.replay_snapshot(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
