"""Contract tests for cloud provider profiles and the OpenAI-compatible adapter."""

from __future__ import annotations

import json
import threading
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from src.core.schemas import CloudRequestPackage, LocalMindError, PreparedContextItem


class RecordingTransport:
    def __init__(self, response: dict | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, dict, dict]] = []

    def post_json(self, path: str, payload: dict, headers: dict) -> dict:
        self.calls.append((path, payload, headers))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class StaticCredentialLoader:
    def __init__(self, credential: str = "provider-key") -> None:
        self.credential = credential
        self.exists_calls = 0
        self.get_calls = 0

    def exists(self, profile: object) -> bool:
        self.exists_calls += 1
        return bool(self.credential)

    def get(self, profile: object) -> str:
        self.get_calls += 1
        if not self.credential:
            raise LocalMindError(
                code="CLOUD_CREDENTIAL_MISSING",
                message="credential missing",
                user_message="未配置云端 API Key。",
                recoverable=False,
            )
        return self.credential


def _request(provider: str = "glm") -> CloudRequestPackage:
    return CloudRequestPackage(
        "task-1",
        "session-1",
        provider,
        "advisory",
        "grant-1",
        [PreparedContextItem("user_entity", "language", "python", False, "local-fingerprint")],
        "仅提供分析建议，不生成执行命令或计划",
        1,
    )


def _response(content: dict | str) -> dict:
    text = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else content
    return {"choices": [{"message": {"content": text}}]}


def test_registry_resolves_current_builtin_profiles() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry

    deepseek = CloudProviderRegistry.resolve("deepseek")
    glm = CloudProviderRegistry.resolve("glm")

    assert deepseek.api_base == "https://api.deepseek.com"
    assert deepseek.default_model == "deepseek-v4-flash"
    assert deepseek.credential_env == "LOCALMIND_DEEPSEEK_API_KEY"
    assert glm.api_base == "https://open.bigmodel.cn/api/paas/v4"
    assert glm.default_model == "glm-4.7-flash"
    assert glm.credential_env == "LOCALMIND_GLM_API_KEY"


def test_registry_rejects_unknown_provider() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry

    with pytest.raises(LocalMindError) as captured:
        CloudProviderRegistry.resolve("mystery")

    assert captured.value.code == "CONFIG_ERROR"
    assert captured.value.recoverable is False


def test_env_loader_keeps_provider_credentials_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import EnvCredentialLoader

    monkeypatch.setenv("LOCALMIND_DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LOCALMIND_GLM_API_KEY", "glm-key")
    loader = EnvCredentialLoader()

    assert loader.get(CloudProviderRegistry.resolve("deepseek")) == "deepseek-key"
    assert loader.get(CloudProviderRegistry.resolve("glm")) == "glm-key"


def test_adapter_sends_only_the_active_provider_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import (
        EnvCredentialLoader,
        OpenAICompatibleAdvisoryBackend,
    )

    monkeypatch.setenv("LOCALMIND_DEEPSEEK_API_KEY", "deepseek-only-key")
    monkeypatch.setenv("LOCALMIND_GLM_API_KEY", "glm-only-key")
    response = _response({"analysis": "ok"})
    deepseek_transport = RecordingTransport(response)
    glm_transport = RecordingTransport(response)

    OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("deepseek"),
        "deepseek-v4-flash",
        30,
        deepseek_transport,
        EnvCredentialLoader(),
    ).advise(_request("deepseek"))
    OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        glm_transport,
        EnvCredentialLoader(),
    ).advise(_request("glm"))

    assert deepseek_transport.calls[0][2]["Authorization"] == "Bearer deepseek-only-key"
    assert glm_transport.calls[0][2]["Authorization"] == "Bearer glm-only-key"


def test_env_loader_legacy_fallback_is_deepseek_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import EnvCredentialLoader

    monkeypatch.delenv("LOCALMIND_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LOCALMIND_GLM_API_KEY", raising=False)
    monkeypatch.setenv("LOCALMIND_CLOUD_API_KEY", "legacy-key")
    loader = EnvCredentialLoader()

    assert loader.get(CloudProviderRegistry.resolve("deepseek")) == "legacy-key"
    assert loader.exists(CloudProviderRegistry.resolve("glm")) is False
    with pytest.raises(LocalMindError) as captured:
        loader.get(CloudProviderRegistry.resolve("glm"))
    assert captured.value.code == "CLOUD_CREDENTIAL_MISSING"


