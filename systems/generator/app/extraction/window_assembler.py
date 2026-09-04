"""Window assembly and deterministic grouping of intermediate extraction fragments."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from systems.generator.app.extraction.extraction_exception import (
    ExtractionDuplicateObservationNotSupportedError,
    ExtractionFragmentConflictError,
    ExtractionFragmentInvalidError,
    ExtractionFragmentVerifyFailedError,
    ExtractionLateRecordNotSupportedError,
)
from systems.generator.app.extraction.gen_data_fragment import (
    ExtractionFragmentManifest,
    GenDataFragmentRepository,
)
from systems.generator.app.extraction.gen_data_mapping import normalize_strict_iso_utc
from systems.generator.app.extraction.window_identity import (
    ExtractionWindow,
    compute_window_dataset_identity,
    resolve_utc_window,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FragmentReference:
    """Reference to a source batch fragment contributing to an assembled window."""

    batch_id: str
    fragment_manifest_sha256: str


@dataclass
class AssembledExtractionWindow:
    """Canonical assembled window payload ready for atomic dataset publication."""

    source_identity: str
    source_uri: str
    site_id: str
    cell_id: str
    dataset_id: str
    dataset_version: str

    window_start: str
    window_end: str
    mapping_id: str
    mapping_version: str
    mapping_sha256: str

    observations: list[dict[str, Any]]
    provenance_records: list[dict[str, Any]]
    rejected_records: list[dict[str, Any]]

    source_fragment_refs: list[FragmentReference]
    source_start_offset: int
    source_end_offset: int


class ExtractionWindowAssembler:
    """Validates intermediate fragments, tracks source watermarks, and groups records into discrete closed UTC windows."""

    def __init__(self, fragment_repo: Optional[GenDataFragmentRepository] = None) -> None:
        self.fragment_repo = fragment_repo or GenDataFragmentRepository()

    def collect_publishable_windows(
        self,
        *,
        source_identity: str,
        fragment_dirs: list[Path],
        window_minutes: int = 60,
        flush_before: Optional[datetime] = None,
        last_published_window_end: Optional[datetime] = None,
        run_id: Optional[str] = None,
    ) -> list[AssembledExtractionWindow]:
        """Collect and assemble all fully closed UTC windows across the given fragment directories.

        Invariants:
        1. Pre-validates each fragment manifest and file checksums.
        2. Computes source watermark across all observations.
        3. Fails closed if duplicate observations (asset_id, observed_at) exist within a window.
        4. Fails closed if late records arriving before last_published_window_end are found.
        5. Closes window only when source_watermark >= window_end or window_end <= flush_before.
        6. Deterministically sorts observation, provenance, and rejected records.
        """
        if not fragment_dirs:
            return []

        # 1. Pre-verify all fragments and load records
        verified_manifests: list[tuple[Path, ExtractionFragmentManifest, str]] = []
        seen_batch_ids: dict[str, Path] = {}
        for f_dir in sorted(fragment_dirs):
            manifest = self.fragment_repo.verify_fragment(f_dir)
            if manifest.source_identity != source_identity:
                raise ExtractionFragmentInvalidError(
                    f"Fragment at '{f_dir}' has mismatched source_identity: expected '{source_identity}', got '{manifest.source_identity}'"
                )
            if manifest.batch_id in seen_batch_ids:
                raise ExtractionFragmentConflictError(
                    f"Duplicate fragment batch_id '{manifest.batch_id}' found in multiple paths: "
                    f"'{seen_batch_ids[manifest.batch_id]}' and '{f_dir}'"
                )
            seen_batch_ids[manifest.batch_id] = f_dir

            manifest_file = f_dir / "fragment_manifest.json"
            self.fragment_repo._get_schema()  # warm cache
            import hashlib
            m_sha = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
            verified_manifests.append((f_dir, manifest, m_sha))

        if not verified_manifests:
            return []

        # Reference values from first manifest
        base_manifest = verified_manifests[0][1]
        site_id = base_manifest.source_identity
        # We need site_id and cell_id from observations or source_uri
        source_uri = base_manifest.source_uri
        mapping_id = base_manifest.mapping_id
        mapping_version = base_manifest.mapping_version
        mapping_sha256 = base_manifest.mapping_sha256

        # Group data structures keyed by window_id
        window_meta_map: dict[str, ExtractionWindow] = {}
        window_obs_map: dict[str, list[dict[str, Any]]] = {}
        window_prov_map: dict[str, list[dict[str, Any]]] = {}
        window_rej_map: dict[str, list[dict[str, Any]]] = {}
        window_frag_refs: dict[str, set[FragmentReference]] = {}
        window_offset_min: dict[str, int] = {}
        window_offset_max: dict[str, int] = {}
        window_seen_keys: dict[str, set[tuple[str, str]]] = {}

        max_observed_dt: Optional[datetime] = None
        extracted_site_id = ""
        extracted_cell_id = ""

        # Unassigned rejected records (no valid timestamp)
        unassigned_rejected: list[dict[str, Any]] = []

        # 2. Iterate and distribute records across windows
        for f_dir, manifest, m_sha in verified_manifests:
            frag_ref = FragmentReference(batch_id=manifest.batch_id, fragment_manifest_sha256=m_sha)

            # Observations
            obs_file = f_dir / "observations.jsonl"
            if obs_file.is_file():
                for line in obs_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    obs = json.loads(line)
                    raw_obs_at = obs.get("observed_at")
                    asset_id = obs.get("asset_id", "")
                    if not extracted_site_id and "site_id" in obs:
                        extracted_site_id = obs["site_id"]
                    if not extracted_cell_id and "cell_id" in obs:
                        extracted_cell_id = obs["cell_id"]

                    if raw_obs_at:
                        win = resolve_utc_window(raw_obs_at, window_minutes=window_minutes)
                        wid = win.window_id
                        obs_dt = win.window_start

                        norm_obs_at = normalize_strict_iso_utc(raw_obs_at)
                        cur_dt = datetime.fromisoformat(norm_obs_at.replace("Z", "+00:00")).astimezone(timezone.utc)
                        if max_observed_dt is None or cur_dt > max_observed_dt:
                            max_observed_dt = cur_dt

                        # Check late record
                        if last_published_window_end is not None and cur_dt < last_published_window_end:
                            raise ExtractionLateRecordNotSupportedError(
                                f"Late record for asset '{asset_id}' observed at '{norm_obs_at}' belongs to previously closed window (closed at {last_published_window_end.isoformat()})"
                            )

                        # Check duplicate in window
                        if wid not in window_seen_keys:
                            window_seen_keys[wid] = set()
                            window_meta_map[wid] = win
                            window_obs_map[wid] = []
                            window_prov_map[wid] = []
                            window_rej_map[wid] = []
                            window_frag_refs[wid] = set()
                            window_offset_min[wid] = manifest.source_start_offset
                            window_offset_max[wid] = manifest.source_end_offset

                        dup_key = (asset_id, norm_obs_at)
                        if dup_key in window_seen_keys[wid]:
                            raise ExtractionDuplicateObservationNotSupportedError(
                                f"Duplicate observation for asset '{asset_id}' at '{norm_obs_at}' within window '{wid}'"
                            )
                        window_seen_keys[wid].add(dup_key)

                        window_obs_map[wid].append(obs)
                        window_frag_refs[wid].add(frag_ref)
                        window_offset_min[wid] = min(window_offset_min[wid], manifest.source_start_offset)
                        window_offset_max[wid] = max(window_offset_max[wid], manifest.source_end_offset)

            # Provenance
            prov_file = f_dir / "provenance.jsonl"
            if prov_file.is_file():
                for line in prov_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    prov = json.loads(line)
                    raw_obs_at = prov.get("observed_at")
                    if raw_obs_at:
                        win = resolve_utc_window(raw_obs_at, window_minutes=window_minutes)
                        wid = win.window_id
                        if wid in window_prov_map:
                            window_prov_map[wid].append(prov)
                            window_frag_refs[wid].add(frag_ref)

            # Rejected
            rej_file = f_dir / "rejected.jsonl"
            if rej_file.is_file():
                for line in rej_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    rej = json.loads(line)
                    raw_rej_at = rej.get("rejected_at") or rej.get("observed_at")
                    try:
                        if raw_rej_at:
                            win = resolve_utc_window(raw_rej_at, window_minutes=window_minutes)
                            wid = win.window_id
                            if wid in window_rej_map:
                                window_rej_map[wid].append(rej)
                                window_frag_refs[wid].add(frag_ref)
                            else:
                                unassigned_rejected.append(rej)
                        else:
                            unassigned_rejected.append(rej)
                    except Exception:
                        unassigned_rejected.append(rej)

        # Fallback site_id/cell_id from source_uri if not in observation dictionary
        if not extracted_site_id or not extracted_cell_id:
            # Parse from source_uri: sensor/facS01/lineL01/...
            import re
            m = re.search(r"fac([^/]+)/line([^/]+)", source_uri)
            if m:
                extracted_site_id = m.group(1)
                extracted_cell_id = m.group(2)
            else:
                extracted_site_id = "UNKNOWN"
                extracted_cell_id = "UNKNOWN"

        # 3. Determine closed windows based on watermark or flush_before
        assembled_windows: list[AssembledExtractionWindow] = []

        for wid, win in sorted(window_meta_map.items()):
            obs_list = window_obs_map[wid]
            if not obs_list:
                continue

            is_closed = False
            if max_observed_dt is not None and max_observed_dt >= win.window_end:
                is_closed = True
            elif flush_before is not None and win.window_end <= flush_before:
                is_closed = True

            if not is_closed:
                logger.info(
                    f"[WindowAssembler] Window '{wid}' [{win.window_start_iso} ~ {win.window_end_iso}) remains open (watermark: {max_observed_dt})"
                )
                continue

            # Deterministic sorting
            sorted_obs = sorted(obs_list, key=lambda o: (o["observed_at"], o["asset_id"]))
            sorted_prov = sorted(
                window_prov_map[wid],
                key=lambda p: (
                    p.get("observed_at", ""),
                    p.get("asset_id", ""),
                    p.get("source_uri", ""),
                    p.get("source_byte_start", 0),
                ),
            )
            sorted_rej = sorted(
                window_rej_map[wid],
                key=lambda r: (
                    r.get("source_uri", ""),
                    r.get("source_byte_start", 0),
                    r.get("source_line_number", 0),
                ),
            )

            ds_id, ds_version = compute_window_dataset_identity(
                site_id=extracted_site_id,
                cell_id=extracted_cell_id,
                window_start=win.window_start,
                mapping_sha256=mapping_sha256,
            )

            sorted_refs = sorted(list(window_frag_refs[wid]), key=lambda r: r.batch_id)

            assembled_windows.append(
                AssembledExtractionWindow(
                    source_identity=source_identity,
                    source_uri=source_uri,
                    site_id=extracted_site_id,
                    cell_id=extracted_cell_id,
                    dataset_id=ds_id,
                    dataset_version=ds_version,
                    window_start=win.window_start_iso,
                    window_end=win.window_end_iso,
                    mapping_id=mapping_id,
                    mapping_version=mapping_version,
                    mapping_sha256=mapping_sha256,
                    observations=sorted_obs,
                    provenance_records=sorted_prov,
                    rejected_records=sorted_rej,
                    source_fragment_refs=sorted_refs,
                    source_start_offset=window_offset_min[wid],
                    source_end_offset=window_offset_max[wid],
                )
            )

        # Write unassigned rejected records if any
        if unassigned_rejected and run_id:
            from systems.generator.generator_config import PATHS
            run_dir = PATHS.data_preprocessed / "extraction_runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            unassigned_file = run_dir / "unassigned_rejected.jsonl"
            lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in unassigned_rejected]
            with open(unassigned_file, "a", encoding="utf-8") as f:
                f.writelines(lines)

        return assembled_windows
