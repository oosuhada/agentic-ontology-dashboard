"""Data models and exploration adapter for gen_data streaming logs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from systems.generator.app.extraction.extraction_exception import (
    ExtractionError,
    ExtractionGenDataRootInvalidError,
    ExtractionGenDataRootNotConfiguredError,
    ExtractionGenDataSourceDiscoveryFailedError,
    ExtractionGenDataSourcePathUnsupportedError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenDataSensorStreamSource:
    """Represents a discovered gen_data sensor stream source."""

    site_id: str
    cell_id: str
    facility_dir_name: str
    line_dir_name: str
    source_path: Path
    source_uri: str
    source_format: str = "gen_data_sensor_stream"


def discover_gen_data_sensor_streams(
    sensor_root: Optional[Path] = None,
) -> list[GenDataSensorStreamSource]:
    """Discover all sensor_stream.jsonl files under {sensor_root}/fac{site_id}/line{cell_id}/.

    Processing rules:
    1. sensor_root is resolved and validated. If None, loaded from PATHS.gen_data_sensor_root.
    2. Explores fac* directories directly under sensor_root, rejecting empty/invalid IDs.
    3. Explores line* directories directly under fac*, rejecting empty/invalid IDs.
    4. Matches files named exactly sensor_stream.jsonl.
    5. Re-validates path bounds against symlinks and path traversal.
    6. Deduplicates physical targets and sorts deterministically by (site_id, cell_id, source_uri).
    """
    if sensor_root is None:
        from systems.generator.generator_config import PATHS

        sensor_root = PATHS.gen_data_sensor_root
        if sensor_root is None:
            raise ExtractionGenDataRootNotConfiguredError(
                "GEN_DATA_OUTPUT_DIR is not configured. Cannot discover gen_data sensor streams."
            )

    root = Path(sensor_root).resolve()

    if not root.exists():
        return []

    if not root.is_dir():
        raise ExtractionGenDataRootInvalidError(
            f"sensor_root path '{root}' exists but is not a directory."
        )

    sources: list[GenDataSensorStreamSource] = []
    seen_paths: set[Path] = set()

    try:
        for fac_entry in root.iterdir():
            # Only directories starting with 'fac'
            if not fac_entry.is_dir():
                continue

            fac_resolved = fac_entry.resolve()
            if not str(fac_resolved).startswith(str(root)):
                raise ExtractionGenDataSourcePathUnsupportedError(
                    f"Facility directory '{fac_entry}' resolves outside sensor_root '{root}'."
                )

            fac_name = fac_entry.name
            if not fac_name.startswith("fac"):
                continue

            site_id = fac_name[3:]
            if not site_id or not site_id.strip() or any(c in site_id for c in ("/", "\\", "..")):
                raise ExtractionGenDataSourcePathUnsupportedError(
                    f"Facility directory name '{fac_name}' yields invalid site_id '{site_id}'."
                )

            for line_entry in fac_entry.iterdir():
                # Only directories starting with 'line'
                if not line_entry.is_dir():
                    continue

                line_resolved = line_entry.resolve()
                if not str(line_resolved).startswith(str(root)):
                    raise ExtractionGenDataSourcePathUnsupportedError(
                        f"Line directory '{line_entry}' resolves outside sensor_root '{root}'."
                    )

                line_name = line_entry.name
                if not line_name.startswith("line"):
                    continue

                cell_id = line_name[4:]
                if not cell_id or not cell_id.strip() or any(c in cell_id for c in ("/", "\\", "..")):
                    raise ExtractionGenDataSourcePathUnsupportedError(
                        f"Line directory name '{line_name}' yields invalid cell_id '{cell_id}'."
                    )

                stream_file = line_entry / "sensor_stream.jsonl"
                if not stream_file.exists():
                    continue

                if stream_file.is_dir():
                    raise ExtractionGenDataSourcePathUnsupportedError(
                        f"Target stream path '{stream_file}' is a directory, not a file."
                    )

                if not stream_file.is_file():
                    continue

                stream_resolved = stream_file.resolve()
                if not str(stream_resolved).startswith(str(root)):
                    raise ExtractionGenDataSourcePathUnsupportedError(
                        f"Stream file '{stream_file}' resolves outside sensor_root '{root}'."
                    )

                if stream_resolved in seen_paths:
                    continue
                seen_paths.add(stream_resolved)

                source_uri = f"sensor/{fac_name}/{line_name}/sensor_stream.jsonl"
                sources.append(
                    GenDataSensorStreamSource(
                        site_id=site_id,
                        cell_id=cell_id,
                        facility_dir_name=fac_name,
                        line_dir_name=line_name,
                        source_path=stream_file,
                        source_uri=source_uri,
                    )
                )

    except (
        ExtractionError,
        ExtractionGenDataRootNotConfiguredError,
        ExtractionGenDataRootInvalidError,
        ExtractionGenDataSourcePathUnsupportedError,
    ):
        raise
    except Exception as exc:
        logger.exception(f"[GenDataSource] Unexpected error exploring '{root}': {exc}")
        raise ExtractionGenDataSourceDiscoveryFailedError(
            f"Failed to discover gen_data sensor streams in '{root}': {exc}"
        ) from exc

    sources.sort(key=lambda s: (s.site_id, s.cell_id, s.source_uri))
    return sources
