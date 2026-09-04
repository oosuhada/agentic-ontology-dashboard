"""File integrity and SHA-256 calculation utilities for Generator domain."""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_file_sha256(path: Path | str) -> str:
    """Compute SHA-256 checksum of a file on disk."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found for sha256 calculation: {p}")
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_bytes_sha256(data: bytes) -> str:
    """Compute SHA-256 checksum of bytes."""
    return hashlib.sha256(data).hexdigest()
