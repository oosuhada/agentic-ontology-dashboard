from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .models import FieldProfile


def _date_like(value: Any) -> bool:
    if isinstance(value, datetime):
        return True
    if not isinstance(value, str) or len(value) < 6 or not re.search(r"[-/:T]", value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _number_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def profile_rows(rows: list[dict[str, Any]], *, sample_limit: int = 500) -> list[FieldProfile]:
    sample = rows[:sample_limit]
    fields = list(dict.fromkeys(key for row in sample for key in row))
    profiles: list[FieldProfile] = []
    for field_id in fields:
        raw = [row.get(field_id) for row in sample]
        present = [value for value in raw if value not in (None, "")]
        numeric = [value for value in present if _number_like(value)]
        dates = [value for value in present if _date_like(value)]
        booleans = [value for value in present if isinstance(value, bool)]
        physical_type = "unknown"
        if present and len(numeric) == len(present):
            physical_type = "number"
        elif present and len(dates) == len(present):
            physical_type = "date"
        elif present and len(booleans) == len(present):
            physical_type = "boolean"
        elif present and all(isinstance(value, str) for value in present):
            physical_type = "string"
        elif present:
            physical_type = "mixed"
        distinct = len({str(value) for value in present})
        ratio = distinct / len(present) if present else 0
        semantic_type = "text"
        if re.search(r"lat(itude)?|lon(gitude)?", field_id, re.IGNORECASE):
            semantic_type = "geo"
        elif re.search(r"(^id$|_id$|uuid|key|code)", field_id, re.IGNORECASE) or (
            len(present) > 4 and ratio > 0.95 and all(isinstance(value, str) for value in present)
        ):
            semantic_type = "identifier"
        elif physical_type == "date" or re.search(r"(date|time|timestamp|month|week|year|day)$", field_id, re.IGNORECASE):
            semantic_type = "temporal"
        elif physical_type == "number":
            semantic_type = "quantitative"
        elif physical_type == "boolean":
            semantic_type = "boolean"
        elif distinct <= max(12, int(len(present) * 0.2 + 0.99)):
            semantic_type = "categorical"
        comparable: list[float | str] = []
        if semantic_type == "quantitative":
            comparable = sorted(float(value) for value in present if _number_like(value))
        elif semantic_type == "temporal":
            comparable = sorted(str(value) for value in present)
        profiles.append(
            FieldProfile(
                id=field_id,
                semantic_type=semantic_type,
                physical_type=physical_type,
                null_ratio=(len(sample) - len(present)) / len(sample) if sample else 0,
                distinct_count=distinct,
                cardinality_ratio=ratio,
                min=comparable[0] if comparable else None,
                max=comparable[-1] if comparable else None,
                sample_values=present[:5],
            )
        )
    return profiles
