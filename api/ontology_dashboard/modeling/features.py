from __future__ import annotations

import json
import math
import uuid
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import numpy as np
import pandas as pd

from .artifacts import LocalArtifactStore
from .models import (
    FeatureDatasetVersion,
    FeatureRecipe,
    FeatureRecipeSet,
    LabelPolicy,
    MappingSet,
    RunStatus,
    canonical_checksum,
)

FEATURE_ENGINE_VERSION = "ontology-feature-engine-v1"
FEATURE_PREFIX = "feature__"
ALLOWED_DERIVED_INPUTS: dict[str, tuple[str, ...]] = {
    "power_w": ("torque_nm", "rotational_speed_rpm"),
    "temperature_gap_k": ("process_temperature_k", "air_temperature_k"),
    "overstrain_load": ("tool_wear_min", "torque_nm"),
}


@dataclass(frozen=True)
class FeatureMaterializationResult:
    dataset_version: FeatureDatasetVersion
    rows: list[dict[str, Any]]


def validate_recipe(recipe: FeatureRecipe, available_properties: set[str]) -> None:
    if recipe.group_by not in available_properties:
        raise ValueError(f"recipe group_by is not approved in Mapping Set: {recipe.group_by}")
    if recipe.order_by not in available_properties:
        raise ValueError(f"recipe order_by is not approved in Mapping Set: {recipe.order_by}")
    if recipe.operation in ALLOWED_DERIVED_INPUTS:
        missing = [item for item in ALLOWED_DERIVED_INPUTS[recipe.operation] if item not in available_properties]
        if missing:
            raise ValueError(f"derived recipe missing approved inputs: {', '.join(missing)}")
    elif recipe.ontology_property not in available_properties:
        raise ValueError(
            f"recipe ontology_property is not approved in Mapping Set: {recipe.ontology_property}"
        )
    expected = canonical_checksum(
        {
            "recipe_id": recipe.recipe_id,
            "version": recipe.version,
            "ontology_property": recipe.ontology_property,
            "operation": recipe.operation,
            "parameters": recipe.parameters,
            "group_by": recipe.group_by,
            "order_by": recipe.order_by,
            "minimum_history": recipe.minimum_history,
            "null_policy": recipe.null_policy,
            "boundary_policy": recipe.boundary_policy,
            "source_grain": recipe.source_grain,
            "output_datatype": recipe.output_datatype,
            "output_unit": recipe.output_unit,
            "leakage_policy": recipe.leakage_policy,
            "status": recipe.status,
        }
    )
    if recipe.checksum_sha256 != expected:
        raise ValueError(f"recipe checksum mismatch: {recipe.recipe_id}")


def validate_label_policy(policy: LabelPolicy, available_properties: set[str]) -> None:
    if policy.observation_time_field not in available_properties:
        raise ValueError("Label Policy observation_time_field is not approved")
    if policy.target_source not in available_properties:
        raise ValueError("Label Policy target_source is not approved")
    forbidden = {item.lower() for item in policy.forbidden_sources}
    if "evaluation_truth" not in forbidden or "hidden_truth" not in forbidden:
        raise ValueError("Label Policy must forbid evaluation_truth and hidden_truth")
    if policy.target_source.lower() in forbidden:
        raise ValueError("Label Policy cannot use evaluator-only truth sources")


def approved_property_mapping(mapping_set: MappingSet) -> dict[str, str]:
    if str(mapping_set.status) != "approved":
        raise ValueError("Feature Recipe Set requires an approved Mapping Set")
    # Work from a serialized snapshot. This keeps the validation/materialization
    # boundary pure even when nested Pydantic objects are reused by callers.
    payload = mapping_set.model_dump(mode="json")
    mapping: dict[str, str] = {}
    for candidate in payload["candidates"]:
        if candidate["status"] != "approved" or candidate["target_property"] is None:
            continue
        target_property = str(candidate["target_property"])
        source_field = str(candidate["source_field"])
        if target_property in mapping.values():
            raise ValueError(f"multiple source fields map to {target_property}")
        mapping[source_field] = target_property
    return mapping


