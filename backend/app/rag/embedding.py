from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Protocol


class EmbeddingProvider(Protocol):
    model_name: str

    def embed(self, text: str) -> list[float]:
        """Return a deterministic-length embedding vector."""


class DeterministicHashEmbedding:
    """Offline embedding used by tests and mock deployments."""

    model_name = "deterministic-hash-v1"

    def __init__(self, dimensions: int = 96) -> None:
        if dimensions < 8:
            raise ValueError("embedding dimensions must be at least 8")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class FastEmbedEmbedding:
    """Optional CPU embedding provider backed by FastEmbed/ONNX Runtime.

    The model is loaded lazily so the deterministic test mode does not need a
    network, a model download, or a large resident process.  A missing model
    dependency or download failure is handled by the Retriever fallback.
    """

    def __init__(self, model_name: str, *, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._model = None

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("fastembed_not_installed") from exc

            kwargs: dict[str, object] = {"model_name": self.model_name}
            if self._cache_dir is not None:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                kwargs["cache_dir"] = str(self._cache_dir)
            self._model = TextEmbedding(**kwargs)

        vectors = list(self._model.embed([text]))
        if not vectors:
            raise RuntimeError("fastembed_returned_no_vector")
        return [float(value) for value in vectors[0]]


def create_embedding_provider(
    provider_name: str,
    *,
    model_name: str,
    dimensions: int,
    cache_dir: str | None = None,
) -> EmbeddingProvider:
    """Build the configured provider without changing the Retriever contract."""

    if provider_name == "deterministic":
        return DeterministicHashEmbedding(dimensions)
    if provider_name == "fastembed":
        return FastEmbedEmbedding(model_name, cache_dir=cache_dir)
    raise ValueError(f"unsupported_embedding_provider:{provider_name}")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True))
    return max(-1.0, min(1.0, score))


def _tokens(text: str) -> tuple[str, ...]:
    normalized = " ".join(text.lower().split())
    values: list[str] = []
    for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized):
        values.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            values.extend(token[index : index + 2] for index in range(max(0, len(token) - 1)))
    return tuple(values)
