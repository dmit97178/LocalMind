"""Allowlisted connection profiles for cloud advisory providers."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.schemas import LocalMindError


@dataclass(frozen=True)
class CloudProviderProfile:
    """Connection facts that configuration cannot override for built-in providers."""

    provider_id: str
    api_base: str
    completion_path: str
    default_model: str
    credential_env: str
    openai_compatible: bool = True


_PROFILES = {
    "deepseek": CloudProviderProfile(
        "deepseek",
        "https://api.deepseek.com",
        "/chat/completions",
        "deepseek-v4-flash",
        "LOCALMIND_DEEPSEEK_API_KEY",
    ),
    "glm": CloudProviderProfile(
        "glm",
        "https://open.bigmodel.cn/api/paas/v4",
        "/chat/completions",
        "glm-4.7-flash",
        "LOCALMIND_GLM_API_KEY",
    ),
    "custom_openai": CloudProviderProfile(
        "custom_openai",
        "",
        "/chat/completions",
        "",
        "LOCALMIND_CUSTOM_OPENAI_API_KEY",
    ),
}


class CloudProviderRegistry:
    """Resolve only providers explicitly shipped with LocalMind."""

    @staticmethod
    def resolve(provider_id: str) -> CloudProviderProfile:
        try:
            return _PROFILES[provider_id]
        except (KeyError, TypeError) as exc:
            raise LocalMindError(
                code="CONFIG_ERROR",
                message=f"Unsupported cloud advisory provider: {provider_id!r}",
                user_message="云端提供商配置无效，请检查 cloud_advisory.provider。",
                recoverable=False,
            ) from exc
