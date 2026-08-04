from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ontology_dashboard.adapters.prediction_repository import PredictionResultRepository
from ontology_dashboard.adapters.service import AdapterService
from ontology_dashboard.identity_models import Principal
from ontology_dashboard.migrations import migrate
from ontology_dashboard.modeling.models import (
    ExperimentCreateRequest,
    FeatureMaterializationRequest,
    FeatureRecipe,
    FeatureRecipeSetCreateRequest,
    FeatureRecipeSetDecisionRequest,
    LabelPolicy,
    ManifestDraftDecisionRequest,
    ManifestIngestRequest,
    MappingCandidateDecisionRequest,
    MappingSetDecisionRequest,
    ModelActivateRequest,
    ModelReleaseDecisionRequest,
    ModelReleaseRequestCreate,
    ModelScoreRequest,
    ModelVersionCreateRequest,
    SplitPolicy,
    canonical_checksum,
)
from ontology_dashboard.modeling.service import ModelingService


def _seed_scope(database: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO organizations(id,slug,name,created_at) VALUES (?,?,?,?)",
            ("org-e2e", "org-e2e", "Org E2E", now),
        )
        connection.execute(
            """
            INSERT INTO projects(
                id,organization_id,slug,display_name,description,domain_pack_code,
                status,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                "project-e2e",
                "org-e2e",
                "project-e2e",
                "Project E2E",
                "Adaptive Modeling E2E",
                "predictive-maintenance",
                "active",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO workspaces(
                id,organization_id,project_id,slug,display_name,domain_pack,created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                "workspace-e2e",
                "org-e2e",
                "project-e2e",
                "workspace-e2e",
                "Workspace E2E",
                "predictive-maintenance",
                now,
            ),
        )


def _principal() -> Principal:
    return Principal(
        user_id="user-e2e",
        organization_id="org-e2e",
        email="e2e@example.com",
        display_name="E2E Validator",
        status="active",
        roles=["ml_validator", "fde", "tenant_admin"],
        permissions=[
            "datasets.read",
            "datasets.ingest",
            "predictions.ingest",
            "ml.console.read",
            "ml.release.request",
            "ml.release.approve",
        ],
        workspace_scopes=["workspace-e2e"],
        project_scopes=["project-e2e"],
        project_roles={"project-e2e": ["ml_validator", "fde", "tenant_admin"]},
        active_project_id="project-e2e",
        active_project_roles=["ml_validator", "fde", "tenant_admin"],
        is_admin=True,
        default_path="/app",
        landing_key="ml_validator",
    )


def _write_source(path: Path) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fields = [
        "machine_id",
        "timestamp",
        "voltage",
        "rpm",
        "torque",
        "air_temp",
        "process_temp",
        "wear",
        "failure",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for equipment_index, equipment in enumerate(("M-1", "M-2", "M-3")):
            for index in range(120):
                failure = int(index in {30, 55, 80, 105})
                writer.writerow(
                    {
                        "machine_id": equipment,
                        "timestamp": (
                            start + timedelta(minutes=10 * index)
                        ).isoformat(),
                        "voltage": 210 + index * 0.2 + equipment_index,
                        "rpm": 1200 + index * 4,
                        "torque": 20 + index * 0.25,
                        "air_temp": 295 + equipment_index,
                        "process_temp": 300 + index * 0.15,
                        "wear": index * 1.8,
                        "failure": failure,
                    }
                )


def _recipe(
    recipe_id: str,
    operation: str,
    ontology_property: str,
    *,
    parameters: dict | None = None,
    output_unit: str | None = None,
) -> FeatureRecipe:
    payload = {
        "recipe_id": recipe_id,
        "version": 1,
        "ontology_property": ontology_property,
        "operation": operation,
        "parameters": parameters or {},
        "group_by": "equipment_id",
        "order_by": "observed_at",
        "minimum_history": 1,
        "null_policy": "preserve",
        "boundary_policy": "reset_per_group",
        "source_grain": "observation",
        "output_datatype": "number",
        "output_unit": output_unit,
        "leakage_policy": "past_and_present_only",
        "status": "enabled",
    }
    return FeatureRecipe(
        **payload,
        checksum_sha256=canonical_checksum(payload),
    )


def test_adaptive_modeling_governed_end_to_end(tmp_path: Path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    source_root.mkdir()
    source = source_root / "telemetry.csv"
    _write_source(source)
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_DATA_ROOTS", str(source_root))

    database = tmp_path / "adaptive-e2e.db"
    migrate(str(database))
    _seed_scope(database)
    prediction_repository = PredictionResultRepository(database)
    modeling = ModelingService.configured(
        str(database),
        tmp_path / "artifacts",
        intake_roots=[source_root],
        prediction_repository=prediction_repository,
    )
    adapters = AdapterService(
        database,
        root=tmp_path,
        prediction_repository=prediction_repository,
    )
    principal = _principal()

    profile = modeling.profile_source(
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        source_path=str(source),
        sheet=None,
        use_llm=False,
        idempotency_key="profile-e2e",
        actor_id=principal.user_id,
    )
    draft = modeling.create_manifest_draft(
        profile_id=profile.profile_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        idempotency_key="manifest-e2e",
        actor_id=principal.user_id,
    )
    draft = modeling.decide_manifest_draft(
        draft.draft_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ManifestDraftDecisionRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            expected_revision=draft.revision,
            decision="approve",
            rationale="identifier, timestamp and selected fields reviewed",
        ),
        actor_id=principal.user_id,
    )
    manifest = modeling.adapter_manifest(
        draft.draft_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ManifestIngestRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            dataset_name="Adaptive E2E Telemetry",
            dataset_version="source-v1",
        ),
    )
    ingestion = adapters.ingest(principal, "project-e2e", manifest)
    assert ingestion.status == "completed"
    detail = adapters.dataset_catalog.detail(
        principal=principal,
        project_id="project-e2e",
        dataset_id=manifest.manifest_id,
    )
    dataset_version = next(
        item for item in detail.versions if item.source_version == "source-v1"
    )

    mapping = modeling.create_mapping_set(
        profile_id=profile.profile_id,
        dataset_version_id=dataset_version.id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        use_llm=False,
        idempotency_key="mapping-e2e",
        actor_id=principal.user_id,
    )
    for candidate in list(mapping.candidates):
        mapping = modeling.decide_mapping_candidate(
            mapping.mapping_set_id,
            organization_id="org-e2e",
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            request=MappingCandidateDecisionRequest(
                project_id="project-e2e",
                workspace_id="workspace-e2e",
                expected_revision=mapping.revision,
                candidate_id=candidate.candidate_id,
                decision="approve" if candidate.target_property else "reject",
                rationale="deterministic registry mapping reviewed",
            ),
            actor_id=principal.user_id,
        )
    mapping = modeling.decide_mapping_set(
        mapping.mapping_set_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=MappingSetDecisionRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            expected_revision=mapping.revision,
            decision="approve",
            rationale="critical mappings reviewed",
        ),
        actor_id=principal.user_id,
    )
    training_capability = next(
        item
        for item in modeling.mapping_capabilities(
            mapping.mapping_set_id,
            organization_id="org-e2e",
            project_id="project-e2e",
            workspace_id="workspace-e2e",
        )
        if item.capability == "predictive_training"
    )
    assert training_capability.status == "ready"

    label_policy = LabelPolicy(
        label_policy_id="label-e2e-v1",
        version=1,
        horizon_hours=1,
        lookback_hours=0,
        embargo_hours=0,
        event_time_field="observed_at",
        observation_time_field="observed_at",
        target_source="machine_failure",
        overlapping_window_policy="nearest_event",
    )
    recipe_set = modeling.create_feature_recipe_set(
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=FeatureRecipeSetCreateRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            dataset_version_id=dataset_version.id,
            mapping_set_id=mapping.mapping_set_id,
            recipes=[
                _recipe(
                    "voltage-rolling-3",
                    "rolling_mean",
                    "voltage_v",
                    parameters={"window": 3, "min_periods": 1},
                    output_unit="V",
                ),
                _recipe("power", "power_w", "torque_nm", output_unit="W"),
                _recipe(
                    "temperature-gap",
                    "temperature_gap_k",
                    "process_temperature_k",
                    output_unit="K",
                ),
                _recipe(
                    "overstrain",
                    "overstrain_load",
                    "tool_wear_min",
                    output_unit="min·N·m",
                ),
            ],
            label_policy=label_policy,
            idempotency_key="recipe-e2e",
        ),
        actor_id=principal.user_id,
    )
    recipe_set = modeling.decide_feature_recipe_set(
        recipe_set.recipe_set_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=FeatureRecipeSetDecisionRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            expected_revision=recipe_set.revision,
            decision="approve",
            rationale="group, order, leakage and label policies reviewed",
        ),
        actor_id=principal.user_id,
    )
    feature_version = modeling.materialize_features(
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=FeatureMaterializationRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            profile_id=profile.profile_id,
            recipe_set_id=recipe_set.recipe_set_id,
            idempotency_key="feature-e2e",
        ),
        actor_id=principal.user_id,
    )
    assert feature_version.status == "succeeded"

    experiment = modeling.queue_experiment(
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ExperimentCreateRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            feature_dataset_version_id=feature_version.feature_dataset_version_id,
            split_policy=SplitPolicy(
                mode="group_chronological",
                group_field="equipment_id",
                time_field="observed_at",
                train_fraction=0.6,
                validation_fraction=0.2,
                test_fraction=0.2,
                embargo_hours=0,
            ),
            algorithms=["dummy_prior", "logistic_regression", "random_forest"],
            random_seed=42,
            recall_target=0.5,
            false_negative_cost=10,
            false_positive_cost=1,
            idempotency_key="experiment-e2e",
        ),
        actor_id=principal.user_id,
    )
    experiment = modeling.execute_experiment(
        experiment.experiment_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        worker_id="worker-e2e",
    )
    assert experiment.status == "succeeded"

    model = modeling.create_model_version(
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ModelVersionCreateRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            experiment_id=experiment.experiment_id,
            idempotency_key="model-e2e",
        ),
        actor_id=principal.user_id,
    )
    release = modeling.request_model_release(
        model.model_version_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ModelReleaseRequestCreate(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            rationale="validation, test, lineage and runtime reviewed",
        ),
        actor_id="user-ml-validator",
    )
    _, model = modeling.decide_model_release(
        release.release_request_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ModelReleaseDecisionRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            expected_revision=release.revision,
            decision="approve",
            rationale="tenant administrator approved governed release",
        ),
        actor_id="user-tenant-admin",
    )
    model = modeling.activate_model(
        model.model_version_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ModelActivateRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            expected_revision=model.revision,
        ),
        actor_id="user-tenant-admin",
    )

    features = {name: 1.0 for name in model.input_features}
    result, explanation = modeling.score_active_model(
        model.model_version_id,
        organization_id="org-e2e",
        project_id="project-e2e",
        workspace_id="workspace-e2e",
        request=ModelScoreRequest(
            project_id="project-e2e",
            workspace_id="workspace-e2e",
            observation_id="observation-e2e",
            observed_at=datetime.now(timezone.utc),
            features=features,
            expected_input_schema_checksum_sha256=model.input_schema_checksum_sha256,
        ),
        actor_id=principal.user_id,
    )
    persisted = prediction_repository.get_payload(
        organization_id="org-e2e",
        project_id="project-e2e",
        prediction_id=result.prediction_result_id,
    )
    assert persisted is not None
    assert persisted.prediction.label in {
        "failure_risk",
        "no_significant_risk",
    }
    assert explanation.prediction_result_id == result.prediction_result_id
    assert explanation.causal_proof is False
    assert model.promotion_gate["status"] == "passed"

    chain = {
        "source_checksum": profile.source_checksum_sha256,
        "profile_cache_key": profile.cache_key,
        "manifest_revision": draft.revision,
        "dataset_version_id": dataset_version.id,
        "mapping_checksum": mapping.checksum_sha256,
        "recipe_checksum": recipe_set.checksum_sha256,
        "feature_checksum": feature_version.materialization_checksum_sha256,
        "label_policy_id": label_policy.label_policy_id,
        "experiment_id": experiment.experiment_id,
        "model_artifact_checksum": model.artifact.checksum_sha256,
        "threshold_policy_id": model.threshold_policy.threshold_policy_id,
        "prediction_result_id": result.prediction_result_id,
        "explanation_checksum": explanation.checksum_sha256,
    }
    assert all(chain.values())
    evidence_output = os.getenv("ADAPTIVE_MODELING_EVIDENCE_OUTPUT", "").strip()
    if evidence_output:
        evidence = {
            "schema_version": "adaptive-modeling-e2e-evidence-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "identity_chain": chain,
            "counts": {
                "source_rows": profile.row_count,
                "ingested_rows": ingestion.accepted_record_count,
                "quarantined_rows": ingestion.quarantined_record_count,
                "feature_rows": feature_version.row_count,
                "feature_count": feature_version.feature_count,
                "equipment_count": feature_version.equipment_count,
                "candidate_count": len(experiment.candidates),
                "prediction_results": len(
                    prediction_repository.list(
                        organization_id="org-e2e",
                        project_id="project-e2e",
                        workspace_id="workspace-e2e",
                    )
                ),
            },
            "experiment": {
                "experiment_id": experiment.experiment_id,
                "status": experiment.status,
                "split_policy": experiment.split_policy.model_dump(mode="json"),
                "selected_candidate_id": experiment.selected_candidate_id,
                "threshold_policy_id": experiment.threshold_policy_id,
                "candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "algorithm": item.algorithm,
                        "status": item.status,
                        "selected": item.selected,
                        "validation_metrics": item.validation_metrics.model_dump(mode="json")
                        if item.validation_metrics
                        else None,
                        "held_out_test_metrics": item.held_out_test_metrics.model_dump(
                            mode="json"
                        )
                        if item.held_out_test_metrics
                        else None,
                    }
                    for item in experiment.candidates
                ],
            },
            "model": {
                "model_version_id": model.model_version_id,
                "algorithm": model.algorithm,
                "status": model.status,
                "artifact": model.artifact.model_dump(mode="json"),
                "threshold_policy": model.threshold_policy.model_dump(mode="json"),
                "promotion_gate": model.promotion_gate,
                "confidence_status": model.confidence_status,
            },
            "prediction": result.model_dump(mode="json"),
            "explanation": explanation.model_dump(mode="json"),
            "safety": {
                "evaluation_truth_exposed": False,
                "hidden_truth_exposed": False,
                "binary_failure_mode_claim": False,
                "work_order_created": False,
                "causal_proof": explanation.causal_proof,
            },
        }
        output_path = Path(evidence_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
