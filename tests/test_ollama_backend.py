"""Offline tests for the Ollama ModelBackend adapter."""

from __future__ import annotations

import json
from collections.abc import Iterator
from urllib.error import HTTPError, URLError

import pytest

from src.core.schemas import LocalMindError, ModelError
from src.main import create_model_backend
from src.models.ollama_backend import OllamaModelBackend


class FakeTransport:
    """Scripted transport used to test adapter behavior without Ollama."""

    def __init__(
        self,
        *,
        get_results: dict[str, object] | None = None,
        post_results: list[object] | None = None,
        stream_results: list[object] | None = None,
    ) -> None:
        self.get_results = get_results or {
            "/api/tags": {"models": [{"name": "qwen3:4b"}]},
            "/api/version": {"version": "0.4.0"},
        }
        self.post_results = list(post_results or [{"response": ""}])
        self.stream_results = list(stream_results or [])
        self.calls: list[tuple[str, str, dict | None]] = []

    def get_json(self, path: str) -> dict:
        self.calls.append(("GET", path, None))
        result = self.get_results[path]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, dict)
        return result

    def post_json(self, path: str, payload: dict) -> dict:
        self.calls.append(("POST", path, payload))
        result = self.post_results.pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, dict)
        return result

    def post_ndjson(self, path: str, payload: dict) -> Iterator[dict]:
        self.calls.append(("STREAM", path, payload))
        for result in self.stream_results:
            if isinstance(result, Exception):
                raise result
            yield result


def _config(**overrides: object) -> dict:
    config: dict[str, object] = {
        "model": "qwen3:4b",
        "base_url": "http://localhost:11434",
        "keep_alive": "30m",
        "request_timeout_seconds": 10,
    }
    config.update(overrides)
    return config


def _loaded_backend(transport: FakeTransport) -> OllamaModelBackend:
    backend = OllamaModelBackend(_config(), transport=transport)
    backend.load()
    return backend


def test_generate_without_schema_returns_text_response() -> None:
    transport = FakeTransport(post_results=[{"response": ""}, {"response": "hello"}])
    backend = _loaded_backend(transport)

    assert backend.generate("say hello") == {"text": "hello"}
    assert transport.calls[-1] == (
        "POST",
        "/api/generate",
        {
            "model": "qwen3:4b",
            "prompt": "say hello",
            "stream": False,
            "keep_alive": "30m",
            "think": False,
            "options": {},
        },
    )


def test_generate_removes_qwen_thinking_block_from_visible_text() -> None:
    transport = FakeTransport(
        post_results=[
            {"response": ""},
            {"response": "<think>private reasoning</think>\n最终答案"},
        ]
    )
    backend = _loaded_backend(transport)

    assert backend.generate("answer") == {"text": "最终答案"}


def test_generate_removes_reasoning_before_orphan_closing_tag() -> None:
    transport = FakeTransport(
        post_results=[{"response": ""}, {"response": "private reasoning</think>\nanswer"}]
    )
    backend = _loaded_backend(transport)

    assert backend.generate("answer") == {"text": "answer"}


def test_factory_creates_ollama_backend_without_connecting() -> None:
    backend = create_model_backend({"model_backend": {"type": "ollama", "config": _config()}})

    assert isinstance(backend, OllamaModelBackend)


def test_generate_with_schema_uses_json_baseline_and_returns_parsed_object() -> None:
    response = json.dumps({"state": "READY", "intent_type": "echo_message"})
    transport = FakeTransport(post_results=[{"response": ""}, {"response": response}])
    backend = _loaded_backend(transport)

    result = backend.generate("echo hello", response_schema={"type": "object"})

    assert result == {"state": "READY", "intent_type": "echo_message"}
    payload = transport.calls[-1][2]
    assert payload is not None
    assert payload["format"] == "json"
    assert "JSON Schema" in payload["prompt"]


def test_invalid_structured_response_raises_model_parse_error() -> None:
    transport = FakeTransport(post_results=[{"response": ""}, {"response": "not json"}])
    backend = _loaded_backend(transport)

    with pytest.raises(ModelError, match="Invalid structured") as raised:
        backend.generate("echo", response_schema={"type": "object"})

    assert raised.value.code == "MODEL_PARSE_ERROR"
    assert raised.value.recoverable is True


def test_stream_yields_chunks_and_accepts_final_done_record_without_response() -> None:
    transport = FakeTransport(
        stream_results=[
            {"response": "hello", "done": False},
            {"response": " world"},
            {"done": True, "total_duration": 1},
        ]
    )
    backend = _loaded_backend(transport)

    assert list(backend.stream("say hello")) == ["hello", " world"]


def test_malformed_stream_record_raises_model_parse_error() -> None:
    backend = _loaded_backend(FakeTransport(stream_results=[{"response": 4}]))

    with pytest.raises(ModelError) as raised:
        list(backend.stream("say hello"))

    assert raised.value.code == "MODEL_PARSE_ERROR"