def validate_recipe_set(recipe_set: FeatureRecipeSet, mapping_set: MappingSet) -> dict[str, Any]:
    # Validation must never mutate governed Mapping/Recipe objects. Pydantic models
    # can carry nested mutable containers, so validate against defensive deep copies.
    mapping_snapshot = mapping_set.model_copy(deep=True)
    recipe_snapshot = recipe_set.model_copy(deep=True)
    source_mapping = approved_property_mapping(mapping_snapshot)
    available = set(source_mapping.values())
    for recipe in recipe_snapshot.recipes:
        validate_recipe(recipe, available)
    validate_label_policy(recipe_snapshot.label_policy, available)
    if not recipe_snapshot.recipes:
        raise ValueError("Feature Recipe Set requires at least one recipe")
    return {
        "valid": True,
        "approved_source_fields": source_mapping,
        "mapping_set_checksum_sha256": mapping_set.checksum_sha256,
        "recipe_count": len(recipe_snapshot.recipes),
        "feature_engine_version": FEATURE_ENGINE_VERSION,
        "future_feature_access": False,
        "group_boundary_reset": True,
        "forbidden_sources": recipe_snapshot.label_policy.forbidden_sources,
    }


def _read_profile_source(source_uri: str, *, delimiter: str | None = None) -> pd.DataFrame:
    parsed = urlparse(source_uri)
    if parsed.scheme != "file":
        raise ValueError("local feature materialization currently requires a file:// intake source")
    path = Path(unquote(parsed.path)).resolve(strict=True)
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        resolved_delimiter = delimiter
        if resolved_delimiter is None:
            sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
            try:
                resolved_delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
            except csv.Error:
                resolved_delimiter = "\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=resolved_delimiter)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path)
    raise ValueError(f"unsupported feature source: {suffix}")


def canonicalize_frame(
    frame: pd.DataFrame,
    mapping_set: MappingSet | None = None,
    *,
    source_mapping: dict[str, str] | None = None,
) -> pd.DataFrame:
    resolved_mapping = source_mapping or (
        approved_property_mapping(mapping_set) if mapping_set is not None else None
    )
    if not resolved_mapping:
        raise ValueError("canonicalization requires an approved source mapping")
    missing = sorted(set(resolved_mapping) - set(frame.columns))
    if missing:
        raise ValueError(f"feature source is missing mapped fields: {', '.join(missing)}")
    canonical = frame[list(resolved_mapping)].rename(columns=resolved_mapping).copy(deep=True)
    return canonical


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _apply_group_recipe(group: pd.DataFrame, recipe: FeatureRecipe) -> pd.Series:
    operation = recipe.operation
    if operation == "identity":
        return group[recipe.ontology_property]
    if operation == "power_w":
        return _numeric(group["torque_nm"]) * _numeric(group["rotational_speed_rpm"]) * 2 * math.pi / 60
    if operation == "temperature_gap_k":
        return _numeric(group["process_temperature_k"]) - _numeric(group["air_temperature_k"])
    if operation == "overstrain_load":
        return _numeric(group["tool_wear_min"]) * _numeric(group["torque_nm"])
    values = _numeric(group[recipe.ontology_property])
    window = int(recipe.parameters.get("window", recipe.minimum_history))
    min_periods = int(recipe.parameters.get("min_periods", recipe.minimum_history))
    if operation in {"rolling_mean", "moving_average"}:
        result = values.rolling(window=window, min_periods=min_periods).mean()
    elif operation == "rolling_std":
        result = values.rolling(window=window, min_periods=min_periods).std(ddof=0)
    elif operation == "lag":
        result = values.shift(int(recipe.parameters.get("periods", 1)))
    elif operation == "diff":
        result = values.diff(int(recipe.parameters.get("periods", 1)))
    elif operation == "gradient":
        result = values.diff(1)
    elif operation == "ema":
        result = values.ewm(
            span=int(recipe.parameters.get("span", 10)),
            adjust=False,
            min_periods=min_periods,
        ).mean()
    else:
        raise ValueError(f"unsupported feature operation: {operation}")
    if recipe.null_policy == "fill_zero":
        result = result.fillna(0)
    return result


