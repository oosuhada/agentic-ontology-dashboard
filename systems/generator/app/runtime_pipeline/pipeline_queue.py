"""Persistent priority-FIFO Queue for the Generator Runtime Pipeline."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from systems.generator.generator_config import PATHS
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineDuplicateInputError,
    PipelineInputNotFoundError,
    PipelineJobNotFailedError,
    PipelineQueueItemInvalidError,
    PipelineQueuePersistError,
    PipelineSourceAlreadyProcessedError,
    PipelineSourceAlreadyRegisteredError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    PipelineQueueItem,
    PredictionResultLineage,
    RuntimeInputIdentity,
    RuntimeSourceContext,
    compute_source_identity,
    now_utc_iso,
)

logger = logging.getLogger(__name__)


def is_temporary_file(file_path: Path | str) -> bool:
    """Check if file path corresponds to a temporary/partial/swap file."""
    p = Path(file_path)
    name = p.name
    suffix = p.suffix.lower()
    if name.startswith(".") or name.startswith("~"):
        return True
    if suffix in (".tmp", ".temp", ".part", ".swp", ".crdownload") or name.endswith("~"):
        return True
    return False


class PipelineQueue:
    """Persistent priority-FIFO queue with deduplication and crash recovery.

    The first maintenance replay job for each maintenance event is promoted ahead
    of ordinary live jobs. Once one replay job for that event succeeds, later
    replay snapshots return to normal FIFO order so live input cannot starve.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            self.db_path = PATHS.pipeline_queue_db
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue_items (
                    job_id TEXT PRIMARY KEY,
                    source_uri TEXT NOT NULL,
                    source_checksum TEXT NOT NULL,
                    dedup_key TEXT UNIQUE NOT NULL,
                    source_identity TEXT,
                    size_bytes INTEGER,
                    dataset_id TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    pipeline_contract_version TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_contract_version TEXT NOT NULL,
                    source_schema_version TEXT NOT NULL,
                    lineage_json TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    retry_of_job_id TEXT,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Check for missing columns in existing table and alter if needed
            cur = conn.execute("PRAGMA table_info(queue_items)")
            columns = [row["name"] for row in cur.fetchall()]
            if "retry_of_job_id" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN retry_of_job_id TEXT")
            if "source_identity" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN source_identity TEXT")
            if "size_bytes" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN size_bytes INTEGER")
            context_columns_added = False
            if "pipeline_contract_version" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN pipeline_contract_version TEXT")
                context_columns_added = True
            if "source_kind" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN source_kind TEXT")
                context_columns_added = True
            if "source_contract_version" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN source_contract_version TEXT")
                context_columns_added = True
            if "source_schema_version" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN source_schema_version TEXT")
                context_columns_added = True
            if "lineage_json" not in columns:
                conn.execute("ALTER TABLE queue_items ADD COLUMN lineage_json TEXT")
                context_columns_added = True

            # Old queue rows predate the canonical source-context contract.  Their
            # provenance cannot be inferred safely, so isolate them instead of
            # silently labelling them as live sensor input.
            if context_columns_added:
                conn.execute(
                    """
                    UPDATE queue_items
                    SET status = 'dead_letter',
                        error_code = 'PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED',
                        updated_at = ?
                    WHERE pipeline_contract_version IS NULL
                       OR source_kind IS NULL
                       OR source_contract_version IS NULL
                       OR source_schema_version IS NULL
                       OR lineage_json IS NULL
                    """,
                    (now_utc_iso(),),
                )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_status_seq ON queue_items (status, sequence)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_source_identity ON queue_items (source_identity, status)")
            conn.commit()

    def normalize_uri(self, uri: str) -> str:
        return str(Path(uri).as_posix()).strip()

    def _row_to_item(self, r: sqlite3.Row, conn: Optional[sqlite3.Connection] = None) -> PipelineQueueItem:
        job_id = r["job_id"]
        col_keys = r.keys()

        raw_lineage = r["lineage_json"] if "lineage_json" in col_keys else None
        source_kind = r["source_kind"] if "source_kind" in col_keys else None
        source_contract_version = r["source_contract_version"] if "source_contract_version" in col_keys else None
        source_schema_version = r["source_schema_version"] if "source_schema_version" in col_keys else None
        pipeline_contract_version = r["pipeline_contract_version"] if "pipeline_contract_version" in col_keys else None
        dataset_id = r["dataset_id"] if "dataset_id" in col_keys else None
        dataset_version = r["dataset_version"] if "dataset_version" in col_keys else None

        if (
            raw_lineage is None
            or source_kind is None
            or source_contract_version is None
            or source_schema_version is None
            or pipeline_contract_version is None
            or dataset_id is None
            or dataset_version is None
        ):
            if conn is not None:
                conn.execute(
                    "UPDATE queue_items SET status = 'dead_letter', error_code = 'PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED', updated_at = ? WHERE job_id = ?",
                    (now_utc_iso(), job_id),
                )
                conn.commit()
            raise PipelineQueueItemInvalidError(
                f"Queue item '{job_id}' is a legacy row lacking mandatory source context columns.",
                code="PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED",
                details=[{"job_id": job_id, "error": "missing_context_columns"}],
                retryable=False,
            )

        try:
            lineage_dict = json.loads(raw_lineage) if isinstance(raw_lineage, str) else raw_lineage
            if not isinstance(lineage_dict, dict):
                raise ValueError("lineage_json must decode to a JSON object")
            lineage = PredictionResultLineage.model_validate(lineage_dict)

            # Validate complete canonical RuntimeInputIdentity
            runtime_input = RuntimeInputIdentity(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                source=RuntimeSourceContext(
                    source_uri=r["source_uri"],
                    source_checksum=r["source_checksum"],
                    source_kind=source_kind,
                    source_contract_version=source_contract_version,
                    source_schema_version=source_schema_version,
                    pipeline_contract_version=pipeline_contract_version,
                    lineage=lineage,
                ),
            )

            return PipelineQueueItem(
                job_id=job_id,
                source_uri=r["source_uri"],
                source_checksum=r["source_checksum"],
                source_identity=r["source_identity"] if "source_identity" in col_keys else None,
                size_bytes=r["size_bytes"] if "size_bytes" in col_keys else None,
                dataset_id=runtime_input.dataset_id,
                dataset_version=runtime_input.dataset_version,
                pipeline_contract_version=runtime_input.source.pipeline_contract_version,
                source_kind=runtime_input.source.source_kind,
                source_contract_version=runtime_input.source.source_contract_version,
                source_schema_version=runtime_input.source.source_schema_version,
                lineage=runtime_input.source.lineage,
                detected_at=r["detected_at"],
                sequence=r["sequence"],
                attempt=r["attempt"],
                retry_of_job_id=r["retry_of_job_id"] if "retry_of_job_id" in col_keys else None,
                status=r["status"],
                error_code=r["error_code"],
            )
        except Exception as exc:
            logger.error(f"[PipelineQueue] Corrupted source context in queue item '{job_id}': {exc}")
            if conn is not None:
                conn.execute(
                    "UPDATE queue_items SET status = 'dead_letter', error_code = 'PIPELINE_SOURCE_CONTEXT_CORRUPTED', updated_at = ? WHERE job_id = ?",
                    (now_utc_iso(), job_id),
                )
                conn.commit()
            raise PipelineQueueItemInvalidError(
                f"Queue item '{job_id}' source context corrupted: {exc}",
                code="PIPELINE_SOURCE_CONTEXT_CORRUPTED",
                details=[{"job_id": job_id, "error": str(exc)}],
                retryable=False,
            ) from exc

    def enqueue(
        self,
        *,
        job_id: str,
        runtime_input: RuntimeInputIdentity,
        size_bytes: Optional[int] = None,
        retry_of_job_id: Optional[str] = None,
    ) -> PipelineQueueItem:
        """Enqueue a new completed observation source file item using canonical RuntimeInputIdentity without fallback defaults."""
        clean_job_id = job_id.strip() if isinstance(job_id, str) else ""
        if not clean_job_id:
            raise PipelineQueueItemInvalidError(
                "job_id must not be empty",
                details=[{"job_id": job_id}],
                retryable=False,
            )

        if not isinstance(runtime_input, RuntimeInputIdentity):
            try:
                runtime_input = RuntimeInputIdentity.model_validate(runtime_input)
            except Exception as exc:
                raise PipelineQueueItemInvalidError(
                    f"Invalid runtime_input: {exc}",
                    details=[{"error": str(exc)}],
                    retryable=False,
                ) from exc

        clean_uri = self.normalize_uri(runtime_input.source.source_uri)
        clean_checksum = runtime_input.source.source_checksum.strip()

        if is_temporary_file(clean_uri):
            raise PipelineQueueItemInvalidError(
                f"임시 파일('{clean_uri}')은 큐 등록 대상에서 제외됩니다.",
                details=[{"source_uri": clean_uri}],
                retryable=False,
            )

        # Infer size_bytes if not passed and file exists locally
        computed_size = size_bytes
        if computed_size is None:
            try:
                local_path = Path(clean_uri)
                if local_path.is_file():
                    computed_size = local_path.stat().st_size
            except Exception:
                pass

        source_identity = compute_source_identity(
            source_checksum=clean_checksum,
            dataset_id=runtime_input.dataset_id,
            dataset_version=runtime_input.dataset_version,
            pipeline_contract_version=runtime_input.source.pipeline_contract_version,
            source_contract_version=runtime_input.source.source_contract_version,
            source_schema_version=runtime_input.source.source_schema_version,
            source_kind=runtime_input.source.source_kind,
            lineage=runtime_input.source.lineage,
        )
        dedup_key = f"{clean_uri}:{clean_checksum}"
        now = now_utc_iso()
        lineage_json = json.dumps(runtime_input.source.lineage.model_dump(mode="json"), ensure_ascii=False)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    # Check if active duplicate already exists by source_identity
                    cur = conn.execute(
                        "SELECT job_id, status FROM queue_items WHERE source_identity = ?",
                        (source_identity,),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        ex_status = existing["status"]
                        if ex_status in ("queued", "running", "retry_wait"):
                            raise PipelineSourceAlreadyRegisteredError(
                                f"동일한 입력(source_identity: {source_identity[:8]}...)이 이미 등록되어 있습니다 ({ex_status}).",
                                details=[{"job_id": existing["job_id"], "status": ex_status, "source_identity": source_identity}],
                            )
                        elif ex_status == "succeeded":
                            raise PipelineSourceAlreadyProcessedError(
                                f"동일한 입력(source_identity: {source_identity[:8]}...)이 이미 처리 완료되었습니다.",
                                details=[{"job_id": existing["job_id"], "status": ex_status, "source_identity": source_identity}],
                            )
                        elif ex_status == "failed":
                            raise PipelineDuplicateInputError(
                                "동일한 입력이 failed 상태입니다. 자동 재등록하지 않고 명시적 retry를 사용해야 합니다.",
                                details=[{"job_id": existing["job_id"], "status": ex_status, "source_identity": source_identity}],
                            )
                        elif ex_status == "dead_letter":
                            raise PipelineDuplicateInputError(
                                f"동일한 입력(source_identity: {source_identity[:8]}...)이 dead_letter 상태입니다. 자동 재등록되지 않습니다.",
                                details=[{"job_id": existing["job_id"], "status": ex_status, "source_identity": source_identity}],
                            )

                    # Get next sequence
                    cur = conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS next_seq FROM queue_items")
                    next_seq = cur.fetchone()["next_seq"]

                    item = PipelineQueueItem(
                        job_id=clean_job_id,
                        source_uri=clean_uri,
                        source_checksum=clean_checksum,
                        source_identity=source_identity,
                        size_bytes=computed_size,
                        dataset_id=runtime_input.dataset_id,
                        dataset_version=runtime_input.dataset_version,
                        pipeline_contract_version=runtime_input.source.pipeline_contract_version,
                        source_kind=runtime_input.source.source_kind,
                        source_contract_version=runtime_input.source.source_contract_version,
                        source_schema_version=runtime_input.source.source_schema_version,
                        lineage=runtime_input.source.lineage,
                        detected_at=now,
                        sequence=next_seq,
                        attempt=1,
                        retry_of_job_id=retry_of_job_id,
                        status="queued",
                    )

                    conn.execute(
                        """
                        INSERT INTO queue_items (
                            job_id, source_uri, source_checksum, dedup_key, source_identity, size_bytes,
                            dataset_id, dataset_version, pipeline_contract_version, source_kind,
                            source_contract_version, source_schema_version, lineage_json, detected_at,
                            sequence, attempt, retry_of_job_id, status, error_code, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.job_id,
                            item.source_uri,
                            item.source_checksum,
                            dedup_key,
                            item.source_identity,
                            item.size_bytes,
                            item.dataset_id,
                            item.dataset_version,
                            item.pipeline_contract_version,
                            item.source_kind,
                            item.source_contract_version,
                            item.source_schema_version,
                            lineage_json,
                            item.detected_at,
                            item.sequence,
                            item.attempt,
                            item.retry_of_job_id,
                            item.status,
                            None,
                            now,
                            now,
                        ),
                    )
                    conn.commit()
                    logger.info(f"[PipelineQueue] Enqueued job '{item.job_id}' (seq={item.sequence}, identity={source_identity[:8]}) for {clean_uri}")
                    return item
            except (PipelineDuplicateInputError, PipelineSourceAlreadyRegisteredError, PipelineSourceAlreadyProcessedError, PipelineQueueItemInvalidError):
                raise
            except Exception as exc:
                logger.exception(f"[PipelineQueue] Failed to persist queue item: {exc}")
                raise PipelineQueuePersistError(f"작업 큐 저장 실패: {exc}") from exc

    def retry_failed_job(self, job_id: str) -> PipelineQueueItem:
        """Atomically re-enqueue a failed or dead_letter job as a new queue item while preserving source context."""
        now = now_utc_iso()
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "SELECT * FROM queue_items WHERE job_id = ?",
                    (job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise PipelineInputNotFoundError(
                        f"재등록 대상 작업을 찾을 수 없습니다: '{job_id}'",
                        details=[{"job_id": job_id}],
                    )

                status = row["status"]
                if status not in ("failed", "dead_letter"):
                    raise PipelineJobNotFailedError(
                        f"실패(failed/dead_letter) 상태의 작업만 재등록할 수 있습니다. 현재 상태: '{status}'",
                        details=[{"job_id": job_id, "status": status}],
                    )

                # Validate the complete persisted context before releasing any
                # uniqueness keys. Legacy/corrupt rows must remain isolated and
                # cannot acquire invented live-sensor provenance during retry.
                original_item = self._row_to_item(row, conn)

                # Release unique constraints on old record while preserving the record
                old_dedup = row["dedup_key"]
                old_identity = original_item.source_identity
                archived_dedup = f"archived:{job_id}:{old_dedup}"
                archived_identity = f"archived:{job_id}:{old_identity}" if old_identity else None
                conn.execute(
                    "UPDATE queue_items SET dedup_key = ?, source_identity = ?, updated_at = ? WHERE job_id = ?",
                    (archived_dedup, archived_identity, now, job_id),
                )

                # Get next sequence
                cur = conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS next_seq FROM queue_items")
                next_seq = cur.fetchone()["next_seq"]

                contract_ver = original_item.pipeline_contract_version
                source_kind = original_item.source_kind
                source_contract_ver = original_item.source_contract_version
                source_schema_ver = original_item.source_schema_version
                lineage_obj = original_item.lineage
                raw_lineage = json.dumps(lineage_obj.model_dump(mode="json"), ensure_ascii=False)
                size_b = original_item.size_bytes

                new_job_id = f"{job_id}-retry-{uuid4().hex[:6]}"
                new_item = PipelineQueueItem(
                    job_id=new_job_id,
                    source_uri=row["source_uri"],
                    source_checksum=row["source_checksum"],
                    source_identity=old_identity,
                    size_bytes=size_b,
                    dataset_id=row["dataset_id"],
                    dataset_version=row["dataset_version"],
                    pipeline_contract_version=contract_ver,
                    source_kind=source_kind,
                    source_contract_version=source_contract_ver,
                    source_schema_version=source_schema_ver,
                    lineage=lineage_obj,
                    detected_at=now,
                    sequence=next_seq,
                    attempt=1,
                    retry_of_job_id=job_id,
                    status="queued",
                )

                conn.execute(
                    """
                    INSERT INTO queue_items (
                        job_id, source_uri, source_checksum, dedup_key, source_identity, size_bytes,
                        dataset_id, dataset_version, pipeline_contract_version, source_kind,
                        source_contract_version, source_schema_version, lineage_json, detected_at,
                        sequence, attempt, retry_of_job_id, status, error_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_item.job_id,
                        new_item.source_uri,
                        new_item.source_checksum,
                        old_dedup,
                        new_item.source_identity,
                        new_item.size_bytes,
                        new_item.dataset_id,
                        new_item.dataset_version,
                        new_item.pipeline_contract_version,
                        new_item.source_kind,
                        new_item.source_contract_version,
                        new_item.source_schema_version,
                        raw_lineage if isinstance(raw_lineage, str) else json.dumps(raw_lineage),
                        new_item.detected_at,
                        new_item.sequence,
                        new_item.attempt,
                        new_item.retry_of_job_id,
                        new_item.status,
                        None,
                        now,
                        now,
                    ),
                )
                conn.commit()
                logger.info(f"[PipelineQueue] Re-enqueued failed job '{job_id}' as new job '{new_job_id}' (seq={next_seq})")
                return new_item

    def claim_next(self) -> Optional[PipelineQueueItem]:
        """Claim the next priority-FIFO item and transition it to running."""
        now = now_utc_iso()
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(
                    """
                    SELECT * FROM queue_items AS candidate
                    WHERE candidate.status = 'queued'
                    ORDER BY
                        CASE
                            WHEN candidate.source_kind = 'maintenance_replay_overlay'
                             AND NULLIF(
                                    TRIM(
                                        json_extract(
                                            CASE
                                                WHEN json_valid(candidate.lineage_json)
                                                THEN candidate.lineage_json
                                                ELSE '{}'
                                            END,
                                            '$.maintenance_event_id'
                                        )
                                    ),
                                    ''
                                 ) IS NOT NULL
                             AND NOT EXISTS (
                                    SELECT 1
                                    FROM queue_items AS completed
                                    WHERE completed.source_kind = 'maintenance_replay_overlay'
                                      AND completed.status = 'succeeded'
                                      AND json_extract(
                                            CASE
                                                WHEN json_valid(completed.lineage_json)
                                                THEN completed.lineage_json
                                                ELSE '{}'
                                            END,
                                            '$.maintenance_event_id'
                                          ) = json_extract(
                                            CASE
                                                WHEN json_valid(candidate.lineage_json)
                                                THEN candidate.lineage_json
                                                ELSE '{}'
                                            END,
                                            '$.maintenance_event_id'
                                          )
                                 )
                            THEN 0
                            ELSE 1
                        END ASC,
                        candidate.sequence ASC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row is None:
                    return None

                job_id = row["job_id"]
                conn.execute(
                    """
                    UPDATE queue_items
                    SET status = 'running', updated_at = ?
                    WHERE job_id = ?
                    """,
                    (now, job_id),
                )
                conn.commit()

                return self._row_to_item(row, conn)

    def mark_succeeded(self, job_id: str) -> None:
        now = now_utc_iso()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE queue_items SET status = 'succeeded', updated_at = ? WHERE job_id = ?",
                (now, job_id),
            )
            conn.commit()

    def mark_failed(self, job_id: str, error_code: Optional[str] = None, dead_letter: bool = False) -> None:
        now = now_utc_iso()
        new_status = "dead_letter" if dead_letter else "failed"
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "UPDATE queue_items SET status = ?, error_code = ?, updated_at = ? WHERE job_id = ?",
                (new_status, error_code, now, job_id),
            )
            conn.commit()

    def mark_retry_wait(self, job_id: str, error_code: Optional[str] = None) -> None:
        now = now_utc_iso()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                UPDATE queue_items
                SET status = 'queued', attempt = attempt + 1, error_code = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (error_code, now, job_id),
            )
            conn.commit()

    def get_item(self, job_id: str) -> Optional[PipelineQueueItem]:
        with self._lock, self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM queue_items WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_item(row, conn)

    def list_items(self, status: Optional[str] = None) -> list[PipelineQueueItem]:
        with self._lock, self._get_connection() as conn:
            if status:
                cur = conn.execute(
                    "SELECT * FROM queue_items WHERE status = ? ORDER BY sequence ASC",
                    (status,),
                )
            else:
                cur = conn.execute("SELECT * FROM queue_items ORDER BY sequence ASC")
            rows = cur.fetchall()
            return [self._row_to_item(r, conn) for r in rows]

    def recover_running_on_startup(self) -> int:
        """Reset any interrupted 'running' jobs back to 'queued' on startup."""
        now = now_utc_iso()
        with self._lock, self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE queue_items
                SET status = 'queued', attempt = attempt + 1, updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
            count = cur.rowcount
            conn.commit()
            if count > 0:
                logger.warning(f"[PipelineQueue] Recovered {count} interrupted 'running' queue items back to 'queued'")
            return count
