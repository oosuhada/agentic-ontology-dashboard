"""Persistent deduplication ledger, idempotency repository, and single-writer lock management."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from systems.generator.generator_config import PATHS
from systems.generator.app.extraction.extraction_exception import (
    ExtractionAlreadyRunningError,
    ExtractionLockLostError,
    ExtractionIdempotencyConflictError,
    ExtractionRequestInProgressError,
)

logger = logging.getLogger(__name__)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DedupRepository:
    """SQLite-backed persistent deduplication store, batch state machine, and single-writer lock manager."""

    def __init__(self, db_path: Optional[Path] = None, state_root: Optional[Path] = None) -> None:
        self.state_root = state_root or (PATHS.data_preprocessed / "extraction_state")
        self._custom_db_path = db_path

    def _get_db_path(self, dataset_id: str, dataset_version: str) -> Path:
        if self._custom_db_path:
            return self._custom_db_path
        folder = self.state_root / dataset_id / dataset_version
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "dedup.db"

    def _get_connection(self, dataset_id: str, dataset_version: str) -> sqlite3.Connection:
        db_path = self._get_db_path(dataset_id, dataset_version)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        self._ensure_tables(conn)
        return conn

    def _get_idempotency_connection(self) -> sqlite3.Connection:
        db_path = self._custom_db_path or (self.state_root / "idempotency.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_ledger (
                    idempotency_key TEXT PRIMARY KEY,
                    request_sha256 TEXT NOT NULL,
                    owner_run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_json TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        return conn

    def _ensure_tables(self, conn: sqlite3.Connection) -> None:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dedup_ledger (
                    source_identity TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (source_identity, source_record_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS single_writer_locks (
                    dataset_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    heartbeat_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS extraction_batches (
                    dataset_id TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    source_identity TEXT NOT NULL,
                    source_start_offset INTEGER NOT NULL,
                    source_end_offset INTEGER NOT NULL,
                    fragment_observations_sha256 TEXT,
                    fragment_provenance_sha256 TEXT,
                    fragment_rejected_sha256 TEXT,
                    record_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (dataset_id, dataset_version, batch_id)
                )
                """
            )

    # --- Single Writer Lock Lease ---

    def acquire_lock(
        self,
        dataset_id: str,
        dataset_version: str,
        run_id: str,
        timeout_seconds: float = 300.0,
    ) -> None:
        """Atomically acquire exclusive single-writer lock for dataset_id + dataset_version using BEGIN IMMEDIATE."""
        dataset_key = f"{dataset_id}:{dataset_version}"
        conn = self._get_connection(dataset_id, dataset_version)
        now_ts = time.time()
        expires_ts = now_ts + timeout_seconds
        now_iso = now_utc_iso()

        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "SELECT run_id, expires_at FROM single_writer_locks WHERE dataset_key = ?",
                (dataset_key,),
            )
            row = cur.fetchone()

            if row is not None:
                existing_run_id = row["run_id"]
                existing_expires = float(row["expires_at"])

                if existing_run_id == run_id:
                    conn.execute(
                        "UPDATE single_writer_locks SET expires_at = ?, heartbeat_at = ? WHERE dataset_key = ? AND run_id = ?",
                        (expires_ts, now_iso, dataset_key, run_id),
                    )
                    conn.execute("COMMIT")
                    return

                if now_ts < existing_expires:
                    conn.execute("ROLLBACK")
                    raise ExtractionAlreadyRunningError(
                        f"동일한 데이터셋({dataset_id}/{dataset_version})에 대한 추출 작업(run_id='{existing_run_id}')이 현재 실행 중입니다.",
                        details=[{
                            "dataset_id": dataset_id,
                            "dataset_version": dataset_version,
                            "active_run_id": existing_run_id,
                            "expires_in_seconds": round(existing_expires - now_ts, 2),
                        }],
                    )
                else:
                    # Conditional atomic takeover of stale lock
                    cur_update = conn.execute(
                        """
                        UPDATE single_writer_locks
                        SET run_id = ?, acquired_at = ?, expires_at = ?, heartbeat_at = ?
                        WHERE dataset_key = ? AND expires_at <= ?
                        """,
                        (run_id, now_iso, expires_ts, now_iso, dataset_key, now_ts),
                    )
                    if cur_update.rowcount == 1:
                        logger.warning(
                            f"[DedupRepository] Stale lock overtaken for {dataset_key} (previously {existing_run_id}, expired at {existing_expires})."
                        )
                        conn.execute("COMMIT")
                        return
                    else:
                        conn.execute("ROLLBACK")
                        raise ExtractionAlreadyRunningError(
                            f"데이터셋({dataset_id}/{dataset_version})의 락 획득 경쟁에서 밀려났습니다."
                        )

            # Insert new lock
            conn.execute(
                """
                INSERT INTO single_writer_locks (dataset_key, run_id, acquired_at, expires_at, heartbeat_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (dataset_key, run_id, now_iso, expires_ts, now_iso),
            )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

    def heartbeat_lock(
        self,
        dataset_id: str,
        dataset_version: str,
        run_id: str,
        lease_seconds: float = 300.0,
    ) -> None:
        """Renew single-writer lock lease. Fast-fails with ExtractionLockLostError if lease was lost."""
        dataset_key = f"{dataset_id}:{dataset_version}"
        conn = self._get_connection(dataset_id, dataset_version)
        now_ts = time.time()
        expires_ts = now_ts + lease_seconds
        now_iso = now_utc_iso()

        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                """
                UPDATE single_writer_locks
                SET expires_at = ?, heartbeat_at = ?
                WHERE dataset_key = ? AND run_id = ?
                """,
                (expires_ts, now_iso, dataset_key, run_id),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                raise ExtractionLockLostError(
                    f"데이터셋({dataset_id}/{dataset_version})에 대한 락 소유권(run_id='{run_id}')을 상실했습니다.",
                    details=[{"dataset_id": dataset_id, "dataset_version": dataset_version, "run_id": run_id}],
                )
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

    def release_lock(
        self,
        dataset_id: str,
        dataset_version: str,
        run_id: str,
    ) -> None:
        """Release single-writer lock held by this run_id."""
        dataset_key = f"{dataset_id}:{dataset_version}"
        try:
            conn = self._get_connection(dataset_id, dataset_version)
            with conn:
                conn.execute(
                    "DELETE FROM single_writer_locks WHERE dataset_key = ? AND run_id = ?",
                    (dataset_key, run_id),
                )
        except Exception as exc:
            logger.warning(f"[DedupRepository] Failed to release lock for {dataset_key}: {exc}")

    # --- Dedup Ledger ---

    def is_record_processed(
        self,
        source_identity: str,
        source_record_id: str,
        dataset_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> bool:
        """Check if source record has already been committed to dedup ledger."""
        ds_id = dataset_id or "default"
        ds_ver = dataset_version or "v1"
        conn = self._get_connection(ds_id, ds_ver)
        cur = conn.execute(
            "SELECT 1 FROM dedup_ledger WHERE source_identity = ? AND source_record_id = ?",
            (source_identity, source_record_id),
        )
        return cur.fetchone() is not None

    def record_processed_batch(
        self,
        source_identity: str,
        source_record_ids: list[str],
        dataset_id: str,
        dataset_version: str,
    ) -> None:
        """Commit a batch of processed source record IDs to persistent SQLite ledger."""
        if not source_record_ids:
            return
        conn = self._get_connection(dataset_id, dataset_version)
        ts = now_utc_iso()
        rows = [(source_identity, rid, ts) for rid in source_record_ids]
        with conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO dedup_ledger (source_identity, source_record_id, processed_at)
                VALUES (?, ?, ?)
                """,
                rows,
            )

    # --- Idempotency Ledger with Pre-Execution Reservation ---

    def reserve_idempotency_key(
        self,
        idempotency_key: str,
        request_sha256: str,
        run_id: str,
    ) -> Optional[dict[str, Any]]:
        """Atomically reserve idempotency key before execution.

        Returns:
            dict: Existing successful response if already completed with identical request.
            None: Key reserved in 'running' state and execution should proceed.

        Raises:
            ExtractionIdempotencyConflictError (409): If key was used with differing request payload.
            ExtractionRequestInProgressError (409): If key is currently being processed by another run.
        """
        conn = self._get_idempotency_connection()
        now_iso = now_utc_iso()

        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "SELECT request_sha256, owner_run_id, status, response_json FROM idempotency_ledger WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cur.fetchone()

            if row is None:
                # First time seeing this key -> reserve in 'running' status
                conn.execute(
                    """
                    INSERT INTO idempotency_ledger (idempotency_key, request_sha256, owner_run_id, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'running', ?, ?)
                    """,
                    (idempotency_key, request_sha256, run_id, now_iso, now_iso),
                )
                conn.execute("COMMIT")
                return None

            stored_sha = row["request_sha256"]
            stored_owner = row["owner_run_id"]
            stored_status = row["status"]
            stored_resp_json = row["response_json"]

            if stored_sha != request_sha256:
                conn.execute("ROLLBACK")
                raise ExtractionIdempotencyConflictError(
                    f"동일한 멱등성 키('{idempotency_key}')로 상이한 요청이 이미 등록되었습니다.",
                    details=[{"idempotency_key": idempotency_key}],
                )

            if stored_status == "succeeded" and stored_resp_json:
                conn.execute("COMMIT")
                return json.loads(stored_resp_json)

            if stored_status == "running":
                if stored_owner == run_id:
                    # Same run retrying -> proceed
                    conn.execute("COMMIT")
                    return None
                else:
                    conn.execute("ROLLBACK")
                    raise ExtractionRequestInProgressError(
                        f"동일한 멱등성 키('{idempotency_key}')의 요청이 다른 실행(run_id='{stored_owner}')에서 진행 중입니다.",
                        details=[{"idempotency_key": idempotency_key, "owner_run_id": stored_owner}],
                    )

            # Failed status -> allow retry by updating status to running
            conn.execute(
                """
                UPDATE idempotency_ledger
                SET owner_run_id = ?, status = 'running', updated_at = ?
                WHERE idempotency_key = ?
                """,
                (run_id, now_iso, idempotency_key),
            )
            conn.execute("COMMIT")
            return None
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise

    def mark_idempotency_succeeded(
        self,
        idempotency_key: str,
        request_sha256: str,
        response_dict: dict[str, Any],
    ) -> None:
        """Mark idempotency record as succeeded with response body."""
        conn = self._get_idempotency_connection()
        now_iso = now_utc_iso()
        with conn:
            conn.execute(
                """
                UPDATE idempotency_ledger
                SET status = 'succeeded', response_json = ?, error_code = NULL, updated_at = ?
                WHERE idempotency_key = ?
                """,
                (json.dumps(response_dict, ensure_ascii=False), now_iso, idempotency_key),
            )

    def mark_idempotency_failed(
        self,
        idempotency_key: str,
        error_code: str,
    ) -> None:
        """Mark idempotency record as failed with error code."""
        conn = self._get_idempotency_connection()
        now_iso = now_utc_iso()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE idempotency_ledger
                    SET status = 'failed', error_code = ?, updated_at = ?
                    WHERE idempotency_key = ?
                    """,
                    (error_code, now_iso, idempotency_key),
                )
        except Exception as exc:
            logger.warning(f"[DedupRepository] Failed to mark idempotency failure for {idempotency_key}: {exc}")

    def get_idempotency_record(
        self,
        idempotency_key: str,
        dataset_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> Optional[tuple[str, dict[str, Any]]]:
        """Fetch existing idempotency record (request_sha256, response_dict) if exists and succeeded."""
        conn = self._get_idempotency_connection()
        cur = conn.execute(
            "SELECT request_sha256, status, response_json FROM idempotency_ledger WHERE idempotency_key = ?",
            (idempotency_key,),
        )
        row = cur.fetchone()
        if row is None or row["status"] != "succeeded" or not row["response_json"]:
            return None
        try:
            resp_dict = json.loads(row["response_json"])
            return row["request_sha256"], resp_dict
        except Exception:
            return None

    # --- Extraction Batch State Machine ---

    def create_batch(
        self,
        batch_id: str,
        run_id: str,
        source_identity: str,
        source_start_offset: int,
        source_end_offset: int,
        record_count: int,
        dataset_id: str,
        dataset_version: str,
    ) -> None:
        """Record a new extraction batch in 'pending' status."""
        conn = self._get_connection(dataset_id, dataset_version)
        ts = now_utc_iso()
        with conn:
            conn.execute(
                """
                INSERT INTO extraction_batches
                (dataset_id, dataset_version, batch_id, run_id, source_identity, source_start_offset, source_end_offset, record_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                ON CONFLICT(dataset_id, dataset_version, batch_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    source_identity = excluded.source_identity,
                    source_start_offset = excluded.source_start_offset,
                    source_end_offset = excluded.source_end_offset,
                    record_count = excluded.record_count,
                    status = 'pending',
                    updated_at = excluded.updated_at
                """,
                (dataset_id, dataset_version, batch_id, run_id, source_identity, source_start_offset, source_end_offset, record_count, ts, ts),
            )

    def mark_batch_staged(
        self,
        batch_id: str,
        dataset_id: str,
        dataset_version: str,
        obs_sha256: Optional[str] = None,
        prov_sha256: Optional[str] = None,
        rej_sha256: Optional[str] = None,
    ) -> None:
        """Transition batch status to 'staged' after fragment files are flushed/fsynced."""
        conn = self._get_connection(dataset_id, dataset_version)
        ts = now_utc_iso()
        with conn:
            conn.execute(
                """
                UPDATE extraction_batches
                SET status = 'staged',
                    fragment_observations_sha256 = ?,
                    fragment_provenance_sha256 = ?,
                    fragment_rejected_sha256 = ?,
                    updated_at = ?
                WHERE dataset_id = ? AND dataset_version = ? AND batch_id = ?
                """,
                (obs_sha256, prov_sha256, rej_sha256, ts, dataset_id, dataset_version, batch_id),
            )

    def mark_batch_committed(
        self,
        batch_id: str,
        dataset_id: str,
        dataset_version: str,
    ) -> None:
        """Transition batch status to 'committed' after dedup and checkpoint updates."""
        conn = self._get_connection(dataset_id, dataset_version)
        ts = now_utc_iso()
        with conn:
            conn.execute(
                """
                UPDATE extraction_batches
                SET status = 'committed', updated_at = ?
                WHERE dataset_id = ? AND dataset_version = ? AND batch_id = ?
                """,
                (ts, dataset_id, dataset_version, batch_id),
            )

    def get_batch(
        self,
        batch_id: str,
        dataset_id: str,
        dataset_version: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch batch record by ID."""
        conn = self._get_connection(dataset_id, dataset_version)
        cur = conn.execute(
            "SELECT * FROM extraction_batches WHERE dataset_id = ? AND dataset_version = ? AND batch_id = ?",
            (dataset_id, dataset_version, batch_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_batches(
        self,
        dataset_id: str,
        dataset_version: str,
        run_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List all batches for dataset version."""
        conn = self._get_connection(dataset_id, dataset_version)
        if run_id:
            cur = conn.execute(
                "SELECT * FROM extraction_batches WHERE dataset_id = ? AND dataset_version = ? AND run_id = ? ORDER BY source_start_offset ASC",
                (dataset_id, dataset_version, run_id),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM extraction_batches WHERE dataset_id = ? AND dataset_version = ? ORDER BY source_start_offset ASC",
                (dataset_id, dataset_version),
            )
        return [dict(r) for r in cur.fetchall()]