def test_non_object_and_non_boolean_done_stream_records_raise_model_parse_error() -> None:
    for record in [["not", "an", "object"], {"done": "true"}]:
        backend = _loaded_backend(FakeTransport(stream_results=[record]))

        with pytest.raises(ModelError) as raised:
            list(backend.stream("say hello"))

        assert raised.value.code == "MODEL_PARSE_ERROR"


def test_connection_and_timeout_errors_are_mapped_to_model_errors() -> None:
    unavailable = OllamaModelBackend(_config(), transport=FakeTransport(post_results=[OSError("offline")]))
    with pytest.raises(ModelError) as unavailable_error:
        unavailable.load()

    assert unavailable_error.value.code == "MODEL_UNAVAILABLE"
    assert unavailable_error.value.recoverable is True

    transport = FakeTransport(post_results=[{"response": ""}, TimeoutError("slow")])
    backend = _loaded_backend(transport)
    with pytest.raises(ModelError) as timeout_error:
        backend.generate("hello")

    assert timeout_error.value.code == "MODEL_TIMEOUT"
    assert timeout_error.value.recoverable is True

    transport = FakeTransport(post_results=[{"response": ""}, URLError(TimeoutError("slow"))])
    backend = _loaded_backend(transport)
    with pytest.raises(ModelError) as url_timeout_error:
        backend.generate("hello")

    assert url_timeout_error.value.code == "MODEL_TIMEOUT"


def test_health_check_is_boolean_and_load_is_idempotent() -> None:
    transport = FakeTransport()
    backend = OllamaModelBackend(_config(), transport=transport)

    assert backend.health_check() is True
    backend.load()
    backend.load()

    assert [call[0] for call in transport.calls].count("POST") == 1


def test_health_check_returns_false_when_model_is_missing_or_transport_fails() -> None:
    missing_model = OllamaModelBackend(
        _config(),
        transport=FakeTransport(get_results={"/api/tags": {"models": []}}),
    )
    unavailable = OllamaModelBackend(
        _config(),
        transport=FakeTransport(get_results={"/api/tags": OSError("offline")}),
    )

    assert missing_model.health_check() is False
    assert unavailable.health_check() is False


def test_load_maps_missing_model_to_non_recoverable_unavailable() -> None:
    backend = OllamaModelBackend(
        _config(),
        transport=FakeTransport(post_results=[HTTPError("http://test", 404, "missing", {}, None)]),
    )

    with pytest.raises(ModelError) as raised:
        backend.load()

    assert raised.value.code == "MODEL_UNAVAILABLE"
    assert raised.value.recoverable is False


def test_calls_require_load_and_unload_prevents_implicit_reload() -> None:
    transport = FakeTransport()
    backend = OllamaModelBackend(_config(), transport=transport)

    with pytest.raises(ModelError) as before_load:
        backend.generate("hello")
    assert before_load.value.code == "MODEL_UNAVAILABLE"
    assert transport.calls == []

    backend.load()
    backend.unload()
    request_count = len(transport.calls)
    with pytest.raises(ModelError):
        backend.get_capabilities()

    assert len(transport.calls) == request_count


def test_unload_swallows_transport_errors() -> None:
    transport = FakeTransport(post_results=[{"response": ""}, OSError("offline")])
    backend = _loaded_backend(transport)

    backend.unload()

    assert backend.health_check() is True


def test_capabilities_report_schema_support_only_when_schema_format_is_available() -> None:
    schema_transport = FakeTransport(
        get_results={
            "/api/tags": {"models": [{"name": "qwen3:4b"}]},
            "/api/version": {"version": "0.5.0"},
        }
    )
    schema_backend = _loaded_backend(schema_transport)
    fallback_backend = _loaded_backend(FakeTransport())

    assert schema_backend.get_capabilities().supports_structured_output is True
    assert fallback_backend.get_capabilities().supports_structured_output is False


@pytest.mark.parametrize(
    "override",
    [
        {"base_url": "http://10.0.0.5:11434"},
        {"base_url": "http://127.evil.com:11434"},
        {"request_timeout_seconds": "fast"},
        {"num_ctx": 0},
        {"options": []},
        {"keep_alive": -1},
        {"think": "false"},
    ],
)
def test_invalid_config_raises_config_error(override: dict[str, object]) -> None:
    with pytest.raises(LocalMindError) as raised:
        OllamaModelBackend(_config(**override), transport=FakeTransport())

    assert raised.value.code == "CONFIG_ERROR"


def test_missing_model_raises_config_error() -> None:
    with pytest.raises(LocalMindError) as raised:
        OllamaModelBackend({}, transport=FakeTransport())

    assert raised.value.code == "CONFIG_ERROR"
