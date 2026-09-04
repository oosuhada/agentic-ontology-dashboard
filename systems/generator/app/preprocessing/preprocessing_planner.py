"""Planner for data structure classification and column preprocessing rules."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional
import pandas as pd

import systems.generator.generator_llm_client as generator_llm_client
from systems.generator.app.preprocessing.preprocessing_schema import (
    PreprocessingStructureResponse,
    PreprocessingPlanResponse,
)
from systems.generator.app.preprocessing.preprocessing_exception import (
    PreprocessingRoleError,
    PreprocessingPlanningError,
)

logger = logging.getLogger(__name__)

PLANNER_VERSION = "preprocessing-planner-v1"


class PreprocessingPlanner:
    """Handles 2-stage analysis (structure classification & column planning) with strict validation and provenance tracking."""

    def __init__(self) -> None:
        self._last_s1_provenance: tuple[bool, Optional[str]] = (False, None)
        self._last_s2_provenance: tuple[bool, Optional[str]] = (False, None)

    def compute_fingerprint(self, df_preview: pd.DataFrame) -> str:
        raw_str = f"cols:{list(df_preview.columns)}|head:{df_preview.head(3).to_json()}"
        return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

    def classify_structure(self, filepath: str, df_preview: pd.DataFrame) -> str:
        """Stage 1: Classify table format into supported structure types."""
        system_prompt = (
            "You are a manufacturing data structure classifier.\n"
            "Classify the input table format into EXACTLY ONE of the following structure types:\n"
            "- tabular_column_as_attribute: Standard table where each column is an attribute/sensor feature.\n"
            "- tabular_row_as_attribute: Long format table where rows contain sensor attribute names and values.\n\n"
            "Respond ONLY with a JSON object: {\"structure_type\": \"...\", \"reason\": \"...\"}"
        )
        prompt = f"File: {os.path.basename(filepath)}\nColumns: {list(df_preview.columns)}\nSample:\n{df_preview.head(3).to_string()}"

        try:
            raw_res = generator_llm_client.call_llm(prompt, system=system_prompt)
            res = generator_llm_client.validate_or_transform_pydantic(raw_res, PreprocessingStructureResponse)
            if res and res.structure_type:
                st_type = res.structure_type
                logger.info(f"[PreprocessingPlanner] Stage 1 structure classification for '{filepath}': {st_type}")
                self._last_s1_provenance = (False, None)
                return st_type
            else:
                logger.warning(f"[PreprocessingPlanner] Stage 1 classification returned empty or invalid response")
                self._last_s1_provenance = (True, "response_validation_failed")
                return "tabular_column_as_attribute"
        except Exception as e:
            logger.warning(f"[PreprocessingPlanner] Stage 1 classification fallback: {e}")
            self._last_s1_provenance = (True, "llm_call_failed")
            return "tabular_column_as_attribute"

    def plan_columns(
        self,
        filepath: str,
        structure_type: str,
        df_preview: pd.DataFrame,
        duplicate_policy: str = "error",
        aggregation: Optional[str] = None,
    ) -> dict[str, Any]:
        """Stage 2: Determine column roles and preprocessing mapping."""
        if structure_type not in ("tabular_column_as_attribute", "tabular_row_as_attribute"):
            raise PreprocessingPlanValidationError(f"지원하지 않는 structure_type입니다: '{structure_type}'")

        avail_cols = list(df_preview.columns)
        if structure_type == "tabular_row_as_attribute":
            system_prompt = (
                "You are a dataset preprocessing planner for long-format (tabular_row_as_attribute) manufacturing sensor data.\n"
                "Analyze the columns and sample data, then specify the exact role for each column:\n"
                "- id_column: The asset/machine identifier column.\n"
                "- time_column: The timestamp column (if present, else null).\n"
                "- attribute_column: The sensor/feature attribute name column.\n"
                "- value_column: The numeric measurement value column.\n"
                "- selected_columns: List of all relevant columns.\n"
                "Respond ONLY with a JSON object: {\n"
                '  "structure_type": "tabular_row_as_attribute",\n'
                '  "id_column": "col_id",\n'
                '  "time_column": "col_time",\n'
                '  "attribute_column": "col_attr",\n'
                '  "value_column": "col_val",\n'
                '  "duplicate_policy": "error",\n'
                '  "selected_columns": ["col1", "col2", ...]\n'
                "}"
            )
        else:
            system_prompt = (
                "You are a dataset column selector for manufacturing predictive maintenance.\n"
                "Select all relevant telemetry sensors, time/date fields, and asset identifiers for model analysis.\n"
                "Respond ONLY with a JSON object: {\"selected_columns\": [\"col1\", \"col2\", ...]}"
            )

        prompt = (
            f"File: {os.path.basename(filepath)}\n"
            f"Structure Type: {structure_type}\n"
            f"Available Columns: {avail_cols}\n"
            f"Sample:\n{df_preview.head(3).to_string()}"
        )

        stage2_fallback_reason: Optional[str] = None
        try:
            raw_res = generator_llm_client.call_llm(prompt, system=system_prompt)
            res = generator_llm_client.validate_or_transform_pydantic(raw_res, PreprocessingPlanResponse)
            if res:
                if structure_type == "tabular_row_as_attribute":
                    roles = [res.id_column, res.attribute_column, res.value_column]
                    if not all(roles) or not all(r in avail_cols for r in roles):
                        raise PreprocessingRoleError(
                            f"Long-format preprocessing requires explicit id, attribute, and value columns; "
                            f"roles {roles} not fully found in columns {avail_cols}"
                        )
                cols = res.selected_columns if res.selected_columns else avail_cols
                self._last_s2_provenance = (False, None)
                return {
                    "structure_type": structure_type,
                    "selected_columns": cols,
                    "id_column": res.id_column,
                    "time_column": res.time_column,
                    "attribute_column": res.attribute_column,
                    "value_column": res.value_column,
                    "duplicate_policy": duplicate_policy or res.duplicate_policy or "error",
                    "aggregation": aggregation or res.aggregation,
                    "decision_source": "llm",
                    "fallback_reason": None,
                }
            else:
                stage2_fallback_reason = "response_validation_failed"
        except PreprocessingRoleError:
            raise
        except Exception as e:
            logger.warning(f"[PreprocessingPlanner] Stage 2 column selection LLM call failed: {e}")
            if structure_type == "tabular_row_as_attribute":
                raise PreprocessingRoleError(
                    f"Long-format preprocessing requires explicit role columns (id, attribute, value). "
                    f"Planning failed: {e}"
                ) from e
            stage2_fallback_reason = "llm_call_failed"

        id_candidates = ["asset_id", "machineID", "Product ID", "product_id", "equipment_id", "device_id", "asset", "machine", "UDI", "udi"]
        time_candidates = ["observed_at", "datetime", "timestamp", "time", "date"]

        found_id = next((c for c in id_candidates if c in avail_cols), None)
        found_time = next((c for c in time_candidates if c in avail_cols), None)

        self._last_s2_provenance = (True, stage2_fallback_reason or "column_planning_fallback")
        return {
            "structure_type": structure_type,
            "id_column": found_id,
            "time_column": found_time,
            "selected_columns": avail_cols,
            "duplicate_policy": duplicate_policy,
            "aggregation": aggregation,
            "decision_source": "rule_fallback",
            "fallback_reason": stage2_fallback_reason or "column_planning_fallback",
        }

    def enforce_key_columns(self, selected_columns: list[str], available_columns: list[str]) -> list[str]:
        """Preserve key machine and timestamp column identifiers if present in available columns."""
        result = list(selected_columns)
        id_candidates = ["asset_id", "machineID", "Product ID", "product_id", "equipment_id", "device_id", "asset", "machine", "UDI", "udi"]
        time_candidates = ["observed_at", "datetime", "timestamp", "time", "date"]

        has_id = any(c in result for c in id_candidates)
        if not has_id:
            found_id = next((c for c in id_candidates if c in available_columns), None)
            if found_id and found_id not in result:
                result.append(found_id)

        has_time = any(c in result for c in time_candidates)
        if not has_time:
            found_time = next((c for c in time_candidates if c in available_columns), None)
            if found_time and found_time not in result:
                result.append(found_time)

        return result

    def build_plan(
        self,
        filepath: str,
        force_reanalyze: bool = False,
        duplicate_policy: str = "error",
        aggregation: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build preprocessing plan from preview data and LLM analysis with full provenance tracking."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".csv":
            df_preview = pd.read_csv(filepath, nrows=5)
        elif ext in (".xlsx", ".xls"):
            df_preview = pd.read_excel(filepath, nrows=5)
        elif ext == ".jsonl":
            df_preview = pd.read_json(filepath, lines=True, nrows=5)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        fingerprint = self.compute_fingerprint(df_preview)
        file_key = os.path.basename(filepath)

        self._last_s1_provenance = (False, None)
        self._last_s2_provenance = (False, None)

        # Stage 1: Structure classification
        structure_type = self.classify_structure(filepath, df_preview)
        if structure_type == "unsupported":
            raise PreprocessingPlanningError(f"File '{filepath}' classified as unsupported format.")

        # Stage 2: Column planning
        stage2_plan = self.plan_columns(
            filepath,
            structure_type,
            df_preview,
            duplicate_policy=duplicate_policy,
            aggregation=aggregation,
        )

        raw_selected = stage2_plan.get("selected_columns", list(df_preview.columns))
        final_selected = self.enforce_key_columns(raw_selected, list(df_preview.columns))

        # Check provenance from Stage 1 & Stage 2
        fallback_reasons = []
        s1_fallback, s1_reason = getattr(self, "_last_s1_provenance", (False, None))
        if s1_fallback:
            fallback_reasons.append(f"stage1: {s1_reason or 'structure_classification_fallback'}")

        s2_fallback, s2_reason = getattr(self, "_last_s2_provenance", (False, None))
        if stage2_plan.get("decision_source") == "rule_fallback" or s2_fallback:
            reason = stage2_plan.get("fallback_reason") or s2_reason or "column_planning_fallback"
            if not any(r.startswith("stage2:") for r in fallback_reasons):
                fallback_reasons.append(f"stage2: {reason}")

        if fallback_reasons:
            decision_source = "rule_fallback"
            fallback_reason = "; ".join(fallback_reasons)
        else:
            decision_source = "llm"
            fallback_reason = None

        plan = {
            "filepath": filepath,
            "filename": file_key,
            "fingerprint": fingerprint,
            "structure_type": structure_type,
            "selected_columns": final_selected,
            "id_column": stage2_plan.get("id_column"),
            "time_column": stage2_plan.get("time_column"),
            "attribute_column": stage2_plan.get("attribute_column"),
            "value_column": stage2_plan.get("value_column"),
            "duplicate_policy": stage2_plan.get("duplicate_policy", duplicate_policy),
            "aggregation": stage2_plan.get("aggregation", aggregation),
            "decision_source": decision_source,
            "fallback_reason": fallback_reason,
            "planner_version": PLANNER_VERSION,
        }
        return plan
