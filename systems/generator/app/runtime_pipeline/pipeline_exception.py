"""Domain exception classes for the Generator Runtime Pipeline."""

from __future__ import annotations

from typing import Any, Optional


class PipelineBaseError(Exception):
    """Base exception for all pipeline domain errors."""

    status_code: int = 500
    code: str = "PIPELINE_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[list[dict[str, Any]]] = None,
        retryable: Optional[bool] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or []
        if retryable is not None:
            self.retryable = retryable


# =====================================================================
# 1. Non-Retryable Errors (Fail Immediately)
# =====================================================================

class PipelinePathNotAllowedError(PipelineBaseError):
    status_code = 403
    code = "PIPELINE_PATH_NOT_ALLOWED"
    retryable = False


class PipelineQueueItemInvalidError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_QUEUE_ITEM_INVALID"
    retryable = False


class PipelineDuplicateInputError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_DUPLICATE_INPUT"
    retryable = False


class PipelineSourceAlreadyRegisteredError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_SOURCE_ALREADY_REGISTERED"
    retryable = False


class PipelineSourceAlreadyProcessedError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_SOURCE_ALREADY_PROCESSED"
    retryable = False


class PipelineAlreadyRunningError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_ALREADY_RUNNING"
    retryable = False


class PipelineStateTransitionInvalidError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_STATE_TRANSITION_INVALID"
    retryable = False


class PipelineInputNotFoundError(PipelineBaseError):
    status_code = 404
    code = "PIPELINE_INPUT_NOT_FOUND"
    retryable = False


class PipelineInputNotReadyError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_INPUT_NOT_READY"
    retryable = False


class PipelineInputChecksumMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_INPUT_CHECKSUM_MISMATCH"
    retryable = False


class PipelineUnsupportedInputFormatError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_UNSUPPORTED_INPUT_FORMAT"
    retryable = False


class PipelineMappingNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_MAPPING_NOT_IMPLEMENTED"
    retryable = False


class PipelineAssetIdMissingError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_ASSET_ID_MISSING"
    retryable = False


class PipelineAssetIdResolutionNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED"
    retryable = False


class PipelineAssetIdColumnMissingError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_ASSET_ID_COLUMN_MISSING"
    retryable = False


class PipelineAssetIdValueMissingError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_ASSET_ID_VALUE_MISSING"
    retryable = False


class PipelineFeatureMetadataAlignmentError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_FEATURE_METADATA_ALIGNMENT_ERROR"
    retryable = False


class PipelineTimestampInvalidError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_TIMESTAMP_INVALID"
    retryable = False


class PipelinePreprocessingFailedError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_PREPROCESSING_FAILED"
    retryable = False


class PipelineSensorValueMissingError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_SENSOR_VALUE_MISSING"
    retryable = False


class PipelineRuntimeFeatureFailedError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_RUNTIME_FEATURE_FAILED"
    retryable = False


class PipelineModelFeatureMissingValueHandlingNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_MODEL_FEATURE_MISSING_VALUE_HANDLING_NOT_IMPLEMENTED"
    retryable = False


class PipelinePredictionObservationAlignmentNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_PREDICTION_OBSERVATION_ALIGNMENT_NOT_IMPLEMENTED"
    retryable = False


class PipelineHistoryInsufficientError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_HISTORY_INSUFFICIENT"
    retryable = False


class PipelineFeatureSchemaMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_FEATURE_SCHEMA_MISMATCH"
    retryable = False


class PipelineNoActiveModelError(PipelineBaseError):
    status_code = 503
    code = "PIPELINE_NO_ACTIVE_MODEL"
    retryable = False


class PipelineModelArtifactInvalidError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_MODEL_ARTIFACT_INVALID"
    retryable = False


class PipelineModelPredictionFailedError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_MODEL_PREDICTION_FAILED"
    retryable = False


class PipelinePartialPredictionError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_PARTIAL_PREDICTION"
    retryable = False


class PipelineBatchBuildingFailedError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_BATCH_BUILDING_FAILED"
    retryable = False


class PipelineJobNotFailedError(PipelineBaseError):
    status_code = 400
    code = "PIPELINE_JOB_NOT_FAILED"
    retryable = False


class PipelineNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_NOT_IMPLEMENTED"
    retryable = False


# =====================================================================
# 2. Retryable Errors (Max 5 Attempts with Exponential Backoff)
# =====================================================================

class PipelineSourceFileNotStableError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_SOURCE_FILE_NOT_STABLE"
    retryable = True


class PipelineSourceChecksumChangedError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_SOURCE_CHECKSUM_CHANGED"
    retryable = True


class PipelineQueuePersistError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_QUEUE_PERSIST_FAILED"
    retryable = True


class PipelineTemporaryFileIoError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_TEMPORARY_FILE_IO_FAILED"
    retryable = True


class PipelineModelArtifactBusyError(PipelineBaseError):
    status_code = 503
    code = "PIPELINE_MODEL_ARTIFACT_BUSY"
    retryable = True


class PipelineRecoveryError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_RECOVERY_FAILED"
    retryable = True


class PipelineDeliveryFailedError(PipelineBaseError):
    status_code = 502
    code = "PIPELINE_DELIVERY_FAILED"
    retryable = True


class PipelineDeliveryTimeoutError(PipelineBaseError):
    status_code = 504
    code = "PIPELINE_DELIVERY_TIMEOUT"
    retryable = True


class PipelineDeliveryServerError(PipelineBaseError):
    status_code = 502
    code = "PIPELINE_DELIVERY_SERVER_ERROR"
    retryable = True


class PipelineDeliveryRetryExhaustedError(PipelineBaseError):
    status_code = 502
    code = "PIPELINE_DELIVERY_RETRY_EXHAUSTED"
    retryable = False