def transform_frame(
    canonical: pd.DataFrame,
    recipe_set: FeatureRecipeSet,
    *,
    include_label: bool,
) -> pd.DataFrame:
    frame = canonical.copy(deep=True)
    order_fields = {recipe.order_by for recipe in recipe_set.recipes}
    group_fields = {recipe.group_by for recipe in recipe_set.recipes}
    if len(order_fields) != 1 or len(group_fields) != 1:
        raise ValueError("all recipes in a set must share one group_by and order_by")
    group_by = next(iter(group_fields))
    order_by = next(iter(order_fields))
    frame[order_by] = pd.to_datetime(frame[order_by], utc=True, errors="raise")
    frame["__source_position"] = np.arange(len(frame))
    frame = frame.sort_values([group_by, order_by, "__source_position"], kind="mergesort").reset_index(drop=True)

    for recipe in recipe_set.recipes:
        feature_name = f"{FEATURE_PREFIX}{recipe.recipe_id}"
        frame[feature_name] = frame.groupby(group_by, sort=False, group_keys=False).apply(
            lambda group: _apply_group_recipe(group, recipe),
            include_groups=False,
        ).reset_index(level=0, drop=True)
        if recipe.null_policy == "drop":
            frame = frame.loc[frame[feature_name].notna()].copy()

    if include_label:
        frame["label"] = build_horizon_label(frame, recipe_set.label_policy, group_by=group_by)
    return frame.drop(columns=["__source_position"])


def build_horizon_label(frame: pd.DataFrame, policy: LabelPolicy, *, group_by: str) -> pd.Series:
    time_field = policy.observation_time_field
    target = pd.to_numeric(frame[policy.target_source], errors="coerce").fillna(0).astype(int)
    result = pd.Series(0, index=frame.index, dtype="int64")
    horizon = pd.Timedelta(hours=policy.horizon_hours)
    lookback = pd.Timedelta(hours=policy.lookback_hours)
    for _, group in frame.groupby(group_by, sort=False):
        # Pandas 3 may preserve microsecond precision for parsed timestamps while
        # ``Timestamp.value`` is always expressed in nanoseconds. Normalize the
        # search index explicitly so horizon labels are independent of the input
        # datetime resolution.
        times = (
            pd.to_datetime(group[time_field], utc=True)
            .astype("datetime64[ns, UTC]")
            .astype("int64")
            .to_numpy()
        )
        labels = target.loc[group.index].to_numpy()
        for offset, row_index in enumerate(group.index):
            lower_time = pd.Timestamp(group.iloc[offset][time_field]) + lookback
            upper_time = pd.Timestamp(group.iloc[offset][time_field]) + horizon
            lower = int(np.searchsorted(times, lower_time.value, side="left"))
            upper = int(np.searchsorted(times, upper_time.value, side="right"))
            if upper > lower:
                result.loc[row_index] = int(labels[lower:upper].max())
    return result


