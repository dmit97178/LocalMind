"""Factory and configuration tests for the P6c cloud provider layer."""

from __future__ import annotations

import time
import tomllib
from pathlib import Path

import pytest

from src.core.schemas import ConsultationProposal, ContextCandidate, LocalMindError, MinimalContext


def _cloud(*, enabled: bool = True, provider: str = "glm", connection: dict | None = None) -> dict:
    return {
        "cloud_advisory": {
            "enabled": enabled,
            "provider": provider,
            "privacy_mode": "balanced",
            "max_context_items": 8,
            "context_byte_budget": 2048,
            "connection": connection or {},
            "policy": {"allowed_scope": "custom advisory scope"},
        }
    }


def test_factory_creates_glm_backend_with_profile_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.adapters.openai_compat_adapter import OpenAICompatibleAdvisoryBackend
    from src.main import create_cloud_advisory_backend

    monkeypatch.setenv("LOCALMIND_GLM_API_KEY", "glm-key")

    backend = create_cloud_advisory_backend(_cloud())

    assert isinstance(backend, OpenAICompatibleAdvisoryBackend)
    assert backend._profile.provider_id == "glm"
    assert backend._model == "glm-4.7-flash"


def test_factory_disabled_provider_has_no_outbound_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.adapters.openai_compat_adapter as adapter_module
    from src.main import create_cloud_advisory_backend
    from src.tools.cloud_advisory import NoopCloudAdvisoryBackend

    monkeypatch.setenv("LOCALMIND_GLM_API_KEY", "real-shaped-key")
    monkeypatch.setattr(
        adapter_module,
        "EnvCredentialLoader",
        lambda: pytest.fail("disabled provider constructed a credential loader"),
    )

    backend = create_cloud_advisory_backend(_cloud(enabled=False))

    assert isinstance(backend, NoopCloudAdvisoryBackend)


def test_factory_rejects_enabled_noop_provider() -> None:
    from src.main import create_cloud_advisory_backend

    with pytest.raises(LocalMindError) as captured:
        create_cloud_advisory_backend(_cloud(enabled=True, provider="noop"))

    assert captured.value.code == "CONFIG_ERROR"


def test_factory_enabled_provider_requires_its_own_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.main import create_cloud_advisory_backend

    monkeypatch.delenv("LOCALMIND_GLM_API_KEY", raising=False)
    monkeypatch.setenv("LOCALMIND_CLOUD_API_KEY", "wrong-provider-key")

    with pytest.raises(LocalMindError) as captured:
        create_cloud_advisory_backend(_cloud())

    assert captured.value.code == "CONFIG_ERROR"
    assert "LOCALMIND_GLM_API_KEY" in captured.value.user_message


def test_factory_migrates_legacy_deepseek_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.main import create_cloud_advisory_backend

    monkeypatch.delenv("LOCALMIND_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LOCALMIND_CLOUD_API_KEY", "legacy-deepseek-key")
    config = {
        "cloud_advisory": {
            "enabled": True,
            "backend": "deepseek",
            "config": {
                "api_base": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "request_timeout_seconds": 30,
                "allowed_scope": "legacy scope",
                "max_turns": 2,
            },
        }
    }

    backend = create_cloud_advisory_backend(config)

    assert backend._profile.provider_id == "deepseek"
    assert backend._model == "deepseek-v4-flash"


def test_factory_rejects_conflicting_provider_sources() -> None:
    from src.main import create_cloud_advisory_backend

    config = _cloud(enabled=False)
    config["cloud_advisory"]["backend"] = "deepseek"

    with pytest.raises(LocalMindError) as captured:
        create_cloud_advisory_backend(config)

    assert captured.value.code == "CONFIG_ERROR"
    assert "conflict" in captured.value.message.lower()


def test_factory_accepts_matching_new_and_legacy_provider_names() -> None:
    from src.main import create_cloud_advisory_backend
    from src.tools.cloud_advisory import NoopCloudAdvisoryBackend

    config = _cloud(enabled=False, provider="deepseek")
    config["cloud_advisory"]["backend"] = "deepseek"

    assert isinstance(create_cloud_advisory_backend(config), NoopCloudAdvisoryBackend)


def test_factory_rejects_unknown_provider_even_when_disabled() -> None:
    from src.main import create_cloud_advisory_backend

    with pytest.raises(LocalMindError) as captured:
        create_cloud_advisory_backend(_cloud(enabled=False, provider="unknown"))

    assert captured.value.code == "CONFIG_ERROR"


