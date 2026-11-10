# Monitor Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Monitor page on nav key 6 that shows live PC hardware and system metrics plus Münsbach weather as big-number keys, and make the current page's nav key visibly highlighted.

**Architecture:** The new `pages/monitor/` subpackage splits the work by responsibility. `sources.py` turns psutil, sysfs hwmon and `nvidia-smi` readings into a `SystemSample`. `weather.py` turns an Open-Meteo response into a `Weather`. `tiles.py` decides what each key shows (`build_tiles`, pure) and draws it (`render_tile`). `__init__.py` holds `MonitorPage`, which polls on a thread only while the page is visible and redraws only the keys that changed. Separately, `DeckController.set_key_image` gains a `label_bg` option, which draws the active-nav-key label strip.

**Tech Stack:** Python 3.13, Pillow, psutil (new), stdlib `urllib`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-monitor-page-design.md`

## Global Constraints

- Run Python via the project venv: `~/.virtualenvs/smashdeck/bin/python`. The repo's `.venv` is a pointer file, not a venv. Tests: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`. Lint: `uvx ruff check <paths>`.
- Work on branch `feat/monitor-page`; it already holds the spec commits.
- New runtime dependency: `psutil` only. Weather uses stdlib `urllib`; GPU readings use the `nvidia-smi` binary.
- Key layout: content keys 8–31. Nav: Home 0, Spotify 1, Hue 2, Kasa 3, Tapo 4, key 5 blank, Monitor 6, Restart 7.
- Colours: GREEN `(60, 200, 110)`, AMBER `(240, 170, 40)`, RED `(235, 70, 60)`, BLUE `(110, 170, 255)`, WHITE `(235, 235, 240)`, GREY `(150, 150, 160)`. The nav accent strip is `(110, 170, 255)` with label text `(10, 20, 40)`.
- Poll only while the Monitor page is visible. System metrics every 2 s. Weather every 15 min, 60 s after a failure, and on the next tick after a weather-key press. Weather older than 3 h shows as "offline".
- No sensor read, subprocess or HTTP call on the Stream Deck key-callback thread: `render()` and `on_key()` must return instantly.
- Network throughput in Mbit/s (Gbit/s at 1000 Mbit/s or more). Disk throughput in kB/s below 1 MB/s, otherwise MB/s.
- Tests need no hardware, network, real sensors or `nvidia-smi`.
- Ruff's BLE001 (blind `except Exception`) is accepted on the deliberate catch-alls. Everything else in new code must lint clean.
- Commit messages: `area: summary` (e.g. `monitor: ...`, `main: ...`), ending with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Deviations from the spec (decided while verifying this plan)

These came from running the plan's code in a scratch worktree; the spec has been updated to match.

- `build_tiles(sample, weather, now_utc, weather_error=None)` takes the key-24 error text (`"offline"` / `"no location"`) as a parameter.
- `SystemSample` has a `pending` flag and a `SystemSample.placeholder(disk_names)` constructor for the "—" state before the first sample. That way `build_tiles` always receives a sample and still knows the disk labels.
- `Rate.update(counter, now)`: the sampler reads its clock once per sample and passes `now` to all four rates.
- `MonitorPage(controller, sampler=None, fetch_weather=None, clock=time.monotonic, utcnow=...)` has a public `tick(stop=None)`, which the poll thread uses and tests call directly. A tick whose `stop` event is set draws nothing; this covers a slow weather fetch outliving `deactivate()`.
- CPU load (key 9) and the throughput keys (20–23) show "—" whenever no rate is available, not "n/a".
- A failed weather fetch prints one line (`monitor: weather fetch failed: ...`), not a traceback, because it repeats every 60 s while offline.

## File map

| File | Change | Task |
|---|---|---|
| `main.py` | `label_bg` on `set_key_image`, nav strip; later `NAV_KEYS[6]` + register page | 1, 6 |
| `tests/test_controller.py` | label-strip tests; nav key 6 test | 1, 6 |
| `pages/monitor/__init__.py` | Create: placeholder docstring (Task 2), then `MonitorPage` (Task 5) | 2, 5 |
| `pages/monitor/weather.py` | Create: Open-Meteo client | 2 |
| `tests/fixtures/openmeteo.json` | Create: trimmed real API response | 2 |
| `tests/test_monitor_weather.py` | Create | 2 |
| `requirements.txt` | add `psutil` | 3 |
| `pages/monitor/sources.py` | Create: `SystemSampler` and helpers | 3 |
| `tests/test_monitor_sources.py` | Create | 3 |
| `generate_icons.py`, `icons/` | `monitor.png` + 9 `weather_*.png` | 4 |
| `pages/monitor/tiles.py` | Create: `build_tiles`, `render_tile` | 4 |
| `tests/test_monitor_tiles.py` | Create | 4 |
| `tests/conftest.py` | `FakeController.pushes` | 5 |
| `tests/test_monitor_page.py` | Create | 5 |
| `config.yaml.dist`, `README.md`, `CLAUDE.md` | Monitor config + docs | 6 |
| `config.yaml` (gitignored, local only) | Monitor section with Münsbach | 6 |

---

### Task 1: Highlight the active nav key with a label strip

The nav icons are opaque 144×144 tiles, so the current `color=` tint is never visible. The fix draws a coloured strip under the label of the active page's nav key, with the label in bold dark text on it.

**Files:**
- Modify: `main.py` (constants after `RESTART_KEY = 7`, `render_nav_bar`, `set_key_image`)
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: the existing `ImageDeck`, `RecordingPage`, `press`, `controller` fixture and the `HOME`/`SPOTIFY` constants in `tests/test_controller.py`.
- Produces: `DeckController.set_key_image(key, icon_filename=None, label=None, color=(0, 0, 0), highlight=None, pil_image=None, label_bg=None)`; module constants `FONT_PATH`, `BOLD_FONT_PATH`, `LABEL_STRIP = 20`, `NAV_ACTIVE_COLOR = (110, 170, 255)`, `LABEL_ON_STRIP = (10, 20, 40)`; helper `_font(path, size)`. Task 6 adds a test that reuses `key_pixel`, `close_to`, `STRIP_PIXEL` and `ACCENT` from this task.

- [ ] **Step 1: Add imports to `tests/test_controller.py`**

Replace the line `import pytest` near the top with:

```python
from io import BytesIO

import pytest
from PIL import Image
```

- [ ] **Step 2: Append the failing tests to `tests/test_controller.py`**

```python
# --- Active nav key: label strip in the accent colour (spec: style C).

ACCENT = (110, 170, 255)
BLACK = (0, 0, 0)
STRIP_PIXEL = (3, 93)  # inside the 20 px label strip of a 96 px key, left of the text


def key_pixel(ctrl, key, xy):
    """Decode a key's native JPEG, undo the XL's flip, return the RGB at xy."""
    img = Image.open(BytesIO(ctrl.deck.key_images[key])).convert("RGB")
    img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    return img.getpixel(xy)


def close_to(rgb, expected, tolerance=24):
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, expected))


def test_active_nav_key_has_accent_label_strip(controller):
    controller.pages = {"home": RecordingPage(controller),
                        "spotify": RecordingPage(controller)}

    press(controller, SPOTIFY)

    assert close_to(key_pixel(controller, SPOTIFY, STRIP_PIXEL), ACCENT)
    assert close_to(key_pixel(controller, HOME, STRIP_PIXEL), BLACK)


def test_label_strip_moves_with_page_switch(controller):
    controller.pages = {"home": RecordingPage(controller),
                        "spotify": RecordingPage(controller)}

    press(controller, SPOTIFY)
    press(controller, HOME)

    assert close_to(key_pixel(controller, HOME, STRIP_PIXEL), ACCENT)
    assert close_to(key_pixel(controller, SPOTIFY, STRIP_PIXEL), BLACK)
```

- [ ] **Step 3: Run them and watch them fail**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/test_controller.py -q`
Expected: `2 failed, 4 passed`. Both failures read `close_to((0, 0, 0), (110, 170, 255))`: today the active key's strip is black.

- [ ] **Step 4: Add the constants and font helper to `main.py`**

Directly after `RESTART_KEY = 7`, insert:

```python

FONT_PATH = "/usr/share/fonts/TTF/DejaVuSans.ttf"
BOLD_FONT_PATH = "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
LABEL_STRIP = 20  # px below the icon reserved for the label
NAV_ACTIVE_COLOR = (110, 170, 255)  # label strip of the current page's nav key
LABEL_ON_STRIP = (10, 20, 40)  # label text drawn on a coloured strip


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()
```

- [ ] **Step 5: Pass the strip from `render_nav_bar`**

Replace:

```python
                page_name, icon, label = NAV_KEYS[key]
                highlight = (50, 50, 80) if page_name == active else None
                self.set_key_image(key, icon, label, color=highlight or (0, 0, 0))
```

with:

```python
                page_name, icon, label = NAV_KEYS[key]
                strip = NAV_ACTIVE_COLOR if page_name == active else None
                self.set_key_image(key, icon, label, label_bg=strip)
