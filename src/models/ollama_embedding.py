"""Loopback-only Ollama implementation of the EmbeddingBackend boundary."""

from __future__ import annotations

import math
from typing import Protocol

from src.core.interfaces import EmbeddingBackend
from src.core.schemas import LocalMindError, Result
from src.models.ollama_backend import _loopback_url, _UrllibOllamaTransport

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT_SECONDS = 5.0


class OllamaEmbeddingTransport(Protocol):
    """Minimal transport seam for deterministic embedding-adapter tests."""

    def post_json(self, path: str, payload: dict) -> dict: ...


class OllamaEmbeddingBackend(EmbeddingBackend):
    """Embed sanitized text locally through Ollama's `/api/embed` endpoint."""

    def __init__(self, config: dict, transport: OllamaEmbeddingTransport | None = None) -> None:
        self._model = _required_string(config, "model")
        self._base_url = _loopback_url(config.get("base_url", _DEFAULT_BASE_URL))
        self._timeout_seconds = _positive_number(
            config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS), "timeout_seconds"
        )
        configured_dim = config.get("dim", 0)
        if (
            not isinstance(configured_dim, int)
            or isinstance(configured_dim, bool)
            or configured_dim < 0
        ):
            raise _config_error("dim must be a non-negative integer")
        self._transport = transport or _UrllibOllamaTransport(self._base_url, self._timeout_seconds)
        self._dimensions = configured_dim
        if self._dimensions == 0:
            self._probe_dimensions()

    def embed_documents(self, texts: list[str]) -> Result[list[list[float]]]:
        if not all(isinstance(text, str) for text in texts):
            return Result.err(_embedding_error("Embedding documents must be text"))
        result = self._embed(texts)
        if result.is_err:
            return Result.err(result.error or _embedding_error("Embedding request failed"))
        vectors = result.value
        if vectors is None:
            return Result.err(_embedding_error("Embedding response was empty"))
        if len(vectors) != len(texts):
            return Result.err(
                _embedding_error("Ollama embedding count did not match document count")
            )
        return Result.ok(vectors)

    def embed_query(self, text: str) -> Result[list[float]]:
        if not isinstance(text, str):
            return Result.err(_embedding_error("Embedding query must be text"))
        result = self._embed([text])
        if result.is_err:
            return Result.err(result.error or _embedding_error("Embedding request failed"))
        vectors = result.value
        if vectors is None or len(vectors) != 1:
            return Result.err(_embedding_error("Ollama embedding query returned an invalid count"))
        return Result.ok(vectors[0])

    def dimensions(self) -> int:
        return self._dimensions

    def model_id(self) -> str:
        return self._model

    def health_check(self) -> bool:
        if self._dimensions < 1:
            return False
        try:
            response = self._transport.post_json(
                "/api/embed", {"model": self._model, "input": [""]}
            )
            vectors = response.get("embeddings") if isinstance(response, dict) else None
            return (
                isinstance(vectors, list)
                and len(vectors) == 1
                and _validate_vector(vectors[0], self._dimensions) is not None
            )
        except Exception:
            return False

    def _probe_dimensions(self) -> None:
        try:
            response = self._transport.post_json(
                "/api/embed", {"model": self._model, "input": [""]}
            )
            vectors = response.get("embeddings") if isinstance(response, dict) else None
            if isinstance(vectors, list) and len(vectors) == 1 and isinstance(vectors[0], list):
                vector = vectors[0]
                if vector and all(
                    isinstance(item, (int, float)) and math.isfinite(item) for item in vector
                ):
                    self._dimensions = len(vector)
        except Exception:
            return

    def _embed(self, texts: list[str]) -> Result[list[list[float]]]:
        if self._dimensions == 0:
            return Result.err(_embedding_error("Embedding dimensions are unavailable"))
        try:
            response = self._transport.post_json(
                "/api/embed", {"model": self._model, "input": texts}
            )
            vectors = response.get("embeddings") if isinstance(response, dict) else None
            if not isinstance(vectors, list):
                return Result.err(
                    _embedding_error("Ollama embedding response did not include embeddings")
                )
            normalized = [_validate_vector(vector, self._dimensions) for vector in vectors]
            return Result.ok(normalized)
        except Exception as exc:
            return Result.err(_embedding_error(f"Ollama embedding request failed: {exc}"))


def _required_string(config: dict, key: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise _config_error(f"{key} must be a non-empty string")


def _positive_number(value: object, key: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    raise _config_error(f"{key} must be a positive number")


def _validate_vector(value: object, dimensions: int) -> list[float]:
    if not isinstance(value, list) or len(value) != dimensions:
        raise ValueError("Ollama embedding dimensions did not match configuration")
    if any(not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
        raise ValueError("Ollama embedding vector contains invalid values")
    return [float(item) for item in value]


def _embedding_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="EMBEDDING_ERROR",
        message=message,
        user_message="语义检索暂不可用，已切换关键词检索。",
        recoverable=True,
        details={},
    )


def _config_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=message,
        user_message="系统配置有误，请检查 memory_backend.config.embedding。",
        recoverable=False,
        details={},
    )
