import io
from urllib.error import HTTPError, URLError

import pytest

from src.adapters.weather_provider import OpenMeteoProvider, WeatherConnectionConfig
from src.core.schemas import LocalMindError, ToolError


class Response(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.was_closed = False

    def close(self):
        self.was_closed = True
        super().close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class ScriptedOpener:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


GEO = b'{"results":[{"name":"Nanjing","admin1":"Jiangsu","country":"China","latitude":32.06,"longitude":118.79}]}'
FORECAST = b'{"timezone":"Asia/Shanghai","current":{"time":"2026-09-21T09:00","temperature_2m":25.5,"weather_code":2},"daily":{"time":["2026-09-21"],"temperature_2m_max":[28.0],"temperature_2m_min":[19.0]}}'


def test_current_weather_normalizes_two_responses_and_minimizes_egress():
    opener = ScriptedOpener(Response(GEO), Response(FORECAST))
    result = OpenMeteoProvider(opener=opener).current_weather("南京")
    assert result == {
        "location": "Nanjing, Jiangsu, China",
        "observed_at": "2026-09-21T09:00:00+08:00",
        "forecast_date": "2026-09-21",
        "weather": "多云",
        "weather_code": 2,
        "temperature_c": 25.5,
        "temperature_max_c": 28.0,
        "temperature_min_c": 19.0,
        "source": "Open-Meteo",
    }
    assert len(opener.requests) == 2
    first, timeout = opener.requests[0]
    assert timeout == 5
    assert first.full_url.startswith("https://geocoding-api.open-meteo.com/v1/search?")
    assert "%E5%8D%97%E4%BA%AC" in first.full_url
    assert dict(first.header_items()) == {"Accept": "application/json"}
    assert opener.requests[1][0].full_url.startswith("https://api.open-meteo.com/v1/forecast?")


@pytest.mark.parametrize("geo,forecast,reason", [
    (b'{"results":[]}', None, "location_not_found"),
    (b'{"generationtime_ms":1}', None, "location_not_found"),
    (b'{', None, "provider_parse_error"),
    (b'[]', None, "provider_parse_error"),
    (b'{"results":[{"name":"X"}]}', None, "provider_parse_error"),
    (GEO, b'{"current":{}}', "provider_parse_error"),
    (GEO, FORECAST.replace(b'"weather_code":2', b'"weather_code":true'), "provider_parse_error"),
    (GEO, FORECAST.replace(b'"temperature_2m":25.5', b'"temperature_2m":"25.5"'), "provider_parse_error"),
])
def test_bad_provider_data_has_contract_error(geo, forecast, reason):
    opener = ScriptedOpener(Response(geo), *([Response(forecast)] if forecast else []))
    with pytest.raises(ToolError) as caught:
        OpenMeteoProvider(opener=opener).current_weather("南京")
    assert caught.value.code == "TOOL_EXEC_ERROR"
    assert caught.value.details["reason"] == reason
    assert caught.value.recoverable


@pytest.mark.parametrize("failure,reason", [
    (TimeoutError(), "provider_timeout"),
    (URLError("offline"), "provider_unreachable"),
    (HTTPError("https://api.open-meteo.com", 302, "redirect", {}, None), "provider_redirect_rejected"),
    (HTTPError("https://api.open-meteo.com", 503, "error", {}, None), "provider_http_error"),
])
def test_transport_failures_are_mapped(failure, reason):
    with pytest.raises(ToolError) as caught:
        OpenMeteoProvider(opener=ScriptedOpener(failure)).current_weather("南京")
    assert caught.value.details["reason"] == reason
    assert caught.value.recoverable


def test_redirect_does_not_issue_a_second_request():
    opener = ScriptedOpener(
        HTTPError("https://geocoding-api.open-meteo.com/v1/search", 302, "redirect", {}, None),
        Response(GEO),
    )
    with pytest.raises(ToolError) as caught:
        OpenMeteoProvider(opener=opener).current_weather("南京")
    assert caught.value.details["reason"] == "provider_redirect_rejected"
    assert len(opener.requests) == 1
    assert len(opener.replies) == 1


def test_oversize_response_is_rejected_and_closed():
    response = Response(b"x" * 65537)
    with pytest.raises(ToolError) as caught:
        OpenMeteoProvider(opener=ScriptedOpener(response)).current_weather("南京")
    assert caught.value.details["reason"] == "provider_response_too_large"
    assert response.was_closed


def test_cumulative_read_deadline_is_enforced_between_chunks(monkeypatch):
    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr("src.adapters.weather_provider.time.monotonic", lambda: next(ticks))
    response = Response(GEO)
    with pytest.raises(ToolError) as caught:
        OpenMeteoProvider(
            connection=WeatherConnectionConfig(read_timeout_seconds=1),
            opener=ScriptedOpener(response),
        ).current_weather("南京")
    assert caught.value.details["reason"] == "provider_timeout"
    assert response.was_closed


def test_unknown_weather_code_is_a_success():
    forecast = FORECAST.replace(b'"weather_code":2', b'"weather_code":42')
    result = OpenMeteoProvider(opener=ScriptedOpener(Response(GEO), Response(forecast))).current_weather("南京")
    assert result["weather"] == "未知天气现象（代码 42）"
    assert result["weather_code"] == 42


@pytest.mark.parametrize("endpoint", [
    "http://geocoding-api.open-meteo.com/v1/search",
    "https://example.com/v1/search",
    "https://u:p@geocoding-api.open-meteo.com/v1/search",
    "https://geocoding-api.open-meteo.com:444/v1/search",
    "https://127.0.0.1/v1/search",
    "https://localhost/v1/search",
    "https://weather.local/v1/search",
    "https://weather.internal/v1/search",
    "https://geocoding-api.open-meteo.com./v1/search",
])
def test_invalid_endpoint_fails_at_construction(endpoint):
    with pytest.raises(LocalMindError) as caught:
        OpenMeteoProvider(geocoding_url=endpoint)
    assert caught.value.code == "CONFIG_ERROR"
    assert caught.value.details["reason"] == "weather_endpoint_invalid"


def test_nonpositive_timeout_fails_at_construction():
    with pytest.raises(LocalMindError) as caught:
        OpenMeteoProvider(connection=WeatherConnectionConfig(read_timeout_seconds=0))
    assert caught.value.code == "CONFIG_ERROR"
