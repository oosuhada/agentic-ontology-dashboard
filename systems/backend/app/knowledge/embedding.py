"""Embedding providers used by enterprise knowledge retrieval.

The local provider is deterministic and dependency-free so development and the
private Mac mini deployment can build a real pgvector index without an external
API.  Production deployments can opt into Google embeddings with the same
1536-dimensional contract.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol


EMBEDDING_DIMENSIONS = 1536
_TOKEN = re.compile(r"[0-9A-Za-z가-힣_.:-]+")


class EmbeddingProvider(Protocol):
    name: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [value / norm for value in values]


class HashingEmbeddingProvider:
    """Stable lexical/subword embedding suitable for local hybrid retrieval.

    It is intentionally not presented as a neural semantic model.  Its purpose
    is to provide deterministic vector indexing, fuzzy token overlap, and a
    production-shaped fallback when external embedding APIs are unavailable.
    """

    name = "hashing-subword-1536-v1"
    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        lowered = text.lower()
        features: list[str] = _TOKEN.findall(lowered)
        compact = re.sub(r"\s+", " ", lowered)
        features.extend(compact[index : index + 3] for index in range(max(0, len(compact) - 2)))
        for feature in features:
            if not feature.strip():
                continue
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            weight = 1.35 if len(feature) > 3 else 0.7
            vector[index] += sign * weight
        return _normalize(vector)


class GoogleEmbeddingProvider:
    name = "google-gemini-embedding-001-1536"
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self, api_key: str, model: str = "gemini-embedding-001") -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def embed(self, text: str) -> list[float]:
        from google.genai import types

        response = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dimensions),
        )
        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise RuntimeError("embedding provider returned no vector")
        values = list(getattr(embeddings[0], "values", None) or [])
        if len(values) != self.dimensions:
            raise RuntimeError(f"unexpected embedding dimensions: {len(values)}")
        return _normalize([float(value) for value in values])


def configured_embedding_provider() -> EmbeddingProvider:
    provider = os.getenv("ONTOLOGY_DASHBOARD_RAG_EMBEDDING_PROVIDER", "hashing").strip().lower()
    if provider == "google":
        api_key = os.getenv("ONTOLOGY_DASHBOARD_RAG_EMBEDDING_API_KEY", "").strip() or os.getenv("LLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Google RAG embedding provider requires an API key")
        model = os.getenv("ONTOLOGY_DASHBOARD_RAG_EMBEDDING_MODEL", "gemini-embedding-001").strip()
        return GoogleEmbeddingProvider(api_key, model=model)
    return HashingEmbeddingProvider()


__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "GoogleEmbeddingProvider",
    "configured_embedding_provider",
]
