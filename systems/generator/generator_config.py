"""
generator_config.py

담당 기능:
- 시스템 전역 환경변수(.env) 싱글톤 로더 및 경로 레지스트리(GeneratorPaths) 모듈.
- PROJECT_ROOT(프로젝트 최상위 디렉토리)를 기준으로 경로를 동적 계산하되, .env에 DATA_DIR, DATA_PREPROCESSED_DIR, MODELS_STORE_DIR, ONTOLOGY_DIR이 설정되어 있으면 해당 외부 경로를 최우선으로 적용한다.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
_config_loaded = False

# 프로젝트 최상위 루트 디렉토리 (systems/generator/generator_config.py 이므로 parents[2])
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def get_generator_runtime_version() -> str:
    """Return the explicitly configured Generator runtime version.

    Runtime provenance must never be invented.  Deployments and tests that emit
    an external Prediction Result Batch therefore have to provide this value.
    """
    value = os.getenv("GENERATOR_RUNTIME_VERSION", "").strip()
    if not value:
        raise RuntimeError(
            "GENERATOR_RUNTIME_VERSION is required when publishing a Prediction Result Batch."
        )
    return value


def load_config(force: bool = False) -> None:
    """.env 파일에서 전역 환경변수를 읽어 설정한다."""
    global _config_loaded
    if _config_loaded and not force:
        return
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path)
            logger.info(f"[GeneratorConfig] Loaded '{env_path}'")
        except ImportError:
            logger.warning("[GeneratorConfig] dotenv package not installed; skipping .env load")
        except Exception as e:
            logger.warning(f"[GeneratorConfig] Failed to load .env at '{env_path}': {e}")
    else:
        logger.warning(f"[GeneratorConfig] .env not found at '{env_path}'.")
    _config_loaded = True


class GeneratorPaths:
    """Generator 시스템 전역 디렉토리 및 영속 파일 경로 레지스트리 (.env 오버라이드 지원)"""

    def __init__(self) -> None:
        load_config()

        # 1. 디렉토리 경로 (.env 설정 우선, 미설정 시 PROJECT_ROOT 하위 기본 디렉토리)
        data_env = os.getenv("DATA_DIR")
        self.data_dir: Path = Path(data_env).resolve() if data_env else (PROJECT_ROOT / "data").resolve()

        preprocessed_env = os.getenv("DATA_PREPROCESSED_DIR")
        self.data_preprocessed: Path = (
            Path(preprocessed_env).resolve() if preprocessed_env else (PROJECT_ROOT / "data_preprocessed").resolve()
        )

        models_env = os.getenv("MODELS_STORE_DIR")
        self.models_store: Path = (
            Path(models_env).resolve() if models_env else (PROJECT_ROOT / "models_store").resolve()
        )

        ontology_env = os.getenv("ONTOLOGY_DIR")
        self.ontology: Path = (
            Path(ontology_env).resolve() if ontology_env else (PROJECT_ROOT / "ontology").resolve()
        )

        # 1-1. gen_data 출력 루트 경로 (.env GEN_DATA_OUTPUT_DIR 우선, 미설정 시 None)
        gen_data_env = os.getenv("GEN_DATA_OUTPUT_DIR")
        self.gen_data_output_dir: Optional[Path] = (
            Path(gen_data_env).resolve() if gen_data_env and gen_data_env.strip() else None
        )
        self.gen_data_sensor_root: Optional[Path] = (
            (self.gen_data_output_dir / "sensor").resolve() if self.gen_data_output_dir else None
        )

        # 2. 핵심 영속 파일 전용 경로
        self.extraction_plan_cache: Path = self.data_preprocessed / "extraction_plan_cache.json"
        self.source_family_registry: Path = self.data_preprocessed / "source_family_registry.json"
        self.mapping_cache: Path = self.ontology / "mapping_cache.json"
        self.feature_catalog: Path = PROJECT_ROOT / "systems" / "generator" / "feature" / "feature_catalog.yaml"
        self.registry_json: Path = self.models_store / "registry.json"
        self.predictions_dir: Path = self.data_preprocessed / "predictions"

        # 3. Runtime Prediction Pipeline 전용 경로 및 설정
        input_roots_env = os.getenv("GENERATOR_PIPELINE_INPUT_ROOTS")
        if input_roots_env:
            self.pipeline_input_roots: list[Path] = [
                Path(p.strip()).resolve() for p in input_roots_env.split(",") if p.strip()
            ]
        else:
            self.pipeline_input_roots = [
                self.data_dir,
                self.data_preprocessed,
                (PROJECT_ROOT / "contracts").resolve(),
            ]

        queue_db_env = os.getenv("GENERATOR_PIPELINE_QUEUE_DB")
        self.pipeline_queue_db: Path = (
            Path(queue_db_env).resolve()
            if queue_db_env
            else self.data_preprocessed / "pipeline_queue" / "queue.db"
        )

        state_root_env = os.getenv("GENERATOR_PIPELINE_STATE_ROOT")
        self.pipeline_state_root: Path = (
            Path(state_root_env).resolve()
            if state_root_env
            else self.data_preprocessed / "pipeline_runs"
        )

        runtime_feat_env = os.getenv("GENERATOR_RUNTIME_FEATURE_ROOT")
        self.runtime_feature_root: Path = (
            Path(runtime_feat_env).resolve()
            if runtime_feat_env
            else self.models_store / "cache" / "runtime_features"
        )

        outbox_env = os.getenv("GENERATOR_NOTIFICATION_OUTBOX_ROOT")
        self.notification_outbox_root: Path = (
            Path(outbox_env).resolve()
            if outbox_env
            else self.data_preprocessed / "notification_outbox"
        )

        max_attempts_env = os.getenv("GENERATOR_PIPELINE_MAX_ATTEMPTS")
        self.pipeline_max_attempts: int = int(max_attempts_env) if max_attempts_env else 5

        backoff_env = os.getenv("GENERATOR_PIPELINE_RETRY_BACKOFF_SECONDS")
        self.pipeline_retry_backoff_seconds: float = float(backoff_env) if backoff_env else 1.0

        pred_enabled_env = os.getenv("GENERATOR_RUNTIME_PREDICTION_ENABLED", "false").strip().lower()
        self.runtime_prediction_enabled: bool = pred_enabled_env in ("true", "1", "yes")

        # 4. Extraction Pipeline 전용 경로 및 환경 변수 설정
        obs_env = os.getenv("GENERATOR_OBSERVATIONS_ROOT")
        self.observations_root: Path = Path(obs_env).resolve() if obs_env else (self.data_dir / "observations").resolve()

        runs_env = os.getenv("GENERATOR_EXTRACTION_RUNS_ROOT")
        self.extraction_runs_root: Path = Path(runs_env).resolve() if runs_env else (self.data_preprocessed / "extraction_runs").resolve()

        state_env = os.getenv("GENERATOR_EXTRACTION_STATE_ROOT")
        self.extraction_state_root: Path = Path(state_env).resolve() if state_env else (self.data_preprocessed / "extraction_state").resolve()

        mapping_env = os.getenv("GENERATOR_MAPPING_ROOT")
        self.mapping_root: Path = Path(mapping_env).resolve() if mapping_env else (self.ontology / "mappings").resolve()

        batch_size_env = os.getenv("GENERATOR_EXTRACTION_BATCH_SIZE")
        self.extraction_batch_size: int = int(batch_size_env) if batch_size_env else 1000

        lease_env = os.getenv("GENERATOR_EXTRACTION_LOCK_LEASE_SECONDS")
        self.extraction_lock_lease_seconds: float = float(lease_env) if lease_env else 300.0

        extract_roots_env = os.getenv("GENERATOR_EXTRACTION_INPUT_ROOTS")
        if extract_roots_env:
            self.extraction_input_roots: list[Path] = [
                Path(p.strip()).resolve() for p in extract_roots_env.split(",") if p.strip()
            ]
        else:
            self.extraction_input_roots = [
                self.data_dir,
                self.data_preprocessed,
                (PROJECT_ROOT / "contracts").resolve(),
                (PROJECT_ROOT / "output").resolve(),
            ]

        # 4-1. Extraction Polling Worker and API Configuration
        ext_enabled_env = os.getenv("GENERATOR_EXTRACTION_ENABLED", "false").strip().lower()
        self.extraction_enabled: bool = ext_enabled_env in ("true", "1", "yes")

        ext_poll_env = os.getenv("GENERATOR_EXTRACTION_POLL_INTERVAL_SECONDS")
        self.extraction_poll_interval_seconds: float = float(ext_poll_env) if ext_poll_env else 5.0

        ext_win_env = os.getenv("GENERATOR_EXTRACTION_WINDOW_MINUTES")
        self.extraction_window_minutes: int = int(ext_win_env) if ext_win_env else 60

        ext_max_rec_env = os.getenv("GENERATOR_EXTRACTION_MAX_RECORDS")
        self.extraction_max_records: int = int(ext_max_rec_env) if ext_max_rec_env else 10000

        ext_max_att_env = os.getenv("GENERATOR_EXTRACTION_MAX_ATTEMPTS")
        self.extraction_max_attempts: int = int(ext_max_att_env) if ext_max_att_env else 5

        ext_backoff_env = os.getenv("GENERATOR_EXTRACTION_RETRY_BACKOFF_SECONDS")
        self.extraction_retry_backoff_seconds: float = float(ext_backoff_env) if ext_backoff_env else 1.0

        ext_conc_env = os.getenv("GENERATOR_EXTRACTION_MAX_CONCURRENCY")
        self.extraction_max_concurrency: int = int(ext_conc_env) if ext_conc_env else 4

        self.extraction_mapping_id: str = os.getenv(
            "GENERATOR_EXTRACTION_MAPPING_ID", "gen-data-sensor-stream-canonical"
        ).strip()
        self.extraction_mapping_version: str = os.getenv(
            "GENERATOR_EXTRACTION_MAPPING_VERSION", "v1"
        ).strip()
        mapping_sha_env = os.getenv("GENERATOR_EXTRACTION_MAPPING_SHA256")
        self.extraction_mapping_sha256: Optional[str] = (
            mapping_sha_env.strip() if mapping_sha_env and mapping_sha_env.strip() else None
        )

        # 4-2. Extraction Runtime Handoff Configuration
        handoff_root_env = os.getenv("GENERATOR_EXTRACTION_HANDOFFS_ROOT")
        self.extraction_handoffs_root: Path = (
            Path(handoff_root_env).resolve()
            if handoff_root_env
            else (self.data_preprocessed / "extraction_handoffs").resolve()
        )

        handoff_enabled_env = os.getenv("GENERATOR_EXTRACTION_RUNTIME_HANDOFF_ENABLED", "false").strip().lower()
        self.extraction_runtime_handoff_enabled: bool = handoff_enabled_env in ("true", "1", "yes")

        handoff_poll_env = os.getenv("GENERATOR_EXTRACTION_HANDOFF_POLL_INTERVAL_SECONDS")
        self.extraction_handoff_poll_interval_seconds: float = float(handoff_poll_env) if handoff_poll_env else 5.0

        handoff_retries_env = os.getenv("GENERATOR_EXTRACTION_HANDOFF_MAX_RETRIES")
        self.extraction_handoff_max_retries: int = int(handoff_retries_env) if handoff_retries_env else 5

        handoff_conc_env = os.getenv("GENERATOR_EXTRACTION_HANDOFF_MAX_CONCURRENCY")
        self.extraction_handoff_max_concurrency: int = int(handoff_conc_env) if handoff_conc_env else 1

    def validate_extraction_config(self) -> None:
        """Validate extraction environment configuration."""
        from systems.generator.app.extraction.extraction_exception import (
            ExtractionConfigurationInvalidError,
            ExtractionMappingConfigurationMissingError,
        )

        if self.extraction_poll_interval_seconds <= 0:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_POLL_INTERVAL_SECONDS must be > 0, got {self.extraction_poll_interval_seconds}"
            )
        if self.extraction_window_minutes <= 0:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_WINDOW_MINUTES must be > 0, got {self.extraction_window_minutes}"
            )
        if self.extraction_max_records <= 0:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_MAX_RECORDS must be > 0, got {self.extraction_max_records}"
            )
        if self.extraction_max_attempts < 1:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_MAX_ATTEMPTS must be >= 1, got {self.extraction_max_attempts}"
            )
        if self.extraction_retry_backoff_seconds < 0:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_RETRY_BACKOFF_SECONDS must be >= 0, got {self.extraction_retry_backoff_seconds}"
            )
        if self.extraction_max_concurrency < 1:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_MAX_CONCURRENCY must be >= 1, got {self.extraction_max_concurrency}"
            )
        if self.extraction_handoff_poll_interval_seconds <= 0:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_HANDOFF_POLL_INTERVAL_SECONDS must be > 0, got {self.extraction_handoff_poll_interval_seconds}"
            )
        if self.extraction_handoff_max_retries < 1:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_HANDOFF_MAX_RETRIES must be >= 1, got {self.extraction_handoff_max_retries}"
            )
        if self.extraction_handoff_max_concurrency < 1:
            raise ExtractionConfigurationInvalidError(
                f"GENERATOR_EXTRACTION_HANDOFF_MAX_CONCURRENCY must be >= 1, got {self.extraction_handoff_max_concurrency}"
            )
        if not self.extraction_mapping_id or not self.extraction_mapping_version:
            raise ExtractionConfigurationInvalidError(
                "GENERATOR_EXTRACTION_MAPPING_ID and GENERATOR_EXTRACTION_MAPPING_VERSION must not be empty"
            )

        if self.extraction_enabled:
            if not self.gen_data_output_dir or not self.gen_data_output_dir.exists():
                raise ExtractionConfigurationInvalidError(
                    f"Background extraction enabled but GEN_DATA_OUTPUT_DIR is missing or invalid: {self.gen_data_output_dir}"
                )
            if not self.extraction_mapping_sha256 or len(self.extraction_mapping_sha256) != 64:
                raise ExtractionMappingConfigurationMissingError(
                    "Background extraction enabled but GENERATOR_EXTRACTION_MAPPING_SHA256 is missing or invalid 64-char hex string."
                )

    def ensure_directories(self) -> None:
        """필요 디렉토리가 존재하는지 검사하고 자동 생성한다."""
        for path in (
            self.data_preprocessed,
            self.models_store,
            self.ontology,
            self.predictions_dir,
            self.pipeline_queue_db.parent,
            self.pipeline_state_root,
            self.runtime_feature_root,
            self.notification_outbox_root,
            self.observations_root,
            self.extraction_runs_root,
            self.extraction_state_root,
        ):
            path.mkdir(parents=True, exist_ok=True)


PATHS = GeneratorPaths()
PATHS.ensure_directories()


def validate_pipeline_source_uri(
    source_uri: str,
    allowed_roots: Optional[list[Path]] = None,
) -> Path:
    """Validate source file URI against allowed input roots, path traversals, and format contracts."""
    from systems.generator.app.runtime_pipeline.pipeline_exception import (
        PipelineInputNotFoundError,
        PipelinePathNotAllowedError,
        PipelineUnsupportedInputFormatError,
    )

    clean_uri = str(source_uri).strip()
    if not clean_uri:
        raise PipelinePathNotAllowedError("source_uri가 비어 있습니다.", retryable=False)

    p = Path(clean_uri)
    if ".." in p.parts:
        raise PipelinePathNotAllowedError(
            f"source_uri에 상위 디렉터리 탐색(..)이 포함되어 있습니다: '{clean_uri}'",
            details=[{"source_uri": clean_uri}],
            retryable=False,
        )

    roots = allowed_roots or PATHS.pipeline_input_roots

    # Resolve candidate path
    resolved: Optional[Path] = None
    if p.is_absolute():
        resolved = p.resolve()
    else:
        # Check relative to each allowed root or PROJECT_ROOT
        candidates = [root / p for root in roots] + [PROJECT_ROOT / p]
        for c in candidates:
            if c.exists():
                resolved = c.resolve()
                break
        if resolved is None:
            resolved = (PROJECT_ROOT / p).resolve()

    # Check if within allowed roots
    is_allowed = False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            is_allowed = True
            break
        except ValueError:
            continue

    if not is_allowed:
        raise PipelinePathNotAllowedError(
            f"source_uri가 허용된 입력 루트({[str(r) for r in roots]}) 범위를 벗어났습니다: '{clean_uri}'",
            details=[{"source_uri": clean_uri, "resolved": str(resolved), "allowed_roots": [str(r) for r in roots]}],
            retryable=False,
        )

    if not resolved.exists() or not resolved.is_file():
        raise PipelineInputNotFoundError(
            f"입력 소스 파일을 찾을 수 없거나 디렉터리입니다: '{resolved}'",
            details=[{"resolved_path": str(resolved)}],
            retryable=False,
        )

    if resolved.suffix.lower() not in (".jsonl", ".csv"):
        raise PipelineUnsupportedInputFormatError(
            f"지원하지 않는 관측 소스 파일 형식입니다: '{resolved.suffix}' (지원: .jsonl, .csv)",
            details=[{"resolved_path": str(resolved), "suffix": resolved.suffix}],
            retryable=False,
        )

    return resolved
