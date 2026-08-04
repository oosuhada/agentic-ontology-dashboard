#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from ontology_dashboard.modeling.schema import adaptive_modeling_schema


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "schemas" / "adaptive-modeling.schema.json"


def main() -> int:
    TARGET.write_text(
        json.dumps(adaptive_modeling_schema(), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
