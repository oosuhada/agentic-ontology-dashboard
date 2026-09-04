"""Pure local/file URI resolution for filesystem-backed Infra adapters."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def local_file_uri_path(uri: str) -> Path:
    """Resolve a local path or ``file://`` URI without touching the filesystem."""

    native_path = Path(uri)
    if native_path.is_absolute():
        return native_path
    parsed = urlparse(uri)
    if parsed.scheme in {"", "file"}:
        if parsed.scheme == "file":
            path = unquote(parsed.path)
            value = url2pathname(f"//{parsed.netloc}{path}" if parsed.netloc else path)
        else:
            value = uri
        return Path(value)
    raise ValueError("local filesystem access only supports paths and file:// URIs")


__all__ = ["local_file_uri_path"]