```

- [ ] **Step 6: Support `label_bg` in `set_key_image`**

In the signature, after `pil_image: Optional[Image.Image] = None,`, add the parameter `label_bg=None,`. At the end of the docstring, before the closing `"""`, add:

```python

        label_bg: optional RGB tuple; fills the label strip below the icon and
        draws the label in bold dark text on it (marks the active nav key).
```

Then replace the body from `image = PILHelper.create_scaled_key_image(` down to the end of the `draw.text(...)` call with:

```python
        image = PILHelper.create_scaled_key_image(
            self.deck,
            source,
            margins=[0, 0, LABEL_STRIP if label else 0, 0],
        )
        draw = ImageDraw.Draw(image)

        if highlight:
            draw.rectangle([(0, 0), (image.width, 4)], fill=highlight)
        if label:
            if label_bg:
                draw.rectangle(
                    [(0, image.height - LABEL_STRIP), (image.width, image.height)],
                    fill=label_bg,
                )
            draw.text(
                (image.width // 2, image.height - 5),
                label,
                font=_font(BOLD_FONT_PATH if label_bg else FONT_PATH, 12),
                anchor="mb",
                fill=LABEL_ON_STRIP if label_bg else "white",
            )
```

Keep the final line, `self.deck.set_key_image(key, PILHelper.to_native_key_format(self.deck, image))`, unchanged.

- [ ] **Step 7: Run the whole suite**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`
Expected: `17 passed`.

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_controller.py
git commit -m "main: highlight the active nav key with a label strip

The nav icons are opaque tiles, so the old background tint never showed.
set_key_image gains label_bg: the label strip is filled with the accent
colour and the label drawn bold and dark on it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Open-Meteo weather client

**Files:**
- Create: `pages/monitor/__init__.py` (placeholder; Task 5 replaces it)
- Create: `pages/monitor/weather.py`
- Create: `tests/fixtures/openmeteo.json`
- Test: `tests/test_monitor_weather.py`

**Interfaces:**
- Produces:
  - `Day(code: int, t_max: float, t_min: float, rain_chance: int | None, sunrise: datetime, sunset: datetime)`, frozen; times are naive and local to the location.
  - `Weather(temp, feels_like, humidity: int, wind_speed, wind_dir, code: int, is_day: bool, uv: float, utc_offset: timedelta, today: Day, tomorrow: Day)`, frozen.
  - `build_url(lat, lon) -> str`, `parse(payload: dict) -> Weather`, `fetch(lat, lon, timeout=5.0) -> Weather`.
  - `condition_icon(code: int, is_day: bool = True) -> str` (an icon filename such as `"weather_rain.png"`).
  - `compass(deg: float) -> str` (`"SW"`).

- [ ] **Step 1: Create the fixture `tests/fixtures/openmeteo.json`**

This is a real response for Open-Meteo's Berlin example, fetched 2026-11-10 and trimmed to the fields used:

```json
{
  "latitude": 52.512604,
  "longitude": 13.419517,
  "utc_offset_seconds": 3600,
  "timezone": "Europe/Berlin",
  "current": {
    "time": "2026-11-10T15:00",
    "temperature_2m": 4.8,
    "apparent_temperature": 2.0,
    "relative_humidity_2m": 82,
    "wind_speed_10m": 7.4,
    "wind_direction_10m": 293,
    "weather_code": 3,
    "is_day": 1,
    "uv_index": 0.65
  },
  "daily": {
    "time": [
      "2026-11-10",
      "2026-11-11"
    ],
    "weather_code": [
      61,
      51
    ],
    "temperature_2m_max": [
      4.8,
      5.1
    ],
    "temperature_2m_min": [
      2.3,
      1.9
    ],
    "precipitation_probability_max": [
      43,
      10
    ],
    "sunrise": [
      "2026-11-10T07:19",
      "2026-11-11T07:20"
    ],
    "sunset": [
      "2026-11-10T16:20",
      "2026-11-11T16:19"
    ]
  }
}
```

- [ ] **Step 2: Create the package placeholder `pages/monitor/__init__.py`**

```python
# pages/monitor/__init__.py
"""Monitor page: live PC metrics (rows 2-3) and Open-Meteo weather (row 4)."""
```

- [ ] **Step 3: Write the failing tests `tests/test_monitor_weather.py`**

```python
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
```

- [ ] **Step 4: Run them and watch them fail**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/test_monitor_weather.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'pages.monitor.weather'`.

- [ ] **Step 5: Implement `pages/monitor/weather.py`**

```python
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
```

- [ ] **Step 6: Run the tests**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`
Expected: `46 passed` (29 new).

- [ ] **Step 7: Lint and commit**

Run: `uvx ruff check pages/monitor tests/test_monitor_weather.py`
Expected: `All checks passed!`

```bash
git add pages/monitor/__init__.py pages/monitor/weather.py tests/fixtures/openmeteo.json tests/test_monitor_weather.py
git commit -m "monitor: Open-Meteo weather client

Current conditions plus today/tomorrow from one keyless request; WMO code
to icon mapping and 8-point compass for the weather keys.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: System metric sources

**Files:**
- Modify: `requirements.txt` (append `psutil`)
- Create: `pages/monitor/sources.py`
- Test: `tests/test_monitor_sources.py`

**Interfaces:**
- Produces:
  - `SystemSample` (mutable dataclass). Every field defaults to `None`: `cpu_temp, cpu_load, cpu_power, gpu_temp, gpu_load, gpu_power, vram_used_gb, vram_total_gb, pc_power, ram_percent, ssd_temp, disk_read, disk_write, net_down, net_up`. Also `disks: list[tuple[str, float | None]]` (name, % full) and `pending: bool = False`. Rates are bytes/s.
  - `SystemSample.placeholder(disk_names) -> SystemSample`, with `pending=True` and `disks=[(name, None), ...]`.
  - `GpuReading(temp, load, power, mem_used_mib, mem_total_mib)`.
  - `read_hwmon_power(root, driver, label) -> float | None` (W); `cpu_temp(temps) -> float | None`; `ssd_temp(temps) -> float | None`; `default_route_interface(route_text) -> str | None`; `parse_nvidia_smi(stdout) -> GpuReading | None`; `query_nvidia_smi(timeout=2.0)`.
  - `Rate().update(counter, now) -> float | None`.
  - `SystemSampler(disks=(), net_interface=None, hwmon_root="/sys/class/hwmon", route_file="/proc/net/route", clock=time.monotonic, gpu_query=query_nvidia_smi)`, whose `.sample()` returns a `SystemSample`. `disks` takes config dicts `{"name", "path"}` (at most 2 are used).

- [ ] **Step 1: Add the dependency**

Append a line `psutil` to `requirements.txt`, then run `~/.virtualenvs/smashdeck/bin/pip install -r requirements.txt`. psutil 7.x may already be present as an IPython dependency; the run makes the requirement explicit.

- [ ] **Step 2: Write the failing tests `tests/test_monitor_sources.py`**

```python
# tests/test_monitor_sources.py
"""System metric sources against fake sysfs trees, canned command output and
monkeypatched psutil: no real sensors, GPU or network needed."""
from collections import namedtuple
from types import SimpleNamespace

import pytest

from pages.monitor import sources
from pages.monitor.sources import (
    GpuReading,
    Rate,
    SystemSampler,
    cpu_temp,
    default_route_interface,
    parse_nvidia_smi,
    read_hwmon_power,
    ssd_temp,
)

T = namedtuple("T", "label current")  # shape of psutil's shwtemp entries


def make_hwmon(root, index, name, sensors):
    """sensors: {"power1": ("label", microwatts)}"""
    d = root / f"hwmon{index}"
    d.mkdir()
    (d / "name").write_text(f"{name}\n")
    for prefix, (label, value) in sensors.items():
        (d / f"{prefix}_label").write_text(f"{label}\n")
        (d / f"{prefix}_input").write_text(f"{value}\n")


# --- read_hwmon_power

def test_hwmon_power_reads_labelled_sensor_in_watts(tmp_path):
    make_hwmon(tmp_path, 0, "nvme", {})
    make_hwmon(tmp_path, 1, "corsairpsu", {"power1": ("power total", 186000000),
                                           "power2": ("power 12v", 150000000)})
    assert read_hwmon_power(str(tmp_path), "corsairpsu", "power total") == 186.0


def test_hwmon_power_missing_driver_or_label_is_none(tmp_path):
    make_hwmon(tmp_path, 0, "zenpower", {"power1": ("RAPL_P_Package", 42164100)})
    assert read_hwmon_power(str(tmp_path), "corsairpsu", "power total") is None
    assert read_hwmon_power(str(tmp_path), "zenpower", "RAPL_P_Core") is None
    assert read_hwmon_power(str(tmp_path / "missing"), "zenpower", "RAPL_P_Package") is None


# --- cpu_temp / ssd_temp

def test_cpu_temp_prefers_zenpower_then_k10temp_then_coretemp():
    both = {"k10temp": [T("Tctl", 61.0)], "zenpower": [T("Tdie", 48.0), T("Tctl", 49.1)]}
    assert cpu_temp(both) == 49.1
    assert cpu_temp({"k10temp": [T("Tccd1", 40.0), T("Tctl", 61.0)]}) == 61.0
    assert cpu_temp({"coretemp": [T("Core 0", 50.0), T("Package id 0", 55.0)]}) == 55.0
    assert cpu_temp({"nvme": [T("Composite", 40.0)]}) is None


def test_ssd_temp_is_hottest_composite():
    temps = {"nvme": [T("Composite", 49.8), T("Sensor 1", 75.0), T("Composite", 60.9)]}
    assert ssd_temp(temps) == 60.9


def test_ssd_temp_without_composite_labels_uses_all_entries():
    assert ssd_temp({"nvme": [T("", 41.0), T("", 44.5)]}) == 44.5
    assert ssd_temp({}) is None


# --- default_route_interface

ROUTE = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
    "wlan0\t00000000\t0101A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0\n"
    "enp15s0u2\t00000000\t0101A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
    "eno1\t0000630A\t00000000\t0001\t0\t0\t50\t00FFFFFF\t0\t0\t0\n"
)


def test_default_route_interface_picks_lowest_metric_default():
    assert default_route_interface(ROUTE) == "enp15s0u2"


def test_default_route_interface_none_without_default_route():
    only_lan = ROUTE.splitlines()[0] + "\n" + ROUTE.splitlines()[3] + "\n"
    assert default_route_interface(only_lan) is None


# --- parse_nvidia_smi

def test_parse_nvidia_smi_first_gpu():
    assert parse_nvidia_smi("58, 4, 55.91, 4789, 32607\n") == GpuReading(58.0, 4.0, 55.91, 4789.0, 32607.0)


def test_parse_nvidia_smi_unsupported_fields_are_none():
    assert parse_nvidia_smi("58, 4, [N/A], 4789, 32607\n").power is None


def test_parse_nvidia_smi_empty_or_malformed_is_none():
    assert parse_nvidia_smi("") is None
    assert parse_nvidia_smi("58, 4\n") is None


# --- Rate

def stepping_clock(times):
    it = iter(times)
    return lambda: next(it)


def test_rate_first_update_is_none_then_bytes_per_second():
    rate = Rate()
    assert rate.update(1000, now=10.0) is None
    assert rate.update(2000, now=12.0) == 500.0
    assert rate.update(2600, now=13.0) == 600.0


def test_rate_counter_reset_is_none():
    rate = Rate()
    rate.update(5000, now=0.0)
    assert rate.update(100, now=2.0) is None
    assert rate.update(300, now=4.0) == 100.0


# --- SystemSampler with faked psutil

@pytest.fixture
def fake_psutil(monkeypatch):
    counters = {"disk": SimpleNamespace(read_bytes=0, write_bytes=0),
                "net": SimpleNamespace(bytes_recv=0, bytes_sent=0)}
    monkeypatch.setattr(sources.psutil, "sensors_temperatures",
                        lambda: {"zenpower": [T("Tctl", 51.1)],
                                 "nvme": [T("Composite", 60.9)]})
    monkeypatch.setattr(sources.psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(sources.psutil, "virtual_memory", lambda: SimpleNamespace(percent=32.0))
    monkeypatch.setattr(sources.psutil, "disk_usage",
                        lambda path: SimpleNamespace(percent={"/": 52.4, "/data": 76.5}[path]))
    monkeypatch.setattr(sources.psutil, "disk_io_counters", lambda: counters["disk"])
    monkeypatch.setattr(sources.psutil, "net_io_counters",
                        lambda pernic=False: {"eth9": counters["net"]})
    return counters


def no_gpu():
    raise FileNotFoundError("nvidia-smi")


@pytest.fixture
def sampler(tmp_path, fake_psutil):
    make_hwmon(tmp_path, 0, "corsairpsu", {"power1": ("power total", 214000000)})
    route = tmp_path / "route"
    route.write_text(ROUTE.replace("enp15s0u2", "eth9"))
    return SystemSampler(
        disks=[{"name": "/", "path": "/"}, {"name": "Data", "path": "/data"}],
        hwmon_root=str(tmp_path),
        route_file=str(route),
        clock=stepping_clock([0.0, 2.0]),
        gpu_query=no_gpu,
    )


def test_sampler_fills_available_fields_and_isolates_failures(sampler):
    s = sampler.sample()
    assert s.cpu_temp == 51.1
    assert s.ssd_temp == 60.9
    assert s.pc_power == 214.0
    assert s.cpu_power is None  # no zenpower hwmon in the fake tree
    assert s.ram_percent == 32.0
    assert s.disks == [("/", 52.4), ("Data", 76.5)]
    assert (s.gpu_temp, s.gpu_load, s.gpu_power, s.vram_used_gb) == (None, None, None, None)
    assert s.pending is False


def test_sampler_rates_need_two_samples(sampler, fake_psutil):
    first = sampler.sample()
    assert (first.cpu_load, first.disk_read, first.net_down) == (None, None, None)

    fake_psutil["disk"].read_bytes, fake_psutil["disk"].write_bytes = 4_000_000, 1_000_000
    fake_psutil["net"].bytes_recv, fake_psutil["net"].bytes_sent = 2_500_000, 500_000
    second = sampler.sample()  # 2 s later on the stepping clock

    assert second.cpu_load == 12.5
    assert (second.disk_read, second.disk_write) == (2_000_000.0, 500_000.0)
    assert (second.net_down, second.net_up) == (1_250_000.0, 250_000.0)


def test_sampler_logs_a_failing_source_once(sampler, capsys):
    sampler.sample()
    sampler.sample()
    assert capsys.readouterr().out.count("source 'gpu' unavailable") == 1


def test_sampler_gpu_reading_converts_vram_to_gb(tmp_path, fake_psutil):
    s = SystemSampler(
        hwmon_root=str(tmp_path), route_file=str(tmp_path / "none"),
        gpu_query=lambda: GpuReading(58.0, 4.0, 55.9, 4608.0, 32768.0),
    ).sample()
    assert (s.gpu_temp, s.gpu_load, s.gpu_power) == (58.0, 4.0, 55.9)
    assert (s.vram_used_gb, s.vram_total_gb) == (4.5, 32.0)


def test_placeholder_sample_is_pending_and_keeps_disk_names():
    s = sources.SystemSample.placeholder(["/", "Fast"])
    assert s.pending is True
    assert s.disks == [("/", None), ("Fast", None)]
```

- [ ] **Step 3: Run them and watch them fail**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/test_monitor_sources.py -q`
Expected: collection error `ImportError: cannot import name 'sources' from 'pages.monitor'`.

- [ ] **Step 4: Implement `pages/monitor/sources.py`**

```python
# pages/monitor/sources.py
"""System metric sources: psutil, sysfs hwmon and nvidia-smi.

