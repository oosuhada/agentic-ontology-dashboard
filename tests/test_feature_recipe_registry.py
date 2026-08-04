from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.artifacts import LocalArtifactStore
from ontology_dashboard.modeling.features import (
    FEATURE_PREFIX,
    canonicalize_frame,
    materialize_feature_dataset,
    transform_frame,
    validate_recipe_set,
)
from ontology_dashboard.modeling.intake import DatasetIntakeProfiler, sha256_file
from ontology_dashboard.modeling.models import (
    FeatureMaterializationRequest,
    FeatureRecipe,
    FeatureRecipeSet,
    FeatureRecipeSetCreateRequest,
    FeatureRecipeSetDecisionRequest,
    LabelPolicy,
    MappingEvidence,
    MappingSet,
    OntologyMappingCandidate,
    canonical_checksum,
)
from ontology_dashboard.modeling.repository import ModelingRepository
from ontology_dashboard.modeling.service import ModelingService


def recipe_checksum(**values) -> str:
    payload = {
        "recipe_id": values["recipe_id"],
        "version": values.get("version", 1),
        "ontology_property": values["ontology_property"],
        "operation": values["operation"],
        "parameters": values.get("parameters", {}),
        "group_by": values.get("group_by", "equipment_id"),
        "order_by": values.get("order_by", "observed_at"),
        "minimum_history": values.get("minimum_history", 1),
        "null_policy": values.get("null_policy", "preserve"),
        "boundary_policy": "reset_per_group",
        "source_grain": values.get("source_grain", "observation"),
        "output_datatype": values.get("output_datatype", "number"),
        "output_unit": values.get("output_unit"),
        "leakage_policy": "past_and_present_only",
        "status": "enabled",
    }
    return canonical_checksum(payload)


def recipe(recipe_id: str, operation: str, ontology_property: str, **kwargs) -> FeatureRecipe:
    values = {
        "recipe_id": recipe_id,
        "version": 1,
        "operation": operation,
        "ontology_property": ontology_property,
        "group_by": "equipment_id",
        "order_by": "observed_at",
        "source_grain": "observation",
        "output_datatype": "number",
        **kwargs,
    }
    return FeatureRecipe(checksum_sha256=recipe_checksum(**values), **values)


def approved_mapping_set() -> MappingSet:
    mapping = {
        "machine_id": ("equipment_id", "string", None, "identifier", True),
        "timestamp": ("observed_at", "datetime", None, "timestamp", False),
        "voltage": ("voltage_v", "number", "V", "measure", False),
        "rpm": ("rotational_speed_rpm", "number", "rpm", "measure", False),
        "torque": ("torque_nm", "number", "N·m", "measure", False),
        "air_temp": ("air_temperature_k", "number", "K", "measure", False),
        "process_temp": ("process_temperature_k", "number", "K", "measure", False),
        "wear": ("tool_wear_min", "number", "minute", "measure", False),
        "failure": ("machine_failure", "boolean", None, "status", False),
    }
    candidates = []
    for source, (target, datatype, unit, role, group_key) in mapping.items():
        candidates.append(
            OntologyMappingCandidate(
                candidate_id=f"candidate-{source}",
                source_field=source,
                target_object_type="telemetry_observation",
                target_property=target,
                datatype=datatype,
                physical_unit=unit,
                grain="observation",
                semantic_role=role,
                group_key=group_key,
                join_key=group_key,
                critical_field=target in {"equipment_id", "observed_at", "machine_failure"},
                confidence=1.0,
                evidences=[
                    MappingEvidence(
                        source="user_confirmation",
                        detail="approved for feature test",
                        score=1.0,
                    )
                ],
                status="approved",
            )
        )
    checksum = canonical_checksum([item.model_dump(mode="json") for item in candidates])
    return MappingSet(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        mapping_set_id="mapping-approved",
        dataset_version_id="dataset-v1",
        version=1,
        checksum_sha256=checksum,
        status="approved",
        candidates=candidates,
        approved_by="user-fde",
        idempotency_key="mapping-approved",
    )