def materialize_feature_dataset(
    *,
    source_frame: pd.DataFrame,
    mapping_set: MappingSet,
    recipe_set: FeatureRecipeSet,
    artifact_store: LocalArtifactStore,
    idempotency_key: str,
    approved_source_mapping: dict[str, str] | None = None,
) -> FeatureMaterializationResult:
    if str(mapping_set.status) != "approved":
        raise ValueError("Feature materialization requires an approved Mapping Set")
    validation = dict(recipe_set.validation_report)
    if approved_source_mapping is None:
        validation = validate_recipe_set(recipe_set, mapping_set)
        approved_source_mapping = validation["approved_source_fields"]
    elif validation.get("mapping_set_checksum_sha256") != mapping_set.checksum_sha256:
        raise ValueError("Feature Recipe Set Mapping checksum no longer matches")
    available = set(approved_source_mapping.values())
    for recipe in recipe_set.recipes:
        validate_recipe(recipe, available)
    validate_label_policy(recipe_set.label_policy, available)
    canonical = canonicalize_frame(source_frame, source_mapping=approved_source_mapping)
    transformed = transform_frame(canonical, recipe_set, include_label=True)
    payload = transformed.to_json(orient="records", lines=True, date_format="iso").encode("utf-8")
    materialization_checksum = canonical_checksum(
        {
            "dataset_version_id": recipe_set.dataset_version_id,
            "mapping_set_checksum": mapping_set.checksum_sha256,
            "recipe_set_checksum": recipe_set.checksum_sha256,
            "row_payload_sha256": __import__("hashlib").sha256(payload).hexdigest(),
            "feature_engine_version": FEATURE_ENGINE_VERSION,
        }
    )
    feature_dataset_version_id = (
        "feature-dataset-"
        + str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{recipe_set.recipe_set_id}:{materialization_checksum}",
            )
        )
    )
    artifact = artifact_store.put_bytes(
        f"feature-datasets/{feature_dataset_version_id}.jsonl",
        payload,
        "application/x-ndjson",
    )
    group_by = recipe_set.recipes[0].group_by
    order_by = recipe_set.recipes[0].order_by
    dataset_version = FeatureDatasetVersion(
        organization_id=recipe_set.organization_id,
        project_id=recipe_set.project_id,
        workspace_id=recipe_set.workspace_id,
        feature_dataset_version_id=feature_dataset_version_id,
        dataset_version_id=recipe_set.dataset_version_id,
        mapping_set_id=mapping_set.mapping_set_id,
        recipe_set_id=recipe_set.recipe_set_id,
        label_policy_id=recipe_set.label_policy.label_policy_id,
        materialization_checksum_sha256=materialization_checksum,
        status=RunStatus.SUCCEEDED,
        row_count=len(transformed),
        feature_count=len([column for column in transformed.columns if column.startswith(FEATURE_PREFIX)]),
        equipment_count=int(transformed[group_by].nunique()),
        time_start=transformed[order_by].min().to_pydatetime() if len(transformed) else None,
        time_end=transformed[order_by].max().to_pydatetime() if len(transformed) else None,
        artifact=artifact,
        schema_metadata={
            "feature_engine_version": FEATURE_ENGINE_VERSION,
            "columns": [
                {"name": column, "dtype": str(transformed[column].dtype)}
                for column in transformed.columns
            ],
            "validation": validation,
            "source_dataset_mutated": False,
            "training_inference_transform_shared": True,
            "group_by": group_by,
            "order_by": order_by,
            "label_column": "label",
        },
        idempotency_key=idempotency_key,
    )
    rows = json.loads(transformed.to_json(orient="records", date_format="iso"))
    return FeatureMaterializationResult(dataset_version=dataset_version, rows=rows)


def read_source_for_profile(source_uri: str, parser_metadata: dict[str, Any]) -> pd.DataFrame:
    return _read_profile_source(source_uri, delimiter=parser_metadata.get("delimiter"))


__all__ = [
    "ALLOWED_DERIVED_INPUTS",
    "FEATURE_ENGINE_VERSION",
    "FEATURE_PREFIX",
    "FeatureMaterializationResult",
    "approved_property_mapping",
    "canonicalize_frame",
    "materialize_feature_dataset",
    "read_source_for_profile",
    "transform_frame",
    "validate_recipe",
    "validate_recipe_set",
]