Every reading is optional. A missing sensor, driver or binary yields None for
that field only, so the page shows "n/a" for one key instead of failing.
"""
from __future__ import annotations

import os
import subprocess
import time
import traceback
from dataclasses import dataclass, field

import psutil

CPU_TEMP_SENSORS = (("zenpower", "Tctl"), ("k10temp", "Tctl"), ("coretemp", "Package id 0"))
CPU_POWER_SENSOR = ("zenpower", "RAPL_P_Package")
PC_POWER_SENSOR = ("corsairpsu", "power total")
NVIDIA_QUERY = "temperature.gpu,utilization.gpu,power.draw,memory.used,memory.total"


@dataclass
class SystemSample:
    """One poll's readings; None means unavailable (or no rate yet)."""

    cpu_temp: float | None = None  # °C
    cpu_load: float | None = None  # %
    cpu_power: float | None = None  # W
    gpu_temp: float | None = None
    gpu_load: float | None = None
    gpu_power: float | None = None
    vram_used_gb: float | None = None
    vram_total_gb: float | None = None
    pc_power: float | None = None
    ram_percent: float | None = None
    disks: list[tuple[str, float | None]] = field(default_factory=list)  # (name, % full)
    ssd_temp: float | None = None
    disk_read: float | None = None  # bytes/s
    disk_write: float | None = None
    net_down: float | None = None
    net_up: float | None = None
    pending: bool = False  # True before the first real sample

    @classmethod
    def placeholder(cls, disk_names) -> SystemSample:
        """Shown before the first real sample: every key reads "—"."""
        return cls(disks=[(name, None) for name in disk_names], pending=True)


@dataclass(frozen=True)
class GpuReading:
    temp: float | None
    load: float | None
    power: float | None
    mem_used_mib: float | None
    mem_total_mib: float | None


def read_hwmon_power(root: str, driver: str, label: str) -> float | None:
    """Watts from the hwmon power sensor `label` of driver `driver`, or None."""
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None
    for entry in entries:
        base = os.path.join(root, entry)
        try:
            with open(os.path.join(base, "name")) as f:
                if f.read().strip() != driver:
                    continue
            for fname in sorted(os.listdir(base)):
                if not (fname.startswith("power") and fname.endswith("_label")):
                    continue
                with open(os.path.join(base, fname)) as f:
                    if f.read().strip() != label:
                        continue
                with open(os.path.join(base, fname[: -len("_label")] + "_input")) as f:
                    return int(f.read().strip()) / 1e6  # µW -> W
        except (OSError, ValueError):
            continue
    return None


def cpu_temp(temps: dict) -> float | None:
    """CPU temperature from psutil.sensors_temperatures() output."""
    for driver, label in CPU_TEMP_SENSORS:
        for entry in temps.get(driver, []):
            if entry.label == label:
                return entry.current
    return None


def ssd_temp(temps: dict) -> float | None:
    """Hottest NVMe 'Composite' reading (any NVMe reading if none is labelled)."""
    entries = temps.get("nvme", [])
    values = [e.current for e in entries if e.label == "Composite"] or [e.current for e in entries]
    return max(values) if values else None


def default_route_interface(route_text: str) -> str | None:
    """Interface of the lowest-metric default route in /proc/net/route text."""
    best = None
    for line in route_text.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 7 or cols[1] != "00000000":
            continue
        metric = int(cols[6])
        if best is None or metric < best[0]:
            best = (metric, cols[0])
    return best[1] if best else None


