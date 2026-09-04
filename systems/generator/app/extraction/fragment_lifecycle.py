"""Fragment consumption tracking and safe atomic lifecycle cleanup."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

import jsonschema
from pydantic import BaseModel

from systems.generator.generator_config import PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionFragmentCleanupFailedError,
    ExtractionRequestInvalidError,
)
from systems.generator.app.extraction.gen_data_fragment import (
    GenDataFragmentRepository,
)

logger = logging.getLogger(__name__)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FragmentConsumptionRecord(BaseModel):
    """Tracks published and pending UTC windows referencing a batch fragment."""

    consumption_schema_version: Literal["generator-extraction-fragment-consumption-v1"] = (
        "generator-extraction-fragment-consumption-v1"
    )
    batch_id: str
    fragment_manifest_sha256: str
    referenced_windows: list[str]
    published_windows: list[str]
    pending_windows: list[str]
    status: Literal["pending", "partially_consumed", "fully_consumed"]
    updated_at: str


class GenDataFragmentLifecycleManager:
    """Manages fragment consumption state transition and verified post-publication cleanup."""

    def __init__(
        self,
        consumption_root: Optional[Path] = None,
        fragment_repo: Optional[GenDataFragmentRepository] = None,
        schema_path: Optional[Path] = None,
    ) -> None:
        from systems.generator.generator_config import PATHS

        self.consumption_root = Path(
            consumption_root
            or (PATHS.data_preprocessed / "extraction_state" / "gen_data" / "fragment_consumption")
        ).resolve()
        self.fragment_repo = fragment_repo or GenDataFragmentRepository()
        self.schema_path = Path(
            schema_path
            or (
                PROJECT_ROOT
                / "contracts"
                / "schemas"
                / "generator-extraction-fragment-consumption.schema.json"
            )
        ).resolve()
        self._schema_cache: Optional[dict[str, Any]] = None

    def _get_schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            if not self.schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Consumption schema not found: {self.schema_path}")
            self._schema_cache = json.loads(self.schema_path.read_text(encoding="utf-8"))
        return self._schema_cache

    def validate_consumption(self, record_data: dict[str, Any]) -> None:
        schema = self._get_schema()
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            validator.validate(record_data)
        except jsonschema.ValidationError as exc:
            raise ExtractionRequestInvalidError(
                f"Consumption record validation failed: {exc.message}",
                details=[{"path": list(exc.path), "error": exc.message}],
            ) from exc

    def load_consumption(self, batch_id: str) -> Optional[FragmentConsumptionRecord]:
        """Load fragment consumption record if exists."""
        rec_file = self.consumption_root / f"{batch_id}.json"
        if not rec_file.is_file():
            return None
        try:
            data = json.loads(rec_file.read_text(encoding="utf-8"))
            self.validate_consumption(data)
            return FragmentConsumptionRecord.model_validate(data)
        except Exception as exc:
            logger.warning(f"Failed to load consumption record for batch '{batch_id}': {exc}")
            return None

    def is_fully_consumed(self, batch_id: str) -> bool:
        """Check if batch fragment has been fully consumed by all referenced windows."""
        record = self.load_consumption(batch_id)
        return record is not None and record.status == "fully_consumed"

    def record_window_publication(
        self,
        *,
        batch_id: str,
        fragment_manifest_sha256: str,
        all_referenced_windows: list[str],
        published_window: str,
    ) -> FragmentConsumptionRecord:
        """Atomically record window publication and update pending vs fully_consumed status."""
        self.consumption_root.mkdir(parents=True, exist_ok=True)
        rec_file = self.consumption_root / f"{batch_id}.json"
        temp_file = self.consumption_root / f".tmp_{batch_id}_{uuid4().hex}.json"

        existing = self.load_consumption(batch_id)
        if existing:
            ref_set = set(existing.referenced_windows) | set(all_referenced_windows)
            pub_set = set(existing.published_windows) | {published_window}
        else:
            ref_set = set(all_referenced_windows) | {published_window}
            pub_set = {published_window}

        pending_set = ref_set - pub_set
        sorted_ref = sorted(list(ref_set))
        sorted_pub = sorted(list(pub_set))
        sorted_pending = sorted(list(pending_set))

        status: Literal["pending", "partially_consumed", "fully_consumed"] = (
            "fully_consumed" if len(sorted_pending) == 0 else "partially_consumed"
        )

        record = FragmentConsumptionRecord(
            batch_id=batch_id,
            fragment_manifest_sha256=fragment_manifest_sha256,
            referenced_windows=sorted_ref,
            published_windows=sorted_pub,
            pending_windows=sorted_pending,
            status=status,
            updated_at=now_utc_iso(),
        )

        record_dict = record.model_dump()
        self.validate_consumption(record_dict)
        content = json.dumps(record_dict, indent=2, ensure_ascii=False) + "\n"

        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            try:
                os.replace(str(temp_file), str(rec_file))
            except OSError as exc:
                raise ExtractionRequestInvalidError(
                    f"Failed to atomically persist consumption record for batch '{batch_id}': {exc}"
                ) from exc

            return record
        except Exception as exc:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            if isinstance(exc, ExtractionRequestInvalidError):
                raise
            raise ExtractionRequestInvalidError(
                f"Failed to persist consumption record for batch '{batch_id}': {exc}"
            ) from exc

    def safe_cleanup_fragment(
        self,
        *,
        fragment_dir: Path,
        batch_id: str,
    ) -> bool:
        """Safely delete fragment directory if and only if consumption status is fully_consumed.

        Invariants:
        - Consumption status must be fully_consumed.
        - Directory is renamed to .cleanup_* staging before rmtree.
        - Cleanup failure logs error but does not fail publication.
        """
        rec = self.load_consumption(batch_id)
        if not rec or rec.status != "fully_consumed":
            logger.info(
                f"[FragmentLifecycle] Fragment '{batch_id}' is not fully consumed (status={rec.status if rec else 'none'}); retaining."
            )
            return False

        path = Path(fragment_dir).resolve()
        if not path.is_dir():
            return True

        cleanup_staging = path.parent / f".cleanup_{batch_id}_{uuid4().hex}"
        try:
            try:
                os.replace(str(path), str(cleanup_staging))
            except OSError:
                shutil.move(str(path), str(cleanup_staging))

            shutil.rmtree(str(cleanup_staging))
            logger.info(f"[FragmentLifecycle] Successfully cleaned up fully consumed fragment '{batch_id}'")
            return True
        except Exception as exc:
            logger.error(f"[FragmentLifecycle] Failed to clean up fragment '{path}': {exc}")
            raise ExtractionFragmentCleanupFailedError(
                f"Failed to remove fragment directory '{path}': {exc}"
            ) from exc
