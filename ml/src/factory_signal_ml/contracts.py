"""Compatibility imports for the pre-systems ML package.

Operational ownership has moved to ``systems/generator`` for model development
and ``systems/backend/app/diagnosis`` for runtime inference/Evidence.
"""

from systems.backend.app.diagnosis.contracts import (  # noqa: F401
    DERIVED_COLUMNS,
    DISPLAY_NAMES,
    SENSOR_RANGES,
    UNITS,
    QualityIssue,
    audit_fixture,
    derive_features,
    fixture_paths,
    load_fixture,
    load_json,
    project_root,
    schema_path,
)
from systems.generator.feature.contracts import (  # noqa: F401
    FAILURE_MODE_COLUMNS,
    IDENTIFIER_COLUMNS,
    MODEL_INPUT_COLUMNS,
    TARGET_COLUMN,
    assert_no_leakage,
    file_sha256,
)
