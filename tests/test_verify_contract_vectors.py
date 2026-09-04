"""Regression tests for systems/verify_contract_vectors.py."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from systems.verify_contract_vectors import ContractVectorVerifier, compute_sha256


def test_real_repository_contract_vectors_pass():
    """Verify that the real repository contract vectors and schemas pass all checks."""
    verifier = ContractVectorVerifier()
    result = verifier.verify_all()
    assert result.passed, f"Errors: {[e.format() for e in result.errors]}"
    assert result.schema_count >= 1
    assert result.vector_count >= 1
    assert result.manifest_count >= 2
    assert result.payload_count >= 2
    assert "generator-feature-input-v1" in result.verified_vectors
    assert "runtime-overlay-output-v1" in result.verified_vectors


def _setup_isolated_contracts(tmp_path: Path) -> tuple[Path, ContractVectorVerifier]:
    """Helper to copy real contracts directory to a temporary path for mutation testing."""
    repo_root = Path(__file__).resolve().parents[1]
    src_contracts = repo_root / "contracts"

    dst_contracts = tmp_path / "contracts"
    shutil.copytree(src_contracts, dst_contracts)

    verifier = ContractVectorVerifier(repo_root=tmp_path)
    return dst_contracts, verifier


def test_valid_isolated_contracts_pass(tmp_path: Path):
    _, verifier = _setup_isolated_contracts(tmp_path)
    result = verifier.verify_all()
    assert result.passed


def test_runtime_overlay_unicode_checksum_vector_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    expected = (
        contracts_dir
        / "test-vectors"
        / "runtime-overlay-output-v1"
        / "expected-observation-sha256.txt"
    )
    expected.write_text("0" * 64 + "\n", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("canonical Unicode checksum mismatch" in error.message for error in result.errors)


def test_runtime_overlay_path_identity_vector_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    identities_path = (
        contracts_dir
        / "test-vectors"
        / "runtime-overlay-output-v1"
        / "path-identities.json"
    )
    identities = json.loads(identities_path.read_text(encoding="utf-8"))
    identities["cases"][0]["expected_storage_reference"] = (
        "runtime_overlay/sha256-" + "0" * 64 + ".jsonl"
    )
    identities_path.write_text(
        json.dumps(identities, ensure_ascii=False),
        encoding="utf-8",
    )

    result = verifier.verify_all()
    assert not result.passed
    assert any("storage path digest mismatch" in error.message for error in result.errors)


def test_invalid_schema_json_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    bad_schema = contracts_dir / "schemas" / "bad.schema.json"
    bad_schema.write_text("{ invalid json: ", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Invalid JSON in schema file" in e.message for e in result.errors)


def test_schema_meta_draft_violation_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    bad_schema = contracts_dir / "schemas" / "bad_meta.schema.json"
    bad_schema.write_text(
        json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "invalid_primitive_type",
        }),
        encoding="utf-8",
    )

    result = verifier.verify_all()
    assert not result.passed
    assert any("Schema violates its meta-schema" in e.message for e in result.errors)


def test_top_level_array_schema_fails(tmp_path: Path):
    """Verify that a schema with top-level array fails false-green check."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    bad_schema = contracts_dir / "schemas" / "array.schema.json"
    bad_schema.write_text("[]", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Schema top-level must be a JSON object" in e.message for e in result.errors)


def test_schema_without_schema_keyword_but_invalid_type_fails(tmp_path: Path):
    """Verify that a schema without $schema keyword still undergoes meta-schema validation."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    bad_schema = contracts_dir / "schemas" / "no_dollar_schema_bad.schema.json"
    bad_schema.write_text(
        json.dumps({
            "type": "invalid_primitive_type",
        }),
        encoding="utf-8",
    )

    result = verifier.verify_all()
    assert not result.passed
    assert any("Schema violates its meta-schema" in e.message for e in result.errors)


@pytest.mark.parametrize("invalid_top_level", [
    "[]",
    '"schema"',
    "123",
    "null",
    "true",
    "false",
])
def test_top_level_non_object_schema_fails(tmp_path: Path, invalid_top_level: str):
    """Verify that any top-level primitive/array/boolean schema fails by project policy."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    bad_schema = contracts_dir / "schemas" / "non_object.schema.json"
    bad_schema.write_text(invalid_top_level, encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Schema top-level must be a JSON object" in e.message for e in result.errors)


def test_duplicate_schema_id_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    # create duplicate id
    existing_schema_path = contracts_dir / "schemas" / "generator-dataset-input-manifest.schema.json"
    existing_schema = json.loads(existing_schema_path.read_text(encoding="utf-8"))
    dup_id = existing_schema["$id"]

    dup_schema = contracts_dir / "schemas" / "duplicate.schema.json"
    dup_schema.write_text(
        json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": dup_id,
            "type": "object",
        }),
        encoding="utf-8",
    )

    result = verifier.verify_all()
    assert not result.passed
    assert any("Duplicate schema $id" in e.message for e in result.errors)


