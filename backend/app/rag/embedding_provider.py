from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


EMBEDDING_DIMENSION = 512
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


class EmbeddingProviderError(RuntimeError):
    """Base error normalized for HybridRetriever fallback tracing."""


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Raised when the optional local embedding runtime cannot be loaded."""


class EmbeddingDimensionError(EmbeddingProviderError):
    """Raised before a vector with the wrong schema reaches PostgreSQL."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_query(self, text: str) -> list[float]:
        """Embed one search query."""

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed authoritative knowledge chunks in input order."""


class FastEmbedEmbeddingProvider:
    """CPU-only FastEmbed adapter that does not load a model until first use."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: str | Path = "var/models/fastembed",
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.dimension = dimension
        self._model: Any | None = None

    def embed_query(self, text: str) -> list[float]:
        vectors = list(self._get_model().query_embed(text))
        if len(vectors) != 1:
            raise EmbeddingProviderError("query embedding returned an unexpected count")
        return self._validated_vector(vectors[0])

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [
            self._validated_vector(vector)
            for vector in self._get_model().passage_embed(list(texts))
        ]
        if len(vectors) != len(texts):
            raise EmbeddingProviderError("passage embedding count does not match input")
        return vectors

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingProviderUnavailableError(
                "fastembed is not installed; keyword retrieval remains available"
            ) from exc

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
            )
        except Exception as exc:
            raise EmbeddingProviderUnavailableError(
                f"unable to load embedding model {self.model_name}"
            ) from exc
        return self._model

    def _validated_vector(self, vector: Any) -> list[float]:
        values = [float(value) for value in vector]
        if len(values) != self.dimension:
            raise EmbeddingDimensionError(
                f"expected {self.dimension} dimensions, received {len(values)}"
            )
        return values


__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
    "EmbeddingDimensionError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderUnavailableError",
    "FastEmbedEmbeddingProvider",
]