def label_policy() -> LabelPolicy:
    return LabelPolicy(
        label_policy_id="label-policy-v1",
        version=1,
        horizon_hours=1,
        lookback_hours=0,
        embargo_hours=0.5,
        event_time_field="observed_at",
        observation_time_field="observed_at",
        target_source="machine_failure",
        overlapping_window_policy="nearest_event",
    )


def recipe_set(status: str = "approved") -> FeatureRecipeSet:
    recipes = [
        recipe(
            "voltage-mean-2",
            "rolling_mean",
            "voltage_v",
            parameters={"window": 2, "min_periods": 1},
            output_unit="V",
        ),
        recipe("voltage-lag-1", "lag", "voltage_v", parameters={"periods": 1}),
        recipe("power", "power_w", "torque_nm", output_unit="W"),
        recipe("temperature-gap", "temperature_gap_k", "process_temperature_k", output_unit="K"),
        recipe("overstrain", "overstrain_load", "tool_wear_min", output_unit="min·N·m"),
    ]
    checksum = canonical_checksum(
        {
            "dataset_version_id": "dataset-v1",
            "mapping_set_id": "mapping-approved",
            "recipes": [item.model_dump(mode="json") for item in recipes],
            "label_policy": label_policy().model_dump(mode="json"),
        }
    )
    return FeatureRecipeSet(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        recipe_set_id="recipe-set-v1",
        dataset_version_id="dataset-v1",
        mapping_set_id="mapping-approved",
        version=1,
        checksum_sha256=checksum,
        status=status,
        recipes=recipes,
        label_policy=label_policy(),
        validation_report={},
        idempotency_key="recipe-set-v1",
    )


def source_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"machine_id": "M-2", "timestamp": "2026-01-01T00:00:00Z", "voltage": 100, "rpm": 1000, "torque": 20, "air_temp": 300, "process_temp": 309, "wear": 5, "failure": 0},
            {"machine_id": "M-1", "timestamp": "2026-01-01T00:10:00Z", "voltage": 20, "rpm": 1500, "torque": 30, "air_temp": 300, "process_temp": 311, "wear": 11, "failure": 0},
            {"machine_id": "M-1", "timestamp": "2026-01-01T00:00:00Z", "voltage": 10, "rpm": 1400, "torque": 25, "air_temp": 300, "process_temp": 310, "wear": 10, "failure": 0},
            {"machine_id": "M-2", "timestamp": "2026-01-01T00:10:00Z", "voltage": 200, "rpm": 1100, "torque": 22, "air_temp": 301, "process_temp": 312, "wear": 6, "failure": 1},
            {"machine_id": "M-1", "timestamp": "2026-01-01T00:40:00Z", "voltage": 30, "rpm": 1600, "torque": 35, "air_temp": 302, "process_temp": 314, "wear": 12, "failure": 1},
        ]
    )


def test_grouped_rolling_lag_and_ordering_do_not_cross_equipment_boundaries() -> None:
    mapping = approved_mapping_set()
    recipes = recipe_set()
    canonical = canonicalize_frame(source_frame(), mapping)
    transformed = transform_frame(canonical, recipes, include_label=True)
    mean = f"{FEATURE_PREFIX}voltage-mean-2"
    lag = f"{FEATURE_PREFIX}voltage-lag-1"
    m1 = transformed[transformed.equipment_id == "M-1"].reset_index(drop=True)
    m2 = transformed[transformed.equipment_id == "M-2"].reset_index(drop=True)
    assert m1.voltage_v.tolist() == [10, 20, 30]
    assert m1[mean].tolist() == [10, 15, 25]
    assert pd.isna(m1.loc[0, lag])
    assert m1.loc[1, lag] == 10
    assert m2[mean].tolist() == [100, 150]
    assert pd.isna(m2.loc[0, lag])
    assert m2.loc[1, lag] == 100


