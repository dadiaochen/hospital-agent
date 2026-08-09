"""Compatibility names for the canonical RAG embedding contract.

New runtime code should import from :mod:`app.rag.embedding_provider`. These
classes remain available for the 2F learning API and older maintenance tests;
they delegate to the same deterministic and FastEmbed implementations.
"""

from __future__ import annotations

import math
from typing import Protocol

from app.rag.embedding_provider import (
    DeterministicHashEmbeddingProvider,
    FastEmbedEmbeddingProvider,
)


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, text: str) -> list[float]:
        """Return one embedding vector for a text."""


class DeterministicHashEmbedding(DeterministicHashEmbeddingProvider):
    """Backward-compatible deterministic provider with configurable size."""

    def __init__(self, dimensions: int = 96) -> None:
        super().__init__(dimension=dimensions)
        self.dimensions = dimensions


class FastEmbedEmbedding(FastEmbedEmbeddingProvider):
    """Backward-compatible single-text FastEmbed adapter."""

    def __init__(
        self,
        model_name: str,
        *,
        cache_dir: str | None = None,
        device: str = "cpu",
    ) -> None:
        super().__init__(
            model_name=model_name,
            cache_dir=cache_dir,
            dimension=None,
            device=device,
        )

    def embed(self, text: str) -> list[float]:
        return self.embed_query(text)


def create_embedding_provider(
    provider_name: str,
    *,
    model_name: str,
    dimensions: int,
    cache_dir: str | None = None,
    device: str = "cpu",
) -> object:
    """Build a provider while preserving the old factory signature."""

    if provider_name == "deterministic":
        return DeterministicHashEmbedding(dimensions)
    if provider_name == "fastembed":
        return FastEmbedEmbeddingProvider(
            model_name=model_name,
            cache_dir=cache_dir or "var/models/fastembed",
            dimension=dimensions,
            device=device,
        )
    raise ValueError(f"unsupported_embedding_provider:{provider_name}")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True))
    return max(-1.0, min(1.0, score / (left_norm * right_norm)))


__all__ = [
    "DeterministicHashEmbedding",
    "EmbeddingProvider",
    "FastEmbedEmbedding",
    "cosine_similarity",
    "create_embedding_provider",
]
