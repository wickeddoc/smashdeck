# tests/test_monitor_weather.py
"""Open-Meteo parsing and helpers, against a trimmed real API response
(tests/fixtures/openmeteo.json, Berlin, fetched 2026-11-10)."""
import io
import json
import os
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

import pages.monitor.weather as weather_mod
from pages.monitor.weather import build_url, compass, condition_icon, fetch, parse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "openmeteo.json")


@pytest.fixture
def payload():
    with open(FIXTURE) as f:
        return json.load(f)


def test_parse_current_conditions(payload):
    w = parse(payload)
    assert w.temp == 4.8
    assert w.feels_like == 2.0
    assert w.humidity == 82
    assert w.wind_speed == 7.4
    assert w.wind_dir == 293
    assert w.code == 3
    assert w.is_day is True
    assert w.uv == 0.65
    assert w.utc_offset == timedelta(hours=1)


def test_parse_today_and_tomorrow(payload):
    w = parse(payload)
    assert (w.today.code, w.today.t_max, w.today.t_min, w.today.rain_chance) == (61, 4.8, 2.3, 43)
    assert w.today.sunrise == datetime(2026, 11, 10, 7, 19)
    assert w.today.sunset == datetime(2026, 11, 10, 16, 20)
    assert (w.tomorrow.code, w.tomorrow.t_max, w.tomorrow.t_min, w.tomorrow.rain_chance) == (51, 5.1, 1.9, 10)
    assert w.tomorrow.sunrise == datetime(2026, 11, 11, 7, 20)
    assert w.tomorrow.sunset == datetime(2026, 11, 11, 16, 19)


def test_parse_missing_rain_chance_and_uv(payload):
    payload["daily"]["precipitation_probability_max"] = [None, None]
    payload["current"]["uv_index"] = None
    w = parse(payload)
    assert w.today.rain_chance is None
    assert w.uv == 0.0


def test_build_url_requests_location_and_fields():
    url = urlparse(build_url(49.63277, 6.26459))
    q = parse_qs(url.query)
    assert url.netloc == "api.open-meteo.com"
    assert q["latitude"] == ["49.63277"]
    assert q["longitude"] == ["6.26459"]
    assert "uv_index" in q["current"][0].split(",")
    assert "apparent_temperature" in q["current"][0].split(",")
    assert "precipitation_probability_max" in q["daily"][0].split(",")
    assert "sunset" in q["daily"][0].split(",")
    assert q["timezone"] == ["auto"]
    assert q["forecast_days"] == ["2"]


def test_fetch_parses_response_with_timeout(payload, monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(weather_mod.urllib.request, "urlopen", fake_urlopen)
    w = fetch(49.63277, 6.26459, timeout=5)
    assert w.temp == 4.8
    assert calls[0][1] == 5
    assert "latitude=49.63277" in calls[0][0]


@pytest.mark.parametrize("code, is_day, icon", [
    (0, True, "weather_clear_day.png"),
    (0, False, "weather_clear_night.png"),
    (2, True, "weather_partly_day.png"),
    (1, False, "weather_partly_night.png"),
    (3, True, "weather_cloudy.png"),
    (45, True, "weather_fog.png"),
    (53, True, "weather_rain.png"),
    (66, False, "weather_rain.png"),
    (81, True, "weather_rain.png"),
    (73, True, "weather_snow.png"),
    (86, True, "weather_snow.png"),
    (95, True, "weather_thunder.png"),
    (99, False, "weather_thunder.png"),
    (42, True, "weather_cloudy.png"),  # unknown code
])
def test_condition_icon(code, is_day, icon):
    assert condition_icon(code, is_day) == icon


@pytest.mark.parametrize("deg, point", [
    (0, "N"), (22, "N"), (23, "NE"), (90, "E"), (180, "S"),
    (225, "SW"), (293, "NW"), (338, "N"), (359.9, "N"), (360, "N"),
])
def test_compass(deg, point):
    assert compass(deg) == point
