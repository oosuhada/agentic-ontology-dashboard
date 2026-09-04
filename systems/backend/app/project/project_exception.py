"""Project domain exceptions."""

from __future__ import annotations


class ProjectError(RuntimeError):
    """Project use-case failure expressed without HTTP transport concerns."""

    def __init__(self, code_or_status: str | int, code_or_message: str, message: str | None = None) -> None:
        if message is None:
            code = str(code_or_status)
            resolved_message = code_or_message
        else:
            code = code_or_message
            resolved_message = message
        super().__init__(resolved_message)
        self.code = code
        self.message = resolved_message


class ProjectContextError(ValueError):
    """Raised when a workspace cannot be resolved to a valid Project context."""


__all__ = ["ProjectContextError", "ProjectError"]
