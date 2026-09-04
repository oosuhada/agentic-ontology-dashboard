"""Identity application errors without HTTP transport concerns."""

from __future__ import annotations


class AuthError(RuntimeError):
    """Identity error expressed only as stable application code and message.

    The temporary three-argument form is accepted for compatibility with
    legacy callers outside the migrated Identity boundary. The numeric HTTP
    value is deliberately discarded and is not part of the error object.
    """

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


__all__ = ["AuthError"]