def parse_nvidia_smi(stdout: str) -> GpuReading | None:
    """First GPU's line of `nvidia-smi --format=csv,noheader,nounits` output."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    values = []
    for raw in lines[0].split(","):
        try:
            values.append(float(raw.strip()))
        except ValueError:  # "[N/A]", "[Not Supported]"
            values.append(None)
    if len(values) != 5:
        return None
    return GpuReading(*values)


def query_nvidia_smi(timeout: float = 2.0) -> GpuReading | None:
    out = subprocess.run(
        ["nvidia-smi", f"--query-gpu={NVIDIA_QUERY}", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=timeout, check=True,
    ).stdout
    return parse_nvidia_smi(out)


class Rate:
    """Turns a cumulative counter into a per-second rate."""

    def __init__(self):
        self._last: tuple[float, float] | None = None  # (time, counter)

    def update(self, counter: float, now: float) -> float | None:
        last, self._last = self._last, (now, counter)
        if last is None or counter < last[1] or now <= last[0]:
            return None
        return (counter - last[1]) / (now - last[0])


class SystemSampler:
    def __init__(self, disks=(), net_interface=None, hwmon_root="/sys/class/hwmon",
                 route_file="/proc/net/route", clock=time.monotonic,
                 gpu_query=query_nvidia_smi):
        self.disks = [(d["name"], d["path"]) for d in disks][:2]
        self.net_interface = net_interface
        self.hwmon_root = hwmon_root
        self.route_file = route_file
        self.gpu_query = gpu_query
        self._clock = clock
        self._rates = {name: Rate() for name in ("read", "write", "down", "up")}
        self._iface: str | None = None
        self._cpu_primed = False
        self._failed: set[str] = set()

    def _try(self, name, fn, default=None):
        try:
            return fn()
        except Exception:
            if name not in self._failed:  # log once per source, not every tick
                self._failed.add(name)
                print(f"monitor: source '{name}' unavailable:")
                traceback.print_exc()
            return default

    def _cpu_load(self):
        value = psutil.cpu_percent(interval=None)
        if not self._cpu_primed:  # the first call has no reference interval
            self._cpu_primed = True
            return None
        return value

    def _net_counters(self):
        iface = self.net_interface
        if iface is None:
            with open(self.route_file) as f:
                iface = default_route_interface(f.read())
        if iface != self._iface:  # interface changed: old counters don't apply
            self._iface = iface
            self._rates["down"], self._rates["up"] = Rate(), Rate()
        if iface is None:
            return None
        return psutil.net_io_counters(pernic=True).get(iface)

    def sample(self) -> SystemSample:
        now = self._clock()
        s = SystemSample()

        temps = self._try("sensors", psutil.sensors_temperatures) or {}
        s.cpu_temp = cpu_temp(temps)
        s.ssd_temp = ssd_temp(temps)
        s.cpu_load = self._try("cpu_load", self._cpu_load)
        s.cpu_power = self._try("cpu_power", lambda: read_hwmon_power(self.hwmon_root, *CPU_POWER_SENSOR))
        s.pc_power = self._try("pc_power", lambda: read_hwmon_power(self.hwmon_root, *PC_POWER_SENSOR))

        gpu = self._try("gpu", self.gpu_query)
        if gpu is not None:
            s.gpu_temp, s.gpu_load, s.gpu_power = gpu.temp, gpu.load, gpu.power
            if gpu.mem_used_mib is not None:
                s.vram_used_gb = gpu.mem_used_mib / 1024
            if gpu.mem_total_mib is not None:
                s.vram_total_gb = gpu.mem_total_mib / 1024

        s.ram_percent = self._try("ram", lambda: psutil.virtual_memory().percent)
        s.disks = [
            (name, self._try(f"disk {path}", lambda p=path: psutil.disk_usage(p).percent))
            for name, path in self.disks
        ]

        io = self._try("disk_io", psutil.disk_io_counters)
        if io is not None:
            s.disk_read = self._rates["read"].update(io.read_bytes, now)
            s.disk_write = self._rates["write"].update(io.write_bytes, now)

        nic = self._try("net", self._net_counters)
        if nic is not None:
            s.net_down = self._rates["down"].update(nic.bytes_recv, now)
            s.net_up = self._rates["up"].update(nic.bytes_sent, now)
        return s
```

- [ ] **Step 5: Run the tests**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`
Expected: `63 passed` (17 new).

- [ ] **Step 6: Smoke-test against the real machine**

```bash
~/.virtualenvs/smashdeck/bin/python -c "
import time
from pages.monitor.sources import SystemSampler
s = SystemSampler(disks=[{'name': '/', 'path': '/'}, {'name': 'Fast', 'path': '/home/wickeddoc/Games'}])
s.sample(); time.sleep(1); print(s.sample())"
```

Expected: every field is a number (CPU ~50 °C, GPU temp and power from the RTX 5090, `pc_power` from the Corsair PSU, both disks), with no traceback. One sample takes about 30–80 ms.

- [ ] **Step 7: Lint and commit**

Run: `uvx ruff check pages/monitor tests/test_monitor_sources.py`
Expected: only `BLE001` on the `_try` catch-all in `sources.py`, which is deliberate.

```bash
git add requirements.txt pages/monitor/sources.py tests/test_monitor_sources.py
git commit -m "monitor: system metric sources (psutil, hwmon, nvidia-smi)

SystemSampler reads CPU/GPU/PSU/RAM/disk/NVMe/network into a SystemSample.
Each source fails independently to None and is logged once.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Key faces (tiles) and icons

**Files:**
- Modify: `generate_icons.py` (new section before `# ── Misc`; calls in `__main__`)
- Create (generated): `icons/monitor.png`, `icons/weather_{clear_day,clear_night,partly_day,partly_night,cloudy,fog,rain,snow,thunder}.png`
- Create: `pages/monitor/tiles.py`
- Test: `tests/test_monitor_tiles.py`

**Interfaces:**
- Consumes: `SystemSample` (Task 3); `Weather`, `Day`, `compass`, `condition_icon` (Task 2).
- Produces: colour constants `GREEN, AMBER, RED, BLUE, WHITE, GREY`; `DASH = "—"`; `SIZE = 144`; `WEATHER_KEYS = range(24, 32)`; frozen dataclasses `Tile(label, value, unit, color)` and `WeatherTile(label, icon, value, detail)`; `BLANK = Tile("", "", "", GREY)`; `level(value, warn, crit)`; `fmt_disk_rate(bps) -> (text, unit)`; `fmt_net_rate(bps) -> (text, unit)`; `uv_band(level: int) -> (text, colour)`; `build_tiles(sample, weather, now_utc, weather_error=None) -> dict[int, Tile | WeatherTile]` (keys 8–31); `render_tile(tile) -> PIL.Image` (144×144 RGB).

- [ ] **Step 1: Add the icon functions to `generate_icons.py`**

Insert this section directly above the `# ── Misc ───...` comment:

```python
# ── Monitor / Weather ───────────────────────────────────

SUN = (250, 200, 50)
MOON = (230, 230, 200)
CLOUD = (225, 230, 240)
DARK_CLOUD = (160, 170, 190)
RAIN = (90, 150, 255)
SNOW = (235, 240, 255)
BOLT = (255, 210, 60)
CLEAR = (0, 0, 0, 0)  # weather icons are transparent: drawn onto black keys


def icon_monitor():
    img, d = new((40, 60, 90))
    for i, h in enumerate((20, 35, 27, 45)):
        x = 15 + i * 12
        d.rectangle([(_s(x), _s(59 - h)), (_s(x + 7), _s(59))], fill=(110, 170, 255))
    save(img, "monitor.png")


def _sun(d, cx, cy, r):
    for a in range(0, 360, 45):
        x, y = math.cos(math.radians(a)), math.sin(math.radians(a))
        d.line(
            [(_s(cx + x * r * 1.4), _s(cy + y * r * 1.4)),
             (_s(cx + x * r * 1.9), _s(cy + y * r * 1.9))],
            fill=SUN, width=_s(3),
        )
    d.ellipse([(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))], fill=SUN)


def _moon(d, cx, cy, r):
    d.ellipse([(_s(cx - r), _s(cy - r)), (_s(cx + r), _s(cy + r))], fill=MOON)
    # Overdraw with transparency to cut the crescent.
    d.ellipse([(_s(cx - r + 8), _s(cy - r - 4)), (_s(cx + r + 8), _s(cy + r - 4))], fill=CLEAR)


def _cloud(d, ox, oy, k=1.0, color=CLOUD):
    """Three puffs on a flat base; spans x ox-11k..ox+34k, y oy-13k..oy+16k."""
    for bx, by, br in ((0, 4, 11), (13, 0, 13), (24, 6, 10)):
        d.ellipse(
            [(_s(ox + (bx - br) * k), _s(oy + (by - br) * k)),
             (_s(ox + (bx + br) * k), _s(oy + (by + br) * k))],
            fill=color,
        )
    d.rectangle([(_s(ox), _s(oy + 4 * k)), (_s(ox + 24 * k), _s(oy + 16 * k))], fill=color)


def icon_weather_clear_day():
    img, d = new(CLEAR)
    _sun(d, 36, 36, 14)
    save(img, "weather_clear_day.png")


def icon_weather_clear_night():
    img, d = new(CLEAR)
    _moon(d, 34, 36, 20)
    save(img, "weather_clear_night.png")


def icon_weather_partly_day():
    img, d = new(CLEAR)
    _sun(d, 27, 27, 11)
    _cloud(d, 30, 40)
    save(img, "weather_partly_day.png")


def icon_weather_partly_night():
    img, d = new(CLEAR)
    _moon(d, 25, 26, 14)
    _cloud(d, 30, 40)
    save(img, "weather_partly_night.png")


def icon_weather_cloudy():
    img, d = new(CLEAR)
    _cloud(d, 23, 18, 0.8, DARK_CLOUD)
    _cloud(d, 22, 36, 1.2)
    save(img, "weather_cloudy.png")


def icon_weather_fog():
    img, d = new(CLEAR)
    _cloud(d, 25, 22, 1.0, DARK_CLOUD)
    for y in (46, 54, 62):
        d.line([(_s(14), _s(y)), (_s(58), _s(y))], fill=CLOUD, width=_s(3))
    save(img, "weather_fog.png")


def icon_weather_rain():
    img, d = new(CLEAR)
    _cloud(d, 24, 22, 1.1, DARK_CLOUD)
    for x in (27, 37, 47):
        d.line([(_s(x), _s(48)), (_s(x - 5), _s(62))], fill=RAIN, width=_s(3))
    save(img, "weather_rain.png")


def icon_weather_snow():
    img, d = new(CLEAR)
    _cloud(d, 24, 22, 1.1, DARK_CLOUD)
    for x, y in ((26, 52), (37, 60), (48, 52)):
        d.ellipse([(_s(x - 3), _s(y - 3)), (_s(x + 3), _s(y + 3))], fill=SNOW)
    save(img, "weather_snow.png")


def icon_weather_thunder():
    img, d = new(CLEAR)
    _cloud(d, 24, 22, 1.1, DARK_CLOUD)
    bolt = [(40, 42), (30, 56), (37, 56), (32, 68), (46, 51), (39, 51), (44, 42)]
    d.polygon([(_s(x), _s(y)) for x, y in bolt], fill=BOLT)
    save(img, "weather_thunder.png")
```

- [ ] **Step 2: Call them from `__main__`**

Directly above `    print("\nMisc:")`, insert:

```python
    print("\nMonitor / Weather:")
    icon_monitor()
    icon_weather_clear_day()
    icon_weather_clear_night()
    icon_weather_partly_day()
    icon_weather_partly_night()
    icon_weather_cloudy()
    icon_weather_fog()
    icon_weather_rain()
    icon_weather_snow()
    icon_weather_thunder()

```

- [ ] **Step 3: Generate and check the icons**

Run: `~/.virtualenvs/smashdeck/bin/python generate_icons.py && git status --short icons/`
Expected: `51 icons generated`, and git lists exactly the 10 new files as untracked (`?? icons/monitor.png`, `?? icons/weather_*.png`). The generator is deterministic, so no existing icon shows as modified. The weather icons have transparent backgrounds; `monitor.png` is a blue bar chart on a `(40, 60, 90)` tile.

- [ ] **Step 4: Write the failing tests `tests/test_monitor_tiles.py`**

```python
# tests/test_monitor_tiles.py
"""What each Monitor key shows (build_tiles) and how it is drawn (render_tile)."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pages.monitor.sources import SystemSample
from pages.monitor.tiles import (
    AMBER,
    BLANK,
    BLUE,
    GREEN,
    GREY,
    RED,
    WHITE,
    Tile,
    WeatherTile,
    build_tiles,
    fmt_disk_rate,
    fmt_net_rate,
    render_tile,
    uv_band,
)
from pages.monitor.weather import Day, Weather