@pytest.mark.parametrize(
    "api_base",
    [
        "http://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example/v1?q=1",
        "https://provider.example/v1#fragment",
        "https://localhost/v1",
        "https://LOCALHOST./v1",
        "https://service.localhost./v1",
        "https://service.local/v1",
        "https://service.internal/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://169.254.1.1/v1",
        "https://[::1]/v1",
        "https://[fc00::1]/v1",
    ],
)
def test_factory_rejects_unsafe_custom_openai_url(api_base: str) -> None:
    from src.main import create_cloud_advisory_backend

    with pytest.raises(LocalMindError) as captured:
        create_cloud_advisory_backend(
            _cloud(
                enabled=False,
                provider="custom_openai",
                connection={"api_base": api_base, "model": "custom-model"},
            )
        )

    assert captured.value.code == "CONFIG_ERROR"
    assert "api_base" in captured.value.message


def test_factory_accepts_public_custom_openai_url_when_disabled() -> None:
    from src.main import create_cloud_advisory_backend
    from src.tools.cloud_advisory import NoopCloudAdvisoryBackend

    backend = create_cloud_advisory_backend(
        _cloud(
            enabled=False,
            provider="custom_openai",
            connection={"api_base": "https://provider.example/v1/", "model": "custom-model"},
        )
    )

    assert isinstance(backend, NoopCloudAdvisoryBackend)


def test_factory_rejects_builtin_endpoint_override() -> None:
    from src.main import create_cloud_advisory_backend

    with pytest.raises(LocalMindError) as captured:
        create_cloud_advisory_backend(
            _cloud(enabled=False, connection={"api_base": "https://proxy.example"})
        )

    assert captured.value.code == "CONFIG_ERROR"
    assert "api_base" in captured.value.message


def test_privacy_policy_builds_package_with_configured_scope() -> None:
    from src.safety.authorization import AuthorizationManager
    from src.safety.privacy_policy import PrivacyPolicy

    policy = PrivacyPolicy("balanced", 8, 2048, allowed_scope="custom advisory scope")
    preparation = policy.prepare(
        ConsultationProposal(
            True,
            "architecture_tradeoff",
            0.9,
            candidate_context=[ContextCandidate("user_entity", "language", "python")],
        ),
        MinimalContext(system_prompt="test"),
        "task-1",
        "session-1",
        "glm",
        "architecture_tradeoff",
    )
    authorization = AuthorizationManager(600, 3, 8, 2048, 300)
    grant = authorization.create_user_grant(
        preparation,
        "task-1",
        "session-1",
        "glm",
        "architecture_tradeoff",
        time.time(),
    )

    package = policy.build_package(preparation, grant)

    assert package.allowed_scope == "custom advisory scope"


def test_bootstrap_exposes_normalized_provider_and_policy_scope(tmp_path: Path) -> None:
    from src.main import bootstrap
    from src.models.mock_backend import MockModelBackend

    source = Path(__file__).parents[1] / "config" / "default.toml"
    text = (
        source.read_text(encoding="utf-8")
        .replace('provider = "noop"', 'provider = "glm"')
        .replace(
            'allowed_scope = "仅提供分析建议，不生成执行命令或计划"',
            'allowed_scope = "custom advisory scope"',
        )
    )
    config_path = tmp_path / "config.toml"
    config_path.write_text(text, encoding="utf-8")

    app = bootstrap(str(config_path), model_backend_override=MockModelBackend())

    assert app.cloud_provider == "glm"
    assert app.cloud_enabled is False
    assert app.privacy_policy.allowed_scope == "custom advisory scope"


@pytest.mark.parametrize(
    "name",
    (
        "default.toml",
        "ollama.example.toml",
        "eval.example.toml",
        "cloud_advisory.example.toml",
    ),
)
def test_repository_cloud_configs_use_provider_shape(name: str) -> None:
    path = Path(__file__).parents[1] / "config" / name
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    cloud = config["cloud_advisory"]

    assert cloud["provider"] in {"noop", "deepseek", "glm", "custom_openai"}
    assert "backend" not in cloud
    assert isinstance(cloud["connection"], dict)
    assert isinstance(cloud["policy"]["allowed_scope"], str)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("CLOUD_AUTH_INVALID", "auth"),
        ("CLOUD_CREDENTIAL_MISSING", "auth"),
        ("CLOUD_ENDPOINT_INVALID", "endpoint"),
        ("CLOUD_RATE_LIMITED", "rate_limited"),
        ("CLOUD_UNAVAILABLE", "unavailable"),
        ("CLOUD_PARSE_ERROR", "unavailable"),
        ("OTHER", "unavailable"),
    ],
)
def test_cloud_failure_reason_is_stable_for_runtime_events(code: str, reason: str) -> None:
    from src.main import _cloud_denied_reason

    assert _cloud_denied_reason(code) == reason
