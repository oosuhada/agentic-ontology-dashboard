"""Lightweight contract vector and schema validation script.

Validates:
1. JSON Schemas under contracts/schemas/**/*.schema.json
2. Example files under contracts/examples/
3. Test vectors under contracts/test-vectors/ (structure, manifest, payload integrity, expected consistency)

This script is standalone, fast, and does NOT execute heavy runtime/Docker/DB services.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import jsonschema
    from jsonschema.validators import validator_for
except ImportError:
    print("ERROR: 'jsonschema' package is required to run systems/verify_contract_vectors.py", file=sys.stderr)
    sys.exit(1)


@dataclass
class VerificationError:
    context: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None

    def format(self) -> str:
        lines = [f"FAIL [{self.context}]: {self.message}"]
        if self.expected is not None:
            lines.append(f"  expected: {self.expected}")
        if self.actual is not None:
            lines.append(f"  actual:   {self.actual}")
        return "\n".join(lines)


@dataclass
class VerificationResult:
    schema_count: int = 0
    example_count: int = 0
    vector_count: int = 0
    manifest_count: int = 0
    payload_count: int = 0
    verified_vectors: list[str] = field(default_factory=list)
    errors: list[VerificationError] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_runtime_overlay_observation_sha256(payload: dict[str, Any]) -> str:
    """Compute the official v1 semantic checksum over canonical UTF-8 JSON bytes."""
    semantic = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "observation_sha256"}
    }
    encoded = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def runtime_overlay_storage_component(
    simulation_session_id: str,
    overlay_branch_id: str,
) -> str:
    identity = json.dumps(
        [str(simulation_session_id), str(overlay_branch_id)],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256-{hashlib.sha256(identity).hexdigest()}"


class ContractVectorVerifier:
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parents[1]
        else:
            self.repo_root = Path(repo_root).resolve()

        self.contracts_dir = self.repo_root / "contracts"
        self.schemas_dir = self.contracts_dir / "schemas"
        self.examples_dir = self.contracts_dir / "examples"
        self.vectors_dir = self.contracts_dir / "test-vectors"

    def verify_all(self) -> VerificationResult:
        result = VerificationResult()

        # 1. Verify JSON Schemas
        self._verify_schemas(result)

        # 2. Verify Examples
        self._verify_examples(result)

        # 3. Verify Test Vectors
        self._verify_test_vectors(result)

        return result

    def _verify_schemas(self, result: VerificationResult) -> None:
        if not self.schemas_dir.is_dir():
            result.errors.append(
                VerificationError(
                    context="schemas_dir",
                    message=f"Schemas directory not found: {self.schemas_dir}",
                )
            )
            return

        schema_files = sorted(self.schemas_dir.glob("**/*.schema.json"))
        if not schema_files:
            result.errors.append(
                VerificationError(
                    context="schemas_dir",
                    message=f"No JSON schema files found under {self.schemas_dir} (false-green protection)",
                    expected=">= 1 schema files",
                    actual="0 schema files",
                )
            )
            return

        seen_ids: dict[str, Path] = {}

        for sfile in schema_files:
            rel_path = sfile.relative_to(self.repo_root)
            try:
                content = sfile.read_text(encoding="utf-8")
                schema = json.loads(content)
            except Exception as e:
                result.errors.append(
                    VerificationError(
                        context=str(rel_path),
                        message=f"Invalid JSON in schema file: {e}",
                    )
                )
                continue

            result.schema_count += 1

            # 1. Top-level must be a JSON Object (primitives/arrays/booleans fail by project policy)
            if not isinstance(schema, dict):
                result.errors.append(
                    VerificationError(
                        context=str(rel_path),
                        message="Schema top-level must be a JSON object",
                        expected="JSON object",
                        actual=type(schema).__name__,
                    )
                )
                continue

            # 2. Validate against Draft meta-schema unconditionally (with or without $schema keyword)
            try:
                validator_cls = validator_for(schema)
                validator_cls.check_schema(schema)
            except Exception as e:
                result.errors.append(
                    VerificationError(
                        context=str(rel_path),
                        message=f"Schema violates its meta-schema: {e}",
                    )
                )
                continue

            # 3. Check $id uniqueness
            if "$id" in schema:
                schema_id = schema["$id"]
                if schema_id in seen_ids:
                    result.errors.append(
                        VerificationError(
                            context=str(rel_path),
                            message=f"Duplicate schema $id '{schema_id}' already used in {seen_ids[schema_id]}",
                            expected="Unique $id across all schema files",
                            actual=f"Duplicate $id '{schema_id}'",
                        )
                    )
                else:
                    seen_ids[schema_id] = rel_path

    def _get_manifest_validator(
        self, result: VerificationResult, context: str
    ) -> Optional[jsonschema.Draft202012Validator]:
        """Load and compile the canonical Dataset Input Manifest schema in a fail-closed manner."""
        manifest_schema_path = self.schemas_dir / "generator-dataset-input-manifest.schema.json"
        if not manifest_schema_path.is_file():
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Required manifest schema not found: {manifest_schema_path}",
                    expected="contracts/schemas/generator-dataset-input-manifest.schema.json exists",
                    actual="File missing",
                )
            )
            return None

        try:
            m_schema = json.loads(manifest_schema_path.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{manifest_schema_path.name}",
                    message=f"Failed to parse manifest schema JSON: {e}",
                )
            )
            return None

        try:
            jsonschema.Draft202012Validator.check_schema(m_schema)
            return jsonschema.Draft202012Validator(m_schema)
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{manifest_schema_path.name}",
                    message=f"Manifest schema definition is invalid: {e}",
                )
            )
            return None

    def _load_json_object(self, path: Path, context: str, result: VerificationResult) -> Optional[dict[str, Any]]:
        """Load a JSON file and ensure its top-level value is a JSON object."""
        if not path.is_file():
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Required JSON file not found: {path}",
                    expected="File exists",
                    actual="File missing",
                )
            )
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Invalid JSON in {path.name}: {e}",
                )
            )
            return None

        if not isinstance(data, dict):
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"{path.name} top-level must be a JSON object, got {type(data).__name__}",
                    expected="JSON object ({...})",
                    actual=type(data).__name__,
                )
            )
            return None
        return data

    def _validate_training_request_data(
        self,
        req_data: dict[str, Any],
        context: str,
        result: VerificationResult,
    ) -> None:
        """Validate Training Request structure against contract requirements."""
        allowed_fields = {
            "dataset_id",
            "dataset_version",
            "feature_dataset_version",
            "training_config_version",
            "activation_policy",
            "model_version",
        }
        extra_fields = set(req_data.keys()) - allowed_fields
        if extra_fields:
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Request contains forbidden extra fields: {sorted(extra_fields)}",
                    expected="Only allowed fields: dataset_id, dataset_version, feature_dataset_version, training_config_version, activation_policy, model_version",
                    actual=str(list(req_data.keys())),
                )
            )

        required_fields = ["dataset_id", "dataset_version", "feature_dataset_version"]
        for field in required_fields:
            val = req_data.get(field)
            if val is None:
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"Missing required field '{field}' in request",
                    )
                )
            elif not isinstance(val, str):
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"Field '{field}' must be a string, got {type(val).__name__}",
                    )
                )
            else:
                cleaned = val.strip()
                if not cleaned:
                    result.errors.append(
                        VerificationError(
                            context=context,
                            message=f"Field '{field}' cannot be empty after stripping whitespace",
                        )
                    )
                if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
                    result.errors.append(
                        VerificationError(
                            context=context,
                            message=f"Field '{field}' contains invalid path characters ('..', '/', '\\'): '{val}'",
                        )
                    )

        if "training_config_version" in req_data and req_data["training_config_version"] is not None:
            tcv = req_data["training_config_version"]
            if not isinstance(tcv, str) or not tcv.strip() or ".." in tcv or "/" in tcv or "\\" in tcv:
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"training_config_version '{tcv}' must be a valid identifier",
                    )
                )

        if "activation_policy" in req_data and req_data["activation_policy"] is not None:
            act_pol = req_data["activation_policy"]
            if act_pol not in ("activate_on_success", "publish_only"):
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"activation_policy '{act_pol}' is invalid. Allowed: 'activate_on_success', 'publish_only'",
                        expected="activate_on_success or publish_only",
                        actual=str(act_pol),
                    )
                )

        if "model_version" in req_data and req_data["model_version"] is not None:
            mv = req_data["model_version"]
            if not isinstance(mv, str):
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"model_version must be a string or null, got {type(mv).__name__}",
                    )
                )
            else:
                cleaned_mv = mv.strip()
                if not cleaned_mv or ".." in cleaned_mv or "/" in cleaned_mv or "\\" in cleaned_mv:
                    result.errors.append(
                        VerificationError(
                            context=context,
                            message=f"model_version contains invalid path characters or is empty: '{mv}'",
                        )
                    )

    def _get_training_config_validator(
        self,
        result: VerificationResult,
        context: str,
    ) -> Optional[jsonschema.Draft202012Validator]:
        """Load and compile the Training Config schema in a fail-closed manner."""
        cfg_schema_path = self.schemas_dir / "generator-training-config.schema.json"
        if not cfg_schema_path.is_file():
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Required training config schema not found: {cfg_schema_path}",
                    expected="contracts/schemas/generator-training-config.schema.json exists",
                    actual="File missing",
                )
            )
            return None

        try:
            cfg_schema = json.loads(cfg_schema_path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(cfg_schema)
            return jsonschema.Draft202012Validator(cfg_schema)
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Failed to compile generator-training-config.schema.json: {e}",
                )
            )
            return None

    def _validate_training_config_data(
        self,
        cfg_data: dict[str, Any],
        cfg_validator: jsonschema.Draft202012Validator,
        context: str,
        result: VerificationResult,
        expected_version: Optional[str] = None,
    ) -> None:
        """Validate Training Config data against schema and business invariants."""
        # 1. JSON Schema validation
        try:
            cfg_validator.validate(cfg_data)
        except jsonschema.ValidationError as e:
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"Training config schema validation failed: {e.message}",
                )
            )

        # 2. Expected version check
        if expected_version is not None:
            if cfg_data.get("training_config_version") != expected_version:
                result.errors.append(
                    VerificationError(
                        context=context,
                        message="training_config_version mismatch",
                        expected=str(expected_version),
                        actual=str(cfg_data.get("training_config_version")),
                    )
                )

        # 3. Split settings check
        split_strategy = cfg_data.get("split_strategy")
        if split_strategy != "asset_time_split":
            result.errors.append(
                VerificationError(
                    context=context,
                    message=f"split_strategy must be 'asset_time_split', got '{split_strategy}'",
                    expected="asset_time_split",
                    actual=str(split_strategy),
                )
            )

        split_ratio = cfg_data.get("split_ratio", {})
        if not isinstance(split_ratio, dict):
            result.errors.append(
                VerificationError(
                    context=context,
                    message="split_ratio must be an object",
                )
            )
        else:
            train_r = split_ratio.get("train")
            val_r = split_ratio.get("validation")
            test_r = split_ratio.get("test")

            for k, v in [("train", train_r), ("validation", val_r), ("test", test_r)]:
                if v is None or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v) or v < 0.0 or v > 1.0:
                    result.errors.append(
                        VerificationError(
                            context=context,
                            message=f"split_ratio.{k} must be a finite number between 0.0 and 1.0, got {v}",
                        )
                    )

            if isinstance(train_r, (int, float)) and isinstance(val_r, (int, float)) and isinstance(test_r, (int, float)):
                if not (math.isnan(train_r) or math.isnan(val_r) or math.isnan(test_r) or math.isinf(train_r) or math.isinf(val_r) or math.isinf(test_r)):
                    ratio_sum = train_r + val_r + test_r
                    if not math.isclose(ratio_sum, 1.0, rel_tol=0.0, abs_tol=1e-9):
                        result.errors.append(
                            VerificationError(
                                context=context,
                                message=f"split_ratio sum must be 1.0, got {ratio_sum}",
                                expected="1.0",
                                actual=str(ratio_sum),
                            )
                        )

        # 4. Metric verification
        metrics = cfg_data.get("metrics")
        primary_metric = cfg_data.get("primary_metric")
        if not isinstance(metrics, list) or not metrics:
            result.errors.append(
                VerificationError(
                    context=context,
                    message="metrics must be a non-empty list of strings",
                )
            )
        else:
            for m in metrics:
                if not isinstance(m, str) or not m.strip():
                    result.errors.append(
                        VerificationError(
                            context=context,
                            message=f"Invalid metric name '{m}' in metrics list",
                        )
                    )
            if len(metrics) != len(set(metrics)):
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"Duplicate metric names found in metrics: {metrics}",
                    )
                )
            if primary_metric not in metrics:
                result.errors.append(
                    VerificationError(
                        context=context,
                        message=f"primary_metric '{primary_metric}' must be included in metrics list",
                        expected=f"One of {metrics}",
                        actual=str(primary_metric),
                    )
                )

        # 5. Hyperparameter verification
        hyperparams = cfg_data.get("hyperparameters", {})
        if not isinstance(hyperparams, dict):
            result.errors.append(
                VerificationError(
                    context=context,
                    message="hyperparameters must be an object",
                )
            )
        else:
            for model_name, model_params in hyperparams.items():
                if not isinstance(model_params, dict):
                    result.errors.append(
                        VerificationError(
                            context=context,
                            message=f"hyperparameters.{model_name} must be an object, got {type(model_params).__name__}",
                        )
                    )
                else:
                    for p_name, p_val in model_params.items():
                        if p_name in {"random_state", "seed", "random_seed"}:
                            result.errors.append(
                                VerificationError(
                                    context=context,
                                    message=(
                                        f"hyperparameters.{model_name} contains reserved seed key '{p_name}'. "
                                        "Use top-level 'random_seed' instead."
                                    ),
                                    expected="No reserved seed key in model hyperparameters",
                                    actual=f"Found '{p_name}' in hyperparameters.{model_name}",
                                )
                            )
                        if isinstance(p_val, float) and (math.isnan(p_val) or math.isinf(p_val)):
                            result.errors.append(
                                VerificationError(
                                    context=context,
                                    message=f"hyperparameters.{model_name}.{p_name} must not be NaN or Infinity, got {p_val}",
                                )
                            )

    def _verify_examples(self, result: VerificationResult) -> None:
        if not self.examples_dir.is_dir():
            return

        example_files = sorted(self.examples_dir.glob("**/*.json"))
        manifest_examples = [ef for ef in example_files if "manifest" in ef.name.lower()]
        manifest_validator = None
        if manifest_examples:
            manifest_validator = self._get_manifest_validator(result, context="examples")

        for efile in example_files:
            rel_path = efile.relative_to(self.repo_root)
            try:
                data = json.loads(efile.read_text(encoding="utf-8"))
            except Exception as e:
                result.errors.append(
                    VerificationError(
                        context=str(rel_path),
                        message=f"Invalid JSON in example file: {e}",
                    )
                )
                continue

            result.example_count += 1

            # If it's a dataset manifest or protocol run manifest example, validate against corresponding schema
            if "manifest" in efile.name.lower():
                if data.get("manifest_version") == "generator-protocol-run-v1" or "source-run-manifest" in efile.name.lower():
                    run_schema_p = self.schemas_dir / "generator-protocol-run-manifest.schema.json"
                    if run_schema_p.is_file():
                        try:
                            r_schema = json.loads(run_schema_p.read_text(encoding="utf-8"))
                            r_val = jsonschema.Draft202012Validator(r_schema, format_checker=jsonschema.FormatChecker())
                            r_val.validate(data)
                        except jsonschema.ValidationError as e:
                            result.errors.append(
                                VerificationError(
                                    context=str(rel_path),
                                    message=f"Example run manifest fails schema validation: {e.message}",
                                )
                            )
                elif data.get("fragment_schema_version") == "generator-extraction-fragment-v1" or "fragment-manifest" in efile.name.lower():
                    frag_schema_p = self.schemas_dir / "generator-extraction-fragment-manifest.schema.json"
                    if frag_schema_p.is_file():
                        try:
                            f_schema = json.loads(frag_schema_p.read_text(encoding="utf-8"))
                            f_val = jsonschema.Draft202012Validator(f_schema, format_checker=jsonschema.FormatChecker())
                            f_val.validate(data)
                        except jsonschema.ValidationError as e:
                            result.errors.append(
                                VerificationError(
                                    context=str(rel_path),
                                    message=f"Example fragment manifest fails schema validation: {e.message}",
                                )
                            )
                elif manifest_validator:
                    try:
                        manifest_validator.validate(data)
                    except jsonschema.ValidationError as e:
                        result.errors.append(
                            VerificationError(
                                context=str(rel_path),
                                message=f"Example manifest fails schema validation: {e.message}",
                            )
                        )

        # Verify Training Examples if generator-training examples directory exists
        training_examples_dir = self.examples_dir / "generator-training"
        if training_examples_dir.is_dir():
            req_training_example_files = [
                training_examples_dir / "training-config-v1.json",
                training_examples_dir / "training-request-all-models.json",
                training_examples_dir / "training-request-single-model.json",
            ]
            missing = [f.name for f in req_training_example_files if not f.is_file()]
            if missing:
                result.errors.append(
                    VerificationError(
                        context="examples/generator-training",
                        message=f"Training examples directory is missing required files: {missing}",
                        expected="All 3 training example files present",
                        actual=f"Missing: {missing}",
                    )
                )
            else:
                # 1. Validate training-request-all-models.json
                all_models_req = self._load_json_object(
                    training_examples_dir / "training-request-all-models.json",
                    "examples/generator-training/training-request-all-models.json",
                    result,
                )
                if all_models_req is not None:
                    self._validate_training_request_data(
                        all_models_req,
                        "examples/generator-training/training-request-all-models.json",
                        result,
                    )

                # 2. Validate training-request-single-model.json
                single_model_req = self._load_json_object(
                    training_examples_dir / "training-request-single-model.json",
                    "examples/generator-training/training-request-single-model.json",
                    result,
                )
                if single_model_req is not None:
                    self._validate_training_request_data(
                        single_model_req,
                        "examples/generator-training/training-request-single-model.json",
                        result,
                    )

                # 3. Validate training-config-v1.json
                cfg_validator = self._get_training_config_validator(
                    result,
                    context="examples/generator-training",
                )
                if cfg_validator is not None:
                    cfg_data = self._load_json_object(
                        training_examples_dir / "training-config-v1.json",
                        "examples/generator-training/training-config-v1.json",
                        result,
                    )
                    if cfg_data is not None:
                        self._validate_training_config_data(
                            cfg_data,
                            cfg_validator,
                            "examples/generator-training/training-config-v1.json",
                            result,
                            expected_version="training-config-v1",
                        )

        # Verify Prediction Result Batch Examples if prediction-result-batch examples directory exists
        prediction_examples_dir = self.examples_dir / "prediction-result-batch"
        if prediction_examples_dir.is_dir():
            batch_schema_path = self.schemas_dir / "prediction-result-batch.schema.json"
            for ex_file in sorted(prediction_examples_dir.glob("*.json")):
                rel_path = ex_file.relative_to(self.repo_root)
                ex_data = self._load_json_object(ex_file, str(rel_path), result)
                if ex_data is not None and batch_schema_path.is_file():
                    try:
                        batch_schema = json.loads(batch_schema_path.read_text(encoding="utf-8"))
                        reg = self._build_schema_registry()
                        format_checker = jsonschema.FormatChecker()
                        if reg is not None:
                            validator = jsonschema.Draft202012Validator(batch_schema, registry=reg, format_checker=format_checker)
                        else:
                            validator = jsonschema.Draft202012Validator(batch_schema, format_checker=format_checker)
                        validator.validate(ex_data)
                    except Exception as e:
                        result.errors.append(
                            VerificationError(
                                context=str(rel_path),
                                message=f"Prediction result batch example failed schema validation: {e}",
                            )
                        )
                    for i, it in enumerate(ex_data.get("results", [])):
                        it_copy = dict(it)
                        claimed_sha = it_copy.pop("payload_sha256", None)
                        c_json = json.dumps(it_copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                        expected_sha = hashlib.sha256(c_json.encode("utf-8")).hexdigest()
                        if claimed_sha != expected_sha:
                            result.errors.append(
                                VerificationError(
                                    context=f"{rel_path}/results[{i}]",
                                    message=f"payload_sha256 checksum mismatch for item '{it.get('event_id')}'",
                                    expected=expected_sha,
                                    actual=str(claimed_sha),
                                )
                            )

        # Verify Generator Runtime Prediction Internal Stage Examples if directory exists
        stage_examples_dir = self.examples_dir / "generator-runtime-prediction"
        if stage_examples_dir.is_dir():
            stage_schema_path = self.schemas_dir / "generator-runtime-prediction-stage.schema.json"
            stage_file = stage_examples_dir / "generator-runtime-prediction-stage.json"
            if stage_file.is_file() and stage_schema_path.is_file():
                rel_path = stage_file.relative_to(self.repo_root)
                st_data = self._load_json_object(stage_file, str(rel_path), result)
                if st_data is not None:
                    try:
                        st_schema = json.loads(stage_schema_path.read_text(encoding="utf-8"))
                        reg = self._build_schema_registry()
                        format_checker = jsonschema.FormatChecker()
                        if reg is not None:
                            validator = jsonschema.Draft202012Validator(st_schema, registry=reg, format_checker=format_checker)
                        else:
                            validator = jsonschema.Draft202012Validator(st_schema, format_checker=format_checker)
                        validator.validate(st_data)
                    except Exception as e:
                        result.errors.append(
                            VerificationError(
                                context=str(rel_path),
                                message=f"Internal stage example failed schema validation: {e}",
                            )
                        )

    def _verify_test_vectors(self, result: VerificationResult) -> None:
        if not self.vectors_dir.is_dir():
            result.errors.append(
                VerificationError(
                    context="test_vectors_dir",
                    message=f"Test vectors directory not found: {self.vectors_dir}",
                )
            )
            return

        vector_dirs = [d for d in sorted(self.vectors_dir.iterdir()) if d.is_dir() and not d.name.startswith(".")]
        if not vector_dirs:
            result.errors.append(
                VerificationError(
                    context="test_vectors_dir",
                    message=f"No test vector directories found under {self.vectors_dir} (false-green protection)",
                    expected=">= 1 test vector directory",
                    actual="0 test vector directories",
                )
            )
            return

        for vdir in vector_dirs:
            vname = vdir.name
            result.vector_count += 1
            error_count_before = len(result.errors)

            if vname.startswith("generator-feature-input"):
                manifest_validator = self._get_manifest_validator(result, context=vname)
                self._verify_feature_input_vector(vname, vdir, manifest_validator, result)
            elif vname.startswith("generator-training"):
                self._verify_training_vector(vname, vdir, result)
            elif vname.startswith("runtime-overlay-output"):
                self._verify_runtime_overlay_output_vector(vname, vdir, result)
            elif vname.startswith("generator-runtime-prediction"):
                self._verify_runtime_prediction_vector(vname, vdir, result)
            elif vname.startswith("generator-protocol-extraction"):
                self._verify_protocol_extraction_vector(vname, vdir, result)
            elif vname.startswith("generator-extraction-runtime-handoff"):
                self._verify_extraction_runtime_handoff_vector(vname, vdir, result)
            elif vname.startswith("generator-pipeline-e2e"):
                self._verify_pipeline_e2e_vector(vname, vdir, result)


            else:
                result.errors.append(
                    VerificationError(
                        context=f"{vname}",
                        message=f"Unknown test vector structure for '{vname}'",
                    )
                )

            if len(result.errors) == error_count_before:
                result.verified_vectors.append(vname)

    def _verify_runtime_overlay_output_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        observation_path = vector_dir / "observation-unicode.json"
        expected_path = vector_dir / "expected-observation-sha256.txt"
        identities_path = vector_dir / "path-identities.json"
        missing = [
            path.name
            for path in (observation_path, expected_path, identities_path)
            if not path.is_file()
        ]
        if missing:
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message=f"Missing required Runtime Overlay vector file(s): {', '.join(missing)}",
                )
            )
            return

        observation = self._load_json_object(
            observation_path,
            f"{vector_name}/observation-unicode.json",
            result,
        )
        identities = self._load_json_object(
            identities_path,
            f"{vector_name}/path-identities.json",
            result,
        )
        if observation is None or identities is None:
            return

        try:
            expected_checksum = expected_path.read_text(encoding="utf-8").strip()
            schema = json.loads(
                (self.schemas_dir / "runtime-overlay-observation.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            validator = jsonschema.Draft202012Validator(
                schema,
                format_checker=jsonschema.FormatChecker(),
            )
        except Exception as exc:
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message=f"Failed to load Runtime Overlay vector contract: {exc}",
                )
            )
            return

        schema_errors = sorted(
            validator.iter_errors(observation),
            key=lambda error: list(error.absolute_path),
        )
        if schema_errors:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/observation-unicode.json",
                    message=f"Runtime Overlay observation schema validation failed: {schema_errors[0].message}",
                )
            )
        actual_checksum = compute_runtime_overlay_observation_sha256(observation)
        declared_checksum = str(observation.get("observation_sha256", ""))
        if not (
            actual_checksum == expected_checksum == declared_checksum
        ):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/observation-unicode.json",
                    message="Runtime Overlay canonical Unicode checksum mismatch",
                    expected=expected_checksum,
                    actual=f"computed={actual_checksum} declared={declared_checksum}",
                )
            )

        cases = identities.get("cases")
        if not isinstance(cases, list) or not cases:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/path-identities.json",
                    message="Runtime Overlay path identity cases must be a non-empty array",
                )
            )
            return
        generated: set[str] = set()
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/path-identities.json[{index}]",
                        message="Path identity case must be an object",
                    )
                )
                continue
            try:
                expected_reference = str(case["expected_storage_reference"])
                actual_reference = (
                    "runtime_overlay/"
                    f"{runtime_overlay_storage_component(str(case['simulation_session_id']), str(case['overlay_branch_id']))}.jsonl"
                )
            except KeyError as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/path-identities.json[{index}]",
                        message=f"Missing path identity field: {exc}",
                    )
                )
                continue
            if actual_reference != expected_reference:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/path-identities.json[{index}]",
                        message="Runtime Overlay storage path digest mismatch",
                        expected=expected_reference,
                        actual=actual_reference,
                    )
                )
            if actual_reference in generated:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/path-identities.json[{index}]",
                        message="Distinct Runtime Overlay vector identities alias the same path",
                        actual=actual_reference,
                    )
                )
            generated.add(actual_reference)
        result.payload_count += 1

    def _verify_feature_input_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        manifest_validator: Optional[jsonschema.Draft202012Validator],
        result: VerificationResult,
    ) -> None:
        # 3.1 Check required files
        req_files = [
            vector_dir / "request.json",
            vector_dir / "observation" / "dataset_manifest.json",
            vector_dir / "failure" / "dataset_manifest.json",
            vector_dir / "expected" / "feature_columns.json",
            vector_dir / "expected" / "labels.json",
            vector_dir / "expected" / "row_metadata.json",
            vector_dir / "expected" / "summary.json",
        ]
        missing = [f.relative_to(vector_dir) for f in req_files if not f.is_file()]
        if missing:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}",
                    message=f"Missing required test vector file(s): {', '.join(str(m) for m in missing)}",
                    expected="All required test vector files present",
                    actual=f"Missing {missing}",
                )
            )
            return

        # 3.2 Validate request.json as valid non-empty JSON object
        req_path = vector_dir / "request.json"
        try:
            req_content = req_path.read_text(encoding="utf-8").strip()
            if not req_content:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/request.json",
                        message="request.json is empty",
                        expected="Non-empty JSON object",
                        actual="Empty file",
                    )
                )
            else:
                req_data = json.loads(req_content)
                if not isinstance(req_data, dict):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/request.json",
                            message=f"request.json top-level must be a JSON object, got {type(req_data).__name__}",
                            expected="JSON object ({...})",
                            actual=f"{type(req_data).__name__}",
                        )
                    )
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/request.json",
                    message=f"Invalid JSON in request.json: {e}",
                )
            )

        # 3.3 Verify Manifest & Payload Integrity (Observation & Failure)
        self._verify_vector_manifest(
            vector_name=vector_name,
            vector_dir=vector_dir,
            manifest_path=vector_dir / "observation" / "dataset_manifest.json",
            expected_dataset_type="observation",
            expected_role="observations",
            manifest_validator=manifest_validator,
            result=result,
        )

        self._verify_vector_manifest(
            vector_name=vector_name,
            vector_dir=vector_dir,
            manifest_path=vector_dir / "failure" / "dataset_manifest.json",
            expected_dataset_type="failure",
            expected_role="failures",
            manifest_validator=manifest_validator,
            result=result,
        )

        # 3.4 Verify Golden Expected Static Consistency
        self._verify_vector_expected(
            vector_name=vector_name,
            vector_dir=vector_dir,
            result=result,
        )

    def _verify_training_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        req_files = [
            vector_dir / "request.json",
            vector_dir / "training-config.json",
            vector_dir / "expected" / "artifact-manifest-required.json",
            vector_dir / "expected" / "split-summary.json",
        ]
        missing = [f.relative_to(vector_dir) for f in req_files if not f.is_file()]
        if missing:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}",
                    message=f"Missing required training test vector file(s): {', '.join(str(m) for m in missing)}",
                    expected="All required training test vector files present",
                    actual=f"Missing {missing}",
                )
            )
            return

        # 1. Validate request.json
        req_data = self._verify_training_request(vector_name, vector_dir, result)

        # 2. Validate training-config.json
        cfg_data = self._verify_training_config(vector_name, vector_dir, req_data, result)

        # 3. Validate expected/artifact-manifest-required.json
        self._verify_training_artifact_expected(vector_name, vector_dir, req_data, result)

        # 4. Validate expected/split-summary.json
        self._verify_training_split_summary(vector_name, vector_dir, cfg_data, result)

    def _verify_training_request(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> Optional[dict[str, Any]]:
        req_path = vector_dir / "request.json"
        req_data = self._load_json_object(req_path, f"{vector_name}/request.json", result)
        if req_data is None:
            return None
        self._validate_training_request_data(req_data, f"{vector_name}/request.json", result)
        return req_data

    def _verify_training_config(
        self,
        vector_name: str,
        vector_dir: Path,
        req_data: Optional[dict[str, Any]],
        result: VerificationResult,
    ) -> Optional[dict[str, Any]]:
        cfg_validator = self._get_training_config_validator(result, context=f"{vector_name}")
        if cfg_validator is None:
            return None

        cfg_file = vector_dir / "training-config.json"
        cfg_data = self._load_json_object(cfg_file, f"{vector_name}/training-config.json", result)
        if cfg_data is None:
            return None

        expected_ver = req_data.get("training_config_version") if (req_data and "training_config_version" in req_data and req_data["training_config_version"]) else None
        self._validate_training_config_data(
            cfg_data,
            cfg_validator,
            f"{vector_name}/training-config.json",
            result,
            expected_version=expected_ver,
        )
        return cfg_data

    def _verify_training_artifact_expected(
        self,
        vector_name: str,
        vector_dir: Path,
        req_data: Optional[dict[str, Any]],
        result: VerificationResult,
    ) -> None:
        exp_file = vector_dir / "expected" / "artifact-manifest-required.json"
        try:
            exp_data = json.loads(exp_file.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/artifact-manifest-required.json",
                    message=f"Invalid JSON in artifact-manifest-required.json: {e}",
                )
            )
            return

        if not isinstance(exp_data, dict):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/artifact-manifest-required.json",
                    message="artifact-manifest-required.json top-level must be a JSON object",
                )
            )
            return

        if req_data and req_data.get("model_version"):
            if exp_data.get("model_version") != req_data["model_version"]:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/artifact-manifest-required.json",
                        message="model_version in expected manifest does not match request.model_version",
                        expected=str(req_data["model_version"]),
                        actual=str(exp_data.get("model_version")),
                    )
                )

        required_manifest_fields = [
            "artifact_type",
            "artifact_schema_version",
            "model_id",
            "dataset_version",
            "feature_schema_version",
            "label_schema_version",
            "history_requirement_version",
            "metrics_schema_version",
        ]
        for field in required_manifest_fields:
            v = exp_data.get(field)
            if not v or not isinstance(v, str) or not v.strip():
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/artifact-manifest-required.json",
                        message=f"Required field '{field}' is missing or empty in artifact-manifest-required.json",
                    )
                )

        if exp_data.get("artifact_type") != "predictive_maintenance_model":
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/artifact-manifest-required.json",
                    message="artifact_type must be 'predictive_maintenance_model'",
                    expected="predictive_maintenance_model",
                    actual=str(exp_data.get("artifact_type")),
                )
            )

        if exp_data.get("artifact_schema_version") != "model-artifact-v1.0":
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/artifact-manifest-required.json",
                    message="artifact_schema_version must be 'model-artifact-v1.0'",
                    expected="model-artifact-v1.0",
                    actual=str(exp_data.get("artifact_schema_version")),
                )
            )

        req_roles = exp_data.get("required_roles")
        if not isinstance(req_roles, list) or not req_roles:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/artifact-manifest-required.json",
                    message="required_roles must be a non-empty list of strings",
                )
            )
        else:
            expected_required_roles = {"model", "feature_schema", "label_schema", "history_requirement", "metrics"}
            for role in req_roles:
                if not isinstance(role, str) or not role.strip():
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/expected/artifact-manifest-required.json",
                            message=f"Invalid role entry '{role}' in required_roles",
                        )
                    )
            if len(req_roles) != len(set(req_roles)):
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/artifact-manifest-required.json",
                        message=f"Duplicate roles found in required_roles: {req_roles}",
                    )
                )
            missing_roles = expected_required_roles - set(req_roles)
            if missing_roles:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/artifact-manifest-required.json",
                        message=f"Missing essential roles in required_roles: {sorted(missing_roles)}",
                        expected=str(sorted(expected_required_roles)),
                        actual=str(req_roles),
                    )
                )

    def _verify_training_split_summary(
        self,
        vector_name: str,
        vector_dir: Path,
        cfg_data: Optional[dict[str, Any]],
        result: VerificationResult,
    ) -> None:
        split_file = vector_dir / "expected" / "split-summary.json"
        try:
            split_data = json.loads(split_file.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message=f"Invalid JSON in split-summary.json: {e}",
                )
            )
            return

        if not isinstance(split_data, dict):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message="split-summary.json top-level must be a JSON object",
                )
            )
            return

        strategy = split_data.get("strategy")
        if strategy != "asset_time_split":
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message=f"strategy must be 'asset_time_split', got '{strategy}'",
                    expected="asset_time_split",
                    actual=str(strategy),
                )
            )
        if cfg_data and "split_strategy" in cfg_data and cfg_data["split_strategy"] != strategy:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message=f"split summary strategy '{strategy}' does not match training config split_strategy '{cfg_data['split_strategy']}'",
                )
            )

        asset_count = split_data.get("asset_count")
        if not isinstance(asset_count, int) or isinstance(asset_count, bool) or asset_count < 0:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message=f"asset_count must be an integer >= 0, got {asset_count}",
                )
            )

        total_rows = split_data.get("total_rows")
        if not isinstance(total_rows, int) or isinstance(total_rows, bool) or total_rows < 0:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message=f"total_rows must be an integer >= 0, got {total_rows}",
                )
            )
            return

        partition_row_sum = 0
        for part in ["train", "val", "test"]:
            p_data = split_data.get(part)
            if not isinstance(p_data, dict):
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/split-summary.json",
                        message=f"Partition '{part}' must be an object",
                    )
                )
                continue

            row_cnt = p_data.get("row_count")
            pos_cnt = p_data.get("positive_count")
            neg_cnt = p_data.get("negative_count")
            pos_ratio = p_data.get("positive_ratio")

            for k, v in [("row_count", row_cnt), ("positive_count", pos_cnt), ("negative_count", neg_cnt)]:
                if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/expected/split-summary.json",
                            message=f"Partition '{part}.{k}' must be an integer >= 0, got {v}",
                        )
                    )

            if isinstance(row_cnt, int) and isinstance(pos_cnt, int) and isinstance(neg_cnt, int):
                partition_row_sum += row_cnt
                if pos_cnt + neg_cnt != row_cnt:
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/expected/split-summary.json",
                            message=f"In partition '{part}': positive_count ({pos_cnt}) + negative_count ({neg_cnt}) != row_count ({row_cnt})",
                        )
                    )

                if isinstance(pos_ratio, (int, float)) and not math.isnan(pos_ratio) and not math.isinf(pos_ratio):
                    if pos_ratio < 0.0 or pos_ratio > 1.0:
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/split-summary.json",
                                message=f"In partition '{part}': positive_ratio must be between 0.0 and 1.0, got {pos_ratio}",
                            )
                        )
                    elif row_cnt > 0:
                        expected_ratio = pos_cnt / row_cnt
                        if not math.isclose(pos_ratio, expected_ratio, rel_tol=1e-4, abs_tol=1e-4):
                            result.errors.append(
                                VerificationError(
                                    context=f"{vector_name}/expected/split-summary.json",
                                    message=f"In partition '{part}': positive_ratio ({pos_ratio}) does not match positive_count/row_count ({expected_ratio})",
                                )
                            )
                    else:
                        if pos_ratio != 0.0:
                            result.errors.append(
                                VerificationError(
                                    context=f"{vector_name}/expected/split-summary.json",
                                    message=f"In partition '{part}': positive_ratio must be 0.0 when row_count == 0, got {pos_ratio}",
                                )
                            )
                else:
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/expected/split-summary.json",
                            message=f"In partition '{part}': positive_ratio must be a finite number",
                        )
                    )

        if partition_row_sum != total_rows:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/split-summary.json",
                    message=f"Sum of partition row_counts ({partition_row_sum}) does not match total_rows ({total_rows})",
                    expected=str(total_rows),
                    actual=str(partition_row_sum),
                )
            )

    def _build_schema_registry(self) -> Any:
        if not hasattr(self, "_registry") or self._registry is None:
            if not self.schemas_dir.is_dir():
                return None
            try:
                import referencing
                reg = referencing.Registry()
                for sf in self.schemas_dir.glob("**/*.schema.json"):
                    try:
                        s_data = json.loads(sf.read_text(encoding="utf-8"))
                        res = referencing.Resource.from_contents(s_data)
                        if "$id" in s_data:
                            reg = reg.with_resource(s_data["$id"], res)
                        reg = reg.with_resource(sf.name, res)
                    except Exception:
                        pass
                self._registry = reg
            except Exception:
                self._registry = None
        return self._registry

    def _verify_runtime_prediction_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        req_files = [
            vector_dir / "input" / "protocol-sample-01.jsonl",
            vector_dir / "expected" / "prediction-results.json",
            vector_dir / "expected" / "prediction-result-batch.json",
        ]
        missing = [f.relative_to(vector_dir) for f in req_files if not f.is_file()]
        if missing:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}",
                    message=f"Missing required test vector file(s): {', '.join(str(m) for m in missing)}",
                    expected="All required test vector files present",
                    actual=f"Missing {missing}",
                )
            )
            return

        # 1. Validate prediction-results.json
        pred_res_path = vector_dir / "expected" / "prediction-results.json"
        pred_schema_path = self.schemas_dir / "generator-model-prediction-result.schema.json"
        try:
            pred_data = json.loads(pred_res_path.read_text(encoding="utf-8"))
            if not isinstance(pred_data, list) or len(pred_data) == 0:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/prediction-results.json",
                        message="prediction-results.json must be a non-empty list of model prediction results",
                    )
                )
            elif pred_schema_path.is_file():
                pred_schema = json.loads(pred_schema_path.read_text(encoding="utf-8"))
                validator = jsonschema.Draft202012Validator(pred_schema)
                for item in pred_data:
                    validator.validate(item)
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/prediction-results.json",
                    message=f"Failed validating prediction-results.json: {e}",
                )
            )

        # 2. Validate prediction-result-batch.json
        batch_path = vector_dir / "expected" / "prediction-result-batch.json"
        batch_schema_path = self.schemas_dir / "prediction-result-batch.schema.json"
        try:
            batch_data = json.loads(batch_path.read_text(encoding="utf-8"))
            if not isinstance(batch_data, dict):
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/prediction-result-batch.json",
                        message="prediction-result-batch.json must be a JSON object",
                    )
                )
            else:
                if not isinstance(batch_data.get("results"), list) or len(batch_data.get("results")) == 0:
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/expected/prediction-result-batch.json",
                            message="'results' must be a non-empty list of PredictionResultItem objects",
                            expected="Non-empty array",
                            actual=type(batch_data.get("results")).__name__,
                        )
                    )
                if batch_schema_path.is_file():
                    batch_schema = json.loads(batch_schema_path.read_text(encoding="utf-8"))
                    reg = self._build_schema_registry()
                    format_checker = jsonschema.FormatChecker()
                    if reg is not None:
                        validator = jsonschema.Draft202012Validator(batch_schema, registry=reg, format_checker=format_checker)
                    else:
                        validator = jsonschema.Draft202012Validator(batch_schema, format_checker=format_checker)
                    validator.validate(batch_data)

                for i, it in enumerate(batch_data.get("results", [])):
                    it_copy = dict(it)
                    claimed_sha = it_copy.pop("payload_sha256", None)
                    c_json = json.dumps(it_copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    expected_sha = hashlib.sha256(c_json.encode("utf-8")).hexdigest()
                    if claimed_sha != expected_sha:
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/prediction-result-batch.json/results[{i}]",
                                message=f"payload_sha256 checksum mismatch for item '{it.get('event_id')}'",
                                expected=expected_sha,
                                actual=str(claimed_sha),
                            )
                        )
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/prediction-result-batch.json",
                    message=f"Failed validating prediction-result-batch.json: {e}",
                )
            )


        # 3. Validate input jsonl format
        input_path = vector_dir / "input" / "protocol-sample-01.jsonl"
        try:
            lines = [l.strip() for l in input_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            if not lines:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/input/protocol-sample-01.jsonl",
                        message="Input jsonl file is empty",
                    )
                )
            else:
                for idx, line in enumerate(lines):
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/input/protocol-sample-01.jsonl:line {idx+1}",
                                message=f"Line {idx+1} must be a JSON object",
                            )
                        )
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/input/protocol-sample-01.jsonl",
                    message=f"Failed parsing input jsonl: {e}",
                )
            )

    def _verify_vector_manifest(
        self,
        vector_name: str,
        vector_dir: Path,
        manifest_path: Path,
        expected_dataset_type: str,
        expected_role: str,
        manifest_validator: Optional[jsonschema.Draft202012Validator],
        result: VerificationResult,
    ) -> None:
        rel_manifest = manifest_path.relative_to(self.repo_root)
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=str(rel_manifest),
                    message=f"Invalid JSON in dataset manifest: {e}",
                )
            )
            return

        result.manifest_count += 1

        # Validate with JSON Schema
        if manifest_validator:
            try:
                manifest_validator.validate(m_data)
            except jsonschema.ValidationError as e:
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Manifest schema validation failed: {e.message}",
                    )
                )

        # dataset_type check
        actual_type = m_data.get("dataset_type")
        if actual_type != expected_dataset_type:
            result.errors.append(
                VerificationError(
                    context=str(rel_manifest),
                    message=f"dataset_type mismatch in manifest",
                    expected=expected_dataset_type,
                    actual=str(actual_type),
                )
            )

        files = m_data.get("files", [])
        if not isinstance(files, list):
            result.errors.append(
                VerificationError(
                    context=str(rel_manifest),
                    message="'files' field must be a list",
                )
            )
            return

        # Check role presence and uniqueness
        matching_roles = [f for f in files if isinstance(f, dict) and f.get("role") == expected_role]
        if len(matching_roles) != 1:
            result.errors.append(
                VerificationError(
                    context=str(rel_manifest),
                    message=f"Manifest must contain exactly one file entry with role '{expected_role}'",
                    expected=f"1 entry with role '{expected_role}'",
                    actual=f"{len(matching_roles)} entries",
                )
            )

        # Check for duplicate roles
        roles = [f.get("role") for f in files if isinstance(f, dict)]
        if len(roles) != len(set(roles)):
            result.errors.append(
                VerificationError(
                    context=str(rel_manifest),
                    message="Duplicate roles declared in files list",
                    expected="All file roles must be unique",
                    actual=str(roles),
                )
            )

        # Verify each payload file
        manifest_dir = manifest_path.parent
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue

            declared_path_str = file_entry.get("path")
            declared_sha = file_entry.get("sha256")
            declared_size = file_entry.get("size_bytes")

            if not declared_path_str:
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message="File entry missing 'path'",
                    )
                )
                continue

            # Path safety checks: must be relative, no '..', not absolute
            is_absolute_path = (
                declared_path_str.startswith("/")
                or declared_path_str.startswith("\\")
                or os.path.isabs(declared_path_str)
                or Path(declared_path_str).is_absolute()
                or (len(declared_path_str) > 1 and declared_path_str[1] == ":")
            )
            if is_absolute_path:
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Payload path must not be absolute: '{declared_path_str}'",
                    )
                )
                continue

            if ".." in Path(declared_path_str).parts:
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Payload path must not traverse parent directories (..): '{declared_path_str}'",
                    )
                )
                continue

            target_path = (manifest_dir / declared_path_str).resolve()
            # Ensure resolved path is inside manifest_dir / vector_dir
            try:
                target_path.relative_to(vector_dir.resolve())
            except ValueError:
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Payload path resolves outside vector directory: '{declared_path_str}'",
                    )
                )
                continue

            if not target_path.is_file():
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Declared payload file does not exist: {target_path}",
                    )
                )
                continue

            # SHA-256 check
            actual_sha = compute_sha256(target_path)
            if declared_sha and actual_sha.lower() != declared_sha.lower():
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Payload SHA-256 checksum mismatch for '{declared_path_str}'",
                        expected=str(declared_sha),
                        actual=str(actual_sha),
                    )
                )

            # File size check
            actual_size = target_path.stat().st_size
            if declared_size is not None and actual_size != declared_size:
                result.errors.append(
                    VerificationError(
                        context=str(rel_manifest),
                        message=f"Payload size_bytes mismatch for '{declared_path_str}'",
                        expected=f"{declared_size} bytes",
                        actual=f"{actual_size} bytes",
                    )
                )

            result.payload_count += 1

    def _verify_vector_expected(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        expected_dir = vector_dir / "expected"

        try:
            feat_cols = json.loads((expected_dir / "feature_columns.json").read_text(encoding="utf-8"))
            labels = json.loads((expected_dir / "labels.json").read_text(encoding="utf-8"))
            row_meta = json.loads((expected_dir / "row_metadata.json").read_text(encoding="utf-8"))
            summary = json.loads((expected_dir / "summary.json").read_text(encoding="utf-8"))
        except Exception as e:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected",
                    message=f"Failed to parse expected JSON file: {e}",
                )
            )
            return

        # 1. feature_columns consistency
        cols = feat_cols.get("columns", [])
        col_count = feat_cols.get("count")
        if not isinstance(cols, list) or col_count != len(cols):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/feature_columns.json",
                    message="feature_columns.json count mismatch",
                    expected=f"count == len(columns) ({len(cols)})",
                    actual=f"count: {col_count}",
                )
            )

        # 2. labels array consistency
        if not isinstance(labels, list):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/labels.json",
                    message="labels.json must be a JSON array",
                )
            )
            return

        for idx, label_val in enumerate(labels):
            if label_val not in (0, 1):
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/labels.json",
                        message=f"Invalid label value at index {idx}: {label_val}",
                        expected="0 or 1",
                        actual=str(label_val),
                    )
                )
                break

        # 3. row_metadata consistency
        if not isinstance(row_meta, list):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/row_metadata.json",
                    message="row_metadata.json must be a JSON array",
                )
            )
            return

        for idx, r_item in enumerate(row_meta):
            if not isinstance(r_item, dict) or "asset_id" not in r_item or "timestamp" not in r_item:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/row_metadata.json",
                        message=f"Row metadata entry at index {idx} missing 'asset_id' or 'timestamp'",
                    )
                )
                break

        # 4. Length parity between labels and row_metadata
        if len(labels) != len(row_meta):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected",
                    message="Length mismatch between labels and row_metadata",
                    expected=f"len(labels) == len(row_metadata) ({len(labels)})",
                    actual=f"labels: {len(labels)}, row_metadata: {len(row_meta)}",
                )
            )

        # 5. summary.json consistency
        expected_row_count = summary.get("row_count")
        expected_feat_count = summary.get("feature_count")
        pos_count = summary.get("positive_label_count")
        neg_count = summary.get("negative_label_count")

        if expected_row_count != len(labels):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/summary.json",
                    message="summary.json row_count mismatch",
                    expected=f"row_count == len(labels) ({len(labels)})",
                    actual=f"row_count: {expected_row_count}",
                )
            )

        if expected_feat_count != len(cols):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/summary.json",
                    message="summary.json feature_count mismatch",
                    expected=f"feature_count == len(columns) ({len(cols)})",
                    actual=f"feature_count: {expected_feat_count}",
                )
            )

        actual_pos = sum(1 for x in labels if x == 1)
        actual_neg = sum(1 for x in labels if x == 0)

        if pos_count != actual_pos:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/summary.json",
                    message="summary.json positive_label_count mismatch",
                    expected=f"positive_label_count == {actual_pos}",
                    actual=f"positive_label_count: {pos_count}",
                )
            )

        if neg_count != actual_neg:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/summary.json",
                    message="summary.json negative_label_count mismatch",
                    expected=f"negative_label_count == {actual_neg}",
                    actual=f"negative_label_count: {neg_count}",
                )
            )

        if pos_count is not None and neg_count is not None and (pos_count + neg_count != len(labels)):
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/summary.json",
                    message="Sum of positive and negative label counts does not equal total row_count",
                    expected=f"pos ({pos_count}) + neg ({neg_count}) == {len(labels)}",
                    actual=f"sum: {pos_count + neg_count}",
                )
            )

    def _verify_protocol_extraction_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        """Verify generator-protocol-extraction test vector contracts, schemas, and payload integrity."""
        input_dir = vector_dir / "input"
        expected_dir = vector_dir / "expected"

        if not input_dir.is_dir() or not expected_dir.is_dir():
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message="Missing input/ or expected/ directory in test vector",
                )
            )
            return

        # 1. Validate input protocol records schema
        records_path = input_dir / "protocol-records.jsonl"
        if not records_path.is_file():
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/input",
                    message="Missing input/protocol-records.jsonl",
                )
            )
            return

        rec_schema_path = self.schemas_dir / "generator-protocol-record.schema.json"
        if rec_schema_path.is_file():
            try:
                rec_schema = json.loads(rec_schema_path.read_text(encoding="utf-8"))
                rec_validator = jsonschema.Draft202012Validator(rec_schema, format_checker=jsonschema.FormatChecker())
                with open(records_path, "r", encoding="utf-8") as f:
                    for line_no, line in enumerate(f, start=1):
                        stripped = line.strip()
                        if not stripped:
                            continue
                        rec_item = json.loads(stripped)
                        rec_validator.validate(rec_item)
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/input/protocol-records.jsonl",
                        message=f"Protocol record validation failed: {exc}",
                    )
                )

        # 2. Validate static mapping table schema
        mapping_path = input_dir / "static-mapping-table.json"
        if not mapping_path.is_file():
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/input",
                    message="Missing input/static-mapping-table.json",
                )
            )
            return

        map_schema_path = self.schemas_dir / "generator-static-mapping-table.schema.json"
        if map_schema_path.is_file():
            try:
                map_schema = json.loads(map_schema_path.read_text(encoding="utf-8"))
                map_validator = jsonschema.Draft202012Validator(map_schema, format_checker=jsonschema.FormatChecker())
                map_data = json.loads(mapping_path.read_text(encoding="utf-8"))
                map_validator.validate(map_data)
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/input/static-mapping-table.json",
                        message=f"Static mapping table validation failed: {exc}",
                    )
                )

        # 2.5 Validate source-run-manifest.json if present
        source_manifest_path = input_dir / "source-run-manifest.json"
        if source_manifest_path.is_file():
            run_manifest_schema_path = self.schemas_dir / "generator-protocol-run-manifest.schema.json"
            if run_manifest_schema_path.is_file():
                try:
                    run_man_schema = json.loads(run_manifest_schema_path.read_text(encoding="utf-8"))
                    run_man_validator = jsonschema.Draft202012Validator(run_man_schema, format_checker=jsonschema.FormatChecker())
                    run_man_data = json.loads(source_manifest_path.read_text(encoding="utf-8"))
                    run_man_validator.validate(run_man_data)
                    result.manifest_count += 1
                except Exception as exc:
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/input/source-run-manifest.json",
                            message=f"Source run manifest validation failed: {exc}",
                        )
                    )

        # 3. Validate dataset_manifest.json in expected/
        manifest_path = expected_dir / "dataset_manifest.json"
        if not manifest_path.is_file():
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected",
                    message="Missing expected/dataset_manifest.json",
                )
            )
            return

        manifest_schema_path = self.schemas_dir / "generator-dataset-input-manifest.schema.json"
        if manifest_schema_path.is_file():
            try:
                man_schema = json.loads(manifest_schema_path.read_text(encoding="utf-8"))
                man_validator = jsonschema.Draft202012Validator(man_schema, format_checker=jsonschema.FormatChecker())
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                man_validator.validate(manifest_data)
                result.manifest_count += 1

                # Verify auxiliary files structure: exactly 1 provenance, 1 rejected
                aux_files = manifest_data.get("auxiliary_files", [])
                aux_roles = [f.get("role") for f in aux_files]
                if aux_roles != ["provenance", "rejected"] and set(aux_roles) != {"provenance", "rejected"}:
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/expected/dataset_manifest.json",
                            message=f"auxiliary_files must contain exactly one 'provenance' and one 'rejected' role, got {aux_roles}",
                        )
                    )

                # Verify files declared in manifest
                all_declared_files = list(manifest_data.get("files", [])) + list(manifest_data.get("auxiliary_files", []))
                for file_entry in all_declared_files:
                    rel_path = file_entry.get("path")
                    target_file = expected_dir / rel_path
                    if not target_file.is_file():
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/dataset_manifest.json",
                                message=f"Declared manifest file '{rel_path}' does not exist",
                            )
                        )
                        continue

                    actual_sha = compute_sha256(target_file)
                    expected_sha = file_entry.get("sha256")
                    if expected_sha and actual_sha != expected_sha:
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/{rel_path}",
                                message=f"SHA-256 mismatch for '{rel_path}'",
                                expected=expected_sha,
                                actual=actual_sha,
                            )
                        )

                    actual_size = target_file.stat().st_size
                    expected_size = file_entry.get("size_bytes")
                    if expected_size is not None and actual_size != expected_size:
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/{rel_path}",
                                message=f"size_bytes mismatch for '{rel_path}'",
                                expected=str(expected_size),
                                actual=str(actual_size),
                            )
                        )
                    result.payload_count += 1
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/dataset_manifest.json",
                        message=f"Dataset manifest validation failed: {exc}",
                    )
                )

    def _verify_extraction_runtime_handoff_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        in_dir = vector_dir / "input"
        exp_dir = vector_dir / "expected"
        if not in_dir.is_dir() or not exp_dir.is_dir():
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message="Missing input or expected directory",
                )
            )
            return

        schema_p = self.schemas_dir / "generator-extraction-runtime-handoff.schema.json"
        if not schema_p.is_file():
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message=f"Missing schema file {schema_p}",
                )
            )
            return

        try:
            schema = json.loads(schema_p.read_text(encoding="utf-8"))
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            for jfile in sorted(in_dir.glob("*.json")):
                data = json.loads(jfile.read_text(encoding="utf-8"))
                validator.validate(data)
                result.payload_count += 1
            for jfile in sorted(exp_dir.glob("*.json")):
                data = json.loads(jfile.read_text(encoding="utf-8"))
                validator.validate(data)
                result.payload_count += 1
        except Exception as exc:
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message=f"Handoff vector schema validation failed: {exc}",
                )
            )

    def _verify_pipeline_e2e_vector(
        self,
        vector_name: str,
        vector_dir: Path,
        result: VerificationResult,
    ) -> None:
        """Verify unified generator-pipeline-e2e contract vector from protocol to prediction result batch."""
        in_dir = vector_dir / "input"
        exp_dir = vector_dir / "expected"
        if not in_dir.is_dir() or not exp_dir.is_dir():
            result.errors.append(
                VerificationError(
                    context=vector_name,
                    message="Missing input or expected directory",
                )
            )
            return

        # 1. Validate input/protocol-records.jsonl against generator-protocol-record.schema.json
        rec_schema_p = self.schemas_dir / "generator-protocol-record.schema.json"
        records_path = in_dir / "protocol-records.jsonl"
        if records_path.is_file() and rec_schema_p.is_file():
            try:
                rec_schema = json.loads(rec_schema_p.read_text(encoding="utf-8"))
                rec_val = jsonschema.Draft202012Validator(rec_schema, format_checker=jsonschema.FormatChecker())
                with open(records_path, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if s:
                            rec_val.validate(json.loads(s))
                result.payload_count += 1
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/input/protocol-records.jsonl",
                        message=f"Protocol record validation failed: {exc}",
                    )
                )

        # 2. Validate input/static-mapping-table.json against generator-static-mapping-table.schema.json
        map_schema_p = self.schemas_dir / "generator-static-mapping-table.schema.json"
        mapping_path = in_dir / "static-mapping-table.json"
        if mapping_path.is_file() and map_schema_p.is_file():
            try:
                map_schema = json.loads(map_schema_p.read_text(encoding="utf-8"))
                map_val = jsonschema.Draft202012Validator(map_schema, format_checker=jsonschema.FormatChecker())
                map_data = json.loads(mapping_path.read_text(encoding="utf-8"))
                map_val.validate(map_data)
                result.payload_count += 1
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/input/static-mapping-table.json",
                        message=f"Static mapping table validation failed: {exc}",
                    )
                )

        # 3. Validate expected/dataset_manifest.json against generator-dataset-input-manifest.schema.json
        man_schema_p = self.schemas_dir / "generator-dataset-input-manifest.schema.json"
        manifest_path = exp_dir / "dataset_manifest.json"
        manifest_data = None
        if manifest_path.is_file() and man_schema_p.is_file():
            try:
                man_schema = json.loads(man_schema_p.read_text(encoding="utf-8"))
                man_val = jsonschema.Draft202012Validator(man_schema, format_checker=jsonschema.FormatChecker())
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                man_val.validate(manifest_data)
                result.manifest_count += 1

                for file_entry in list(manifest_data.get("files", [])) + list(manifest_data.get("auxiliary_files", [])):
                    rel_p = file_entry.get("path")
                    target_f = exp_dir / rel_p
                    if not target_f.is_file():
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/{rel_p}",
                                message=f"Declared manifest file '{rel_p}' does not exist",
                            )
                        )
                        continue
                    actual_sha = compute_sha256(target_f)
                    expected_sha = file_entry.get("sha256")
                    if expected_sha and actual_sha != expected_sha:
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/{rel_p}",
                                message=f"SHA-256 mismatch for '{rel_p}'",
                                expected=expected_sha,
                                actual=actual_sha,
                            )
                        )
                    actual_sz = target_f.stat().st_size
                    expected_sz = file_entry.get("size_bytes")
                    if expected_sz is not None and actual_sz != expected_sz:
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/expected/{rel_p}",
                                message=f"size_bytes mismatch for '{rel_p}'",
                                expected=str(expected_sz),
                                actual=str(actual_sz),
                            )
                        )
                    result.payload_count += 1
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/dataset_manifest.json",
                        message=f"Dataset manifest validation failed: {exc}",
                    )
                )

        # 4. Validate expected/runtime-handoff.json against generator-extraction-runtime-handoff.schema.json
        handoff_schema_p = self.schemas_dir / "generator-extraction-runtime-handoff.schema.json"
        handoff_path = exp_dir / "runtime-handoff.json"
        handoff_data = None
        if handoff_path.is_file() and handoff_schema_p.is_file():
            try:
                ho_schema = json.loads(handoff_schema_p.read_text(encoding="utf-8"))
                ho_val = jsonschema.Draft202012Validator(ho_schema, format_checker=jsonschema.FormatChecker())
                handoff_data = json.loads(handoff_path.read_text(encoding="utf-8"))
                ho_val.validate(handoff_data)
                result.payload_count += 1
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/runtime-handoff.json",
                        message=f"Runtime handoff schema validation failed: {exc}",
                    )
                )

        # 5. Validate expected/prediction-result-batch.json against prediction-result-batch.schema.json
        batch_schema_p = self.schemas_dir / "prediction-result-batch.schema.json"
        batch_path = exp_dir / "prediction-result-batch.json"
        batch_data = None
        if batch_path.is_file() and batch_schema_p.is_file():
            try:
                b_schema = json.loads(batch_schema_p.read_text(encoding="utf-8"))
                reg = self._build_schema_registry()
                if reg is not None:
                    b_val = jsonschema.Draft202012Validator(b_schema, registry=reg, format_checker=jsonschema.FormatChecker())
                else:
                    b_val = jsonschema.Draft202012Validator(b_schema, format_checker=jsonschema.FormatChecker())
                batch_data = json.loads(batch_path.read_text(encoding="utf-8"))
                b_val.validate(batch_data)
                result.payload_count += 1
            except Exception as exc:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/prediction-result-batch.json",
                        message=f"Prediction result batch schema validation failed: {exc}",
                    )
                )

        # 6. Verify Deterministic Identity Invariants across the entire chain
        det_path = exp_dir / "deterministic-identities.json"
        if not det_path.is_file():
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected",
                    message="Missing expected/deterministic-identities.json",
                )
            )
            return

        try:
            det_data = json.loads(det_path.read_text(encoding="utf-8"))
            result.payload_count += 1
            required_invariant_keys = {
                "dataset_id",
                "dataset_version",
                "source_uri",
                "source_checksum",
                "source_kind",
                "source_contract_version",
                "source_schema_version",
                "pipeline_contract_version",
                "handoff_id",
                "runtime_job_id",
                "asset_id",
                "model_id",
                "model_version",
            }
            missing_inv = required_invariant_keys - set(det_data.keys())
            if missing_inv:
                result.errors.append(
                    VerificationError(
                        context=f"{vector_name}/expected/deterministic-identities.json",
                        message=f"Missing required deterministic invariant keys: {sorted(missing_inv)}",
                    )
                )

            # Compare with manifest
            if manifest_data:
                if manifest_data.get("dataset_id") != det_data.get("dataset_id"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/dataset_manifest.json",
                            message="dataset_id mismatch with deterministic identities",
                            expected=det_data.get("dataset_id"),
                            actual=manifest_data.get("dataset_id"),
                        )
                    )
                if manifest_data.get("dataset_version") != det_data.get("dataset_version"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/dataset_manifest.json",
                            message="dataset_version mismatch with deterministic identities",
                            expected=det_data.get("dataset_version"),
                            actual=manifest_data.get("dataset_version"),
                        )
                    )

            # Compare with handoff
            if handoff_data:
                if handoff_data.get("handoff_id") != det_data.get("handoff_id"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/runtime-handoff.json",
                            message="handoff_id mismatch with deterministic identities",
                            expected=det_data.get("handoff_id"),
                            actual=handoff_data.get("handoff_id"),
                        )
                    )
                rt_src = handoff_data.get("runtime_input", {}).get("source", {})
                for k in ("source_uri", "source_checksum", "source_kind", "source_contract_version", "source_schema_version", "pipeline_contract_version"):
                    if rt_src.get(k) != det_data.get(k):
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/runtime-handoff.json:runtime_input.source.{k}",
                                message=f"{k} mismatch with deterministic identities",
                                expected=str(det_data.get(k)),
                                actual=str(rt_src.get(k)),
                            )
                        )
                deliv = handoff_data.get("delivery", {})
                if deliv.get("runtime_job_id") != det_data.get("runtime_job_id"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/runtime-handoff.json:delivery.runtime_job_id",
                            message="runtime_job_id mismatch with deterministic identities",
                            expected=det_data.get("runtime_job_id"),
                            actual=deliv.get("runtime_job_id"),
                        )
                    )

            # Compare with prediction batch
            if batch_data:
                b_src = batch_data.get("source_context", {})
                for k in ("dataset_id", "dataset_version", "source_uri", "source_checksum", "source_kind", "source_contract_version", "source_schema_version", "pipeline_contract_version"):
                    if b_src.get(k) != det_data.get(k):
                        result.errors.append(
                            VerificationError(
                                context=f"{vector_name}/prediction-result-batch.json:source_context.{k}",
                                message=f"{k} mismatch with deterministic identities",
                                expected=str(det_data.get(k)),
                                actual=str(b_src.get(k)),
                            )
                        )
                first_res = batch_data.get("results", [{}])[0]
                if first_res.get("asset_id") != det_data.get("asset_id"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/prediction-result-batch.json:results[0].asset_id",
                            message="asset_id mismatch with deterministic identities",
                            expected=det_data.get("asset_id"),
                            actual=first_res.get("asset_id"),
                        )
                    )
                if first_res.get("model_id") != det_data.get("model_id"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/prediction-result-batch.json:results[0].model_id",
                            message="model_id mismatch with deterministic identities",
                            expected=det_data.get("model_id"),
                            actual=first_res.get("model_id"),
                        )
                    )
                if first_res.get("model_version") != det_data.get("model_version"):
                    result.errors.append(
                        VerificationError(
                            context=f"{vector_name}/prediction-result-batch.json:results[0].model_version",
                            message="model_version mismatch with deterministic identities",
                            expected=det_data.get("model_version"),
                            actual=first_res.get("model_version"),
                        )
                    )
        except Exception as exc:
            result.errors.append(
                VerificationError(
                    context=f"{vector_name}/expected/deterministic-identities.json",
                    message=f"Deterministic identity validation failed: {exc}",
                )
            )



def main() -> int:
    verifier = ContractVectorVerifier()
    result = verifier.verify_all()

    if result.passed:
        print(f"PASS schemas: {result.schema_count}")
        print(f"PASS examples: {result.example_count}")
        print(f"PASS vectors: {result.vector_count}")
        print(f"PASS manifests: {result.manifest_count}")
        print(f"PASS payload integrity: {result.payload_count}")
        if result.verified_vectors:
            print(f"PASS expected consistency: {', '.join(result.verified_vectors)}")
        print("Contract vector verification passed.")
        return 0
    else:
        for err in result.errors:
            print(err.format(), file=sys.stderr)
        print(f"\nContract vector verification failed with {len(result.errors)} error(s).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
