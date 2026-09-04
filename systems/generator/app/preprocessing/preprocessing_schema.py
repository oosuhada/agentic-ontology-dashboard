"""Pydantic schemas and contract definitions for preprocessing domain."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator


# --- Supported Structure Types ---

SupportedStructureType = Literal[
    "tabular_column_as_attribute",
    "tabular_row_as_attribute",
]


# --- Preprocessing Plan LLM Schemas ---

class PreprocessingStructureResponse(BaseModel):
    structure_type: SupportedStructureType = "tabular_column_as_attribute"
    reason: Optional[str] = None


class PreprocessingColumnsResponse(BaseModel):
    selected_columns: list[str] = Field(default_factory=list)


class PreprocessingPlanResponse(BaseModel):
    structure_type: SupportedStructureType = "tabular_column_as_attribute"
    selected_columns: list[str] = Field(default_factory=list)
    id_column: Optional[str] = None
    time_column: Optional[str] = None
    attribute_column: Optional[str] = None
    value_column: Optional[str] = None
    duplicate_policy: Literal["error", "aggregate"] = "error"
    aggregation: Optional[Literal["mean", "first", "sum"]] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _validate_contract_rules(self) -> "PreprocessingPlanResponse":
        if self.duplicate_policy == "aggregate" and self.aggregation is None:
            raise ValueError("duplicate_policy='aggregate' requires a non-null aggregation")
        if self.duplicate_policy == "error" and self.aggregation is not None:
            raise ValueError("duplicate_policy='error' must not specify an aggregation")

        if self.structure_type == "tabular_row_as_attribute":
            if not self.id_column or not str(self.id_column).strip():
                raise ValueError("Long-format preprocessing (tabular_row_as_attribute) requires an explicit 'id_column'")
            if not self.attribute_column or not str(self.attribute_column).strip():
                raise ValueError("Long-format preprocessing (tabular_row_as_attribute) requires an explicit 'attribute_column'")
            if not self.value_column or not str(self.value_column).strip():
                raise ValueError("Long-format preprocessing (tabular_row_as_attribute) requires an explicit 'value_column'")

            roles = [self.id_column, self.attribute_column, self.value_column]
            if self.time_column and str(self.time_column).strip():
                roles.append(self.time_column)

            if len(roles) != len(set(roles)):
                raise ValueError(f"Long-format role columns must be unique and cannot overlap: {roles}")

            if self.selected_columns:
                missing_in_selected = [r for r in roles if r not in self.selected_columns]
                if missing_in_selected:
                    raise ValueError(f"Long-format role columns {missing_in_selected} must be present in selected_columns")

        if self.structure_type == "tabular_column_as_attribute":
            if self.selected_columns:
                if self.id_column and str(self.id_column).strip() and self.id_column not in self.selected_columns:
                    raise ValueError(f"Wide-format id_column '{self.id_column}' must be present in selected_columns")
                if self.time_column and str(self.time_column).strip() and self.time_column not in self.selected_columns:
                    raise ValueError(f"Wide-format time_column '{self.time_column}' must be present in selected_columns")

        return self


# --- API Request & Response Schemas ---

class PreprocessingRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, description="Dataset identifier")
    dataset_version: str = Field(..., min_length=1, description="Dataset version string")
    source_uri: Optional[str] = Field(None, description="Optional relative source URI or dataset path")
    force_reanalyze: bool = Field(False, description="Force re-analyzing plan even if cached")
    duplicate_policy: Literal["error", "aggregate"] = Field("error", description="Duplicate handling policy")
    aggregation: Optional[Literal["mean", "first", "sum"]] = Field(None, description="Aggregation function if duplicate_policy='aggregate'")

    model_config = {
        "extra": "forbid",
    }

    @model_validator(mode="after")
    def _validate_duplicate_aggregation(self) -> "PreprocessingRequest":
        if self.duplicate_policy == "aggregate" and self.aggregation is None:
            raise ValueError("duplicate_policy='aggregate' requires a non-null aggregation ('mean', 'first', or 'sum')")
        if self.duplicate_policy == "error" and self.aggregation is not None:
            raise ValueError("duplicate_policy='error' must not specify an aggregation")
        return self


class PreprocessingResultPayload(BaseModel):
    structure_type: SupportedStructureType = "tabular_column_as_attribute"
    id_column: Optional[str] = None
    time_column: Optional[str] = None
    attribute_column: Optional[str] = None
    value_column: Optional[str] = None
    duplicate_policy: Literal["error", "aggregate"] = "error"
    aggregation: Optional[Literal["mean", "first", "sum"]] = None
    preprocessing_plan_uri: str
    preprocessing_plan_sha256: str


class PreprocessingResponse(BaseModel):
    request_id: str
    run_id: str
    status: Literal["succeeded"] = "succeeded"
    dataset_id: str
    dataset_version: str
    preprocessing_plan_id: str
    preprocessing_plan_version: str
    result: PreprocessingResultPayload


# --- Error Envelope Schemas ---

class ErrorDetail(BaseModel):
    loc: list[str | int] = Field(default_factory=list)
    msg: str
    type: str


class ErrorEnvelopeBody(BaseModel):
    code: str
    message: str
    path: str
    request_id: str
    error_id: str
    details: list[Any] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    error: ErrorEnvelopeBody
