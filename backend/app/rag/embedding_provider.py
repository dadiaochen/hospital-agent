from __future__ import annotations

from collections.abc import Sequence
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Protocol, runtime_checkable


EMBEDDING_DIMENSION = 512
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_SCHEMA_VERSION = "rag-embedding-v1"


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


class DeterministicHashEmbeddingProvider:
    """Offline provider implementing the same contract as FastEmbed.

    This provider is deterministic and intended for tests, demos, and
    environments without a model download. It is not a semantic model.
    """

    def __init__(
        self,
        *,
        model_name: str = "deterministic-hash-v1",
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        if dimension < 8:
            raise ValueError("embedding dimensions must be at least 8")
        self.model_name = model_name
        self.dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed(self, text: str) -> list[float]:
        """Compatibility alias for the pre-4B embedding API."""

        return self.embed_query(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class FastEmbedEmbeddingProvider:
    """FastEmbed adapter with lazy CPU/CUDA device selection."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: str | Path | None = "var/models/fastembed",
        dimension: int | None = EMBEDDING_DIMENSION,
        device: str = "cpu",
    ) -> None:
        if device not in {"cpu", "cuda", "auto"}:
            raise ValueError("device must be one of: cpu, cuda, auto")
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.dimension = dimension
        self.device = device
        self._model: Any | None = None

    def embed_query(self, text: str) -> list[float]:
        model = self._get_model()
        query_embed = getattr(model, "query_embed", None)
        vectors = list(query_embed(text) if callable(query_embed) else model.embed([text]))
        if len(vectors) != 1:
            raise EmbeddingProviderError("query embedding returned an unexpected count")
        return self._validated_vector(vectors[0])

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        passage_embed = getattr(model, "passage_embed", None)
        raw_vectors = (
            passage_embed(list(texts))
            if callable(passage_embed)
            else model.embed(list(texts))
        )
        vectors = [self._validated_vector(vector) for vector in raw_vectors]
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

        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            kwargs: dict[str, Any] = {"model_name": self.model_name}
            if self.cache_dir is not None:
                kwargs["cache_dir"] = str(self.cache_dir)
            # FastEmbed's default is automatic device selection. Keep an
            # explicit CPU default for reproducible local runs, while allowing
            # benchmark jobs to opt into CUDA through configuration.
            if self.device != "auto":
                kwargs["cuda"] = self.device == "cuda"
            model = TextEmbedding(**kwargs)
            if self.device == "cuda":
                session = getattr(getattr(model, "model", None), "model", None)
                get_providers = getattr(session, "get_providers", None)
                providers = list(get_providers()) if callable(get_providers) else []
                if "CUDAExecutionProvider" not in providers:
                    raise EmbeddingProviderUnavailableError(
                        "CUDA was requested but FastEmbed did not create a CUDAExecutionProvider"
                    )
            self._model = model
        except EmbeddingProviderUnavailableError:
            self._model = None
            raise
        except Exception as exc:
            raise EmbeddingProviderUnavailableError(
                f"unable to load embedding model {self.model_name} on {self.device}"
            ) from exc
        return self._model

    def _validated_vector(self, vector: Any) -> list[float]:
        values = [float(value) for value in vector]
        if self.dimension is not None and len(values) != self.dimension:
            raise EmbeddingDimensionError(
                f"expected {self.dimension} dimensions, received {len(values)}"
            )
        return values


def _tokens(text: str) -> tuple[str, ...]:
    normalized = " ".join(text.lower().split())
    values: list[str] = []
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized):
        values.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            values.extend(
                token[index : index + 2]
                for index in range(max(0, len(token) - 1))
            )
    return tuple(values)


__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_SCHEMA_VERSION",
    "DeterministicHashEmbeddingProvider",
    "EmbeddingDimensionError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderUnavailableError",
    "FastEmbedEmbeddingProvider",
]
