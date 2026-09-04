"""Domain exceptions for preprocessing domain."""

from __future__ import annotations
from typing import Any


class PreprocessingError(ValueError):
    """Base exception for all preprocessing domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "PREPROCESSING_ERROR",
        status_code: int = 500,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


class DatasetNotFoundError(PreprocessingError):
    """Raised when the specified dataset cannot be found."""

    def __init__(
        self,
        message: str = "지정한 데이터셋을 찾을 수 없습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message=message, code="DATASET_NOT_FOUND", status_code=404, details=details)


class DatasetContractError(PreprocessingError):
    """Raised when the dataset structure violates minimum format/contract rules."""

    def __init__(
        self,
        message: str = "데이터셋 계약 검증에 실패했습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message=message, code="DATASET_CONTRACT_ERROR", status_code=422, details=details)


class PreprocessingRoleError(PreprocessingError):
    """Raised when long-format required role columns cannot be determined or are missing."""

    def __init__(
        self,
        message: str = "Long-format 전처리에 필요한 컬럼 역할을 결정할 수 없습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PREPROCESSING_ROLE_COLUMNS_MISSING",
            status_code=422,
            details=details,
        )


class PreprocessingPlanningError(PreprocessingError):
    """Raised when preprocessing plan generation fails."""

    def __init__(
        self,
        message: str = "전처리 계획 수립에 실패했습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PREPROCESSING_PLANNING_ERROR",
            status_code=422,
            details=details,
        )


class PreprocessingPlanValidationError(PreprocessingError):
    """Raised when preprocessing plan validation fails against actual dataset columns."""

    def __init__(
        self,
        message: str = "전처리 계획 검증에 실패했습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PREPROCESSING_PLAN_VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class PreprocessingPlanPublishError(PreprocessingError):
    """Raised when atomic publishing of a preprocessing plan fails."""

    def __init__(
        self,
        message: str = "전처리 계획 저장 및 발행에 실패했습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PREPROCESSING_PLAN_PUBLISH_ERROR",
            status_code=500,
            details=details,
        )


class PreprocessingConflictError(PreprocessingError):
    """Raised when a concurrent conflicting preprocessing is in progress or duplicate version conflict."""

    def __init__(
        self,
        message: str = "동일한 전처리 작업이 이미 진행 중이거나 충돌이 발생했습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PREPROCESSING_CONFLICT",
            status_code=409,
            details=details,
        )


class PreprocessingPlanConflictError(PreprocessingError):
    """Raised when existing plan conflicts with dataset checksum or requested policies (409)."""

    def __init__(
        self,
        message: str = "기존 전처리 계획과 현재 데이터셋 또는 요청 정책 간의 충돌이 발생했습니다.",
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="PREPROCESSING_PLAN_CONFLICT",
            status_code=409,
            details=details,
        )
