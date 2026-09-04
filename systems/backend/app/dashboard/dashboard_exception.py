from __future__ import annotations


class DashboardAccessError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class DashboardNotFoundError(KeyError):
    pass


class DashboardConflictError(RuntimeError):
    pass


class DashboardPreferenceConflict(DashboardConflictError):
    pass


__all__ = [
    "DashboardAccessError",
    "DashboardConflictError",
    "DashboardNotFoundError",
    "DashboardPreferenceConflict",
]