def test_future_rows_do_not_change_past_feature_values() -> None:
    mapping = approved_mapping_set()
    recipes = recipe_set()
    frame = source_frame()
    historical = frame[frame["timestamp"] <= "2026-01-01T00:10:00Z"].copy()
    past = transform_frame(canonicalize_frame(historical, mapping), recipes, include_label=False)
    full = transform_frame(canonicalize_frame(frame, mapping), recipes, include_label=False)
    feature_columns = [column for column in full.columns if column.startswith(FEATURE_PREFIX)]
    comparison = full[full.observed_at <= pd.Timestamp("2026-01-01T00:10:00Z")]
    pd.testing.assert_frame_equal(
        past[["equipment_id", "observed_at", *feature_columns]].reset_index(drop=True),
        comparison[["equipment_id", "observed_at", *feature_columns]].reset_index(drop=True),
    )


def test_allowlisted_physical_formulas_and_horizon_label_are_reproducible() -> None:
    transformed = transform_frame(
        canonicalize_frame(source_frame(), approved_mapping_set()),
        recipe_set(),
        include_label=True,
    )
    row = transformed[(transformed.equipment_id == "M-1") & (transformed.voltage_v == 10)].iloc[0]
    assert row[f"{FEATURE_PREFIX}power"] == pytest.approx(25 * 1400 * 2 * 3.141592653589793 / 60)
    assert row[f"{FEATURE_PREFIX}temperature-gap"] == pytest.approx(10)
    assert row[f"{FEATURE_PREFIX}overstrain"] == pytest.approx(250)
    # M-1 fails 40 minutes later, inside the one-hour horizon.
    assert row["label"] == 1


def test_recipe_and_label_guards_reject_unapproved_or_evaluator_truth_inputs() -> None:
    mapping = approved_mapping_set()
    invalid_mapping = mapping.model_copy(update={"status": "draft"})
    with pytest.raises(ValueError, match="approved Mapping Set"):
        validate_recipe_set(recipe_set(), invalid_mapping)
    invalid_policy = label_policy().model_copy(update={"target_source": "evaluation_truth"})
    invalid_set = recipe_set().model_copy(update={"label_policy": invalid_policy})
    with pytest.raises(ValueError, match="not approved|evaluator-only"):
        validate_recipe_set(invalid_set, mapping)
    bad_recipe = recipe(
        "unknown",
        "rolling_mean",
        "unknown_measure",
        parameters={"window": 2},
    )
    with pytest.raises(ValueError, match="not approved"):
        validate_recipe_set(recipe_set().model_copy(update={"recipes": [bad_recipe]}), mapping)


def test_recipe_validation_does_not_mutate_mapping_or_recipe_contracts() -> None:
    mapping = approved_mapping_set()
    recipes = recipe_set()
    mapping_before = mapping.model_dump(mode="json")
    recipes_before = recipes.model_dump(mode="json")
    assert validate_recipe_set(recipes, mapping)["valid"] is True
    assert mapping.model_dump(mode="json") == mapping_before
    assert recipes.model_dump(mode="json") == recipes_before


def test_feature_dataset_artifact_identity_and_source_immutability(tmp_path: Path) -> None:
    source = source_frame()
    source_before = source.copy(deep=True)
    store = LocalArtifactStore(tmp_path / "artifacts")
    result = materialize_feature_dataset(
        source_frame=source,
        mapping_set=approved_mapping_set(),
        recipe_set=recipe_set(),
        artifact_store=store,
        idempotency_key="materialize-v1",
    )
    pd.testing.assert_frame_equal(source, source_before)
    assert result.dataset_version.status == "succeeded"
    assert result.dataset_version.row_count == len(source)
    assert result.dataset_version.feature_count == 5
    assert result.dataset_version.equipment_count == 2
    assert result.dataset_version.artifact is not None
    assert result.dataset_version.artifact.uri.startswith("artifact://feature-datasets/")
    artifact_bytes = store.read_bytes(result.dataset_version.artifact)
    assert hashlib.sha256(artifact_bytes).hexdigest() == result.dataset_version.artifact.checksum_sha256
    assert result.dataset_version.schema_metadata["source_dataset_mutated"] is False
    assert result.dataset_version.schema_metadata["training_inference_transform_shared"] is True


