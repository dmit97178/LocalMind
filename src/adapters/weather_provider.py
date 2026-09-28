"""Open-Meteo weather adapter with bounded, unauthenticated egress."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPException
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.schemas import LocalMindError, ToolError

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_MAX_RESPONSE_BYTES = 65536
_CHUNK_BYTES = 8192
_WEATHER_CODES = {
    0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴", 45: "雾", 48: "霜雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "强毛毛雨", 56: "冻毛毛雨",
    57: "强冻毛毛雨", 61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "强冻雨", 71: "小雪", 73: "中雪", 75: "大雪",
    77: "雪粒", 80: "小阵雨", 81: "中阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "强阵雪", 95: "雷雨", 96: "雷雨伴小冰雹",
    99: "雷雨伴大冰雹",
}


class WeatherProvider(Protocol):
    def current_weather(self, location: str) -> dict: ...


class WeatherOpener(Protocol):
    def open(self, request: Request, *, timeout: float) -> Any: ...


@dataclass(frozen=True)
class WeatherConnectionConfig:
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 10


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OpenMeteoProvider:
    def __init__(
        self,
        connection: WeatherConnectionConfig | None = None,
        *,
        opener: WeatherOpener | None = None,
        geocoding_url: str = _GEO_URL,
        forecast_url: str = _FORECAST_URL,
    ) -> None:
        self._connection = connection or WeatherConnectionConfig()
        for value in (self._connection.connect_timeout_seconds, self._connection.read_timeout_seconds):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise _config_error("Weather timeouts must be positive finite numbers", "weather_connection_invalid")
        _validate_endpoint(geocoding_url, "geocoding-api.open-meteo.com", "/v1/search")
        _validate_endpoint(forecast_url, "api.open-meteo.com", "/v1/forecast")
        self._geocoding_url = geocoding_url
        self._forecast_url = forecast_url
        self._opener = opener if opener is not None else build_opener(NoRedirectHandler())

    def current_weather(self, location: str) -> dict:
        geo = self._get_json(self._geocoding_url, {"name": location, "count": 1, "language": "zh", "format": "json"})
        try:
            results = geo.get("results", [])
            if not isinstance(results, list):
                raise ValueError("results must be an array")
            if not results:
                raise _tool_error("location_not_found")
            place = results[0]
            if not isinstance(place, dict):
                raise ValueError("geocoding result must be an object")
            name = _field(place, "name", str)
            latitude = _number(place, "latitude")
            longitude = _number(place, "longitude")
            labels = [name]
            for key in ("admin1", "country"):
                value = place.get(key)
                if value is not None:
                    if not isinstance(value, str):
                        raise ValueError(f"{key} must be text")
                    if value and value not in labels:
                        labels.append(value)
            forecast = self._get_json(self._forecast_url, {
                "latitude": latitude, "longitude": longitude,
                "current": "temperature_2m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "auto", "forecast_days": 1,
            })
            return _normalize(forecast, ", ".join(labels))
        except (KeyError, IndexError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise _tool_error("provider_parse_error") from exc

    def _get_json(self, base_url: str, params: dict) -> dict:
        expected_host = "geocoding-api.open-meteo.com" if base_url == self._geocoding_url else "api.open-meteo.com"
        expected_path = "/v1/search" if base_url == self._geocoding_url else "/v1/forecast"
        _validate_endpoint(base_url, expected_host, expected_path)
        request = Request(f"{base_url}?{urlencode(params)}", headers={"Accept": "application/json"})
        try:
            with self._opener.open(request, timeout=self._connection.connect_timeout_seconds) as response:
                started = time.monotonic()
                chunks = []
                size = 0
                while True:
                    if time.monotonic() - started > self._connection.read_timeout_seconds:
                        raise _tool_error("provider_timeout")
                    chunk = response.read(_CHUNK_BYTES)
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        raise _tool_error("provider_response_too_large")
                    if not chunk:
                        break
                    chunks.append(chunk)
            parsed = json.loads(b"".join(chunks).decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("JSON root must be an object")
            return parsed
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise _tool_error("provider_redirect_rejected") from exc
            raise _tool_error("provider_http_error", status=exc.code) from exc
        except TimeoutError as exc:
            raise _tool_error("provider_timeout") from exc
        except URLError as exc:
            reason = "provider_timeout" if isinstance(exc.reason, TimeoutError) else "provider_unreachable"
            raise _tool_error(reason) from exc
        except (OSError, HTTPException) as exc:
            raise _tool_error("provider_unreachable") from exc
        except (UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise _tool_error("provider_parse_error") from exc


def _validate_endpoint(url: str, host: str, path: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https" and parsed.hostname == host and
            parsed.port in (None, 443) and parsed.username is None and
            parsed.password is None and parsed.path == path and
            not parsed.query and not parsed.fragment and parsed.netloc == host
        )
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise _config_error("Weather endpoint is not allowlisted", "weather_endpoint_invalid")


def _field(value: dict, key: str, kind: type):
    item = value[key]
    if not isinstance(item, kind) or (kind is int and isinstance(item, bool)):
        raise ValueError(f"{key} has invalid type")
    return item


def _number(value: dict, key: str) -> float:
    item = value[key]
    if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
        raise ValueError(f"{key} must be a finite number")
    return float(item)


def _first(value: dict, key: str):
    items = _field(value, key, list)
    return items[0]


def _normalize(data: dict, location: str) -> dict:
    timezone = ZoneInfo(_field(data, "timezone", str))
    current = _field(data, "current", dict)
    daily = _field(data, "daily", dict)
    observed = datetime.fromisoformat(_field(current, "time", str))
    if observed.tzinfo is not None:
        raise ValueError("expected local observation time")
    forecast_date = _first(daily, "time")
    if not isinstance(forecast_date, str) or datetime.fromisoformat(forecast_date).date().isoformat() != forecast_date:
        raise ValueError("invalid forecast date")
    code = _field(current, "weather_code", int)
    maximum = _number({"value": _first(daily, "temperature_2m_max")}, "value")
    minimum = _number({"value": _first(daily, "temperature_2m_min")}, "value")
    return {
        "location": location,
        "observed_at": observed.replace(tzinfo=timezone).isoformat(),
        "forecast_date": forecast_date,
        "weather": _WEATHER_CODES.get(code, f"未知天气现象（代码 {code}）"),
        "weather_code": code,
        "temperature_c": _number(current, "temperature_2m"),
        "temperature_max_c": maximum,
        "temperature_min_c": minimum,
        "source": "Open-Meteo",
    }


def _tool_error(reason: str, **details) -> ToolError:
    return ToolError(
        code="TOOL_EXEC_ERROR", message=f"Weather provider failed: {reason}",
        user_message="天气查询未能完成。", recoverable=True,
        details={"reason": reason, **details},
    )


def _config_error(message: str, reason: str) -> LocalMindError:
    return LocalMindError(
        code="CONFIG_ERROR", message=message, user_message="天气服务配置无效。",
        recoverable=False, details={"reason": reason},
    )