def test_zero_schemas_fails_false_green_protection(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    shutil.rmtree(contracts_dir / "schemas")
    (contracts_dir / "schemas").mkdir()

    result = verifier.verify_all()
    assert not result.passed
    assert any("No JSON schema files found" in e.message for e in result.errors)


def test_zero_test_vectors_fails_false_green_protection(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    shutil.rmtree(contracts_dir / "test-vectors")
    (contracts_dir / "test-vectors").mkdir()

    result = verifier.verify_all()
    assert not result.passed
    assert any("No test vector directories found" in e.message for e in result.errors)


def test_missing_required_expected_file_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    (vdir / "expected" / "summary.json").unlink()

    result = verifier.verify_all()
    assert not result.passed
    assert any("Missing required test vector file" in e.message for e in result.errors)


def test_payload_sha256_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    csv_file = vdir / "observation" / "observations.csv"
    csv_file.write_text(csv_file.read_text(encoding="utf-8") + "\n# corrupted row", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Payload SHA-256 checksum mismatch" in e.message for e in result.errors)


def test_payload_size_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    manifest_path = vdir / "observation" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["size_bytes"] = 99999999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Payload size_bytes mismatch" in e.message for e in result.errors)


def test_payload_parent_directory_traversal_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    manifest_path = vdir / "observation" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../secret.csv"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Payload path must not traverse parent directories" in e.message for e in result.errors)


def test_payload_absolute_path_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    manifest_path = vdir / "observation" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "/etc/passwd"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Payload path must not be absolute" in e.message for e in result.errors)


def test_expected_labels_and_row_metadata_length_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    labels_file = vdir / "expected" / "labels.json"
    labels = json.loads(labels_file.read_text(encoding="utf-8"))
    labels.append(0)  # extra label
    labels_file.write_text(json.dumps(labels), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Length mismatch between labels and row_metadata" in e.message for e in result.errors)


def test_expected_summary_row_count_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    summary_file = vdir / "expected" / "summary.json"
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    summary["row_count"] = summary["row_count"] + 10
    summary_file.write_text(json.dumps(summary), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("summary.json row_count mismatch" in e.message for e in result.errors)


def test_invalid_label_value_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    labels_file = vdir / "expected" / "labels.json"
    labels = json.loads(labels_file.read_text(encoding="utf-8"))
    labels[0] = 2  # invalid label
    labels_file.write_text(json.dumps(labels), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Invalid label value" in e.message for e in result.errors)


# ==========================================
# Manifest Schema Fail-Closed Tests
# ==========================================

def test_missing_manifest_schema_fails(tmp_path: Path):
    """Verify that deleting generator-dataset-input-manifest.schema.json fails verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    schema_path = contracts_dir / "schemas" / "generator-dataset-input-manifest.schema.json"
    schema_path.unlink()

    result = verifier.verify_all()
    assert not result.passed
    assert any("Required manifest schema not found" in e.message for e in result.errors)


def test_invalid_json_manifest_schema_fails(tmp_path: Path):
    """Verify that malformed JSON in manifest schema fails verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    schema_path = contracts_dir / "schemas" / "generator-dataset-input-manifest.schema.json"
    schema_path.write_text("{ unclosed json: ", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Failed to parse manifest schema JSON" in e.message or "Invalid JSON in schema file" in e.message for e in result.errors)


def test_invalid_meta_manifest_schema_fails(tmp_path: Path):
    """Verify that invalid schema definition in manifest schema fails verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    schema_path = contracts_dir / "schemas" / "generator-dataset-input-manifest.schema.json"
    schema_path.write_text(
        json.dumps({
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "not_a_valid_json_schema_type",
        }),
        encoding="utf-8",
    )

    result = verifier.verify_all()
    assert not result.passed
    assert any("Manifest schema definition is invalid" in e.message or "Schema violates its meta-schema" in e.message for e in result.errors)


def test_manifest_missing_manifest_version_fails(tmp_path: Path):
    """Verify that removing manifest_version from dataset manifest fails schema check."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    manifest_path = vdir / "observation" / "dataset_manifest.json"
    m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    del m_data["manifest_version"]
    manifest_path.write_text(json.dumps(m_data), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Manifest schema validation failed" in e.message for e in result.errors)


def test_manifest_missing_dataset_version_fails(tmp_path: Path):
    """Verify that removing dataset_version from dataset manifest fails schema check."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    manifest_path = vdir / "observation" / "dataset_manifest.json"
    m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    del m_data["dataset_version"]
    manifest_path.write_text(json.dumps(m_data), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Manifest schema validation failed" in e.message for e in result.errors)


def test_manifest_file_entry_missing_media_type_fails(tmp_path: Path):
    """Verify that removing media_type from files entry fails schema check."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    manifest_path = vdir / "observation" / "dataset_manifest.json"
    m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    del m_data["files"][0]["media_type"]
    manifest_path.write_text(json.dumps(m_data), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Manifest schema validation failed" in e.message for e in result.errors)


# ==========================================
# Feature Vector request.json Tests
# ==========================================

def test_feature_vector_request_json_syntax_error_fails(tmp_path: Path):
    """Verify that syntax error in request.json fails verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    (vdir / "request.json").write_text("{ syntax error: ", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Invalid JSON in request.json" in e.message for e in result.errors)


def test_feature_vector_request_json_array_fails(tmp_path: Path):
    """Verify that top-level JSON array in request.json fails verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    (vdir / "request.json").write_text(json.dumps(["item1", "item2"]), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("request.json top-level must be a JSON object" in e.message for e in result.errors)


def test_feature_vector_request_json_empty_fails(tmp_path: Path):
    """Verify that empty request.json fails verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    vdir = contracts_dir / "test-vectors" / "generator-feature-input-v1"
    (vdir / "request.json").write_text("", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("request.json is empty" in e.message for e in result.errors)


# ==========================================
# Training Vector Fail-Closed & Semantic Tests
# ==========================================

def _setup_valid_synthetic_training_vector(contracts_dir: Path) -> Path:
    schema_path = contracts_dir / "schemas" / "generator-training-config.schema.json"
    schema_data = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://contracts.ontology.local/schemas/generator-training-config.schema.json",
        "title": "Generator Training Config Schema",
        "type": "object",
        "required": ["training_config_version", "split_strategy", "split_ratio", "primary_metric", "metrics"],
        "properties": {
            "training_config_version": {"type": "string"},
            "split_strategy": {"type": "string", "enum": ["asset_time_split"]},
            "split_ratio": {
                "type": "object",
                "required": ["train", "validation", "test"],
                "properties": {
                    "train": {"type": "number"},
                    "validation": {"type": "number"},
                    "test": {"type": "number"}
                }
            },
            "primary_metric": {"type": "string"},
            "metrics": {
                "type": "array",
                "items": {"type": "string"}
            },
            "hyperparameters": {"type": "object"}
        }
    }
    schema_path.write_text(json.dumps(schema_data), encoding="utf-8")

    t_vdir = contracts_dir / "test-vectors" / "generator-training-v1"
    t_vdir.mkdir(parents=True, exist_ok=True)
    (t_vdir / "expected").mkdir(parents=True, exist_ok=True)

    request_data = {
        "dataset_id": "ai4i",
        "dataset_version": "v1.0",
        "feature_dataset_version": "f-v1.0",
        "training_config_version": "tc-v1.0",
        "activation_policy": "activate_on_success",
        "model_version": "pdm-lgb-v1.0"
    }
    (t_vdir / "request.json").write_text(json.dumps(request_data), encoding="utf-8")

    training_config_data = {
        "training_config_version": "tc-v1.0",
        "split_strategy": "asset_time_split",
        "split_ratio": {
            "train": 0.7,
            "validation": 0.15,
            "test": 0.15
        },
        "primary_metric": "f1_score",
        "metrics": ["f1_score", "roc_auc"],
        "hyperparameters": {
            "lightgbm": {
                "n_estimators": 50,
                "learning_rate": 0.05
            }
        }
    }
    (t_vdir / "training-config.json").write_text(json.dumps(training_config_data), encoding="utf-8")

    artifact_data = {
        "artifact_type": "predictive_maintenance_model",
        "artifact_schema_version": "model-artifact-v1.0",
        "model_id": "pdm-lgb",
        "model_version": "pdm-lgb-v1.0",
        "dataset_version": "v1.0",
        "feature_schema_version": "fs-v1.0",
        "label_schema_version": "ls-v1.0",
        "history_requirement_version": "hr-v1.0",
        "metrics_schema_version": "ms-v1.0",
        "required_roles": ["model", "feature_schema", "label_schema", "history_requirement", "metrics"]
    }
    (t_vdir / "expected" / "artifact-manifest-required.json").write_text(json.dumps(artifact_data), encoding="utf-8")

    split_summary_data = {
        "strategy": "asset_time_split",
        "asset_count": 5,
        "total_rows": 100,
        "train": {
            "row_count": 70,
            "positive_count": 7,
            "negative_count": 63,
            "positive_ratio": 0.1
        },
        "val": {
            "row_count": 15,
            "positive_count": 3,
            "negative_count": 12,
            "positive_ratio": 0.2
        },
        "test": {
            "row_count": 15,
            "positive_count": 3,
            "negative_count": 12,
            "positive_ratio": 0.2
        }
    }
    (t_vdir / "expected" / "split-summary.json").write_text(json.dumps(split_summary_data), encoding="utf-8")
    return t_vdir


def test_valid_synthetic_training_vector_passes(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    _setup_valid_synthetic_training_vector(contracts_dir)

    result = verifier.verify_all()
    assert result.passed, f"Errors: {[e.format() for e in result.errors]}"
    assert "generator-training-v1" in result.verified_vectors


def test_training_vector_missing_schema_fails(tmp_path: Path):
    """Verify that if a training vector exists without its schema, verification fails fail-closed."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    _setup_valid_synthetic_training_vector(contracts_dir)
    schema_path = contracts_dir / "schemas" / "generator-training-config.schema.json"
    if schema_path.exists():
        schema_path.unlink()

    result = verifier.verify_all()
    assert not result.passed
    assert any("Required training config schema not found" in e.message for e in result.errors)


def test_training_request_forbidden_extra_field_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    req = json.loads((t_vdir / "request.json").read_text(encoding="utf-8"))
    req["extra_forbidden_field"] = "bad"
    (t_vdir / "request.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("forbidden extra fields" in e.message for e in result.errors)


def test_training_request_path_traversal_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    req = json.loads((t_vdir / "request.json").read_text(encoding="utf-8"))
    req["dataset_id"] = "../traversal_id"
    (t_vdir / "request.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("invalid path characters" in e.message for e in result.errors)


def test_training_request_invalid_activation_policy_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    req = json.loads((t_vdir / "request.json").read_text(encoding="utf-8"))
    req["activation_policy"] = "auto_merge"
    (t_vdir / "request.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("activation_policy 'auto_merge' is invalid" in e.message for e in result.errors)


def test_training_config_split_ratio_sum_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    cfg = json.loads((t_vdir / "training-config.json").read_text(encoding="utf-8"))
    cfg["split_ratio"]["train"] = 0.8  # sum is 0.8 + 0.15 + 0.15 = 1.1
    (t_vdir / "training-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("split_ratio sum must be 1.0" in e.message for e in result.errors)


def test_training_config_primary_metric_not_in_metrics_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    cfg = json.loads((t_vdir / "training-config.json").read_text(encoding="utf-8"))
    cfg["primary_metric"] = "custom_loss"
    (t_vdir / "training-config.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("primary_metric 'custom_loss' must be included in metrics list" in e.message for e in result.errors)


def test_training_artifact_expected_missing_roles_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    art = json.loads((t_vdir / "expected" / "artifact-manifest-required.json").read_text(encoding="utf-8"))
    art["required_roles"] = ["model", "metrics"]  # missing feature_schema, label_schema, history_requirement
    (t_vdir / "expected" / "artifact-manifest-required.json").write_text(json.dumps(art), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Missing essential roles in required_roles" in e.message for e in result.errors)


def test_training_split_summary_partition_sum_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    split_s = json.loads((t_vdir / "expected" / "split-summary.json").read_text(encoding="utf-8"))
    split_s["total_rows"] = 150  # partition sum is 70 + 15 + 15 = 100 != 150
    (t_vdir / "expected" / "split-summary.json").write_text(json.dumps(split_s), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("does not match total_rows" in e.message for e in result.errors)


def test_training_split_summary_positive_negative_sum_mismatch_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    split_s = json.loads((t_vdir / "expected" / "split-summary.json").read_text(encoding="utf-8"))
    split_s["train"]["positive_count"] = 10  # 10 + 63 = 73 != 70
    (t_vdir / "expected" / "split-summary.json").write_text(json.dumps(split_s), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("positive_count (10) + negative_count (63) != row_count (70)" in e.message for e in result.errors)


def test_training_split_summary_invalid_positive_ratio_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    t_vdir = _setup_valid_synthetic_training_vector(contracts_dir)
    split_s = json.loads((t_vdir / "expected" / "split-summary.json").read_text(encoding="utf-8"))
    split_s["train"]["positive_ratio"] = 0.99  # actual is 7/70 = 0.1
    (t_vdir / "expected" / "split-summary.json").write_text(json.dumps(split_s), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("positive_ratio (0.99) does not match positive_count/row_count" in e.message for e in result.errors)


def test_unknown_vector_prefix_fails_fail_closed(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    unknown_vdir = contracts_dir / "test-vectors" / "unknown-pipeline-v1"
    unknown_vdir.mkdir(parents=True, exist_ok=True)
    (unknown_vdir / "request.json").write_text("{}", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Unknown test vector structure" in e.message for e in result.errors)


# ==========================================
# Training Example Semantic Tests
# ==========================================

def _setup_valid_training_examples(contracts_dir: Path) -> Path:
    # Ensure training config schema exists
    schema_path = contracts_dir / "schemas" / "generator-training-config.schema.json"
    if not schema_path.exists():
        schema_data = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://contracts.ontology.local/schemas/generator-training-config.schema.json",
            "title": "Generator Training Config Schema",
            "type": "object",
            "required": ["training_config_version", "split_strategy", "split_ratio", "primary_metric", "metrics"],
            "properties": {
                "training_config_version": {"type": "string"},
                "split_strategy": {"type": "string", "enum": ["asset_time_split"]},
                "split_ratio": {
                    "type": "object",
                    "required": ["train", "validation", "test"],
                    "properties": {
                        "train": {"type": "number"},
                        "validation": {"type": "number"},
                        "test": {"type": "number"}
                    }
                },
                "primary_metric": {"type": "string"},
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "hyperparameters": {"type": "object"}
            }
        }
        schema_path.write_text(json.dumps(schema_data), encoding="utf-8")

    ex_dir = contracts_dir / "examples" / "generator-training"
    ex_dir.mkdir(parents=True, exist_ok=True)

    all_req = {
        "dataset_id": "ai4i",
        "dataset_version": "v1.0",
        "feature_dataset_version": "f-v1.0",
        "training_config_version": "training-config-v1",
        "model_version": "lightgbm-v1.0",
        "activation_policy": "activate_on_success"
    }
    (ex_dir / "training-request-all-models.json").write_text(json.dumps(all_req), encoding="utf-8")

    single_req = {
        "dataset_id": "ai4i",
        "dataset_version": "v1.0",
        "feature_dataset_version": "f-v1.0",
        "training_config_version": "training-config-v1",
        "model_version": "lightgbm-v1.0",
        "activation_policy": "publish_only"
    }
    (ex_dir / "training-request-single-model.json").write_text(json.dumps(single_req), encoding="utf-8")

    cfg_data = {
        "training_config_version": "training-config-v1",
        "split_strategy": "asset_time_split",
        "split_ratio": {
            "train": 0.7,
            "validation": 0.15,
            "test": 0.15
        },
        "random_seed": 42,
        "primary_metric": "f1",
        "metrics": ["f1", "precision", "recall"],
        "hyperparameters": {
            "lightgbm": {
                "n_estimators": 50
            }
        }
    }
    (ex_dir / "training-config-v1.json").write_text(json.dumps(cfg_data), encoding="utf-8")
    return ex_dir


def test_valid_training_examples_pass(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    _setup_valid_training_examples(contracts_dir)

    result = verifier.verify_all()
    assert result.passed, f"Errors: {[e.format() for e in result.errors]}"


def test_training_examples_missing_file_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    (ex_dir / "training-request-single-model.json").unlink()

    result = verifier.verify_all()
    assert not result.passed
    assert any("missing required files" in e.message for e in result.errors)


def test_training_examples_request_invalid_json_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    (ex_dir / "training-request-all-models.json").write_text("{ invalid json: ", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Invalid JSON" in e.message for e in result.errors)


def test_training_examples_request_array_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    (ex_dir / "training-request-all-models.json").write_text("[]", encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("must be a JSON object" in e.message for e in result.errors)


def test_training_examples_request_missing_required_field_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    req = json.loads((ex_dir / "training-request-all-models.json").read_text(encoding="utf-8"))
    del req["feature_dataset_version"]
    (ex_dir / "training-request-all-models.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Missing required field 'feature_dataset_version'" in e.message for e in result.errors)


def test_training_examples_request_path_traversal_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    req = json.loads((ex_dir / "training-request-all-models.json").read_text(encoding="utf-8"))
    req["dataset_version"] = "../secret"
    (ex_dir / "training-request-all-models.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("invalid path characters" in e.message for e in result.errors)


def test_training_examples_request_invalid_activation_policy_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    req = json.loads((ex_dir / "training-request-all-models.json").read_text(encoding="utf-8"))
    req["activation_policy"] = "invalid_policy"
    (ex_dir / "training-request-all-models.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("activation_policy 'invalid_policy' is invalid" in e.message for e in result.errors)


def test_training_examples_request_extra_field_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    req = json.loads((ex_dir / "training-request-all-models.json").read_text(encoding="utf-8"))
    req["unsupported_field"] = "bad"
    (ex_dir / "training-request-all-models.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("forbidden extra fields" in e.message for e in result.errors)


def test_training_examples_config_split_ratio_sum_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    cfg = json.loads((ex_dir / "training-config-v1.json").read_text(encoding="utf-8"))
    cfg["split_ratio"]["train"] = 0.9  # 0.9 + 0.15 + 0.15 = 1.2
    (ex_dir / "training-config-v1.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("split_ratio sum must be 1.0" in e.message for e in result.errors)


def test_training_examples_config_duplicate_metrics_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    cfg = json.loads((ex_dir / "training-config-v1.json").read_text(encoding="utf-8"))
    cfg["metrics"] = ["f1", "f1"]
    (ex_dir / "training-config-v1.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("Duplicate metric names found" in e.message for e in result.errors)


def test_training_examples_config_missing_primary_metric_fails(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    cfg = json.loads((ex_dir / "training-config-v1.json").read_text(encoding="utf-8"))
    cfg["primary_metric"] = "roc_auc"
    (ex_dir / "training-config-v1.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("primary_metric 'roc_auc' must be included in metrics list" in e.message for e in result.errors)


def test_training_examples_optional_model_version_null_or_omitted_passes(tmp_path: Path):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    req = json.loads((ex_dir / "training-request-all-models.json").read_text(encoding="utf-8"))
    req["model_version"] = None
    del req["activation_policy"]
    (ex_dir / "training-request-all-models.json").write_text(json.dumps(req), encoding="utf-8")

    result = verifier.verify_all()
    assert result.passed, f"Errors: {[e.format() for e in result.errors]}"


@pytest.mark.parametrize("model_name,reserved_key", [
    ("lightgbm", "random_state"),
    ("xgboost", "seed"),
    ("random_forest", "random_seed"),
])
def test_training_examples_config_reserved_seed_keys_fails(tmp_path: Path, model_name: str, reserved_key: str):
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    ex_dir = _setup_valid_training_examples(contracts_dir)
    cfg = json.loads((ex_dir / "training-config-v1.json").read_text(encoding="utf-8"))
    cfg["hyperparameters"][model_name] = {reserved_key: 42, "n_estimators": 50}
    (ex_dir / "training-config-v1.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any(f"hyperparameters.{model_name} contains reserved seed key '{reserved_key}'" in e.message for e in result.errors)


def test_runtime_prediction_vector_verification_passes():
    """Verify that real repository generator-runtime-prediction-v1 vector verifies cleanly."""
    from systems.verify_contract_vectors import ContractVectorVerifier
    verifier = ContractVectorVerifier()
    result = verifier.verify_all()
    assert result.passed, f"Errors: {[e.format() for e in result.errors]}"
    assert "generator-runtime-prediction-v1" in result.verified_vectors


def test_pipeline_e2e_vector_verification_passes():
    """Verify that real repository generator-pipeline-e2e-v1 vector verifies cleanly."""
    verifier = ContractVectorVerifier()
    result = verifier.verify_all()
    assert result.passed, f"Errors: {[e.format() for e in result.errors]}"
    assert "generator-pipeline-e2e-v1" in result.verified_vectors


def test_pipeline_e2e_vector_deterministic_identity_mismatch_fails(tmp_path: Path):
    """Tampering with deterministic identities in generator-pipeline-e2e-v1 must fail verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    det_path = (
        contracts_dir
        / "test-vectors"
        / "generator-pipeline-e2e-v1"
        / "expected"
        / "deterministic-identities.json"
    )
    det = json.loads(det_path.read_text(encoding="utf-8"))
    det["dataset_id"] = "tampered-dataset-id"
    det_path.write_text(json.dumps(det), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("dataset_id mismatch with deterministic identities" in e.message for e in result.errors)


def test_pipeline_e2e_vector_corrupted_manifest_sha_fails(tmp_path: Path):
    """Tampering with file checksum in dataset_manifest.json must fail verification."""
    contracts_dir, verifier = _setup_isolated_contracts(tmp_path)
    man_path = (
        contracts_dir
        / "test-vectors"
        / "generator-pipeline-e2e-v1"
        / "expected"
        / "dataset_manifest.json"
    )
    man = json.loads(man_path.read_text(encoding="utf-8"))
    man["files"][0]["sha256"] = "0" * 64
    man_path.write_text(json.dumps(man), encoding="utf-8")

    result = verifier.verify_all()
    assert not result.passed
    assert any("SHA-256 mismatch" in e.message for e in result.errors)
