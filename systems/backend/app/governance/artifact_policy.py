from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

RetentionClass = Literal["ephemeral", "standard", "regulated", "backup", "legal_hold"]


class RetentionPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    retention_class: RetentionClass
    retain_until: datetime | None = None
    legal_hold: bool = False


class RetentionPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["retain", "delete", "skip_legal_hold"]
    reason: str


def evaluate_retention(
    policy: RetentionPolicyInput,
    *,
    now: datetime,
) -> RetentionPolicyDecision:
    if policy.legal_hold or policy.retention_class == "legal_hold":
        return RetentionPolicyDecision(
            action="skip_legal_hold",
            reason="legal hold blocks deletion",
        )
    if policy.retain_until is not None and policy.retain_until <= now:
        return RetentionPolicyDecision(
            action="delete",
            reason="retention period expired",
        )
    return RetentionPolicyDecision(
        action="retain",
        reason="retention period remains active",
    )


__all__ = [
    "RetentionClass",
    "RetentionPolicyDecision",
    "RetentionPolicyInput",
    "evaluate_retention",
]
