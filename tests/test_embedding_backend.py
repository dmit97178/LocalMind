"""P5 Ollama embedding adapter behavior without a live Ollama service."""

from src.models.ollama_embedding import OllamaEmbeddingBackend


class FakeEmbeddingTransport:
    def __init__(self, response: dict | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def post_json(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        if isinstance(self.response, Exception):
            raise self.response
        return {"embeddings": self.response["embeddings"][: len(payload["input"])]}


def test_embedding_backend_embeds_documents_and_query() -> None:
    transport = FakeEmbeddingTransport({"embeddings": [[1.0, 0.0], [0.0, 1.0]]})
    backend = OllamaEmbeddingBackend(
        {"model": "nomic-embed-text", "base_url": "http://localhost:11434", "dim": 2},
        transport=transport,
    )

    documents = backend.embed_documents(["first", "second"])
    query = backend.embed_query("question")

    assert documents.value == [[1.0, 0.0], [0.0, 1.0]]
    assert query.value == [1.0, 0.0]
    assert backend.model_id() == "nomic-embed-text"
    assert backend.dimensions() == 2
    assert backend.health_check() is True
    assert transport.calls[0] == (
        "/api/embed",
        {"model": "nomic-embed-text", "input": ["first", "second"]},
    )


def test_embedding_backend_rejects_non_loopback_and_degrades_after_probe_failure() -> None:
    try:
        OllamaEmbeddingBackend({"model": "nomic-embed-text", "base_url": "https://remote.example"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "CONFIG_ERROR"
    else:
        raise AssertionError("non-loopback embedding endpoint must be rejected")

    unavailable = OllamaEmbeddingBackend(
        {"model": "nomic-embed-text", "dim": 0},
        transport=FakeEmbeddingTransport(OSError("offline")),
    )

    assert unavailable.dimensions() == 0
    assert unavailable.health_check() is False
    result = unavailable.embed_query("question")
    assert result.is_err is True
    assert result.error is not None
    assert result.error.code == "EMBEDDING_ERROR"


def test_embedding_backend_returns_error_when_document_count_is_wrong() -> None:
    backend = OllamaEmbeddingBackend(
        {"model": "nomic-embed-text", "dim": 2},
        transport=FakeEmbeddingTransport({"embeddings": [[1.0, 0.0]]}),
    )

    result = backend.embed_documents(["first", "second"])

    assert result.is_err is True
    assert result.error is not None
    assert result.error.code == "EMBEDDING_ERROR"