def test_repository_recipe_insert_does_not_overwrite_mapping_payload(tmp_path: Path) -> None:
    database = tmp_path / "repository-purity.db"
    migrate(str(database))
    repository = ModelingRepository(database)
    mapping = approved_mapping_set()
    mapping_payload = mapping.model_dump(mode="json")
    repository.put("mapping_set", mapping_payload, idempotency_key="mapping-purity")
    recipes = recipe_set(status="draft")
    repository.put(
        "recipe_set",
        recipes.model_dump(mode="json"),
        idempotency_key="recipe-purity",
    )
    loaded = repository.get(
        "mapping_set",
        mapping.mapping_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    )
    assert loaded == mapping_payload


def test_service_requires_approved_recipe_set_and_persists_immutable_feature_version(tmp_path: Path) -> None:
    source_path = tmp_path / "sources" / "telemetry.csv"
    source_path.parent.mkdir(parents=True)
    source_frame().to_csv(source_path, index=False)
    source_checksum = sha256_file(source_path)
    database = tmp_path / "service.db"
    migrate(str(database))
    repository = ModelingRepository(database)
    modeling = ModelingService(
        repository,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        intake_profiler=DatasetIntakeProfiler([source_path.parent]),
    )
    profile = modeling.profile_source(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        source_path=str(source_path),
        sheet=None,
        use_llm=False,
        idempotency_key="profile-feature",
        actor_id="user-fde",
    )
    mapping = approved_mapping_set()
    repository.put("mapping_set", mapping.model_dump(mode="json"), idempotency_key=mapping.idempotency_key)
    requested = recipe_set(status="draft")
    created = modeling.create_feature_recipe_set(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=FeatureRecipeSetCreateRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            dataset_version_id="dataset-v1",
            mapping_set_id=mapping.mapping_set_id,
            recipes=requested.recipes,
            label_policy=requested.label_policy,
            idempotency_key="recipe-service",
        ),
        actor_id="user-fde",
    )
    with pytest.raises(ValueError, match="approved Feature Recipe Set"):
        modeling.materialize_features(
            organization_id="org-a",
            project_id="project-a",
            workspace_id="workspace-a",
            request=FeatureMaterializationRequest(
                project_id="project-a",
                workspace_id="workspace-a",
                profile_id=profile.profile_id,
                recipe_set_id=created.recipe_set_id,
                idempotency_key="feature-service",
            ),
            actor_id="user-fde",
        )
    approved = modeling.decide_feature_recipe_set(
        created.recipe_set_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=FeatureRecipeSetDecisionRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            expected_revision=1,
            decision="approve",
            rationale="recipes validated",
        ),
        actor_id="user-fde",
    )
    feature_version = modeling.materialize_features(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=FeatureMaterializationRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            profile_id=profile.profile_id,
            recipe_set_id=approved.recipe_set_id,
            idempotency_key="feature-service",
        ),
        actor_id="user-fde",
    )
    repeated = modeling.materialize_features(
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
        request=FeatureMaterializationRequest(
            project_id="project-a",
            workspace_id="workspace-a",
            profile_id=profile.profile_id,
            recipe_set_id=approved.recipe_set_id,
            idempotency_key="feature-service",
        ),
        actor_id="user-fde",
    )
    assert repeated.feature_dataset_version_id == feature_version.feature_dataset_version_id
    assert sha256_file(source_path) == source_checksum
    assert modeling.feature_dataset_version(
        feature_version.feature_dataset_version_id,
        organization_id="org-a",
        project_id="project-a",
        workspace_id="workspace-a",
    ).materialization_checksum_sha256 == feature_version.materialization_checksum_sha256
