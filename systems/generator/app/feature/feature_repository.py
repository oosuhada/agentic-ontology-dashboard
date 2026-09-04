"""Feature Repository managing immutable Feature Dataset Bundle storage and integrity."""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from systems.generator.app.feature.feature_exception import (
    FeatureContractError,
    FeatureDatasetIntegrityError,
    FeaturePublishConflictError,
    FeaturePublishError,
)
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS

logger = logging.getLogger(__name__)

_bundle_lock = threading.Lock()


@dataclass(frozen=True)
class PublishedFeatureBundle:
    """Represents a validated immutable Feature Dataset Bundle."""
    feature_dataset_version: str
    row_count: int
    feature_count: int
    features_uri: str
    labels_uri: str
    metadata_uri: str
    bundle_dir: Path


@dataclass(frozen=True)
class LoadedFeatureBundle:
    """Represents loaded in-memory data from a validated Feature Dataset Bundle."""
    dataset_id: str
    dataset_version: str
    feature_dataset_version: str
    features: np.ndarray
    labels: np.ndarray
    feature_columns: list[str]
    row_metadata: list[dict[str, Any]]
    feature_metadata: dict[str, Any]
    feature_metadata_sha256: str
    bundle_dir: Path


def compute_feature_dataset_version(fingerprint_dict: dict[str, Any]) -> str:
    """Compute 16-hex deterministic SHA-256 version from canonical fingerprint."""
    import hashlib
    serialized = json.dumps(fingerprint_dict, sort_keys=True, ensure_ascii=True)
    hash_val = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f"feature-dataset-{hash_val}"


