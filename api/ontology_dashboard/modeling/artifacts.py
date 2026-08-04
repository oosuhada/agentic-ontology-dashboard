from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from .models import ArtifactReference


class ArtifactStoreBlocked(RuntimeError):
    pass


class LocalArtifactStore:
    """Portable artifact URI facade over a configured local root."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.getenv("ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT")
        if not configured:
            raise ArtifactStoreBlocked("adaptive modeling artifact root is not configured")
        self.root = Path(configured).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or "\\" in key:
            raise ValueError("artifact key must be a portable relative path")
        candidate = (self.root / unquote(key)).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("artifact path traversal is not allowed")
        return candidate

    def put_bytes(self, key: str, content: bytes, media_type: str | None = None) -> ArtifactReference:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        return ArtifactReference(
            uri=f"artifact://{key}",
            checksum_sha256=checksum,
            media_type=media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            size_bytes=len(content),
        )

    def resolve(self, reference: ArtifactReference, *, verify: bool = True) -> Path:
        parsed = urlparse(reference.uri)
        if parsed.scheme != "artifact":
            raise ValueError("local artifact store only resolves artifact:// URIs")
        key = f"{parsed.netloc}{parsed.path}"
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(reference.uri)
        if verify:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != reference.checksum_sha256:
                raise ValueError("artifact checksum mismatch")
        return path

    def read_bytes(self, reference: ArtifactReference) -> bytes:
        return self.resolve(reference).read_bytes()
