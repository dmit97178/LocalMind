"""OpenAI-compatible cloud advisory transport and adapter."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from src.adapters.cloud_profiles import CloudProviderProfile
from src.core.interfaces import CloudAdvisoryBackend
from src.core.schemas import AdvisoryResult, CloudRequestPackage, LocalMindError

_JSON_OUTPUT_PROTOCOL = """仅输出一个 JSON 对象，不要 Markdown、围栏或解释文字。
字段必须为：analysis（字符串，必填）、suggested_tools（字符串数组或 null）、risks（字符串数组）、requires_local_validation（布尔值且必须为 true）、needs_more_info（布尔值）、requested_context_categories（字符串数组）、followup_question（字符串）。
最小示例：{"analysis":"<对候选上下文的分析建议>","suggested_tools":null,"risks":[],"requires_local_validation":true,"needs_more_info":false,"requested_context_categories":[],"followup_question":""}。"""
_LOCAL_BOUNDARY_FIELDS = frozenset(
    {"task_id", "session_id", "provider", "purpose", "grant_id", "turn", "fingerprint"}
)


class CloudCredentialLoader(Protocol):
    def exists(self, profile: CloudProviderProfile) -> bool: ...

    def get(self, profile: CloudProviderProfile) -> str: ...


class EnvCredentialLoader:
    """Read only the environment variable assigned to the active provider."""

    def exists(self, profile: CloudProviderProfile) -> bool:
        return bool(self._value(profile))

    def get(self, profile: CloudProviderProfile) -> str:
        value = self._value(profile)
        if value:
            return value
        raise LocalMindError(
            code="CLOUD_CREDENTIAL_MISSING",
            message=f"Cloud credential missing for provider {profile.provider_id}",
            user_message=(
                f"未配置 {profile.provider_id} 的 API Key，请设置 {profile.credential_env}。"
            ),
            recoverable=False,
        )

    @staticmethod
    def _value(profile: CloudProviderProfile) -> str:
        value = os.environ.get(profile.credential_env, "").strip()
        if not value and profile.provider_id == "deepseek":
            value = os.environ.get("LOCALMIND_CLOUD_API_KEY", "").strip()
        return value


class CloudTransport(Protocol):
    def post_json(self, path: str, payload: dict, headers: dict) -> dict: ...


class NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so credentials never leave the configured origin."""

    def redirect_request(
        self,
        req: object,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


class UrllibCloudTransport:
    """Dependency-free JSON transport with redirects disabled."""

    def __init__(self, api_base: str, timeout_seconds: float) -> None:
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(NoRedirectHandler())

    def post_json(self, path: str, payload: dict, headers: dict) -> dict:
        request = Request(
            f"{self._api_base}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with self._opener.open(request, timeout=self._timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Cloud response must be a JSON object")
        return parsed


class OpenAICompatibleAdvisoryBackend(CloudAdvisoryBackend):
    """Translate the advisory contract to an allowlisted OpenAI-compatible profile."""

    def __init__(
        self,
        profile: CloudProviderProfile,
        model: str,
        request_timeout_seconds: float,
        transport: CloudTransport | None = None,
        credential_loader: CloudCredentialLoader | None = None,
    ) -> None:
        if not isinstance(profile, CloudProviderProfile) or not profile.openai_compatible:
            raise _config_error("Cloud provider profile is not OpenAI compatible")
        if not profile.api_base or not profile.completion_path:
            raise _config_error("Cloud provider profile has no endpoint")
        if not isinstance(model, str) or not model.strip():
            raise _config_error("Cloud advisory model must be a non-empty string")
        if (
            not isinstance(request_timeout_seconds, (int, float))
            or isinstance(request_timeout_seconds, bool)
            or request_timeout_seconds <= 0
        ):
            raise _config_error("Cloud advisory timeout must be positive")
        self._profile = profile
        self._model = model.strip()
        self._credential_loader = credential_loader or EnvCredentialLoader()
        self._transport = transport or UrllibCloudTransport(
            profile.api_base, float(request_timeout_seconds)
        )

    def advise(self, request: CloudRequestPackage) -> AdvisoryResult:
        if not isinstance(request, CloudRequestPackage):
            raise _parse_error("Cloud request package had an invalid type")
        payload = {
            "model": self._model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": f"{_JSON_OUTPUT_PROTOCOL}\n{request.allowed_scope}",
                },
                {"role": "user", "content": _request_content(request)},
            ],
        }
        credential = self._credential_loader.get(self._profile)
        try:
            response = self._transport.post_json(
                self._profile.completion_path,
                payload,
                {"Authorization": f"Bearer {credential}"},
            )
            return _advisory_result(response)
        except LocalMindError:
            raise
        except HTTPError as exc:
            raise _http_error(exc.code, self._profile.provider_id) from exc
        except (HTTPException, URLError, OSError, TimeoutError) as exc:
            raise _unavailable_error(self._profile.provider_id, type(exc).__name__) from exc
        except (TypeError, ValueError, json.JSONDecodeError, KeyError, IndexError) as exc:
            raise _parse_error(f"Invalid cloud advisory response: {type(exc).__name__}") from exc