NOW = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)  # 15:00 in the weather's UTC+1

FULL = SystemSample(
    cpu_temp=51.1, cpu_load=12.4, cpu_power=42.2,
    gpu_temp=48.0, gpu_load=6.0, gpu_power=67.6,
    vram_used_gb=4.8, vram_total_gb=31.84, pc_power=214.0,
    ram_percent=32.0, disks=[("/", 52.4), ("Fast", 76.4)], ssd_temp=60.9,
    disk_read=8_192.0, disk_write=885_000.0, net_down=2_500_000.0, net_up=25_000.0,
)

WEATHER = Weather(
    temp=12.3, feels_like=9.4, humidity=78, wind_speed=18.2, wind_dir=225,
    code=2, is_day=True, uv=2.4, utc_offset=timedelta(hours=1),
    today=Day(2, 15.2, 6.1, 40, datetime(2026, 11, 10, 7, 41), datetime(2026, 11, 10, 16, 52)),
    tomorrow=Day(61, 14.0, 7.0, 80, datetime(2026, 11, 11, 7, 43), datetime(2026, 11, 11, 16, 51)),
)


def test_covers_exactly_the_content_keys():
    assert sorted(build_tiles(FULL, WEATHER, NOW)) == list(range(8, 32))


def test_hardware_row():
    t = build_tiles(FULL, WEATHER, NOW)
    assert t[8] == Tile("CPU", "51°", "°C", GREEN)
    assert t[9] == Tile("CPU load", "12", "%", GREEN)
    assert t[10] == Tile("CPU pwr", "42", "W", BLUE)
    assert t[11] == Tile("GPU", "48°", "°C", GREEN)
    assert t[12] == Tile("GPU load", "6", "%", GREEN)
    assert t[13] == Tile("GPU pwr", "68", "W", BLUE)
    assert t[14] == Tile("VRAM", "4.8", "of 32 GB", GREEN)
    assert t[15] == Tile("PC power", "214", "W", BLUE)


def test_system_row():
    t = build_tiles(FULL, WEATHER, NOW)
    assert t[16] == Tile("RAM", "32", "%", GREEN)
    assert t[17] == Tile("Disk /", "52", "% full", GREEN)
    assert t[18] == Tile("Disk Fast", "76", "% full", GREEN)
    assert t[19] == Tile("SSD", "61°", "°C hottest", GREEN)
    assert t[20] == Tile("Disk read", "8", "kB/s", BLUE)
    assert t[21] == Tile("Disk write", "885", "kB/s", BLUE)
    assert t[22] == Tile("Net ↓", "20", "Mbit/s", BLUE)
    assert t[23] == Tile("Net ↑", "0.2", "Mbit/s", BLUE)


@pytest.mark.parametrize("changes, key, color", [
    ({"cpu_temp": 74.9}, 8, GREEN),
    ({"cpu_temp": 75.0}, 8, AMBER),
    ({"cpu_temp": 89.9}, 8, AMBER),
    ({"cpu_temp": 90.0}, 8, RED),
    ({"cpu_load": 70.0}, 9, AMBER),
    ({"gpu_temp": 85.0}, 11, RED),
    ({"gpu_load": 95.0}, 12, RED),
    ({"vram_used_gb": 25.6, "vram_total_gb": 32.0}, 14, AMBER),  # 80 %
    ({"ram_percent": 92.0}, 16, RED),
    ({"disks": [("/", 90.0)]}, 17, RED),
    ({"ssd_temp": 70.0}, 19, AMBER),
    ({"ssd_temp": 80.0}, 19, RED),
])
def test_threshold_colours(changes, key, color):
    assert build_tiles(replace(FULL, **changes), WEATHER, NOW)[key].color == color


@pytest.mark.parametrize("bps, shown", [
    (0, ("0.0", "Mbit/s")),
    (125_000, ("1.0", "Mbit/s")),
    (1_250_000, ("10", "Mbit/s")),
    (150_000_000, ("1.20", "Gbit/s")),
])
def test_network_rate_in_mbit(bps, shown):
    assert fmt_net_rate(bps) == shown


@pytest.mark.parametrize("bps, shown", [
    (999_499, ("999", "kB/s")),
    (1_000_000, ("1.0", "MB/s")),
    (12_400_000, ("12", "MB/s")),
])
def test_disk_rate(bps, shown):
    assert fmt_disk_rate(bps) == shown


def test_unavailable_sensor_is_na_and_missing_rate_is_dash():
    t = build_tiles(SystemSample(disks=[("/", None)]), WEATHER, NOW)
    assert t[8] == Tile("CPU", "n/a", "", GREY)
    assert t[14] == Tile("VRAM", "n/a", "", GREY)
    assert t[17] == Tile("Disk /", "n/a", "", GREY)
    assert t[9] == Tile("CPU load", "—", "", GREY)
    assert t[22] == Tile("Net ↓", "—", "", GREY)


def test_placeholder_sample_shows_dashes_with_labels():
    t = build_tiles(SystemSample.placeholder(["/"]), None, NOW)
    assert t[8] == Tile("CPU", "—", "", GREY)
    assert t[17] == Tile("Disk /", "—", "", GREY)
    assert all(t[k].value == "—" for k in list(range(8, 18)) + list(range(19, 24)))


def test_unused_second_disk_slot_is_blank():
    t = build_tiles(replace(FULL, disks=[("/", 52.4)]), WEATHER, NOW)
    assert t[18] == BLANK


def test_weather_row():
    t = build_tiles(FULL, WEATHER, NOW)
    assert t[24] == WeatherTile("Now", "weather_partly_day.png", "12°", "H 15° · L 6°")
    assert t[25] == Tile("Feels like", "9°", "°C", WHITE)
    assert t[26] == Tile("Humidity", "78", "%", WHITE)
    assert t[27] == Tile("Wind SW", "18", "km/h", WHITE)
    assert t[28] == Tile("Rain", "40", "% today", WHITE)
    assert t[29] == Tile("UV", "2", "low", GREEN)
    assert t[30] == WeatherTile("Tomorrow", "weather_rain.png", "14° / 7°", "80% rain")
    assert t[31] == Tile("Sunset", "16:52", "rise 07:43", WHITE)


@pytest.mark.parametrize("utc_hour, tile", [
    (6, Tile("Sunrise", "07:41", "set 16:52", WHITE)),   # 07:00 local, before sunrise
    (14, Tile("Sunset", "16:52", "rise 07:43", WHITE)),  # 15:00 local, daytime
    (17, Tile("Sunrise", "07:43", "set 16:51", WHITE)),  # 18:00 local, after sunset
])
def test_next_sun_event(utc_hour, tile):
    now = datetime(2026, 11, 10, utc_hour, 0, tzinfo=UTC)
    assert build_tiles(FULL, WEATHER, now)[31] == tile


@pytest.mark.parametrize("level, band", [
    (0, ("low", GREEN)), (2, ("low", GREEN)),
    (3, ("moderate", AMBER)), (5, ("moderate", AMBER)),
    (6, ("high", AMBER)), (7, ("high", AMBER)),
    (8, ("very high", RED)), (10, ("very high", RED)),
    (11, ("extreme", RED)),
])
def test_uv_band(level, band):
    assert uv_band(level) == band


def test_uv_value_is_rounded_before_banding():
    t = build_tiles(FULL, replace(WEATHER, uv=2.6), NOW)
    assert t[29] == Tile("UV", "3", "moderate", AMBER)


def test_negative_zero_temperature_shows_as_zero():
    t = build_tiles(FULL, replace(WEATHER, feels_like=-0.4), NOW)
    assert t[25].value == "0°"


def test_missing_rain_chances():
    w = replace(WEATHER, today=replace(WEATHER.today, rain_chance=None),
                tomorrow=replace(WEATHER.tomorrow, rain_chance=None))
    t = build_tiles(FULL, w, NOW)
    assert t[28] == Tile("Rain", "—", "% today", WHITE)
    assert t[30].detail == ""


def test_weather_not_fetched_yet_shows_dashes():
    t = build_tiles(FULL, None, NOW)
    assert t[24] == WeatherTile("Now", "", "—", "")
    assert t[25] == Tile("Feels like", "—", "", GREY)
    assert t[30] == WeatherTile("Tomorrow", "", "—", "")
    assert t[31] == Tile("Sun", "—", "", GREY)


def test_weather_error_shows_error_tile():
    t = build_tiles(FULL, None, NOW, weather_error="offline")
    assert t[24] == WeatherTile("Weather", "error.png", "—", "offline")
    assert t[27] == Tile("Wind", "—", "", GREY)


# --- render_tile

def black_columns(img, xs):
    return all(img.getpixel((x, y)) == (0, 0, 0) for x in xs for y in range(img.height))


def test_render_tile_is_144px_rgb():
    img = render_tile(Tile("CPU", "51°", "°C", GREEN))
    assert (img.size, img.mode) == ((144, 144), "RGB")


def test_render_tile_shrinks_long_values_to_fit():
    img = render_tile(Tile("Disk write", "88888888", "kB/s", BLUE))
    assert black_columns(img, (0, 1, 2, 141, 142, 143))


def test_render_weather_tile_draws_icon():
    img = render_tile(WeatherTile("Now", "weather_clear_day.png", "12°", "H 15° · L 6°"))
    icon_area = img.crop((40, 30, 104, 90))
    assert icon_area.getbbox() is not None  # something non-black was drawn


def test_render_blank_tile_is_black():
    assert render_tile(BLANK).getbbox() is None
