"""Ollama-backed implementation of the local ModelBackend contract."""

from __future__ import annotations

import json
import re
import socket
from collections.abc import Iterator
from ipaddress import ip_address
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from src.core.interfaces import ModelBackend
from src.core.schemas import LocalMindError, ModelCapabilities, ModelError

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_KEEP_ALIVE = "30m"
_DEFAULT_TIMEOUT_SECONDS = 120
_DEFAULT_CONTEXT_TOKENS = 4096
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.IGNORECASE | re.DOTALL)
_THINK_CLOSE_RE = re.compile(r"</think>\s*", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>", re.IGNORECASE)


class OllamaTransport(Protocol):
    """Small transport seam that keeps backend tests independent of Ollama."""

    def get_json(self, path: str) -> dict: ...

    def post_json(self, path: str, payload: dict) -> dict: ...

    def post_ndjson(self, path: str, payload: dict) -> Iterator[dict]: ...


class _UrllibOllamaTransport:
    """Zero-dependency HTTP transport for a loopback Ollama service."""

    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_json(self, path: str) -> dict:
        request = Request(f"{self._base_url}{path}", method="GET")
        return self._read_json(request)

    def post_json(self, path: str, payload: dict) -> dict:
        request = self._json_request(path, payload)
        return self._read_json(request)

    def post_ndjson(self, path: str, payload: dict) -> Iterator[dict]:
        request = self._json_request(path, payload)
        with urlopen(request, timeout=self._timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if line:
                    yield json.loads(line)

    def _json_request(self, path: str, payload: dict) -> Request:
        body = json.dumps(payload).encode("utf-8")
        return Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def _read_json(self, request: Request) -> dict:
        with urlopen(request, timeout=self._timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Ollama response must be a JSON object")
        return parsed


class OllamaModelBackend(ModelBackend):
    """Adapter that converts Ollama REST calls into the ModelBackend contract."""

    def __init__(self, config: dict, transport: OllamaTransport | None = None) -> None:
        self._model = _required_string(config, "model")
        self._base_url = _loopback_url(config.get("base_url", _DEFAULT_BASE_URL))
        self._keep_alive = _keep_alive(config.get("keep_alive", _DEFAULT_KEEP_ALIVE))
        self._timeout_seconds = _positive_number(
            config.get("request_timeout_seconds", _DEFAULT_TIMEOUT_SECONDS),
            "request_timeout_seconds",
        )
        self._think = _boolean(config.get("think", False), "think")
        self._num_ctx = _optional_positive_int(config.get("num_ctx"), "num_ctx")
        self._options = _options(config.get("options", {}))
        if self._num_ctx is not None:
            self._options["num_ctx"] = self._num_ctx

        self._transport = transport or _UrllibOllamaTransport(self._base_url, self._timeout_seconds)
        self._loaded = False
        self._supports_schema_format = False

    def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
        self._ensure_loaded("generate")
        if response_schema is None:
            response = self._post_json(self._generate_payload(prompt))
            return {"text": _response_text(response)}

        response = self._structured_response(prompt, response_schema)
        text = _response_text(response)
        try:
            parsed = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _parse_error("Invalid structured Ollama response") from exc
        if not isinstance(parsed, dict):
            raise _parse_error("Structured Ollama response was not an object")
        return parsed

    def stream(self, prompt: str) -> Iterator[str]:
        self._ensure_loaded("stream")
        payload = self._generate_payload(prompt, stream=True)
        try:
            for record in self._transport.post_ndjson("/api/generate", payload):
                if not isinstance(record, dict):
                    raise _parse_error("Ollama stream record was not an object")
                if "response" in record and not isinstance(record["response"], str):
                    raise _parse_error("Ollama stream response was not text")
                response = record.get("response", "")
                if response:
                    yield response
                done = record.get("done", False)
                if not isinstance(done, bool):
                    raise _parse_error("Ollama stream done flag was not boolean")
                if done:
                    return
        except ModelError:
            raise
        except Exception as exc:
            raise _model_error(exc) from exc

    def get_capabilities(self) -> ModelCapabilities:
        self._ensure_loaded("get_capabilities")
        return ModelCapabilities(
            supports_structured_output=self._supports_schema_format,
            max_context_tokens=self._num_ctx or _DEFAULT_CONTEXT_TOKENS,
            local_only=True,
        )

    def load(self) -> None:
        if self._loaded:
            return
        self._supports_schema_format = self._detect_schema_format_support()
        self._post_json(self._generate_payload(""))
        self._loaded = True

    def unload(self) -> None:
        if not self._loaded:
            return
        try:
            payload = self._generate_payload("")
            payload["keep_alive"] = 0
            self._transport.post_json("/api/generate", payload)
        except Exception:
            pass
        finally:
            self._loaded = False

    def health_check(self) -> bool:
        try:
            payload = self._transport.get_json("/api/tags")
            models = payload.get("models", [])
            return any(isinstance(item, dict) and item.get("name") == self._model for item in models)
        except Exception:
            return False

    def _structured_response(self, prompt: str, response_schema: dict) -> dict:
        if self._supports_schema_format:
            payload = self._generate_payload(prompt)
            payload["format"] = response_schema
            try:
                return self._post_json(payload)
            except ModelError as exc:
                if not _is_schema_rejection(exc):
                    raise
                self._supports_schema_format = False

        schema_prompt = f"{prompt}\n\nOnly return an object matching this JSON Schema:\n{json.dumps(response_schema)}"
        payload = self._generate_payload(schema_prompt)
        payload["format"] = "json"
        return self._post_json(payload)

    def _generate_payload(self, prompt: str, *, stream: bool = False) -> dict:
        return {
            "model": self._model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "think": self._think,
            "options": dict(self._options),
        }

    def _post_json(self, payload: dict) -> dict:
        try:
            return self._transport.post_json("/api/generate", payload)
        except Exception as exc:
            raise _model_error(exc) from exc

    def _detect_schema_format_support(self) -> bool:
        try:
            version_data = self._transport.get_json("/api/version")
            version = version_data.get("version")
            return isinstance(version, str) and _version_at_least(version, (0, 5, 0))
        except Exception:
            return False

    def _ensure_loaded(self, operation: str) -> None:
        if self._loaded:
            return
        raise ModelError(
            code="MODEL_UNAVAILABLE",
            message=f"Ollama model must be loaded before {operation}",
            user_message="本地模型尚未就绪，请稍候。",
            recoverable=True,
            details={"operation": operation},
        )


def _required_string(config: dict, key: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise _config_error(f"{key} must be a non-empty string")


def _loopback_url(value: object) -> str:
    if not isinstance(value, str):
        raise _config_error("base_url must be a string")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"}:
        raise _config_error("base_url must be an HTTP(S) URL without a path")
    host = parsed.hostname.lower()
    if host != "localhost" and not _is_loopback_ip(host):
        raise LocalMindError(
            code="CONFIG_ERROR",
            message=f"Ollama base_url must be loopback, got {value}",
            user_message="当前仅支持本机 Ollama。",
            recoverable=False,
            details={"base_url": value},
        )
    return value.rstrip("/")


def _is_loopback_ip(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _keep_alive(value: object) -> str | int | float:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return value
    raise _config_error("keep_alive must be a non-empty string or non-negative number")


def _positive_number(value: object, key: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    raise _config_error(f"{key} must be a positive number")


def _optional_positive_int(value: object, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise _config_error(f"{key} must be a positive integer")


def _boolean(value: object, key: str) -> bool:
    if isinstance(value, bool):
        return value
    raise _config_error(f"{key} must be a boolean")


def _options(value: object) -> dict:
    if not isinstance(value, dict):
        raise _config_error("options must be a mapping")
    copied = dict(value)
    try:
        json.dumps(copied)
    except (TypeError, ValueError) as exc:
        raise _config_error("options must be JSON serializable") from exc
    return copied


def _response_text(response: dict) -> str:
    value = response.get("response")
    if not isinstance(value, str):
        raise _parse_error("Ollama response did not include text")
    return _strip_thinking(value)


def _strip_thinking(value: str) -> str:
    """Remove Qwen reasoning wrappers even when Ollama omits the opening tag."""

    visible = _THINK_BLOCK_RE.sub("", value)
    if _THINK_CLOSE_RE.search(visible):
        visible = _THINK_CLOSE_RE.split(visible)[-1]
    opening = _THINK_OPEN_RE.search(visible)
    if opening is not None:
        visible = visible[:opening.start()]
    return visible.strip()


def _version_at_least(value: str, minimum: tuple[int, int, int]) -> bool:
    try:
        parsed = tuple(int(part) for part in value.split(".")[:3])
    except ValueError:
        return False
    padded = parsed + (0,) * (3 - len(parsed))
    return padded >= minimum


def _is_schema_rejection(error: ModelError) -> bool:
    return error.details is not None and error.details.get("status") == 400


def _model_error(error: Exception) -> ModelError:
    if isinstance(error, ModelError):
        return error
    if isinstance(error, TimeoutError | socket.timeout):
        return ModelError(
            code="MODEL_TIMEOUT",
            message=f"Ollama request timed out: {error}",
            user_message="模型响应超时，请稍后重试。",
            recoverable=True,
            details={},
        )
    if isinstance(error, URLError) and isinstance(error.reason, TimeoutError | socket.timeout):
        return ModelError(
            code="MODEL_TIMEOUT",
            message=f"Ollama request timed out: {error.reason}",
            user_message="模型响应超时，请稍后重试。",
            recoverable=True,
            details={},
        )
    if isinstance(error, HTTPError):
        return ModelError(
            code="MODEL_UNAVAILABLE",
            message=f"Ollama returned HTTP {error.code}",
            user_message="本地模型不可用，请检查 Ollama 与模型是否就绪。",
            recoverable=False,
            details={"status": error.code},
        )
    if isinstance(error, (json.JSONDecodeError, ValueError)):
        return _parse_error(f"Invalid Ollama JSON response: {error}")
    if isinstance(error, (OSError, URLError)):
        return ModelError(
            code="MODEL_UNAVAILABLE",
            message=f"Ollama connection failed: {error}",
            user_message="本地模型尚未就绪，请稍候。",
            recoverable=True,
            details={},
        )
    return ModelError(
        code="MODEL_UNAVAILABLE",
        message=f"Unexpected Ollama transport failure: {error}",
        user_message="本地模型尚未就绪，请稍候。",
        recoverable=True,
        details={},
    )


def _parse_error(message: str) -> ModelError:
    return ModelError(
        code="MODEL_PARSE_ERROR",
        message=message,
        user_message="模型返回格式异常，正在重试。",
        recoverable=True,
        details={},
    )


def _config_error(message: str) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR",
        message=message,
        user_message="系统配置有误，请检查 model_backend.config。",
        recoverable=False,
        details={},
    )
