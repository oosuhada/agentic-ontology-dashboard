"""Identity computation and prefix integrity verification for gen_data append sources."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from systems.generator.app.extraction.extraction_exception import (
    ExtractionSourceNotFoundError,
    ExtractionSourcePrefixMismatchError,
    ExtractionSourceTruncatedError,
)

logger = logging.getLogger(__name__)

PREFIX_VERIFICATION_MAX_BYTES = 65536


def compute_gen_data_source_lock_identity(
    *,
    source_uri: str,
    site_id: str,
    cell_id: str,
    source_format: str = "gen_data_sensor_stream",
) -> str:
    """Compute deterministic SHA-256 lock identity for a logical source scope.

    Lock identity binds only logical coordinate fields without content dependency:
    - logical source_uri
    - site_id and cell_id
    - source_format
    """
    payload = {
        "cell_id": cell_id,
        "site_id": site_id,
        "source_format": source_format,
        "source_uri": source_uri,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_gen_data_source_identity(
    *,
    source_uri: str,
    site_id: str,
    cell_id: str,
    first_record_sha256: str,
    source_format: str = "gen_data_sensor_stream",
) -> str:
    """Compute deterministic SHA-256 identity for a gen_data sensor stream source.

    Identity binds:
    - logical source_uri
    - site_id and cell_id
    - first completed record raw sha256
    - source_format
    """
    payload = {
        "cell_id": cell_id,
        "first_record_sha256": first_record_sha256,
        "site_id": site_id,
        "source_format": source_format,
        "source_uri": source_uri,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_extraction_batch_id(
    *,
    source_identity: str,
    source_start_offset: int,
    source_end_offset: int,
    mapping_sha256: str,
) -> str:
    """Compute deterministic SHA-256 batch_id for an extraction slice."""
    payload = {
        "mapping_sha256": mapping_sha256,
        "source_end_offset": source_end_offset,
        "source_identity": source_identity,
        "source_start_offset": source_start_offset,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_source_prefix_info(source_path: Path, committed_offset: int) -> tuple[int, str]:
    """Compute verified prefix length and SHA-256 for a committed source offset."""
    path = Path(source_path).resolve()
    if not path.is_file():
        raise ExtractionSourceNotFoundError(f"Source file not found: {path}")

    prefix_len = min(committed_offset, PREFIX_VERIFICATION_MAX_BYTES)
    with open(path, "rb") as f:
        prefix_bytes = f.read(prefix_len)

    if len(prefix_bytes) < prefix_len:
        raise ExtractionSourceTruncatedError(
            f"Source file '{path}' is smaller ({len(prefix_bytes)} bytes) than expected prefix length ({prefix_len} bytes)"
        )

    prefix_sha = hashlib.sha256(prefix_bytes).hexdigest()
    return prefix_len, prefix_sha


def verify_source_prefix(
    *,
    source_path: Path,
    expected_length: int,
    expected_sha256: str,
    last_committed_offset: int,
) -> None:
    """Verify source file integrity against recorded prefix checksum and committed offset.

    Detects:
    - File truncation (file size < last_committed_offset or < expected_length)
    - File replacement (prefix SHA-256 mismatch)
    """
    path = Path(source_path).resolve()
    if not path.is_file():
        raise ExtractionSourceNotFoundError(f"Source file not found: {path}")

    current_size = path.stat().st_size
    if current_size < last_committed_offset:
        raise ExtractionSourceTruncatedError(
            f"Source file '{path}' size ({current_size} bytes) is smaller than last committed offset ({last_committed_offset} bytes). File was truncated."
        )

    if expected_length == 0:
        return

    if current_size < expected_length:
        raise ExtractionSourceTruncatedError(
            f"Source file '{path}' size ({current_size} bytes) is smaller than verified prefix length ({expected_length} bytes)."
        )

    with open(path, "rb") as f:
        prefix_bytes = f.read(expected_length)

    actual_sha = hashlib.sha256(prefix_bytes).hexdigest()
    if actual_sha != expected_sha256:
        raise ExtractionSourcePrefixMismatchError(
            f"Source file '{path}' prefix checksum mismatch. Expected {expected_sha256}, actual {actual_sha}. Source file was modified or replaced."
        )