```

- [ ] **Step 5: Run them and watch them fail**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/test_monitor_tiles.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'pages.monitor.tiles'`.

- [ ] **Step 6: Implement `pages/monitor/tiles.py`**

```python
# pages/monitor/tiles.py
"""Monitor key faces: what each key shows (build_tiles) and how it is drawn
(render_tile). build_tiles is pure, so formatting, thresholds and the
sun-event logic are tested without images."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from pages.monitor.sources import SystemSample
from pages.monitor.weather import Weather, compass, condition_icon

RGB = tuple[int, int, int]
GREEN: RGB = (60, 200, 110)
AMBER: RGB = (240, 170, 40)
RED: RGB = (235, 70, 60)
BLUE: RGB = (110, 170, 255)  # no meaningful limit: watts, throughput
WHITE: RGB = (235, 235, 240)  # weather
GREY: RGB = (150, 150, 160)  # labels, units, missing values

DASH = "—"
SIZE = 144  # render size; the Stream Deck library downscales like the icons
ICONS = os.path.join(os.path.dirname(__file__), "..", "..", "icons")
FONT = "/usr/share/fonts/TTF/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
WEATHER_KEYS = range(24, 32)


@dataclass(frozen=True)
class Tile:
    label: str
    value: str
    unit: str
    color: RGB


@dataclass(frozen=True)
class WeatherTile:
    label: str
    icon: str  # filename in icons/, "" for none
    value: str
    detail: str


BLANK = Tile("", "", "", GREY)


# --- formatting --------------------------------------------------------------

def level(value: float, warn: float, crit: float) -> RGB:
    if value >= crit:
        return RED
    if value >= warn:
        return AMBER
    return GREEN


def _int(v: float) -> str:
    return str(round(v))  # round() -> int, so -0.4 prints "0", not "-0"


def _deg(v: float) -> str:
    return f"{round(v)}°"


def fmt_disk_rate(bps: float) -> tuple[str, str]:
    if bps < 1e6:
        return f"{bps / 1e3:.0f}", "kB/s"
    mb = bps / 1e6
    return (f"{mb:.1f}" if mb < 10 else f"{mb:.0f}"), "MB/s"


def fmt_net_rate(bps: float) -> tuple[str, str]:
    mbit = bps * 8 / 1e6
    if mbit >= 1000:
        return f"{mbit / 1000:.2f}", "Gbit/s"
    return (f"{mbit:.1f}" if mbit < 10 else f"{mbit:.0f}"), "Mbit/s"


def uv_band(uv_level: int) -> tuple[str, RGB]:
    if uv_level < 3:
        return "low", GREEN
    if uv_level < 6:
        return "moderate", AMBER
    if uv_level < 8:
        return "high", AMBER
    if uv_level < 11:
        return "very high", RED
    return "extreme", RED


def _hhmm(t: datetime) -> str:
    return t.strftime("%H:%M")


# --- tiles -------------------------------------------------------------------

def _system_tiles(s: SystemSample) -> dict[int, Tile]:
    missing = DASH if s.pending else "n/a"

    def metric(label, value, text, unit, color, missing_text=None):
        if value is None:
            return Tile(label, missing_text or missing, "", GREY)
        return Tile(label, text(value), unit, color(value))

    def rate(label, value, fmt):
        if value is None:  # no rate on the first sample
            return Tile(label, DASH, "", GREY)
        text, unit = fmt(value)
        return Tile(label, text, unit, BLUE)

    def blue(_):
        return BLUE

    def lv(warn, crit):
        return lambda v: level(v, warn, crit)

    def vram_color(used_gb):
        if not s.vram_total_gb:
            return BLUE
        return level(used_gb / s.vram_total_gb * 100, 80, 92)

    vram_unit = f"of {round(s.vram_total_gb)} GB" if s.vram_total_gb else "GB"

    tiles = {
        8: metric("CPU", s.cpu_temp, _deg, "°C", lv(75, 90)),
        9: metric("CPU load", s.cpu_load, _int, "%", lv(70, 90), missing_text=DASH),
        10: metric("CPU pwr", s.cpu_power, _int, "W", blue),
        11: metric("GPU", s.gpu_temp, _deg, "°C", lv(75, 85)),
        12: metric("GPU load", s.gpu_load, _int, "%", lv(70, 90)),
        13: metric("GPU pwr", s.gpu_power, _int, "W", blue),
        14: metric("VRAM", s.vram_used_gb, lambda v: f"{v:.1f}", vram_unit, vram_color),
        15: metric("PC power", s.pc_power, _int, "W", blue),
        16: metric("RAM", s.ram_percent, _int, "%", lv(80, 92)),
        19: metric("SSD", s.ssd_temp, _deg, "°C hottest", lv(70, 80)),
        20: rate("Disk read", s.disk_read, fmt_disk_rate),
        21: rate("Disk write", s.disk_write, fmt_disk_rate),
        22: rate("Net ↓", s.net_down, fmt_net_rate),
        23: rate("Net ↑", s.net_up, fmt_net_rate),
    }
    for i, key in enumerate((17, 18)):
        if i < len(s.disks):
            name, pct = s.disks[i]
            tiles[key] = metric(f"Disk {name}", pct, _int, "% full", lv(80, 90))
        else:
            tiles[key] = BLANK
    return tiles


def _sun_tile(w: Weather, local_now: datetime) -> Tile:
    today, tomorrow = w.today, w.tomorrow
    if local_now < today.sunrise:
        return Tile("Sunrise", _hhmm(today.sunrise), f"set {_hhmm(today.sunset)}", WHITE)
    if local_now < today.sunset:
        return Tile("Sunset", _hhmm(today.sunset), f"rise {_hhmm(tomorrow.sunrise)}", WHITE)
    return Tile("Sunrise", _hhmm(tomorrow.sunrise), f"set {_hhmm(tomorrow.sunset)}", WHITE)


def _weather_tiles(w: Weather | None, now_utc: datetime,
                   error: str | None) -> dict[int, Tile | WeatherTile]:
    if w is None:
        now_tile = (WeatherTile("Weather", "error.png", DASH, error) if error
                    else WeatherTile("Now", "", DASH, ""))
        return {
            24: now_tile,
            25: Tile("Feels like", DASH, "", GREY),
            26: Tile("Humidity", DASH, "", GREY),
            27: Tile("Wind", DASH, "", GREY),
            28: Tile("Rain", DASH, "", GREY),
            29: Tile("UV", DASH, "", GREY),
            30: WeatherTile("Tomorrow", "", DASH, ""),
            31: Tile("Sun", DASH, "", GREY),
        }

    local_now = (now_utc + w.utc_offset).replace(tzinfo=None)
    today, tomorrow = w.today, w.tomorrow
    uv_level = int(w.uv + 0.5)
    uv_text, uv_color = uv_band(uv_level)
    rain_today = DASH if today.rain_chance is None else str(today.rain_chance)
    rain_tomorrow = "" if tomorrow.rain_chance is None else f"{tomorrow.rain_chance}% rain"
    return {
        24: WeatherTile("Now", condition_icon(w.code, w.is_day), _deg(w.temp),
                        f"H {_deg(today.t_max)} · L {_deg(today.t_min)}"),
        25: Tile("Feels like", _deg(w.feels_like), "°C", WHITE),
        26: Tile("Humidity", str(w.humidity), "%", WHITE),
        27: Tile(f"Wind {compass(w.wind_dir)}", _int(w.wind_speed), "km/h", WHITE),
        28: Tile("Rain", rain_today, "% today", WHITE),
        29: Tile("UV", str(uv_level), uv_text, uv_color),
        30: WeatherTile("Tomorrow", condition_icon(tomorrow.code, True),
                        f"{_deg(tomorrow.t_max)} / {_deg(tomorrow.t_min)}", rain_tomorrow),
        31: _sun_tile(w, local_now),
    }


def build_tiles(sample: SystemSample, weather: Weather | None, now_utc: datetime,
                weather_error: str | None = None) -> dict[int, Tile | WeatherTile]:
    """Every content key (8-31) -> what it should show."""
    return {**_system_tiles(sample), **_weather_tiles(weather, now_utc, weather_error)}


# --- rendering ---------------------------------------------------------------

def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _fit(text: str, path: str, size: int, max_width: int):
    """The largest font (stepping down by 2 px) whose text fits max_width."""
    while size > 10:
        font = _font(path, size)
        if font.getlength(text) <= max_width:
            return font
        size -= 2
    return _font(path, size)


def render_tile(tile: Tile | WeatherTile) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), "black")
    d = ImageDraw.Draw(img)
    mid = SIZE // 2
    if isinstance(tile, WeatherTile):
        d.text((mid, 14), tile.label, font=_fit(tile.label, FONT, 17, SIZE - 8),
               fill=GREY, anchor="mm")
        if tile.icon:
            icon = Image.open(os.path.join(ICONS, tile.icon)).convert("RGBA")
            icon.thumbnail((72, 72))
            img.paste(icon, (mid - icon.width // 2, 24), icon)
        d.text((mid, 110), tile.value, font=_fit(tile.value, BOLD, 30, SIZE - 12),
               fill=WHITE, anchor="mm")
        d.text((mid, 133), tile.detail, font=_fit(tile.detail, FONT, 15, SIZE - 8),
               fill=GREY, anchor="mm")
        return img
    d.text((mid, 21), tile.label, font=_fit(tile.label, FONT, 19, SIZE - 8),
           fill=GREY, anchor="mm")
    d.text((mid, 78), tile.value, font=_fit(tile.value, BOLD, 45, SIZE - 12),
           fill=tile.color, anchor="mm")
    d.text((mid, 123), tile.unit, font=_fit(tile.unit, FONT, 18, SIZE - 8),
           fill=GREY, anchor="mm")
    return img
```

- [ ] **Step 7: Run the tests**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`
Expected: `110 passed` (47 new).

- [ ] **Step 8: Lint and commit**

Run: `uvx ruff check pages/monitor/tiles.py tests/test_monitor_tiles.py`
Expected: `All checks passed!`

```bash
git add generate_icons.py icons/monitor.png icons/weather_*.png pages/monitor/tiles.py tests/test_monitor_tiles.py
git commit -m "monitor: key faces and weather icons