def _request_content(request: CloudRequestPackage) -> str:
    content = {
        "allowed_scope": request.allowed_scope,
        "context": [
            {
                "category": item.category,
                "label": item.label,
                "value": item.value,
                "redacted": item.redacted,
            }
            for item in request.context_items
        ],
    }
    _assert_no_local_boundary_fields(content)
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def _assert_no_local_boundary_fields(value: object) -> None:
    """Reject local authorization keys anywhere in the outbound content shape."""

    if isinstance(value, Mapping):
        if _LOCAL_BOUNDARY_FIELDS.intersection(str(key) for key in value):
            raise LocalMindError(
                code="SAFETY_CLOUD_BLOCK",
                message="Cloud adapter payload included local boundary fields",
                user_message="数据发送到云端被安全策略拦截。",
                recoverable=False,
            )
        for item in value.values():
            _assert_no_local_boundary_fields(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _assert_no_local_boundary_fields(item)


def _advisory_result(response: dict) -> AdvisoryResult:
    if not isinstance(response, dict):
        raise ValueError("Cloud response was not an object")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Cloud response did not include a choice")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ValueError("Cloud response did not include message content")
    content = message["content"].strip()
    if content.startswith("```json") and content.endswith("```"):
        content = content[7:-3].strip()
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("analysis"), str):
        raise ValueError("Cloud response did not include advisory analysis")
    risks = parsed.get("risks", [])
    suggested_tools = parsed.get("suggested_tools")
    requested = parsed.get("requested_context_categories", [])
    followup = parsed.get("followup_question", "")
    return AdvisoryResult(
        analysis=parsed["analysis"],
        risks=risks if isinstance(risks, list) else [],
        suggested_tools=suggested_tools if isinstance(suggested_tools, list) else None,
        requires_local_validation=True,
        needs_more_info=parsed.get("needs_more_info") is True,
        requested_context_categories=(
            tuple(item for item in requested if isinstance(item, str))
            if isinstance(requested, list)
            else ()
        ),
        followup_question=followup if isinstance(followup, str) else "",
    )


def _http_error(status: int, provider: str) -> LocalMindError:
    if status in {401, 403}:
        return LocalMindError(
            code="CLOUD_AUTH_INVALID",
            message=f"Cloud authentication failed for {provider}: HTTP {status}",
            user_message=f"云端凭据无效或无权限，请检查 {provider} 的 API Key。",
            recoverable=False,
            details={"provider": provider, "http_status": status},
        )
    if status == 429:
        return LocalMindError(
            code="CLOUD_RATE_LIMITED",
            message=f"Cloud rate limit reached for {provider}: HTTP 429",
            user_message="云端请求达到限流或配额上限，请稍后再试。",
            recoverable=True,
            details={"provider": provider, "http_status": status},
        )
    if status == 408 or status >= 500:
        return _unavailable_error(provider, f"HTTP {status}", status)
    return LocalMindError(
        code="CLOUD_ENDPOINT_INVALID",
        message=f"Cloud endpoint rejected request for {provider}: HTTP {status}",
        user_message="云端模型或服务地址配置有误，请检查 provider 与 connection.model。",
        recoverable=False,
        details={"provider": provider, "http_status": status},
    )


def _unavailable_error(
    provider: str, reason: str, http_status: int | None = None
) -> LocalMindError:
    details: dict[str, object] = {"provider": provider, "reason": reason}
    if http_status is not None:
        details["http_status"] = http_status
    return LocalMindError(
        code="CLOUD_UNAVAILABLE",
        message=f"Cloud service unavailable for {provider}: {reason}",
        user_message="云端服务暂不可用。",
        recoverable=True,
        details=details,
    )


def _parse_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="CLOUD_PARSE_ERROR",
        message=message,
        user_message="云端返回格式异常。",
        recoverable=True,
    )


def _config_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=message,
        user_message="云端配置无效，请检查 provider 与 connection 设置。",
        recoverable=False,
    )