def test_adapter_sends_provider_neutral_json_protocol_and_maps_response() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    transport = RecordingTransport(
        _response(
            {
                "analysis": "检查查询计划。",
                "risks": ["统计信息可能过期"],
                "suggested_tools": ["database.explain"],
                "requires_local_validation": True,
                "needs_more_info": True,
                "requested_context_categories": ["memory_evidence"],
                "followup_question": "请提供相关历史。",
            }
        )
    )
    loader = StaticCredentialLoader()
    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"), "glm-4.7-flash", 30, transport, loader
    )

    result = backend.advise(_request())

    path, payload, headers = transport.calls[0]
    assert path == "/chat/completions"
    assert payload["model"] == "glm-4.7-flash"
    assert payload["temperature"] == 0.1
    assert "仅输出" in payload["messages"][0]["content"]
    protocol = payload["messages"][0]["content"]
    for field in (
        "analysis",
        "suggested_tools",
        "risks",
        "requires_local_validation",
        "needs_more_info",
        "requested_context_categories",
        "followup_question",
    ):
        assert field in protocol
    assert '"analysis":"<对候选上下文的分析建议>"' in protocol
    assert "glm" not in protocol.lower()
    assert "provider-key" not in json.dumps(payload, ensure_ascii=False)
    assert headers["Authorization"] == "Bearer provider-key"
    assert loader.exists_calls == 0
    assert loader.get_calls == 1
    assert result.analysis == "检查查询计划。"
    assert result.requested_context_categories == ("memory_evidence",)


def test_adapter_never_serializes_local_boundary_fields() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    transport = RecordingTransport(_response({"analysis": "继续在本地验证。"}))
    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        transport,
        StaticCredentialLoader(),
    )

    backend.advise(_request())

    serialized = json.dumps(transport.calls[0][1], ensure_ascii=False)
    for forbidden in ("task-1", "session-1", "grant-1", "local-fingerprint", '"provider"'):
        assert forbidden not in serialized


def test_payload_guard_rejects_nested_local_boundary_field() -> None:
    from src.adapters.openai_compat_adapter import _assert_no_local_boundary_fields

    with pytest.raises(LocalMindError) as captured:
        _assert_no_local_boundary_fields(
            {"context": [{"category": "user_entity", "fingerprint": "must-stay-local"}]}
        )

    assert captured.value.code == "SAFETY_CLOUD_BLOCK"
    assert captured.value.recoverable is False


def test_adapter_accepts_json_fence() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        RecordingTransport(_response('```json\n{"analysis":"ok"}\n```')),
        StaticCredentialLoader(),
    )

    assert backend.advise(_request()).analysis == "ok"


def _http_error(status: int) -> HTTPError:
    return HTTPError("https://provider.example/chat/completions", status, "error", {}, None)


@pytest.mark.parametrize(
    ("error", "code", "recoverable"),
    [
        (_http_error(302), "CLOUD_ENDPOINT_INVALID", False),
        (_http_error(401), "CLOUD_AUTH_INVALID", False),
        (_http_error(403), "CLOUD_AUTH_INVALID", False),
        (_http_error(400), "CLOUD_ENDPOINT_INVALID", False),
        (_http_error(404), "CLOUD_ENDPOINT_INVALID", False),
        (_http_error(429), "CLOUD_RATE_LIMITED", True),
        (_http_error(408), "CLOUD_UNAVAILABLE", True),
        (_http_error(500), "CLOUD_UNAVAILABLE", True),
        (_http_error(503), "CLOUD_UNAVAILABLE", True),
        (URLError("dns failed"), "CLOUD_UNAVAILABLE", True),
        (TimeoutError("timed out"), "CLOUD_UNAVAILABLE", True),
        (HTTPException("malformed status line"), "CLOUD_UNAVAILABLE", True),
    ],
)
def test_adapter_classifies_transport_failures(
    error: Exception, code: str, recoverable: bool
) -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        RecordingTransport(error),
        StaticCredentialLoader("unique-secret-marker"),
    )

    with pytest.raises(LocalMindError) as captured:
        backend.advise(_request())

    assert captured.value.code == code
    assert captured.value.recoverable is recoverable
    assert "unique-secret-marker" not in str(captured.value)
    assert "unique-secret-marker" not in str(captured.value.details)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        _response("not-json"),
        _response({"risks": []}),
    ],
)
def test_adapter_rejects_malformed_responses(response: dict) -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        RecordingTransport(response),
        StaticCredentialLoader(),
    )

    with pytest.raises(LocalMindError) as captured:
        backend.advise(_request())

    assert captured.value.code == "CLOUD_PARSE_ERROR"
    assert captured.value.recoverable is True


