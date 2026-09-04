"""Pure, non-mutating intervention policy transforms."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import ToolReplacementPolicy


def apply_tool_replacement(
    observation: dict[str, Any],
    policy: ToolReplacementPolicy,
) -> dict[str, Any]:
    """Return a maintenance-state copy with tool wear reset by policy.

    This function does not score the result or fabricate subsequent sensor
    rows. The timeline generator must later rebuild the post-action window
    before the unchanged prediction model is called.
    """

    if observation.get("tool_wear_min") is None:
        raise ValueError("tool replacement requires tool_wear_min")
    try:
        current_wear = float(observation["tool_wear_min"])
    except (TypeError, ValueError) as exc:
        raise ValueError("tool_wear_min must be numeric") from exc
    if current_wear < 0:
        raise ValueError("tool_wear_min must not be negative")

    transformed = deepcopy(observation)
    transformed["tool_wear_min"] = policy.tool_wear_after
    transformed["is_operating"] = 0
    transformed["operating_state"] = "maintenance"
    return transformed