build_tiles maps a sample + weather to what each of keys 8-31 shows
(formatting, thresholds, next sun event); render_tile draws the approved
big-number style at 144 px. Adds monitor.png and nine weather icons.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: MonitorPage (polling, diff-redraw, weather schedule)

**Files:**
- Modify: `tests/conftest.py` (record every pushed key)
- Modify: `pages/monitor/__init__.py` (replace the placeholder)
- Test: `tests/test_monitor_page.py`

**Interfaces:**
- Consumes: `SystemSample.placeholder`, `SystemSampler` (Task 3); `weather.fetch` (Task 2); `build_tiles`, `render_tile`, `WEATHER_KEYS` (Task 4); `BasePage` (`pages/__init__.py`).
- Produces: `MonitorPage(controller, sampler=None, fetch_weather=None, clock=time.monotonic, utcnow=_utcnow)` with `render()`, `on_key(key)`, `activate()`, `deactivate()` and `tick(stop=None)`. It reads config `monitor.disks`, `monitor.net_interface` and `monitor.weather.latitude/longitude`. The poll thread is named `monitor-poll`. Module constants: `POLL_SECONDS = 2.0`, `WEATHER_EVERY = 900`, `WEATHER_RETRY = 60`, `WEATHER_STALE = 10800`.

- [ ] **Step 1: Record pushes in `FakeController` (`tests/conftest.py`)**

After the line `self.images = {}  # key index -> kwargs of last render`, add:

```python
        self.pushes = []  # key index of every set_key_image call, in order
```

As the first line of `FakeController.set_key_image`'s body, before `self.images[key] = {`, add:

```python
        self.pushes.append(key)
```

- [ ] **Step 2: Write the failing tests `tests/test_monitor_page.py`**

```python
# tests/test_monitor_page.py
"""MonitorPage lifecycle, polling and weather scheduling with an injected
sampler, weather fetch and clocks. render_tile is swapped for identity so each
key's recorded "image" is the Tile it would show."""
import json
import os
import threading
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from pages import monitor
from pages.monitor import MonitorPage
from pages.monitor.sources import SystemSample
from pages.monitor.tiles import GREEN, GREY, Tile, WeatherTile
from pages.monitor.weather import parse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "openmeteo.json")
LOCATION = {"latitude": 49.63277, "longitude": 6.26459}
FIXED_NOW = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)


class FakeSampler:
    def __init__(self):
        self.calls = 0
        self.next = SystemSample(cpu_temp=50.0, ram_percent=30.0, disks=[("/", 50.0)])

    def sample(self):
        self.calls += 1
        return self.next


class FakeWeather:
    def __init__(self):
        with open(FIXTURE) as f:
            self.weather = parse(json.load(f))
        self.calls = []
        self.fail = False

    def __call__(self, lat, lon):
        self.calls.append((lat, lon))
        if self.fail:
            raise OSError("network down")
        return self.weather


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def tiles_as_images(monkeypatch):
    monkeypatch.setattr(monitor, "render_tile", lambda tile: tile)


def make_page(ctrl, monitor_cfg):
    ctrl.config = {"monitor": monitor_cfg}
    p = SimpleNamespace(sampler=FakeSampler(), weather=FakeWeather(), clock=Clock(), ctrl=ctrl)
    p.page = MonitorPage(ctrl, sampler=p.sampler, fetch_weather=p.weather,
                         clock=p.clock, utcnow=lambda: FIXED_NOW)
    return p


@pytest.fixture
def p(ctrl):
    return make_page(ctrl, {"disks": [{"name": "/", "path": "/"}], "weather": LOCATION})


def shown(ctrl, key):
    return ctrl.images[key]["pil_image"]


def test_render_draws_all_content_keys_without_polling(p):
    p.page.render()
    assert sorted(set(p.ctrl.pushes)) == list(range(8, 32))
    assert p.sampler.calls == 0
    assert p.weather.calls == []
    assert shown(p.ctrl, 8) == Tile("CPU", "—", "", GREY)
    assert shown(p.ctrl, 17) == Tile("Disk /", "—", "", GREY)


def test_tick_samples_and_fetches_weather(p):
    p.page.render()
    p.page.tick()
    assert p.sampler.calls == 1
    assert p.weather.calls == [(49.63277, 6.26459)]
    assert shown(p.ctrl, 8) == Tile("CPU", "50°", "°C", GREEN)
    assert shown(p.ctrl, 24).label == "Now"


def test_tick_redraws_only_changed_keys(p):
    p.page.render()
    p.page.tick()
    p.ctrl.pushes.clear()

    p.sampler.next = replace(p.sampler.next, cpu_temp=51.0)
    p.page.tick()

    assert p.ctrl.pushes == [8]


def test_render_redraws_everything_again(p):
    p.page.render()
    p.page.tick()
    p.ctrl.pushes.clear()

    p.page.render()  # e.g. the Monitor nav key pressed again

    assert sorted(p.ctrl.pushes) == list(range(8, 32))


def test_weather_refreshes_after_15_minutes(p):
    p.page.tick()
    p.clock.t += 899
    p.page.tick()
    assert len(p.weather.calls) == 1
    p.clock.t += 2
    p.page.tick()
    assert len(p.weather.calls) == 2


def test_weather_key_press_fetches_on_next_tick_not_in_on_key(p):
    p.page.tick()
    p.page.on_key(9)  # not a weather key
    p.page.on_key(26)
    assert len(p.weather.calls) == 1
    p.page.tick()
    assert len(p.weather.calls) == 2


def test_failed_fetch_shows_offline_and_retries_after_a_minute(p):
    p.weather.fail = True
    p.page.tick()
    assert shown(p.ctrl, 24) == WeatherTile("Weather", "error.png", "—", "offline")
    p.clock.t += 59
    p.page.tick()
    assert len(p.weather.calls) == 1
    p.clock.t += 2
    p.page.tick()
    assert len(p.weather.calls) == 2


def test_failures_keep_last_weather_for_3_hours(p):
    p.page.tick()  # success at t0
    t0 = p.clock.t
    p.weather.fail = True

    p.clock.t = t0 + 3 * 3600 - 1
    p.page.tick()
    assert shown(p.ctrl, 24).label == "Now"

    p.clock.t = t0 + 3 * 3600 + 1
    p.page.tick()
    assert shown(p.ctrl, 24) == WeatherTile("Weather", "error.png", "—", "offline")


def test_no_location_shows_error_and_never_fetches(ctrl):
    p = make_page(ctrl, {"disks": []})
    p.page.render()
    p.page.tick()
    assert shown(p.ctrl, 24) == WeatherTile("Weather", "error.png", "—", "no location")
    assert p.weather.calls == []


def poll_threads():
    return [t for t in threading.enumerate() if t.name == "monitor-poll" and t.is_alive()]


def test_deactivate_stops_the_poll_thread(p):
    p.page.activate()
    assert len(poll_threads()) == 1
    p.page.deactivate()
    assert poll_threads() == []


def test_tick_after_stop_draws_nothing(p):
    # A tick still running when deactivate() returns (slow weather fetch)
    # must not draw over the page that is now active.
    stop = threading.Event()
    stop.set()
    p.page.tick(stop)
    assert p.ctrl.pushes == []
```

- [ ] **Step 3: Run them and watch them fail**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/test_monitor_page.py -q`
Expected: collection error `ImportError: cannot import name 'MonitorPage' from 'pages.monitor'`.

- [ ] **Step 4: Implement `pages/monitor/__init__.py`**

Replace the placeholder with:

```python
# pages/monitor/__init__.py
"""Monitor page: live PC metrics (rows 2-3) and Open-Meteo weather (row 4).

Polls only while visible: activate() starts a thread that ticks every
POLL_SECONDS, deactivate() stops it. Each tick redraws only the keys whose
tile changed. Sensor reads and the weather HTTP call never run on the
Stream Deck's key-callback thread.
"""
from __future__ import annotations

import threading
import time
import traceback
from datetime import UTC, datetime

from pages import BasePage
from pages.monitor import weather as weather_api
from pages.monitor.sources import SystemSample, SystemSampler
from pages.monitor.tiles import WEATHER_KEYS, build_tiles, render_tile

POLL_SECONDS = 2.0
WEATHER_EVERY = 15 * 60  # s between successful fetches
WEATHER_RETRY = 60  # s after a failed fetch
WEATHER_STALE = 3 * 60 * 60  # s without success before the row shows "offline"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MonitorPage(BasePage):
    def __init__(self, controller, sampler=None, fetch_weather=None,
                 clock=time.monotonic, utcnow=_utcnow):
        super().__init__(controller)
        cfg = controller.config.get("monitor") or {}
        disks = (cfg.get("disks") or [])[:2]
        location = cfg.get("weather") or {}
        self._lat = location.get("latitude")
        self._lon = location.get("longitude")
        self._sampler = sampler or SystemSampler(
            disks=disks, net_interface=cfg.get("net_interface"))
        self._fetch_weather = fetch_weather or weather_api.fetch
        self._clock = clock
        self._utcnow = utcnow

        self._sample = SystemSample.placeholder([d["name"] for d in disks])
        self._weather = None
        self._weather_at = 0.0  # clock() of the last successful fetch
        self._weather_due = 0.0  # clock() when the next fetch is due
        self._weather_failed = False

        self._shown = {}  # key -> tile currently on the deck
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    # --- BasePage ---

    def render(self):
        self._draw(full=True)

    def on_key(self, key):
        if key in WEATHER_KEYS:
            self._weather_due = 0.0  # the poll thread fetches on its next tick

    def activate(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(self._stop,), name="monitor-poll", daemon=True)
        self._thread.start()

    def deactivate(self):
        if self._stop is not None:
            self._stop.set()
        with self._lock:
            pass  # wait out an in-flight draw; later ones see the stop flag
        if self._thread is not None:
            self._thread.join(timeout=POLL_SECONDS + 0.5)
        self._stop = None
        self._thread = None

    # --- polling ---

    def _run(self, stop: threading.Event):
        while not stop.is_set():
            try:
                self.tick(stop)
            except Exception:
                traceback.print_exc()
            stop.wait(POLL_SECONDS)

    def tick(self, stop: threading.Event | None = None):
        """One poll: sample the system, fetch weather if due, redraw changes."""
        self._sample = self._sampler.sample()
        if self._has_location() and self._clock() >= self._weather_due:
            self._refresh_weather()
        self._draw(full=False, stop=stop)

    def _has_location(self) -> bool:
        return self._lat is not None and self._lon is not None

    def _refresh_weather(self):
        try:
            self._weather = self._fetch_weather(self._lat, self._lon)
        except Exception as e:
            print(f"monitor: weather fetch failed: {e!r}")
            self._weather_failed = True
            self._weather_due = self._clock() + WEATHER_RETRY
            return
        self._weather_at = self._clock()
        self._weather_failed = False
        self._weather_due = self._weather_at + WEATHER_EVERY

    def _weather_view(self):
        """(weather to show, error text for key 24)."""
        if not self._has_location():
            return None, "no location"
        if self._weather is not None and self._clock() - self._weather_at <= WEATHER_STALE:
            return self._weather, None
        return None, ("offline" if self._weather_failed else None)

    def _draw(self, full: bool, stop: threading.Event | None = None):
        weather, error = self._weather_view()
        tiles = build_tiles(self._sample, weather, self._utcnow(), weather_error=error)
        with self._lock:
            if stop is not None and stop.is_set():
                return
            if full:
                self._shown = {}
            for key, tile in tiles.items():
                if self._shown.get(key) != tile:
                    self.ctrl.set_key_image(key, pil_image=render_tile(tile))
                    self._shown[key] = tile
