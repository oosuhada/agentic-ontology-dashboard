from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

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
    DatasetVersionOption,
    DatasetVersionOptions,
    DatasetVersionRuntimeContext,
    GovernedProductResult,
    GovernanceProvenance,
    GraphReadiness,
    ObservationQueryResponse,
    PolicyRecommendation,
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
from .repository import PredictiveMaintenanceRuntimeRepository


V3_1_SOURCE_VERSION = "canonical-ai4i-physics-v3.1"
V3_1_MODEL_VERSION = "independent-logreg-v3.1"
V3_1_RESULT_SCHEMA = "result-artifact-v1.0"
PREDICTION_TASK = "binary_failure_within_horizon"


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
    ) -> DatasetVersionRuntimeContext:
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
                    model_version=model_version,
                    result_artifact_schema_version=result_schema,
                    prediction_task=prediction_task,
                    graph=self._graph(row),
                    release_ready=self._release_ready(row, governance),
                    is_latest=index == 0,
                    is_v3_1=str(row["source_version"]) == V3_1_SOURCE_VERSION,
                )
            )
        return DatasetVersionOptions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            items=items,
            default_dataset_version_id=(items[0].dataset_version_id if items else None),
            rollback_supported=len(items) > 1,
        )

    def release_overview(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
    ) -> PredictiveMaintenanceReleaseOverview:
        active = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        versions = self.versions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
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
