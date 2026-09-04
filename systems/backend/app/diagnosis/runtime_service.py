from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal

from pydantic import ValidationError
from jsonschema import Draft202012Validator, FormatChecker

from app.common.runtime_settings import project_root
from .diagnosis_schema import (
    DataQuality,
    EvidenceSource,
    PredictionEvidence,
    PredictionModel,
    PredictionResult,
    PredictionSubject,
    PredictionValue,
    RecommendedAction,
)
from .evidence import validate_product_result_artifact
from .evidence_projection import (
    event_evidence_projection_to_legacy_evidence,
    product_result_artifact_to_event_evidence_projection,
)
from .materialization import (
    ProductResultMaterializationCommand,
    ProductResultMaterializationService,
)
from .runtime_schema import (
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
    ProductEvidenceActionSummary,
    ProductEvidenceGapSummary,
    ProductEvidenceSourceFieldSummary,
    ProductResultBatchLineageSummary,
    ProductResultEvidenceSummary,
    PredictionBatchPromotionItemReceipt,
    PredictionBatchPromotionReceipt,
    PredictiveMaintenanceDashboardResponse,
    PredictionInboxItemReceipt,
    PredictionInboxReceipt,
    PredictionResultBatch,
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
from .ports import ALLOWED_DERIVED_MEASURES, DiagnosisRuntimeRepositoryPort
from .presentation_dictionary import (
    PRESENTATION_DICTIONARY_VERSION,
    asset_display_name,
    partition_factors,
    presentation_field,
    source_display_name,
)

AppLocale = Literal["ko-KR", "en-US"]


def _normalize_prediction_result_checksum_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        return value.replace("+00:00", "Z") if value.endswith("+00:00") else value
    if isinstance(value, dict):
        return {
            key: _normalize_prediction_result_checksum_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_normalize_prediction_result_checksum_value(item) for item in value]
    return value


V3_1_SOURCE_VERSION = "canonical-ai4i-physics-v3.1"
V3_1_MODEL_VERSION = "independent-logreg-v3.1"
V3_1_RESULT_SCHEMA = "result-artifact-v1.0"
PREDICTION_TASK = "binary_failure_within_horizon"
PREDICTION_RESULT_BATCH_SCHEMA_NAME = "prediction-result-batch.schema.json"

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
        "voltage_raw": "전압 신호",
        "rotation_raw": "회전 신호",
        "pressure_raw": "압력 신호",
        "vibration_raw": "진동 신호",
        "relative_vibration_z": "상대 진동 Z-score",
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
        "voltage_raw": "Voltage signal",
        "rotation_raw": "Rotation signal",
        "pressure_raw": "Pressure signal",
        "vibration_raw": "Vibration signal",
        "relative_vibration_z": "Relative vibration Z-score",
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


def _localize_legacy_top_factors(
    factors: list[dict[str, Any]],
    locale: AppLocale,
) -> list[dict[str, Any]]:
    fallback_range = "관리형 모델 계약 참조" if locale == "ko-KR" else "See governed model contract"
    return [
        {
            **factor,
            "display_name": presentation_field(str(factor.get("feature") or ""), locale)["label"],
            "normal_range": (
                fallback_range
                if str(factor.get("normal_range") or "") in {"", "근거 부족"}
                else factor["normal_range"]
            ),
        }
        for factor in factors
    ]


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


def _datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@lru_cache(maxsize=1)
def _prediction_result_batch_json_schema_validator() -> Draft202012Validator:
    schema_path = (
        project_root() / "contracts" / "schemas" / PREDICTION_RESULT_BATCH_SCHEMA_NAME
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


class PredictiveMaintenanceRuntimeService:
    def __init__(self, repository: DiagnosisRuntimeRepositoryPort) -> None:
        self.repository = repository
        self.materialization = ProductResultMaterializationService()

    @staticmethod
    def _canonical_json_sha256(value: dict[str, Any]) -> str:
        canonical = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _prediction_item_sha256(cls, item: dict[str, Any]) -> str:
        seed = dict(item)
        seed.pop("payload_sha256", None)
        seed = _normalize_prediction_result_checksum_value(seed)
        return cls._canonical_json_sha256(seed)

    @classmethod
    def _prediction_batch_sha256(cls, payload: dict[str, Any]) -> str:
        seed = dict(payload)
        seed.pop("emitted_at", None)
        seed.pop("batch_id", None)
        if isinstance(seed.get("producer"), dict):
            producer = dict(seed["producer"])
            producer.pop("outbox_id", None)
            seed["producer"] = producer
        if isinstance(seed.get("results"), list):
            seed["results"] = sorted(
                seed["results"],
                key=lambda item: (
                    str(item.get("asset_id", "")) if isinstance(item, dict) else "",
                    str(item.get("model_id", "")) if isinstance(item, dict) else "",
                    str(item.get("model_version", "")) if isinstance(item, dict) else "",
                    str(item.get("observed_at", "")) if isinstance(item, dict) else "",
                    str(item.get("event_id", "")) if isinstance(item, dict) else "",
                ),
            )
        return cls._canonical_json_sha256(seed)

    @staticmethod
    def _validate_prediction_result_batch_json_schema(payload: dict[str, Any]) -> None:
        errors = sorted(
            _prediction_result_batch_json_schema_validator().iter_errors(payload),
            key=lambda item: list(item.absolute_path),
        )
        if not errors:
            return
        first = errors[0]
        path = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise ValueError(f"{path}: {first.message}")

    @staticmethod
    def _model_identity(model: Any) -> tuple[str, str]:
        return (str(model.model_id), str(model.model_version))

    @classmethod
    def _model_snapshot_index(
        cls,
        batch: PredictionResultBatch,
    ) -> tuple[dict[tuple[str, str], Any], set[tuple[str, str]]]:
        snapshots: dict[tuple[str, str], Any] = {}
        duplicates: set[tuple[str, str]] = set()
        for model in batch.model_set.models:
            identity = cls._model_identity(model)
            if identity in snapshots:
                duplicates.add(identity)
                continue
            snapshots[identity] = model
        return snapshots, duplicates

    @classmethod
    def _model_lineage_rejection_reason(
        cls,
        *,
        item: Any,
        snapshots: dict[tuple[str, str], Any],
        duplicate_identities: set[tuple[str, str]],
    ) -> str | None:
        if item.output_status != "predicted":
            return None
        identity = (str(item.model_id), str(item.model_version))
        if identity in duplicate_identities:
            return (
                "model_set_duplicate_identity: "
                f"model_id={item.model_id}, model_version={item.model_version}"
            )
        snapshot = snapshots.get(identity)
        if snapshot is None:
            return (
                "model_set_snapshot_missing: "
                f"model_id={item.model_id}, model_version={item.model_version}"
            )
        expected = str(snapshot.model_artifact_manifest_sha256)
        actual = str(item.model_artifact_manifest_sha256)
        if actual != expected:
            return (
                "model_artifact_manifest_sha256_mismatch: "
                f"expected {expected}, got {actual}"
            )
        return None

    def receive_prediction_result_batch(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        payload: dict[str, Any],
    ) -> PredictionInboxReceipt:
        """Receive-only gate for Generator Prediction Result Batch payloads."""

        raw_payload = dict(payload)
        raw_payload_sha256 = self._canonical_json_sha256(raw_payload)
        batch_id = str(raw_payload.get("batch_id") or f"invalid-{raw_payload_sha256[:32]}")
        received_at = self.repository.clock_now()
        try:
            self._validate_prediction_result_batch_json_schema(raw_payload)
            batch = PredictionResultBatch.model_validate(raw_payload)
        except (ValidationError, ValueError) as error:
            if isinstance(error, ValidationError):
                message = error.errors()[0]["msg"]
            else:
                message = str(error)
            row = self.repository.save_prediction_batch_inbox(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                batch_id=batch_id,
                payload_sha256=raw_payload_sha256,
                validation_status="rejected",
                rejection_reason=f"schema_invalid: {message}",
                raw_payload=raw_payload,
                received_at=received_at,
                item_receipts=[],
            )
            return self._prediction_inbox_receipt_from_row(row)

        batch_payload = batch.model_dump(mode="json")
        batch_payload_sha256 = self._prediction_batch_sha256(batch_payload)
        item_receipts: list[dict[str, Any]] = []
        invalid_reasons: list[str] = []
        asset_ids = {item.asset_id for item in batch.results}
        scoped_assets = self.repository.assets_exist_in_workspace(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_ids=sorted(asset_ids),
        )
        missing_assets = sorted(asset_ids - set(scoped_assets))
        if missing_assets:
            invalid_reasons.append(f"scope_invalid: unknown assets {missing_assets}")
        model_snapshots, duplicate_model_identities = self._model_snapshot_index(batch)

        for parsed_item, item in zip(batch.results, batch_payload["results"], strict=True):
            expected = self._prediction_item_sha256(item)
            actual = str(item["payload_sha256"])
            lineage_reason = self._model_lineage_rejection_reason(
                item=parsed_item,
                snapshots=model_snapshots,
                duplicate_identities=duplicate_model_identities,
            )
            if expected != actual:
                item_receipts.append(
                    {
                        "event_id": item["event_id"],
                        "payload_sha256": actual,
                        "validation_status": "rejected",
                        "rejection_reason": (
                            "payload_sha256_mismatch: "
                            f"expected {expected}, got {actual}"
                        ),
                    }
                )
                invalid_reasons.append(f"payload_sha256_mismatch:{item['event_id']}")
            elif item["asset_id"] in missing_assets:
                item_receipts.append(
                    {
                        "event_id": item["event_id"],
                        "payload_sha256": actual,
                        "validation_status": "rejected",
                        "rejection_reason": "scope_invalid: asset is not in workspace",
                    }
                )
            elif lineage_reason:
                item_receipts.append(
                    {
                        "event_id": item["event_id"],
                        "payload_sha256": actual,
                        "validation_status": "rejected",
                        "rejection_reason": lineage_reason,
                    }
                )
                invalid_reasons.append(f"{lineage_reason}:{item['event_id']}")
            else:
                item_receipts.append(
                    {
                        "event_id": item["event_id"],
                        "payload_sha256": actual,
                        "validation_status": "accepted",
                        "rejection_reason": None,
                    }
                )

        validation_status = "rejected" if invalid_reasons else "accepted"
        row = self.repository.save_prediction_batch_inbox(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            batch_id=batch.batch_id,
            payload_sha256=batch_payload_sha256,
            validation_status=validation_status,
            rejection_reason="; ".join(invalid_reasons) or None,
            raw_payload=batch_payload,
            received_at=received_at,
            item_receipts=item_receipts,
        )
        return self._prediction_inbox_receipt_from_row(row)

    @staticmethod
    def _prediction_inbox_receipt_from_row(row: dict[str, Any]) -> PredictionInboxReceipt:
        item_receipts = [
            PredictionInboxItemReceipt.model_validate(item)
            for item in row.get("item_receipts", [])
        ]
        counts = {
            "accepted": sum(1 for item in item_receipts if item.validation_status == "accepted"),
            "duplicate": sum(1 for item in item_receipts if item.validation_status == "duplicate"),
            "conflict": sum(1 for item in item_receipts if item.validation_status == "conflict"),
            "rejected": sum(1 for item in item_receipts if item.validation_status == "rejected"),
        }
        return PredictionInboxReceipt(
            batch_id=str(row["batch_id"]),
            payload_sha256=str(row["payload_sha256"]),
            validation_status=row["validation_status"],
            rejection_reason=row.get("rejection_reason"),
            received_results=len(item_receipts),
            accepted_results=counts["accepted"],
            duplicate_results=counts["duplicate"],
            conflict_results=counts["conflict"],
            rejected_results=counts["rejected"],
            item_receipts=item_receipts,
        )

    def promote_prediction_result_batch(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        batch_id: str,
    ) -> PredictionBatchPromotionReceipt:
        context = self.repository.prediction_batch_promotion_context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            batch_id=batch_id,
        )
        if context is None:
            raise KeyError(batch_id)
        batch = PredictionResultBatch.model_validate(context["raw_payload"])
        assets = context.get("assets", {})
        promotions: list[dict[str, Any]] = []
        item_receipts: list[PredictionBatchPromotionItemReceipt] = []
        for item in batch.results:
            if item.output_status != "predicted":
                item_receipts.append(
                    PredictionBatchPromotionItemReceipt(
                        event_id=item.event_id,
                        promotion_status="skipped",
                        reason=f"output_status={item.output_status}",
                    )
                )
                continue
            asset = assets.get(item.asset_id)
            if not asset:
                item_receipts.append(
                    PredictionBatchPromotionItemReceipt(
                        event_id=item.event_id,
                        promotion_status="skipped",
                        reason="asset_not_found_in_dataset_version",
                    )
                )
                continue
            materialized = self.materialization.materialize(
                ProductResultMaterializationCommand(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    dataset_version_id=str(context["dataset_version_id"]),
                    asset=asset,
                    batch=batch,
                    item=item,
                )
            )
            promotions.append(
                {
                    "event_id": materialized.event_id,
                    "artifact": materialized.artifact,
                    "prediction_result": materialized.prediction_result.model_dump(mode="json"),
                    "prediction_result_id": materialized.prediction_result_id,
                    "source_sha256": materialized.source_sha256,
                }
            )
            item_receipts.append(
                PredictionBatchPromotionItemReceipt(
                    event_id=item.event_id,
                    promotion_status="promoted",
                    product_result_id=materialized.prediction_result_id,
                    artifact_id=materialized.artifact_id,
                )
            )
        stored = self.repository.save_prediction_batch_promotions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            batch_id=batch_id,
            dataset_version_id=str(context["dataset_version_id"]),
            promotions=promotions,
        )
        by_event = {item.event_id: item for item in item_receipts}
        stored_receipts = []
        for item in stored.get("item_receipts", []):
            original = by_event.get(str(item["event_id"]))
            stored_receipts.append(
                PredictionBatchPromotionItemReceipt(
                    event_id=str(item["event_id"]),
                    promotion_status=str(item["promotion_status"]),
                    product_result_id=item.get("product_result_id"),
                    artifact_id=item.get("artifact_id"),
                    reason=item.get("reason") or (original.reason if original else None),
                )
            )
        skipped = [item for item in item_receipts if item.promotion_status == "skipped"]
        final_receipts = stored_receipts + skipped
        promoted = sum(1 for item in final_receipts if item.promotion_status == "promoted")
        already = sum(1 for item in final_receipts if item.promotion_status == "already_promoted")
        skipped_count = sum(1 for item in final_receipts if item.promotion_status == "skipped")
        if promoted:
            status_value = "promoted" if not skipped_count else "partially_promoted"
        elif already and not skipped_count:
            status_value = "already_promoted"
        elif already:
            status_value = "partially_promoted"
        else:
            status_value = "not_promoted"
        return PredictionBatchPromotionReceipt(
            batch_id=batch_id,
            promotion_status=status_value,
            product_result_created=promoted > 0,
            received_results=len(batch.results),
            promoted_results=promoted,
            already_promoted_results=already,
            skipped_results=skipped_count,
            product_result_ids=[
                item.product_result_id for item in final_receipts if item.product_result_id
            ],
            artifact_ids=[item.artifact_id for item in final_receipts if item.artifact_id],
            item_receipts=final_receipts,
        )

    @staticmethod
    def _supports_dashboard_evidence_detail(
        source_contract: str,
        producer_artifact: dict[str, Any] | None = None,
    ) -> bool:
        return (
            source_contract == "result_artifact"
            and isinstance(producer_artifact, dict)
            and isinstance(producer_artifact.get("evidence_payload"), dict)
        )

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
        latest_result_observed_at: dict[str, datetime | None] = {}
        for index, row in enumerate(rows):
            profile = _dict(row.get("profile_json"))
            governance = self._safe_governance(profile)
            model_version, result_schema, prediction_task = self._runtime_contract(row)
            dataset_version_key = str(row["id"])
            raw_latest_observed = row.get("latest_result_observed_at")
            latest_result_observed_at[dataset_version_key] = (
                raw_latest_observed
                if isinstance(raw_latest_observed, datetime)
                else None
            )
            items.append(
                DatasetVersionOption(
                    dataset_id=str(row["dataset_id"]),
                    dataset_name=str(row.get("dataset_name") or row["dataset_id"]),
                    dataset_version_id=dataset_version_key,
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
            # The default Operations workspace is a wall-clock view, not a
            # replay browser.  Never auto-select a Dataset Version whose latest
            # Product Result is in the future.  Historical/replay versions stay
            # selectable explicitly.
            wall_clock_cutoff = datetime.now(timezone.utc) + timedelta(minutes=5)
            safe_items = [
                item
                for item in items
                if (
                    latest_result_observed_at.get(item.dataset_version_id) is None
                    or latest_result_observed_at[item.dataset_version_id] <= wall_clock_cutoff
                )
            ]
            wall_clock_live = next(
                (
                    item
                    for item in safe_items
                    if item.source_version == "gen-data-wall-clock-live-v2"
                    and item.dataset_status == "published"
                    and item.result_artifact_count > 0
                ),
                None,
            )
            canonical = next(
                (
                    item
                    for item in safe_items
                    if item.is_v3_1
                    and item.release_ready
                    and item.dataset_status == "published"
                ),
                None,
            )
            published = next(
                (item for item in safe_items if item.dataset_status == "published"),
                None,
            )
            selected = wall_clock_live or canonical or published or (safe_items[0] if safe_items else None)
            selected_id = selected.dataset_version_id if selected else None
            selection_mode = "automatic"
            selection_reason = (
                "wall_clock_live_runtime"
                if wall_clock_live is not None
                else "canonical_v3_1_release_ready"
                if canonical is not None
                else "latest_published_predictive_maintenance"
                if published is not None
                else "latest_wall_clock_safe_predictive_maintenance"
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

    @staticmethod
    def _stored_producer_artifact(row: dict[str, Any]) -> dict[str, Any] | None:
        artifact = _dict(row.get("prediction_result_payload"))
        if not isinstance(artifact.get("evidence_payload"), dict):
            return None
        provenance = _dict(artifact.get("provenance"))
        if provenance.get("source_type") != "product_runtime_inference":
            return None
        validate_product_result_artifact(artifact)
        for field in ("artifact_id", "asset_id", "asset_type", "schema_version"):
            if str(artifact.get(field)) != str(row[field]):
                raise ValueError(f"stored Product Result Artifact {field} does not match runtime index")
        if str(provenance.get("prediction_id")) != str(row["prediction_id"]):
            raise ValueError("stored Product Result Artifact prediction_id does not match runtime index")
        return artifact

    @staticmethod
    def _product_result_evidence_summary(
        producer_artifact: dict[str, Any] | None,
    ) -> ProductResultEvidenceSummary | None:
        if producer_artifact is None:
            return None
        payload = _dict(producer_artifact.get("evidence_payload"))
        provenance = _dict(producer_artifact.get("provenance"))
        lineage = _dict(producer_artifact.get("lineage"))
        source_context = _dict(lineage.get("source_context"))
        source_lineage = _dict(source_context.get("lineage"))
        model_artifact = _dict(provenance.get("model_artifact"))
        sensor_evidence = _dict(payload.get("sensor_evidence"))
        sensor_window = _dict(sensor_evidence.get("window"))
        return ProductResultEvidenceSummary(
            available=True,
            batch_lineage=ProductResultBatchLineageSummary(
                batch_id=(
                    None if lineage.get("batch_id") is None else str(lineage.get("batch_id"))
                ),
                event_id=(
                    None if lineage.get("event_id") is None else str(lineage.get("event_id"))
                ),
                emitted_at=_datetime_or_none(producer_artifact.get("generated_at")),
                generated_at=_datetime_or_none(producer_artifact.get("generated_at")),
                source_kind=(
                    None
                    if source_context.get("source_kind") is None
                    else str(source_context.get("source_kind"))
                ),
                producer_id=(
                    None
                    if source_context.get("producer_run_id") is None
                    else str(source_context.get("producer_run_id"))
                ),
                model_id=(
                    None if model_artifact.get("model_id") is None else str(model_artifact.get("model_id"))
                ),
                source_reference=(
                    None
                    if provenance.get("source_reference") is None
                    else str(provenance.get("source_reference"))
                ),
                simulation_session_id=source_lineage.get("simulation_session_id"),
                overlay_branch_id=source_lineage.get("overlay_branch_id"),
                history_segment_id=source_lineage.get("history_segment_id"),
                maintenance_action_id=source_lineage.get("maintenance_action_id"),
                maintenance_event_id=source_lineage.get("maintenance_event_id"),
                state_version=source_lineage.get("state_version"),
            ),
            evidence_payload_reference=_dict(
                provenance.get("evidence_payload_reference")
            )
            or None,
            sensor_window_rows=int(sensor_evidence.get("window_rows") or 0),
            sensor_window=sensor_window,
            component_hypotheses=[
                _dict(item)
                for item in payload.get("component_hypotheses") or []
                if isinstance(item, dict)
            ],
            recommended_actions=[
                ProductEvidenceActionSummary(
                    action_id=str(item.get("action_id") or ""),
                    label=str(item.get("label") or item.get("action_id") or ""),
                    kind=str(item.get("kind") or ""),
                    requires_human_approval=bool(
                        item.get("requires_human_approval", True)
                    ),
                    basis=[str(ref) for ref in item.get("basis") or []],
                )
                for item in payload.get("recommended_actions") or []
                if isinstance(item, dict)
            ],
            source_fields=[
                ProductEvidenceSourceFieldSummary(
                    field_id=str(item.get("field_id") or ""),
                    label=str(item.get("label") or item.get("field_id") or ""),
                    source_path=str(item.get("source_path") or ""),
                    description=(
                        None
                        if item.get("description") is None
                        else str(item.get("description"))
                    ),
                )
                for item in payload.get("source_fields") or []
                if isinstance(item, dict)
            ],
            evidence_gaps=[
                ProductEvidenceGapSummary(
                    gap_id=str(item.get("gap_id") or ""),
                    field=str(item.get("field") or ""),
                    owner_domain=str(item.get("owner_domain") or ""),
                    display_policy=str(item.get("display_policy") or ""),
                    reason=(
                        None if item.get("reason") is None else str(item.get("reason"))
                    ),
                    required_source=(
                        None
                        if item.get("required_source") is None
                        else str(item.get("required_source"))
                    ),
                )
                for item in payload.get("evidence_gaps") or []
                if isinstance(item, dict)
            ],
        )

    def _product_result(
        self,
        *,
        context: DatasetVersionRuntimeContext,
        row: dict[str, Any],
        source_contract: str,
    ) -> GovernedProductResult:
        factors = self._factor_models(row.get("top_factors"))
        producer_artifact: dict[str, Any] | None = None
        provenance: dict[str, Any] = {}
        if source_contract == "result_artifact":
            producer_artifact = self._stored_producer_artifact(row)
        if source_contract == "result_artifact":
            provenance = _dict(row.get("provenance"))
            recommendation_raw = _dict(row.get("recommended_action"))
            prediction_task = str(row["prediction_task"])
            model_version = str(row["model_version"])
            schema_version = str(row["schema_version"])
            source_checksum = str(row["source_sha256"])
            recommendation = (
                PolicyRecommendation(
                    action=str(recommendation_raw["action"]),
                    priority=str(recommendation_raw["priority"]),
                )
                if recommendation_raw
                else None
            )
            canonical_mutated = provenance.get("canonical_source_mutated")
            if canonical_mutated is not False:
                raise ValueError("Result Artifact provenance must assert canonical_source_mutated=false")
            if prediction_task != PREDICTION_TASK:
                raise ValueError("Result Artifact prediction task mismatch")
            source_type = str(provenance.get("source_type") or "derived_result_artifact")
            if context.source_version == V3_1_SOURCE_VERSION:
                if schema_version != V3_1_RESULT_SCHEMA:
                    raise ValueError("V3.1 Result Artifact model/schema provenance mismatch")
                # The immutable gen_data regression fixture uses the Week-2
                # independent-logreg model. Product runtime inference may use a
                # different injected Model Artifact or the explicit demo-only
                # heuristic fallback; the model version is therefore provenance,
                # not a source-dataset identity constraint.
                if (
                    source_type != "product_runtime_inference"
                    and model_version != V3_1_MODEL_VERSION
                ):
                    raise ValueError("V3.1 Result Artifact model/schema provenance mismatch")
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
        producer_lineage = _dict(
            _dict(_dict(producer_artifact).get("lineage")).get("source_context")
        )
        producer_lineage = _dict(producer_lineage.get("lineage"))

        def runtime_lineage_value(field: str) -> Any:
            return producer_lineage.get(field, provenance.get(field))

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
            evidence_summary=self._product_result_evidence_summary(producer_artifact),
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
                simulation_session_id=runtime_lineage_value("simulation_session_id"),
                overlay_branch_id=runtime_lineage_value("overlay_branch_id"),
                history_segment_id=runtime_lineage_value("history_segment_id"),
                maintenance_action_id=runtime_lineage_value("maintenance_action_id"),
                maintenance_event_id=runtime_lineage_value("maintenance_event_id"),
                state_version=runtime_lineage_value("state_version"),
            ),
            governance=context.governance,
            graph=context.graph,
            prediction_result=prediction_result,
            producer_artifact=producer_artifact,
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

    def post_maintenance_result(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        asset_id: str,
        maintenance_event_id: str,
    ) -> GovernedProductResult | None:
        row = self.repository.post_maintenance_result_row(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_id=asset_id,
            maintenance_event_id=maintenance_event_id,
        )
        if row is None:
            return None
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=str(row["dataset_version_id"]),
        )
        return self._product_result(
            context=context,
            row=row,
            source_contract="result_artifact",
        )

    def post_maintenance_runtime_status(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        asset_id: str,
        maintenance_event_id: str,
    ) -> dict[str, Any] | None:
        resolver = getattr(self.repository, "post_maintenance_runtime_status_row", None)
        if not callable(resolver):
            return None
        row = resolver(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_id=asset_id,
            maintenance_event_id=maintenance_event_id,
        )
        if row is None:
            return None
        return {
            "status": str(row.get("status") or ""),
            "failure_reason": row.get("failure_reason"),
            "observed_at": row.get("observed_at"),
            "model_id": row.get("model_id"),
            "model_version": row.get("model_version"),
            "lineage": row.get("lineage") or {},
            "received_at": row.get("received_at"),
            "updated_at": row.get("updated_at"),
        }

    @staticmethod
    def _dashboard_event_id(result: GovernedProductResult) -> str:
        return result.artifact_id or result.provenance.prediction_id

    def _historical_selected_result(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        selected_event_id: str,
    ) -> tuple[GovernedProductResult, DatasetVersionRuntimeContext] | None:
        """Resolve a frozen historical Result Artifact for an explicit Case.

        Latest-result collections intentionally advance with new observations.
        A Decision Case must instead retain the exact Result Artifact selected
        by the user, while remaining scoped to the active Project/Workspace and
        Dataset Version.
        """
        selected_row = self.repository.result_artifact_row(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            artifact_id=selected_event_id,
        )
        if selected_row is None:
            return None
        historical_context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=str(selected_row["dataset_version_id"]),
        )
        return self._product_result(
            context=historical_context,
            row=selected_row,
            source_contract="result_artifact",
        ), historical_context

    def event_evidence_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
    ) -> dict[str, Any] | None:
        """Resolve the canonical, scoped authorization projection for Maintenance."""

        row = self.repository.result_artifact_row(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            artifact_id=event_id,
        )
        if row is None:
            return None
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=str(row["dataset_version_id"]),
        )
        result = self._product_result(
            context=context,
            row=row,
            source_contract="result_artifact",
        )
        if result.producer_artifact is None:
            raise ValueError("runtime Result Artifact does not include producer evidence payload")
        projection = product_result_artifact_to_event_evidence_projection(
            result.producer_artifact
        )
        canonical_event_id = self._dashboard_event_id(result)
        projection["event_id"] = canonical_event_id
        projection["evidence_id"] = f"EVD-{canonical_event_id}"
        projection["artifact_reference"]["event_id"] = canonical_event_id
        return projection

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
        report_type: str | None = None,
        intent: str,
        locale: AppLocale,
        view: Literal["legacy", "canonical"] = "legacy",
    ) -> DashboardEventDetail:
        event_id = self._dashboard_event_id(result)
        recommendation = result.recommended_action
        action = recommendation.action if recommendation else "Review governed prediction"
        action_label = _pm_label(PM_ACTION_LABELS, locale, action)
        status_label = _pm_label(PM_STATUS_LABELS, locale, result.status_grade)
        confidence = (
            f"{result.confidence * 100:.1f}% · 보정됨"
            if locale == "ko-KR"
            else f"{result.confidence * 100:.1f}% · calibrated"
        )
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
        maintenance_context = {
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
        }
        producer_artifact = result.producer_artifact
        if producer_artifact is None:
            raise ValueError("runtime Result Artifact does not include producer evidence payload")
        canonical_evidence = product_result_artifact_to_event_evidence_projection(producer_artifact)
        canonical_evidence["event_id"] = event_id
        canonical_evidence["scenario_id"] = f"{result.asset_type}:{result.site_id}:{result.cell_id}"
        canonical_evidence["subject"] = equipment.model_dump(mode="json")
        canonical_evidence["artifact_reference"]["event_id"] = event_id
        canonical_evidence["report_projection"]["maintenance_context"] = maintenance_context
        legacy_evidence = event_evidence_projection_to_legacy_evidence(
            canonical_evidence,
            ranked_factor_evidence=producer_artifact.get("ranked_factor_evidence"),
        )
        legacy_evidence["top_factors"] = _localize_legacy_top_factors(
            legacy_evidence["top_factors"],
            locale,
        )
        legacy_evidence["evidence_id"] = f"pm-evidence:{event_id}"
        legacy_evidence["equipment"] = equipment.model_dump(mode="json")
        legacy_evidence["confidence"] = confidence
        legacy_evidence["maintenance_context"] = maintenance_context
        legacy_evidence["lineage"].update(
            {
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
            }
        )
        evidence = canonical_evidence if view == "canonical" else legacy_evidence
        factors = legacy_evidence["top_factors"]
        presentation_factors = partition_factors(factors, locale)
        physical_factors = presentation_factors["physical"]
        decision_basis = presentation_factors["decision_basis"]
        asset_label = asset_display_name(result.asset_id, locale)
        resolved_report_type = report_type or (
            "executive-brief" if role == "executive" else "inspection-summary" if role == "engineer" else "operations-decision"
        )
        report = {
            "report_id": f"pm-report:{event_id}:{role}:{resolved_report_type}:{locale}",
            "event_id": event_id,
            "role": role,
            "report_type": resolved_report_type,
            "locale": locale,
            "mode": "deterministic_result_artifact",
            "presentation_dictionary_version": PRESENTATION_DICTIONARY_VERSION,
            "presentation_facts": {
                "asset_label": asset_label,
                "risk_percent": round(result.failure_probability * 100, 1),
                "prediction_horizon_hours": result.prediction_horizon_hours,
                "physical_factors": physical_factors,
                "decision_basis": decision_basis,
                "technical_metadata": presentation_factors["technical_metadata"],
            },
            "headline": (
                f"{asset_label} · {status_label} · 고장 위험"
                if locale == "ko-KR"
                else f"{asset_label} · {status_label} failure risk"
            ),
            "summary": (
                f"이 설비는 {result.prediction_horizon_hours}시간 이내 고장 위험이 "
                f"{result.failure_probability * 100:.1f}%로 분류됐습니다. 현장 점검 전에는 원인을 확정하지 않으며 모든 조치는 담당자가 검토합니다."
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
                            f"{_pm_label(PM_FEATURE_LABELS, locale, str(item.get('feature')))} "
                            f"{'위험 증가' if item.get('direction') == 'risk_up' else '위험 감소'}"
                            if locale == "ko-KR"
                            else (
                                f"{_pm_label(PM_FEATURE_LABELS, locale, str(item.get('feature')))} "
                                f"{str(item.get('direction')).replace('_', ' ')}"
                            )
                        )
                        for item in physical_factors
                    ) or (
                        "현재 결과에는 센서별 기여도 근거가 포함되지 않았습니다. 현장 점검 전에는 원인을 확정하지 않습니다."
                        if locale == "ko-KR"
                        else "This result does not include sensor-level contribution evidence. The cause remains unconfirmed until field inspection."
                    ),
                    "evidence_field_ids": [item["evidence_field_id"] for item in physical_factors],
                },
                {
                    "section_id": "decision-basis",
                    "title": "판정 기준" if locale == "ko-KR" else "Decision basis",
                    "body": (
                        f"모델 위험 점수와 운영 판정 기준을 비교해 {status_label} 상태로 분류했습니다."
                        if locale == "ko-KR"
                        else f"The model score was compared with the operating threshold and classified as {status_label}."
                    ),
                    "evidence_field_ids": [item["evidence_field_id"] for item in decision_basis],
                },
                {
                    "section_id": "maintenance",
                    "title": "정비 이력" if locale == "ko-KR" else "Maintenance history",
                    "body": (
                        f"이 설비에는 확인된 점검·정비 이력 {len(maintenance)}건이 연결되어 있습니다."
                        if locale == "ko-KR"
                        else f"{len(maintenance)} canonical maintenance events are linked to this asset."
                    ),
                    "evidence_field_ids": source_refs[2:],
                },
                {
                    "section_id": "provenance",
                    "title": "데이터 기준" if locale == "ko-KR" else "Data basis",
                    "body": (
                        f"{source_display_name(context.source_version, locale)}와 "
                        f"{source_display_name(result.provenance.model_version, locale)}을 기준으로 작성했습니다."
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
        if role == "executive":
            risk_text = f"{result.failure_probability * 100:.1f}%"
            criticality_label = {
                "high": "높음" if locale == "ko-KR" else "high",
                "medium": "중간" if locale == "ko-KR" else "medium",
                "low": "낮음" if locale == "ko-KR" else "low",
            }.get(equipment.criticality, "확인 필요" if locale == "ko-KR" else "not provided")
            if resolved_report_type == "operations-decision":
                report["headline"] = f"{asset_label} · 경영 의사결정 요청"
                report["summary"] = f"현재 위험도 {risk_text}, 상태 {status_label}입니다. 현재 요청된 판단은 '{action_label}'이며 자동 실행되지 않습니다."
                report["sections"] = [
                    {"section_id": "decision-request", "title": "의사결정 요청", "body": action_label, "evidence_field_ids": ["recommended_decision"]},
                    {"section_id": "operational-exposure", "title": "운영 노출", "body": f"설비 중요도 {criticality_label} · 예상 정지 노출 {equipment.estimated_downtime_minutes}분", "evidence_field_ids": ["equipment.criticality", "equipment.estimated_downtime_minutes"]},
                ]
            elif resolved_report_type == "inspection-summary":
                report["headline"] = f"{asset_label} · 현장 확인 필요"
                report["summary"] = f"현재 위험도 {risk_text}입니다. 예측 결과는 고장 확정이 아니며 '{action_label}'을 통해 현장 확인이 필요합니다."
                report["sections"] = [
                    {"section_id": "inspection-request", "title": "확인 요청", "body": action_label, "evidence_field_ids": ["recommended_decision"]},
                    {"section_id": "inspection-limit", "title": "판단 경계", "body": "현장 점검 전에는 원인과 정비 필요성을 확정하지 않습니다.", "evidence_field_ids": ["status"]},
                ]
            elif resolved_report_type == "maintenance-effect":
                report["headline"] = f"{asset_label} · 정비 효과 확인 대기"
                report["summary"] = "이 Event에 직접 연결된 Maintenance Event와 정비 후 관측이 확인되기 전에는 정비 효과를 현재 Case의 Outcome으로 표시하지 않습니다."
                report["sections"] = [
                    {"section_id": "maintenance-state", "title": "현재 상태", "body": "정비 완료와 후속 관측의 인과 연결을 확인해야 합니다.", "evidence_field_ids": ["status"]},
                ]
            elif resolved_report_type == "weekly-risk":
                report["headline"] = f"주간 리스크 참고 · {asset_label}"
                report["summary"] = f"선택 Case snapshot의 위험도는 {risk_text}, 상태는 {status_label}입니다. 전체 주간 포트폴리오 집계와는 구분합니다."
                report["sections"] = [
                    {"section_id": "case-risk", "title": "선택 Case", "body": report["summary"], "evidence_field_ids": ["status", "failure_probability"]},
                ]
            else:
                report["headline"] = f"경영진 운영 브리프 · {asset_label}"
                report["summary"] = f"현재 위험도 {risk_text}, 상태 {status_label}입니다. 고장 유형은 현장 확인 전 가설이며 현재 경영 판단 요청은 '{action_label}'입니다."
                report["sections"] = [
                    {"section_id": "executive-status", "title": "경영 판단 요약", "body": report["summary"], "evidence_field_ids": ["status", "failure_probability", "recommended_decision"]},
                    {"section_id": "executive-exposure", "title": "운영 노출", "body": f"예상 정지 노출 {equipment.estimated_downtime_minutes}분 · 설비 중요도 {criticality_label}", "evidence_field_ids": ["equipment.estimated_downtime_minutes", "equipment.criticality"]},
                ]
            # Raw feature identifiers and release provenance remain available
            # through Evidence details, not the normal executive narrative.
            report["citations"] = ["status", "failure_probability", "recommended_decision", "equipment.estimated_downtime_minutes"]
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
            "locale": locale,
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
        report_type: str | None = None,
        intent: str,
        locale: AppLocale = "ko-KR",
        view: Literal["legacy", "canonical"] = "legacy",
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
        context_by_event: dict[str, DatasetVersionRuntimeContext] = {}
        for result in results.items:
            event_id = self._dashboard_event_id(result)
            # Evidence for a prediction must not include maintenance completed
            # after that prediction timestamp. This also keeps replay/report
            # context free of future operational information.
            maintenance = [
                item
                for item in maintenance_by_asset.get(result.asset_id, [])
                if item.get("completed_at") is not None
                and item["completed_at"] <= result.observed_at
            ]
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
            context_by_event[event_id] = context

        # A Decision Case is a frozen prediction snapshot, not an alias for the
        # latest prediction of the same asset.  The latest-results collection
        # intentionally advances as new observations arrive, so explicitly
        # requested historical Result Artifacts have to be re-hydrated from the
        # artifact repository instead of silently falling forward to a newer
        # event.
        if selected_event_id and selected_event_id not in result_by_event:
            historical = self._historical_selected_result(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                selected_event_id=selected_event_id,
            )
            if historical is not None:
                selected_result, selected_context = historical
                selected_maintenance = [
                    item
                    for item in maintenance_by_asset.get(selected_result.asset_id, [])
                    if item.get("completed_at") is not None
                    and item["completed_at"] <= selected_result.observed_at
                ]
                selected_equipment = self._dashboard_equipment(selected_result, selected_maintenance)
                canonical_selected_id = self._dashboard_event_id(selected_result)
                events.append(
                    DashboardEventSummary(
                        event_id=canonical_selected_id,
                        scenario_id=f"{selected_result.asset_type}:{selected_result.site_id}:{selected_result.cell_id}",
                        ontology_object_id=ontology_by_asset.get(selected_result.asset_id),
                        equipment=selected_equipment,
                        status=selected_result.status_grade,
                        failure_probability=selected_result.failure_probability,
                        confidence=f"{selected_result.confidence * 100:.1f}% · calibrated",
                        predicted_failure_type=selected_result.predicted_failure_type,
                        recommended_decision=(
                            selected_result.recommended_action.action
                            if selected_result.recommended_action
                            else "Review governed prediction"
                        ),
                        observed_at=selected_result.observed_at,
                        dataset_version_id=selected_context.dataset_version_id,
                    )
                )
                equipment_by_event[canonical_selected_id] = selected_equipment
                result_by_event[canonical_selected_id] = selected_result
                context_by_event[canonical_selected_id] = selected_context
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
            if selected_event_id and selected_event_id in result_by_event
            else None
            if selected_event_id
            else events[0].event_id
            if events
            else None
        )
        detail = None
        if selected_id:
            selected_result = result_by_event[selected_id]
            selected_context = context_by_event[selected_id]
            selected_maintenance = [
                item
                for item in maintenance_by_asset.get(selected_result.asset_id, [])
                if item.get("completed_at") is not None
                and item["completed_at"] <= selected_result.observed_at
            ]
            if self._supports_dashboard_evidence_detail(
                selected_result.source_contract,
                selected_result.producer_artifact,
            ):
                detail = self._dashboard_detail(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    context=selected_context,
                    result=selected_result,
                    equipment=equipment_by_event[selected_id],
                    maintenance=selected_maintenance,
                    role=role,
                    report_type=report_type,
                    intent=intent,
                    locale=locale,
                    view=view,
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

    def resolve_maintenance_replay_session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        session_id: str,
        equipment_id: str,
    ) -> dict[str, str]:
        """Validate a replay selector for a downstream Maintenance workflow.

        Diagnosis owns Replay Session eligibility and Dataset membership.  The
        consumer receives only the verified opaque reference and target scope;
        mutable Session or Dataset internals are not exposed for reinterpretation.
        """

        row = self.repository.session(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=session_id,
            advance=False,
        )
        record = ReplaySessionRecord.model_validate(row)
        expected_scope = (organization_id, project_id, workspace_id)
        actual_scope = (
            record.organization_id,
            record.project_id,
            record.workspace_id,
        )
        if actual_scope != expected_scope:
            raise ValueError("Replay Session scope does not match the request")
        if record.id != session_id:
            raise ValueError("Replay Session canonical identity does not match the selector")
        if record.state not in {"running", "paused"}:
            raise ValueError("Replay Session is not eligible for Maintenance")
        if not record.dataset_version_id:
            raise ValueError("Replay Session Dataset Version is missing")
        if not self.repository.asset_exists_in_version(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=record.dataset_version_id,
            asset_id=equipment_id,
        ):
            raise ValueError("equipment is not present in the Replay Session Dataset Version")
        return {
            "organization_id": organization_id,
            "project_id": project_id,
            "workspace_id": workspace_id,
            "equipment_id": equipment_id,
            "simulation_session_id": record.id,
        }

    def resolve_maintenance_source_session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        source_product_result_id: str,
        equipment_id: str,
    ) -> dict[str, str] | None:
        """Resolve the source simulation session recorded by a Product Result."""

        row = self.repository.result_artifact_row(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            artifact_id=source_product_result_id,
        )
        if row is None:
            raise KeyError(source_product_result_id)
        context = self.context(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=str(row["dataset_version_id"]),
        )
        result = self._product_result(
            context=context,
            row=row,
            source_contract="result_artifact",
        )
        if result.artifact_id != source_product_result_id:
            raise ValueError("Product Result canonical identity does not match the selector")
        if result.asset_id != equipment_id:
            raise ValueError("Product Result equipment identity mismatch")
        simulation_session_id = result.provenance.simulation_session_id
        if simulation_session_id is None or not simulation_session_id.strip():
            return None
        return {
            "organization_id": organization_id,
            "project_id": project_id,
            "workspace_id": workspace_id,
            "equipment_id": equipment_id,
            "simulation_session_id": simulation_session_id,
        }

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