```

- [ ] **Step 5: Run the tests**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`
Expected: `121 passed` (11 new).

- [ ] **Step 6: Lint and commit**

Run: `uvx ruff check pages/monitor tests/`
Expected: only `BLE001` on the deliberate catch-alls (`_run` and `_refresh_weather` in `pages/monitor/__init__.py`, `_try` in `sources.py`).

```bash
git add tests/conftest.py pages/monitor/__init__.py tests/test_monitor_page.py
git commit -m "monitor: MonitorPage with poll thread and diff-redraw

Polls every 2 s only while visible and redraws only changed keys. Weather
refreshes every 15 min (60 s after a failure, or on a weather-key press)
on the poll thread, and turns to an offline error after 3 h.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Wire up nav key 6, config and docs

**Files:**
- Modify: `main.py` (`NAV_KEYS`, page registration)
- Test: `tests/test_controller.py`
- Modify: `config.yaml.dist`, `README.md`, `CLAUDE.md`
- Modify (local only, gitignored, never committed): `config.yaml`

**Interfaces:**
- Consumes: `MonitorPage` (Task 5); `key_pixel`, `close_to`, `STRIP_PIXEL`, `ACCENT` (Task 1 tests).
- Produces: `NAV_KEYS[6] = ("monitor", "monitor.png", "Monitor")`; `self.pages["monitor"]`.

- [ ] **Step 1: Write the failing test**

In `tests/test_controller.py`, change `HOME, SPOTIFY, HUE, KASA = 0, 1, 2, 3` to:

```python
HOME, SPOTIFY, HUE, KASA, MONITOR = 0, 1, 2, 3, 6
```

and append:

```python
def test_nav_key_6_opens_monitor_page(controller):
    monitor = RecordingPage(controller)
    controller.pages = {"home": RecordingPage(controller), "monitor": monitor}

    press(controller, MONITOR)

    assert controller.current_page is monitor
    assert close_to(key_pixel(controller, MONITOR, STRIP_PIXEL), ACCENT)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/test_controller.py -q`
Expected: `1 failed, 6 passed`, with `assert None is <...RecordingPage...>`: key 6 is not a nav key yet.

- [ ] **Step 3: Register the page in `main.py`**

Add to `NAV_KEYS`, after the `4: ("tapo", ...)` entry:

```python
    6: ("monitor", "monitor.png", "Monitor"),
```

In `DeckController.start()`, add `from pages.monitor import MonitorPage` after `from pages.kasa import KasaPage`. Add `"monitor": MonitorPage(self),` after `"tapo": TapoPage(self),` in the `self.pages` dict.

- [ ] **Step 4: Run the whole suite**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q`
Expected: `122 passed`.

- [ ] **Step 5: Document the config in `config.yaml.dist`**

Append:

```yaml

monitor:
  # Up to 2 disks, shown on keys 17-18 as "Disk <name>" (% full).
  disks:
    - name: "/"
      path: "/"
    - name: "Home"
      path: "/home"
  # net_interface: "eth0"     # optional; default = interface on the default route
  weather:
    # Sent to api.open-meteo.com (no API key). This example is Berlin.
    latitude: 52.52
    longitude: 13.41
```

- [ ] **Step 6: Configure the local `config.yaml` (gitignored, do not commit)**

Append to `config.yaml`:

```yaml

monitor:
  disks:
    - name: "/"
      path: "/"
    - name: "Fast"
      path: "/home/wickeddoc/Games"   # the 2 TB "fast" btrfs drive
  weather:
    # Münsbach, Luxembourg (Open-Meteo geocoding; Europe/Luxembourg)
    latitude: 49.63277
    longitude: 6.26459
```

- [ ] **Step 7: Update `README.md`**

- After the integrations-table row `| Tapo    | ...`, add:
  `| Monitor | psutil, sysfs hwmon, `nvidia-smi`, Open-Meteo | Implemented |`
- In the Requirements deps list, append `` `psutil` `` after `` `jeepney` ``. Add a bullet: `- Optional: `nvidia-smi` (NVIDIA driver) for the Monitor page's GPU keys; without it they show "n/a".`
- In the Setup comment, change `# Tapo credentials, Spotify playlists` to `# Tapo credentials, Spotify playlists, Monitor disks + weather location`.
- Replace the Layout bullets `- **Keys 0–4** — global nav bar: Home, Spotify, Hue, Kasa, Tapo` and `- **Keys 5–6** — reserved / blank` with:
  `- **Keys 0–4, 6** — global nav bar: Home, Spotify, Hue, Kasa, Tapo, Monitor (the current page's key has a blue label strip)`
  `- **Key 5** — reserved / blank`
- After the per-page bullet `- **Kasa / Tapo** — devices on row 2, tap to toggle`, add:
  `- **Monitor** — row 2: CPU/GPU temperature, load and power, VRAM, whole-PC power; row 3: RAM, two disks, hottest NVMe, disk read/write, network down/up (Mbit/s); row 4: Open-Meteo weather (now, feels like, humidity, wind, rain, UV, tomorrow, next sunrise/sunset). Values are colour-coded green/amber/red and refresh every 2 s while the page is open; weather refreshes every 15 min, or immediately when a weather key is pressed.`
- In the Project layout block, after `  tapo.py          TapoPage — toggle Tapo devices`, add:

```
  monitor/         MonitorPage — PC metrics + weather (nav key 6)
    sources.py     psutil / hwmon / nvidia-smi -> SystemSample
    weather.py     Open-Meteo client (no API key)
    tiles.py       what each key shows (build_tiles) and how it is drawn
```

- [ ] **Step 8: Update `CLAUDE.md`**

- In the Project Overview sentence, after `and Tapo (via the `tapo` SDK).`, insert ` A Monitor page shows PC metrics (psutil, sysfs hwmon, `nvidia-smi`) and Open-Meteo weather.`
- After the bullet `- **KasaPage / TapoPage** — row 2 lists devices; tap to toggle.`, add:
  `- **MonitorPage** (`pages/monitor/`) — rows 2–3 live PC metrics, row 4 weather, in a big-number key style. A `monitor-poll` thread runs only while the page is visible (2 s ticks; weather every 15 min on the same thread) and redraws only keys whose tile changed. `tiles.build_tiles` is pure (formatting, thresholds, sun events) and `render_tile` draws 144 px images passed as `pil_image`. Every sensor degrades to "n/a" independently.`
- In Key Layout Convention, replace `Keys 0–4 are a persistent global nav bar (Home, Spotify, Hue, Kasa, Tapo), defined by `NAV_KEYS` in `main.py`. Keys 5–6 are reserved/blank.` with `Keys 0–4 and 6 are a persistent global nav bar (Home, Spotify, Hue, Kasa, Tapo, Monitor), defined by `NAV_KEYS` in `main.py`; the current page's nav key gets a blue label strip (`set_key_image(..., label_bg=NAV_ACTIVE_COLOR)`). Key 5 is reserved/blank.`
- In the Configuration paragraph, replace `and `spotify` (`playlists` only — playback goes over DBus, no OAuth).` with `, `spotify` (`playlists` only — playback goes over DBus, no OAuth), and `monitor` (`disks`, optional `net_interface`, `weather.latitude/longitude`).`
- In Dependencies, after the `jeepney` bullet, add `- `psutil` — CPU/RAM/disk/network/temperature readings for `pages/monitor/sources.py``.

- [ ] **Step 9: Full verification**

Run: `~/.virtualenvs/smashdeck/bin/python -m pytest tests/ -q && uvx ruff check pages/monitor tests/ main.py`
Expected: `122 passed`; in `pages/monitor` and `tests/` ruff shows only the three deliberate `BLE001` catch-alls. `main.py`'s findings (`BLE001`, `UP045`) predate this work and stay as they are.

- [ ] **Step 10: Commit (without `config.yaml`)**

```bash
git add main.py tests/test_controller.py config.yaml.dist README.md CLAUDE.md
git status --short   # config.yaml must not be listed (gitignored)
git commit -m "monitor: add Monitor page on nav key 6

Registers MonitorPage between Tapo and Restart, documents the monitor
config section, and updates README/CLAUDE.md for the new page and the
active nav-key highlight.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 11: Check on the real deck (user)**

With SmashDeck running from this checkout, press **Restart** (key 7) to reload the code, then press **Monitor** (key 6). Expected: the Monitor label strip turns blue; within about 2 s rows 2–3 fill with live values; within a few seconds row 4 shows Münsbach weather. The network keys move when you download something; pressing any weather key refreshes the weather on the next tick.
