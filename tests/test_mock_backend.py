"""Tests for the P0 mock model backend."""

from src.core.interfaces import ModelBackend
from src.core.schemas import ModelCapabilities, ModelError
from src.models.mock_backend import MockModelBackend


def test_mock_model_backend_implements_model_backend() -> None:
    backend = MockModelBackend()

    assert isinstance(backend, ModelBackend)


def test_health_check_tracks_load_state() -> None:
    backend = MockModelBackend()

    assert backend.health_check() is False
    backend.load()
    assert backend.health_check() is True
    backend.unload()
    assert backend.health_check() is False


def test_get_capabilities_after_load_returns_p0_mock_capabilities() -> None:
    backend = MockModelBackend()
    backend.load()

    assert backend.get_capabilities() == ModelCapabilities(
        supports_structured_output=True,
        max_context_tokens=4096,
        local_only=True,
    )


def test_get_capabilities_before_load_raises_model_error() -> None:
    backend = MockModelBackend()

    try:
        backend.get_capabilities()
    except ModelError as exc:
        assert exc.code == "MODEL_UNAVAILABLE"
        assert exc.recoverable is True
    else:
        raise AssertionError("get_capabilities should require load() first")


def test_generate_without_schema_returns_text_dict() -> None:
    backend = MockModelBackend()
    backend.load()

    result = backend.generate("hello")

    assert result == {"text": "Mock response: hello"}


def test_generate_with_schema_returns_configured_structured_response_copy() -> None:
    structured_response = {
        "state": "READY",
        "intent_type": "check_system_status",
        "entities": {"target": "port"},
    }
    backend = MockModelBackend(structured_response=structured_response)
    backend.load()

    result = backend.generate("check port", response_schema={"type": "object"})
    result["entities"]["target"] = "mutated"

    assert result is not structured_response
    assert structured_response["entities"]["target"] == "port"


def test_generate_before_load_raises_model_error() -> None:
    backend = MockModelBackend()

    try:
        backend.generate("hello")
    except ModelError as exc:
        assert exc.code == "MODEL_UNAVAILABLE"
        assert exc.recoverable is True
    else:
        raise AssertionError("generate should require load() first")


def test_stream_returns_text_chunks() -> None:
    backend = MockModelBackend(text_response="alpha beta")
    backend.load()

    assert list(backend.stream("ignored")) == ["alpha", " ", "beta"]


def test_stream_uses_default_prompt_response_when_text_response_is_not_configured() -> None:
    backend = MockModelBackend()
    backend.load()

    assert list(backend.stream("hello world")) == [
        "Mock",
        " ",
        "response:",
        " ",
        "hello",
        " ",
        "world",
    ]


def test_calls_after_unload_raise_model_unavailable() -> None:
    backend = MockModelBackend()
    backend.load()
    backend.unload()

    for call in [lambda: backend.generate("hello"), lambda: list(backend.stream("hello"))]:
        try:
            call()
        except ModelError as exc:
            assert exc.code == "MODEL_UNAVAILABLE"
            assert exc.user_message == "本地模型尚未就绪，请稍候。"
            assert exc.recoverable is True
        else:
            raise AssertionError("model calls should fail after unload()")
