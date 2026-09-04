"""Configuration loading for the gen_data simulator."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def _load_local_dotenv(path: Path = ROOT_DIR / ".env") -> None:
    """Load a small KEY=VALUE .env file without requiring a third-party package."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_dotenv()

DEFAULT_OUTPUT_DIR = str(ROOT_DIR / "output")
_raw_output_dir = os.environ.get("GEN_DATA_OUTPUT_DIR", "").strip()
if _raw_output_dir:
    GEN_DATA_OUTPUT_DIR = _raw_output_dir
    OUTPUT_DIR_SOURCE = "env"
else:
    GEN_DATA_OUTPUT_DIR = DEFAULT_OUTPUT_DIR
    OUTPUT_DIR_SOURCE = "default_fallback"

DEFAULTS: dict[str, object] = {
    "GEN_DATA_OPCUA_ENDPOINT": "opc.tcp://127.0.0.1:4840/gen-data/",
    "GEN_DATA_API_HOST": "127.0.0.1",
    "GEN_DATA_API_PORT": 8000,
}


def _load_generation_settings() -> tuple[dict[str, object], str]:
    configured_path = os.environ.get("GEN_DATA_SETTING_CONFIG_PATH", "").strip()
    config_path = Path(configured_path) if configured_path else ROOT_DIR / "setting.config"
    if not config_path.exists():
        return dict(DEFAULTS), "hardcoded_default"

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"setting.config must contain a JSON object: {config_path}")
    return {**DEFAULTS, **payload}, "setting.config"


_settings, SETTINGS_SOURCE = _load_generation_settings()
GEN_DATA_OPCUA_ENDPOINT = os.environ.get(
    "GEN_DATA_OPCUA_ENDPOINT", str(_settings["GEN_DATA_OPCUA_ENDPOINT"])
)
GEN_DATA_API_HOST = os.environ.get("GEN_DATA_API_HOST", str(_settings["GEN_DATA_API_HOST"]))
GEN_DATA_API_PORT = int(os.environ.get("GEN_DATA_API_PORT", _settings["GEN_DATA_API_PORT"]))
_raw_overlay_event_file = os.environ.get(
    "GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE", ""
).strip()
GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE = (
    Path(_raw_overlay_event_file) if _raw_overlay_event_file else None
)
GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS = int(
    os.environ.get("GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS", "36")
)
if not 0 <= GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS <= 10_000:
    raise ValueError(
        "GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS must be between 0 and 10000"
    )

GEN_DATA_AUTOSTART_CONTINUOUS = os.environ.get(
    "GEN_DATA_AUTOSTART_CONTINUOUS", "0"
).strip().lower() in {"1", "true", "yes", "on"}
GEN_DATA_AUTOSTART_SPEED = float(os.environ.get("GEN_DATA_AUTOSTART_SPEED", "60"))
GEN_DATA_AUTOSTART_BACKFILL_HOURS = int(
    os.environ.get("GEN_DATA_AUTOSTART_BACKFILL_HOURS", "168")
)
GEN_DATA_AUTOSTART_DURATION_HOURS = int(
    os.environ.get("GEN_DATA_AUTOSTART_DURATION_HOURS", "8760")
)
if GEN_DATA_AUTOSTART_SPEED <= 0:
    raise ValueError("GEN_DATA_AUTOSTART_SPEED must be positive")
if GEN_DATA_AUTOSTART_BACKFILL_HOURS < 6:
    raise ValueError("GEN_DATA_AUTOSTART_BACKFILL_HOURS must be at least 6")
if GEN_DATA_AUTOSTART_DURATION_HOURS <= GEN_DATA_AUTOSTART_BACKFILL_HOURS:
    raise ValueError(
        "GEN_DATA_AUTOSTART_DURATION_HOURS must exceed the backfill horizon"
    )
