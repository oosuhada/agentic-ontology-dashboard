"""Deterministic asset-time dataset splitting for predictive maintenance."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
import numpy as np

from systems.generator.app.training.training_exception import TrainingDatasetError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetSplits:
    """Container for split feature matrices and labels."""
    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    train_indices: list[int]
    val_indices: list[int]
    test_indices: list[int]
    summary: dict[str, Any]


def _parse_timestamp(val: Any) -> float:
    """Parse various timestamp formats (including ISO datetime, unix epoch, and synthetic step strings)."""
    if isinstance(val, bool):
        raise TrainingDatasetError(f"timestamp는 bool 값을 사용할 수 없습니다: {val!r}")

    parsed: float | None = None
    if isinstance(val, (int, float)):
        parsed = float(val)
    elif isinstance(val, str):
        # Try ISO format
        try:
            parsed = datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp()
        except ValueError:
            parsed = None

        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(val, fmt).timestamp()
                    break
                except ValueError:
                    pass

        if parsed is None and (val.startswith("t_") or val.startswith("step_") or val.startswith("row_")):
            try:
                parsed = float(val.split("_", 1)[1])
            except ValueError:
                pass

        if parsed is None:
            try:
                parsed = float(val)
            except ValueError:
                raise TrainingDatasetError(f"타임스탬프 '{val}'를 시간 객체로 변환할 수 없습니다.")
    else:
        raise TrainingDatasetError(f"타임스탬프 '{val}'는 유효한 타입이 아닙니다 ({type(val).__name__}).")

    if not math.isfinite(parsed):
        raise TrainingDatasetError(f"timestamp는 유한한 값이어야 합니다: {val!r}")

    return parsed


def asset_time_split(
    features: np.ndarray,
    labels: np.ndarray,
    row_metadata: list[dict[str, Any]],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    min_samples: int = 10,
) -> DatasetSplits:
    """Split dataset by asset and time without future leakage across boundaries."""
    total_rows = len(labels)
    if total_rows < min_samples:
        raise TrainingDatasetError(
            f"학습 가능한 데이터셋 행 수({total_rows})가 최소 요구치({min_samples}) 미만입니다."
        )

    unique_classes = set(np.unique(labels))
    if len(unique_classes) < 2:
        raise TrainingDatasetError(
            f"데이터셋에 최소 2개 이상의 클래스가 존재해야 합니다 (현재 클래스: {unique_classes})."
        )

    if not isinstance(row_metadata, list):
        raise TrainingDatasetError("row_metadata는 리스트 형태여야 합니다.")

    if len(row_metadata) != total_rows:
        raise TrainingDatasetError(
            f"row_metadata 항목 수({len(row_metadata)})와 Label 행 수({total_rows})가 일치하지 않습니다."
        )

    # Group row indices by asset_id
    asset_groups: dict[str, list[tuple[int, float]]] = {}
    for idx, meta in enumerate(row_metadata):
        if not isinstance(meta, dict):
            raise TrainingDatasetError(f"row_metadata {idx}번째 항목은 딕셔너리여야 합니다.")

        raw_asset = meta.get("asset_id")
        if raw_asset is None or isinstance(raw_asset, bool) or not isinstance(raw_asset, (str, int)) or str(raw_asset).strip() == "":
            raise TrainingDatasetError(f"row_metadata {idx}번째 행에 유효한 asset_id가 누락되었습니다.")
        asset_id = str(raw_asset).strip()

        raw_ts = meta.get("timestamp")
        if raw_ts is None or (isinstance(raw_ts, str) and raw_ts.strip() == ""):
            raise TrainingDatasetError(f"row_metadata {idx}번째 행에 유효한 timestamp가 누락되었습니다.")
        ts = _parse_timestamp(raw_ts)

        if asset_id not in asset_groups:
            asset_groups[asset_id] = []
        asset_groups[asset_id].append((idx, ts))

    train_indices: list[int] = []
    val_indices: list[int] = []
    test_indices: list[int] = []

    # Sort each asset group by timestamp
    for asset_id, items in sorted(asset_groups.items(), key=lambda x: x[0]):
        items_sorted = sorted(items, key=lambda x: x[1])
        n_items = len(items_sorted)

        if n_items == 1:
            train_indices.append(items_sorted[0][0])
            continue

        n_train = max(1, int(round(n_items * train_ratio)))
        n_val = int(round(n_items * val_ratio))
        if n_train + n_val >= n_items and n_items > 2:
            n_train = n_items - 2
            n_val = 1

        train_slice = items_sorted[:n_train]
        val_slice = items_sorted[n_train : n_train + n_val]
        test_slice = items_sorted[n_train + n_val :]

        for idx, _ in train_slice:
            train_indices.append(idx)
        for idx, _ in val_slice:
            val_indices.append(idx)
        for idx, _ in test_slice:
            test_indices.append(idx)

    # Fallback if val or test ended up empty
    if not val_indices and len(train_indices) > 2:
        val_indices.append(train_indices.pop())
    if not test_indices and len(train_indices) > 2:
        test_indices.append(train_indices.pop())

    train_indices.sort()
    val_indices.sort()
    test_indices.sort()

    X_train = features[train_indices]
    y_train = labels[train_indices]

    if len(np.unique(y_train)) < 2:
        raise TrainingDatasetError(
            "시간 분할 후 train partition에 두 클래스가 모두 존재하지 않습니다."
        )

    X_val = features[val_indices] if val_indices else X_train[:0]
    y_val = labels[val_indices] if val_indices else y_train[:0]

    X_test = features[test_indices] if test_indices else X_train[:0]
    y_test = labels[test_indices] if test_indices else y_train[:0]

    def _calc_distribution(y_arr: np.ndarray) -> dict[str, Any]:
        count = len(y_arr)
        if count == 0:
            return {"row_count": 0, "positive_count": 0, "negative_count": 0, "positive_ratio": 0.0}
        pos = int(np.sum(y_arr == 1))
        neg = int(np.sum(y_arr == 0))
        return {
            "row_count": count,
            "positive_count": pos,
            "negative_count": neg,
            "positive_ratio": float(pos / count) if count > 0 else 0.0,
        }

    summary = {
        "strategy": "asset_time_split",
        "asset_count": len(asset_groups),
        "total_rows": total_rows,
        "train": _calc_distribution(y_train),
        "val": _calc_distribution(y_val),
        "test": _calc_distribution(y_test),
    }

    return DatasetSplits(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        train_indices=train_indices,
        val_indices=val_indices,
        test_indices=test_indices,
        summary=summary,
    )
