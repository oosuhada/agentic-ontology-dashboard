"""Dataset-owned application errors independent of HTTP and Identity implementations."""

from __future__ import annotations


class DatasetAccessError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


__all__ = ["DatasetAccessError"]
