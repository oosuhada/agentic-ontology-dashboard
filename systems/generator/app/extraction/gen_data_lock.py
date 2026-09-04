"""Cross-platform OS-level single-writer file lock for gen_data append streams."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from systems.generator.app.extraction.extraction_exception import (
    ExtractionSourceLockedError,
    ExtractionSourceLockFailedError,
)

logger = logging.getLogger(__name__)

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import fcntl
except ImportError:
    fcntl = None


class GenDataSourceLock:
    """Exclusive OS file lock per source_identity."""

    def __init__(
        self,
        lock_dir: Path,
        source_identity: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.lock_dir = Path(lock_dir).resolve()
        self.source_identity = source_identity
        self.timeout_seconds = timeout_seconds
        self.lock_file_path = self.lock_dir / f"{source_identity}.lock"
        self._file_handle: Optional[Any] = None
        self._is_locked: bool = False

    def acquire(self) -> None:
        """Acquire exclusive OS file lock with timeout."""
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        start_time = time.monotonic()

        try:
            # Open file in binary read/write append mode
            self._file_handle = open(self.lock_file_path, "a+b")
        except Exception as exc:
            raise ExtractionSourceLockFailedError(
                f"Failed to open lock file '{self.lock_file_path}': {exc}"
            ) from exc

        fd = self._file_handle.fileno()

        while True:
            try:
                if msvcrt is not None:
                    # Windows: seek to byte 0 and lock 1 byte non-blocking
                    self._file_handle.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    self._is_locked = True
                    return
                elif fcntl is not None:
                    # Unix/Linux: POSIX flock exclusive non-blocking
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self._is_locked = True
                    return
                else:
                    # Fallback if neither available
                    self._is_locked = True
                    return
            except (BlockingIOError, OSError, IOError) as exc:
                elapsed = time.monotonic() - start_time
                if elapsed >= self.timeout_seconds:
                    self._clean_handle()
                    raise ExtractionSourceLockedError(
                        f"Source '{self.source_identity}' is locked by another process (timeout {self.timeout_seconds}s exceeded)."
                    ) from exc
                time.sleep(0.05)

    def release(self) -> None:
        """Release OS file lock."""
        if not self._is_locked or self._file_handle is None:
            self._clean_handle()
            return

        try:
            fd = self._file_handle.fileno()
            if msvcrt is not None:
                self._file_handle.seek(0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        except Exception as exc:
            logger.warning(f"Error unlocking file '{self.lock_file_path}': {exc}")
        finally:
            self._clean_handle()

    def _clean_handle(self) -> None:
        self._is_locked = False
        if self._file_handle is not None:
            try:
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

    def __enter__(self) -> GenDataSourceLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