def test_adapter_constructor_does_not_read_credentials() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    loader = StaticCredentialLoader("")
    OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"), "glm-4.7-flash", 30, RecordingTransport({}), loader
    )

    assert loader.exists_calls == 0
    assert loader.get_calls == 0


def test_adapter_missing_credential_does_not_start_network() -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend

    transport = RecordingTransport(_response({"analysis": "unused"}))
    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        transport,
        StaticCredentialLoader(""),
    )

    with pytest.raises(LocalMindError) as captured:
        backend.advise(_request())

    assert captured.value.code == "CLOUD_CREDENTIAL_MISSING"
    assert transport.calls == []


def test_no_redirect_handler_refuses_redirect_request() -> None:
    from src.adapters.openai_compat_adapter import NoRedirectHandler

    assert (
        NoRedirectHandler().redirect_request(None, None, 302, "found", {}, "https://elsewhere")
        is None
    )


def test_default_transport_does_not_follow_redirect_or_forward_authorization() -> None:
    from src.adapters.openai_compat_adapter import UrllibCloudTransport

    target_requests: list[str | None] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            target_requests.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_address[1]}/capture")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    threads = [
        threading.Thread(target=server.serve_forever, daemon=True) for server in (target, redirect)
    ]
    for thread in threads:
        thread.start()
    try:
        transport = UrllibCloudTransport(f"http://127.0.0.1:{redirect.server_address[1]}", 2)
        with pytest.raises(HTTPError) as captured:
            transport.post_json("/chat/completions", {}, {"Authorization": "Bearer never-forward"})
        assert captured.value.code == 302
        assert target_requests == []
    finally:
        for server in (redirect, target):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_cloud_credential_never_leaks_to_persisted_channels(tmp_path: Path) -> None:
    from src.adapters.cloud_profiles import CloudProviderRegistry
    from src.adapters.openai_compat_adapter import (
        OpenAICompatibleAdvisoryBackend,
        _http_error,
    )
    from src.core.schemas import PrivacyPreparation, RuntimeEvent
    from src.evaluation.child import _transcript_writer
    from src.observability.sinks import JsonlEventSink
    from src.safety.authorization import AuthorizationManager
    from src.safety.cloud_boundary import CloudBoundary
    from src.safety.privacy_policy import PrivacyPolicy
    from src.safety.side_effect_gateway import SideEffectGateway

    credential = "sk-p6cLeakMarker123456789012345"
    item = PreparedContextItem("user_entity", "language", "python", False, "safe-fingerprint")
    preparation = PrivacyPreparation([item], [], frozenset({"user_entity"}), 80)
    manager = AuthorizationManager(600, 3, 3, 2048, 300)
    grant = manager.create_user_grant(preparation, "task-1", "session-1", "glm", "advisory", 10.0)
    package = PrivacyPolicy("balanced", 3, 2048).build_package(preparation, grant)
    backend = OpenAICompatibleAdvisoryBackend(
        CloudProviderRegistry.resolve("glm"),
        "glm-4.7-flash",
        30,
        RecordingTransport(_response({"analysis": "本地复核后再采用。"})),
        StaticCredentialLoader(credential),
    )
    gateway = SideEffectGateway(CloudBoundary(), backend, manager, now=lambda: 11.0)

    result = gateway.execute_cloud_turn(package, grant, "task-1", "intent-1", 1)

    event_path = tmp_path / "events.jsonl"
    JsonlEventSink(event_path).emit(
        RuntimeEvent(
            "run-1",
            "turn-1",
            "session-1",
            1,
            "2026-09-13T00:00:00+00:00",
            "cloud_consult",
            "detail",
            {"phase": "error", "raw_response": credential},
        )
    )
    transcript_path = tmp_path / "transcript.md"
    writer = _transcript_writer(transcript_path)
    assert writer is not None
    writer(credential, result.analysis, {"reason": credential})
    error = _http_error(401, "glm")

    persisted = "\n".join(
        (
            repr(gateway.audit_log),
            event_path.read_text(encoding="utf-8"),
            transcript_path.read_text(encoding="utf-8"),
            repr(error),
            str(error.details),
        )
    )
    assert credential not in persisted
