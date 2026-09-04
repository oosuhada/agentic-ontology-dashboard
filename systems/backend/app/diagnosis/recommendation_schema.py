from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProducerRecommendation(BaseModel):
    """Diagnosis-owned recommendation contract consumed by Maintenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_action_id: str = Field(min_length=1, max_length=240)
    source_product_result_id: str = Field(min_length=1, max_length=240)
    source_evidence_id: str = Field(min_length=1, max_length=240)
    source_schema_version: str = Field(min_length=1, max_length=160)
    source_policy_version: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=128)
    requires_human_approval: bool
    basis: tuple[str, ...] = Field(min_length=1)

    @property
    def materialization_key(self) -> str:
        return f"{self.source_product_result_id}:{self.source_action_id}"


__all__ = ["ProducerRecommendation"]
