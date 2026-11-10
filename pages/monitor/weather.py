# pages/monitor/weather.py
"""Open-Meteo client: current conditions plus today/tomorrow, no API key.

Times in the response are naive and local to the requested location
(``timezone=auto``); ``utc_offset_seconds`` converts "now" into that frame.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta

API_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = (
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "wind_speed_10m", "wind_direction_10m", "weather_code", "is_day", "uv_index",
)
DAILY_FIELDS = (
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "precipitation_probability_max", "sunrise", "sunset",
)


@dataclass(frozen=True)
class Day:
    code: int
    t_max: float
    t_min: float
    rain_chance: int | None
    sunrise: datetime  # naive, location-local
    sunset: datetime


@dataclass(frozen=True)
class Weather:
    temp: float
    feels_like: float
    humidity: int
    wind_speed: float  # km/h
    wind_dir: float  # degrees, direction the wind comes from
    code: int  # WMO weather code
    is_day: bool
    uv: float
    utc_offset: timedelta
    today: Day
    tomorrow: Day


def build_url(lat: float, lon: float) -> str:
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": ",".join(CURRENT_FIELDS),
            "daily": ",".join(DAILY_FIELDS),
            "timezone": "auto",
            "forecast_days": 2,
        },
        safe=",",
    )
    return f"{API_URL}?{query}"


def _day(daily: dict, i: int) -> Day:
    rain = daily["precipitation_probability_max"][i]
    return Day(
        code=int(daily["weather_code"][i]),
        t_max=float(daily["temperature_2m_max"][i]),
        t_min=float(daily["temperature_2m_min"][i]),
        rain_chance=None if rain is None else int(rain),
        sunrise=datetime.fromisoformat(daily["sunrise"][i]),
        sunset=datetime.fromisoformat(daily["sunset"][i]),
    )


def parse(payload: dict) -> Weather:
    cur = payload["current"]
    daily = payload["daily"]
    return Weather(
        temp=float(cur["temperature_2m"]),
        feels_like=float(cur["apparent_temperature"]),
        humidity=int(cur["relative_humidity_2m"]),
        wind_speed=float(cur["wind_speed_10m"]),
        wind_dir=float(cur["wind_direction_10m"]),
        code=int(cur["weather_code"]),
        is_day=bool(cur["is_day"]),
        uv=float(cur["uv_index"] or 0.0),
        utc_offset=timedelta(seconds=int(payload["utc_offset_seconds"])),
        today=_day(daily, 0),
        tomorrow=_day(daily, 1),
    )


def fetch(lat: float, lon: float, timeout: float = 5.0) -> Weather:
    with urllib.request.urlopen(build_url(lat, lon), timeout=timeout) as resp:
        return parse(json.load(resp))


def condition_icon(code: int, is_day: bool = True) -> str:
    """Icon filename in icons/ for a WMO weather code."""
    if code == 0:
        return "weather_clear_day.png" if is_day else "weather_clear_night.png"
    if code in (1, 2):
        return "weather_partly_day.png" if is_day else "weather_partly_night.png"
    if code in (45, 48):
        return "weather_fog.png"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "weather_rain.png"
    if 71 <= code <= 77 or code in (85, 86):
        return "weather_snow.png"
    if 95 <= code <= 99:
        return "weather_thunder.png"
    return "weather_cloudy.png"


_POINTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass(deg: float) -> str:
    """8-point compass name for a wind direction in degrees."""
    return _POINTS[int((deg % 360) / 45 + 0.5) % 8]