class FeatureRepository:
    """Repository handling atomic persistence and integrity checks for Feature Dataset Bundles."""

    REQUIRED_BUNDLE_FILES = [
        "features.npy",
        "labels.npy",
        "feature_columns.json",
        "row_metadata.json",
        "feature_metadata.json",
    ]

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            models_store = getattr(PATHS, "models_store", Path("models_store"))
            self.base_dir = Path(models_store) / "cache" / "features"
        else:
            self.base_dir = Path(base_dir)

    def get_bundle_dir(self, dataset_id: str, dataset_version: str, feature_dataset_version: str) -> Path:
        """Resolve directory path for a feature bundle."""
        clean_id = dataset_id.strip()
        clean_ver = dataset_version.strip()
        clean_feat_ver = feature_dataset_version.strip()
        if ".." in clean_id or ".." in clean_ver or ".." in clean_feat_ver or "/" in clean_id or "\\" in clean_id:
            raise FeatureContractError("Path traversal 또는 안전하지 않은 경로 문자가 감지되었습니다.")
        return self.base_dir / clean_id / clean_ver / clean_feat_ver

    def get_logical_uri(self, path: Path | None) -> str:
        """Convert local filesystem path to relative URI with forward slashes (Fail-Closed)."""
        if path is None:
            return ""
        resolved = path.resolve()

        # 1. PATHS.data_dir
        try:
            data_dir = getattr(PATHS, "data_dir", Path("data")).resolve()
            if resolved == data_dir:
                return "data"
            if data_dir in resolved.parents:
                return f"data/{resolved.relative_to(data_dir).as_posix()}"
        except Exception:
            pass

        # 2. PATHS.models_store
        try:
            models_store = getattr(PATHS, "models_store", Path("models_store")).resolve()
            if resolved == models_store:
                return "models_store"
            if models_store in resolved.parents:
                return f"models_store/{resolved.relative_to(models_store).as_posix()}"
        except Exception:
            pass

        # 3. Project workspace
        try:
            cwd = Path.cwd().resolve()
            if resolved == cwd:
                return "."
            if cwd in resolved.parents:
                rel = resolved.relative_to(cwd).as_posix()
                if not rel.startswith(".."):
                    return rel
        except Exception:
            pass

        raise FeatureContractError(f"논리 URI로 변환할 수 없는 허용 범위 밖의 경로입니다: '{path.name}'")

    def find_feature_bundle(
        self,
        dataset_id: str,
        dataset_version: str,
        feature_dataset_version: str,
        expected_fingerprint: dict[str, Any] | None = None,
    ) -> PublishedFeatureBundle | None:
        """Locate and strictly validate existing Feature Dataset Bundle."""
        bundle_dir = self.get_bundle_dir(dataset_id, dataset_version, feature_dataset_version)
        if not bundle_dir.exists() or not bundle_dir.is_dir():
            return None

        # 1. Check all 5 files exist
        for fname in self.REQUIRED_BUNDLE_FILES:
            fpath = bundle_dir / fname
            if not fpath.exists() or fpath.stat().st_size == 0:
                raise FeatureDatasetIntegrityError(
                    f"Feature Dataset Bundle이 손상되었습니다. 필수 파일 누락 또는 0바이트: {fname}"
                )

        # 2. Read feature_metadata.json
        meta_path = bundle_dir / "feature_metadata.json"
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as exc:
            raise FeatureDatasetIntegrityError(f"feature_metadata.json 파싱 실패: {exc}") from exc

        # 3. Verify metadata declared version
        declared_ver = meta.get("feature_dataset_version")
        if declared_ver != feature_dataset_version:
            raise FeatureDatasetIntegrityError(
                f"feature_metadata.json의 버전('{declared_ver}')과 디렉터리 버전('{feature_dataset_version}')이 일치하지 않습니다."
            )

        # 4. Verify fingerprint match (if expected_fingerprint is provided)
        if expected_fingerprint is not None:
            saved_fingerprint = meta.get("fingerprint", {})
            if saved_fingerprint != expected_fingerprint:
                logger.error(
                    f"[FeatureRepository] Fingerprint conflict for {feature_dataset_version}. "
                    f"Saved: {saved_fingerprint}, Expected: {expected_fingerprint}"
                )
                raise FeaturePublishConflictError(
                    f"Feature Dataset Version '{feature_dataset_version}'에 상이한 지문(fingerprint)이 이미 존재합니다."
                )

        # 5. Verify payload checksums against declared metadata
        payload_checksums = meta.get("payload_checksums", {})
        for fname in ["features.npy", "labels.npy", "feature_columns.json", "row_metadata.json"]:
            expected_sha = payload_checksums.get(fname)
            if not expected_sha:
                raise FeatureDatasetIntegrityError(
                    f"feature_metadata.json에 {fname}의 체크섬이 누락되었습니다."
                )
            actual_sha = compute_file_sha256(bundle_dir / fname)
            if actual_sha != expected_sha:
                raise FeatureDatasetIntegrityError(
                    f"Feature Dataset Bundle 파일 체크섬 불일치 ({fname}): 기대값={expected_sha}, 실제={actual_sha}"
                )

        # 6. Verify numpy array integrity (finite, dimensions, row count alignment, label values)
        try:
            features = np.load(bundle_dir / "features.npy", allow_pickle=False)
            labels = np.load(bundle_dir / "labels.npy", allow_pickle=False)
        except Exception as exc:
            raise FeatureDatasetIntegrityError(f"Feature/Label npy 파일 로드 실패: {exc}") from exc

        if not np.isfinite(features).all():
            raise FeatureDatasetIntegrityError("features.npy에 NaN 또는 Inf 값이 포함되어 있습니다.")

        if features.ndim != 2:
            raise FeatureDatasetIntegrityError(f"features.npy는 2차원 배열이어야 합니다 (실제 차원: {features.ndim})")

        if labels.ndim != 1:
            raise FeatureDatasetIntegrityError(f"labels.npy는 1차원 배열이어야 합니다 (실제 차원: {labels.ndim})")

        if not np.isin(labels, [0, 1]).all():
            raise FeatureDatasetIntegrityError("labels.npy의 값은 {0, 1} 이진 레이블이어야 합니다.")

        row_count = int(features.shape[0])
        feature_count = int(features.shape[1])

        if labels.shape[0] != row_count:
            raise FeatureDatasetIntegrityError(
                f"Feature 행 수({row_count})와 Label 행 수({labels.shape[0]})가 일치하지 않습니다."
            )

        with open(bundle_dir / "row_metadata.json", "r", encoding="utf-8") as f:
            row_meta = json.load(f)
            if not isinstance(row_meta, list):
                raise FeatureDatasetIntegrityError("row_metadata.json은 JSON 배열이어야 합니다.")
            if len(row_meta) != row_count:
                raise FeatureDatasetIntegrityError(
                    f"row_metadata.json 항목 수({len(row_meta)})와 Feature 행 수({row_count})가 일치하지 않습니다."
                )
            for index, item in enumerate(row_meta):
                if not isinstance(item, dict):
                    raise FeatureDatasetIntegrityError(
                        f"row_metadata.json의 {index}번째 항목은 JSON 객체여야 합니다."
                    )

        with open(bundle_dir / "feature_columns.json", "r", encoding="utf-8") as f:
            col_data = json.load(f)
            cols = col_data.get("columns", [])
            if len(cols) != feature_count:
                raise FeatureDatasetIntegrityError(
                    f"feature_columns.json 열 수({len(cols)})와 Feature 열 수({feature_count})가 일치하지 않습니다."
                )
            if len(set(cols)) != len(cols):
                raise FeatureDatasetIntegrityError("feature_columns.json에 중복된 컬럼명이 존재합니다.")

        return PublishedFeatureBundle(
            feature_dataset_version=feature_dataset_version,
            row_count=row_count,
            feature_count=feature_count,
            features_uri=self.get_logical_uri(bundle_dir / "features.npy"),
            labels_uri=self.get_logical_uri(bundle_dir / "labels.npy"),
            metadata_uri=self.get_logical_uri(bundle_dir / "feature_metadata.json"),
            bundle_dir=bundle_dir,
        )

    def load_bundle_data(
        self,
        dataset_id: str,
        dataset_version: str,
        feature_dataset_version: str,
    ) -> LoadedFeatureBundle | None:
        """Load full array and metadata objects for training after integrity validation."""
        bundle = self.find_feature_bundle(dataset_id, dataset_version, feature_dataset_version)
        if bundle is None:
            return None

        bundle_dir = bundle.bundle_dir
        meta_path = bundle_dir / "feature_metadata.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        features = np.load(bundle_dir / "features.npy", allow_pickle=False)
        labels = np.load(bundle_dir / "labels.npy", allow_pickle=False)

        if not np.isfinite(features).all():
            raise FeatureDatasetIntegrityError("features.npy에 NaN 또는 Inf 값이 포함되어 있습니다.")
        if features.ndim != 2:
            raise FeatureDatasetIntegrityError(f"features.npy는 2차원 배열이어야 합니다 (실제 차원: {features.ndim})")
        if labels.ndim != 1:
            raise FeatureDatasetIntegrityError(f"labels.npy는 1차원 배열이어야 합니다 (실제 차원: {labels.ndim})")

        row_count = int(features.shape[0])
        if labels.shape[0] != row_count:
            raise FeatureDatasetIntegrityError(
                f"Feature 행 수({row_count})와 Label 행 수({labels.shape[0]})가 일치하지 않습니다."
            )

        with open(bundle_dir / "feature_columns.json", "r", encoding="utf-8") as f:
            feat_cols_data = json.load(f)
            feature_columns = feat_cols_data.get("columns", [])
            if len(feature_columns) != features.shape[1]:
                raise FeatureDatasetIntegrityError(
                    f"feature_columns.json 컬럼 수({len(feature_columns)})와 features.npy 열 수({features.shape[1]})가 일치하지 않습니다."
                )

        with open(bundle_dir / "row_metadata.json", "r", encoding="utf-8") as f:
            row_meta = json.load(f)
            if not isinstance(row_meta, list):
                raise FeatureDatasetIntegrityError("row_metadata.json은 JSON 배열이어야 합니다.")
            if len(row_meta) != row_count:
                raise FeatureDatasetIntegrityError(
                    f"row_metadata.json 항목 수({len(row_meta)})와 Feature 행 수({row_count})가 일치하지 않습니다."
                )
            for index, item in enumerate(row_meta):
                if not isinstance(item, dict):
                    raise FeatureDatasetIntegrityError(
                        f"row_metadata.json의 {index}번째 항목은 JSON 객체여야 합니다."
                    )

        metadata_sha256 = compute_file_sha256(meta_path)

        return LoadedFeatureBundle(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            feature_dataset_version=feature_dataset_version,
            features=features,
            labels=labels,
            feature_columns=feature_columns,
            row_metadata=row_meta,
            feature_metadata=meta,
            feature_metadata_sha256=metadata_sha256,
            bundle_dir=bundle_dir,
        )

    def publish_bundle(
        self,
        dataset_id: str,
        dataset_version: str,
        feature_dataset_version: str,
        features: np.ndarray,
        labels: np.ndarray,
        feature_columns: list[str],
        row_metadata: list[dict[str, Any]],
        fingerprint: dict[str, Any],
        provenance_metadata: dict[str, Any],
        run_id: str,
    ) -> PublishedFeatureBundle:
        """Atomically stage, validate, and publish a 5-file immutable Feature Dataset Bundle."""
        with _bundle_lock:
            bundle_dir = self.get_bundle_dir(dataset_id, dataset_version, feature_dataset_version)
            bundle_dir.parent.mkdir(parents=True, exist_ok=True)

            # Check if bundle already exists — NEVER overwrite or delete existing bundles!
            if bundle_dir.exists():
                existing = self.find_feature_bundle(
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    feature_dataset_version=feature_dataset_version,
                    expected_fingerprint=fingerprint,
                )
                if existing is not None:
                    logger.info(f"[FeatureRepository] Existing valid immutable bundle found at {bundle_dir}, reusing.")
                    return existing

            # Pre-validation of arrays
            if not isinstance(features, np.ndarray) or not isinstance(labels, np.ndarray):
                raise FeaturePublishError("Features 및 Labels는 numpy ndarray여야 합니다.")

            if features.ndim != 2:
                raise FeatureDatasetIntegrityError(f"features는 2차원이어야 합니다: ndim={features.ndim}")

            if labels.ndim != 1:
                raise FeatureDatasetIntegrityError(f"labels는 1차원이어야 합니다: ndim={labels.ndim}")

            if not np.isfinite(features).all():
                raise FeatureDatasetIntegrityError("생성된 features.npy에 NaN 또는 Inf가 포함되어 발행이 중단되었습니다.")

            if not np.isin(labels, [0, 1]).all():
                raise FeatureDatasetIntegrityError("생성된 labels.npy의 값은 {0, 1} 이진 레이블이어야 합니다.")

            row_count = int(features.shape[0])
            feature_count = int(features.shape[1])

            if labels.shape[0] != row_count or len(row_metadata) != row_count:
                raise FeatureDatasetIntegrityError("Features, Labels, row_metadata 행 수 불일치")

            if len(feature_columns) != feature_count:
                raise FeatureDatasetIntegrityError("feature_columns 수와 Feature 열 수 불일치")

            if len(set(feature_columns)) != len(feature_columns):
                raise FeatureDatasetIntegrityError("feature_columns에 중복된 컬럼명이 존재합니다.")

            # Create temporary staging directory
            temp_dir = bundle_dir.parent / f".tmp_{uuid.uuid4().hex}_{feature_dataset_version}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                # 1. Save features.npy
                features_path = temp_dir / "features.npy"
                np.save(features_path, features.astype(np.float64), allow_pickle=False)
                features_sha = compute_file_sha256(features_path)

                # 2. Save labels.npy
                labels_path = temp_dir / "labels.npy"
                np.save(labels_path, labels.astype(np.int64), allow_pickle=False)
                labels_sha = compute_file_sha256(labels_path)

                # 3. Save feature_columns.json
                columns_path = temp_dir / "feature_columns.json"
                columns_payload = {
                    "columns": feature_columns,
                    "count": feature_count,
                }
                with open(columns_path, "w", encoding="utf-8") as f:
                    json.dump(columns_payload, f, ensure_ascii=False, indent=2)
                columns_sha = compute_file_sha256(columns_path)

                # 4. Save row_metadata.json
                row_meta_path = temp_dir / "row_metadata.json"
                with open(row_meta_path, "w", encoding="utf-8") as f:
                    json.dump(row_metadata, f, ensure_ascii=False, indent=2)
                row_meta_sha = compute_file_sha256(row_meta_path)

                # Calculate class distribution
                pos_count = int(np.sum(labels == 1))
                neg_count = int(np.sum(labels == 0))
                class_distribution = {
                    "positive_count": pos_count,
                    "negative_count": neg_count,
                    "positive_rate": float(pos_count / row_count) if row_count > 0 else 0.0,
                }

                # 5. Save feature_metadata.json (no self-referential checksum)
                full_metadata = {
                    "feature_dataset_version": feature_dataset_version,
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "run_id": run_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "row_count": row_count,
                    "feature_count": feature_count,
                    "class_distribution": class_distribution,
                    "fingerprint": fingerprint,
                    "provenance": provenance_metadata,
                    "payload_checksums": {
                        "features.npy": features_sha,
                        "labels.npy": labels_sha,
                        "feature_columns.json": columns_sha,
                        "row_metadata.json": row_meta_sha,
                    },
                }
                meta_path = temp_dir / "feature_metadata.json"
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(full_metadata, f, ensure_ascii=False, indent=2)

                # Atomic rename staging directory to final target bundle_dir
                if bundle_dir.exists():
                    # Double-check: if already created concurrently, reuse and discard staging
                    existing = self.find_feature_bundle(dataset_id, dataset_version, feature_dataset_version, fingerprint)
                    if existing is not None:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return existing

                try:
                    temp_dir.replace(bundle_dir)
                except OSError:
                    if bundle_dir.exists():
                        shutil.rmtree(bundle_dir, ignore_errors=True)
                    shutil.move(str(temp_dir), str(bundle_dir))
                logger.info(f"[FeatureRepository] Atomically published Feature Bundle to {bundle_dir}")

                return PublishedFeatureBundle(
                    feature_dataset_version=feature_dataset_version,
                    row_count=row_count,
                    feature_count=feature_count,
                    features_uri=self.get_logical_uri(bundle_dir / "features.npy"),
                    labels_uri=self.get_logical_uri(bundle_dir / "labels.npy"),
                    metadata_uri=self.get_logical_uri(bundle_dir / "feature_metadata.json"),
                    bundle_dir=bundle_dir,
                )
            except Exception as exc:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                if isinstance(exc, (FeatureDatasetIntegrityError, FeaturePublishConflictError)):
                    raise
                logger.exception(f"[FeatureRepository] Failed to publish bundle: {exc}")
                raise FeaturePublishError(f"Feature Dataset Bundle 발행에 실패했습니다: {exc}") from exc