# =====================================================================
# 3. Checkpoint, Resumption & Intermediate Cleanup Errors
# =====================================================================

class PipelineCheckpointInvalidError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_CHECKPOINT_INVALID"
    retryable = False


class PipelineCheckpointIncompatibleError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_CHECKPOINT_INCOMPATIBLE"
    retryable = False


class PipelineCheckpointOutputMissingError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_CHECKPOINT_OUTPUT_MISSING"
    retryable = False


class PipelineCheckpointChecksumMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_CHECKPOINT_CHECKSUM_MISMATCH"
    retryable = False


class PipelineResumeNotAllowedError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_RESUME_NOT_ALLOWED"
    retryable = False


class PipelineResumeFailedError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_RESUME_FAILED"
    retryable = False


class PipelineIntermediateCleanupFailedError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_INTERMEDIATE_CLEANUP_FAILED"
    retryable = False


class PipelineCleanupTargetNotAllowedError(PipelineBaseError):
    status_code = 403
    code = "PIPELINE_CLEANUP_TARGET_NOT_ALLOWED"
    retryable = False


class PipelineCleanupChecksumMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_CLEANUP_CHECKSUM_MISMATCH"
    retryable = False


class PipelineRunAlreadyActiveError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_RUN_ALREADY_ACTIVE"
    retryable = False


class PipelineCheckpointLockConflictError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_CHECKPOINT_LOCK_CONFLICT"
    retryable = False


class PipelineCleanupInProgressError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_CLEANUP_IN_PROGRESS"
    retryable = False


class PipelineModelSnapshotIncompatibleError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_MODEL_SNAPSHOT_INCOMPATIBLE"
    retryable = False


class PipelineModelSnapshotArtifactMissingError(PipelineBaseError):
    status_code = 404
    code = "PIPELINE_MODEL_SNAPSHOT_ARTIFACT_MISSING"
    retryable = False


class PipelineModelSnapshotChecksumMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_MODEL_SNAPSHOT_CHECKSUM_MISMATCH"
    retryable = False


class PipelineModelSetChangedError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_MODEL_SET_CHANGED"
    retryable = False


class PipelineOutboxEventConflictError(PipelineBaseError):
    status_code = 409
    code = "PIPELINE_OUTBOX_EVENT_CONFLICT"
    retryable = False


class PipelineOutboxPayloadChecksumMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_OUTBOX_PAYLOAD_CHECKSUM_MISMATCH"
    retryable = False


class PipelineOutboxPartialPublishError(PipelineBaseError):
    status_code = 500
    code = "PIPELINE_OUTBOX_PARTIAL_PUBLISH"
    retryable = False


class ModelSetUpdateLockedError(PipelineBaseError):
    status_code = 409
    code = "MODEL_SET_UPDATE_LOCKED"
    retryable = False


class ModelSetUpdateConflictError(PipelineBaseError):
    status_code = 409
    code = "MODEL_SET_UPDATE_CONFLICT"
    retryable = False


class ModelSetContractInvalidError(PipelineBaseError):
    status_code = 422
    code = "MODEL_SET_CONTRACT_INVALID"
    retryable = False


class ModelSetArtifactNotFoundError(PipelineBaseError):
    status_code = 404
    code = "MODEL_SET_ARTIFACT_NOT_FOUND"
    retryable = False


class ModelSetArtifactIntegrityError(PipelineBaseError):
    status_code = 422
    code = "MODEL_SET_ARTIFACT_INTEGRITY_ERROR"
    retryable = False


class ModelSetAtomicPublishFailedError(PipelineBaseError):
    status_code = 500
    code = "MODEL_SET_ATOMIC_PUBLISH_FAILED"
    retryable = False


class ModelSetOptionalModelPolicyNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "MODEL_SET_OPTIONAL_MODEL_POLICY_NOT_IMPLEMENTED"
    retryable = False


class PipelineRuntimePredictionDisabledError(PipelineBaseError):
    status_code = 503
    code = "PIPELINE_RUNTIME_PREDICTION_DISABLED"
    retryable = False


class PipelineModelManifestChecksumMissingError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_MODEL_MANIFEST_CHECKSUM_MISSING"
    retryable = False


class PipelineDeliveryUnprocessableError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_DELIVERY_UNPROCESSABLE"
    retryable = False


class PipelineDeliveryUnauthorizedError(PipelineBaseError):
    status_code = 401
    code = "PIPELINE_DELIVERY_UNAUTHORIZED"
    retryable = False


class ModelSetNotConfiguredError(PipelineBaseError):
    status_code = 404
    code = "MODEL_SET_NOT_CONFIGURED"
    retryable = False


class ModelSetModelNotRegisteredError(PipelineBaseError):
    status_code = 422
    code = "MODEL_SET_MODEL_NOT_REGISTERED"
    retryable = False


class PipelineModelSetChangedError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_MODEL_SET_CHANGED"
    retryable = False


class PipelineModelSetSnapshotMismatchError(PipelineBaseError):
    status_code = 422
    code = "PIPELINE_MODEL_SET_SNAPSHOT_MISMATCH"
    retryable = False


class ModelSetArtifactPathUnsupportedError(PipelineBaseError):
    status_code = 400
    code = "MODEL_SET_ARTIFACT_PATH_UNSUPPORTED"
    retryable = False


class PipelineModelSetMembershipChangeNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_MODEL_SET_MEMBERSHIP_CHANGE_NOT_IMPLEMENTED"
    retryable = False


class PipelineModelSetHotReloadNotImplementedError(PipelineBaseError):
    status_code = 501
    code = "PIPELINE_MODEL_SET_HOT_RELOAD_NOT_IMPLEMENTED"
    retryable = False
