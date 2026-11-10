# Monitor page: PC hardware, system resources, weather

**Date:** 2026-11-10
**Status:** Approved; implementation plan in `docs/superpowers/plans/2026-11-10-monitor-page.md`
**Scope:** A new `Monitor` page that fills the deck's 24 content keys with live
PC metrics and local weather, reachable from nav key 6 (left of Restart).

## Goals

- One glanceable page: CPU/GPU/PC power and temperatures, RAM/disk/network,
  and current + next-day weather.
- "Big number" key style (label, large value, unit). The value is coloured by
  threshold: green fine, amber warm or filling up, red hot or nearly full.
  Metrics with no meaningful limit (watts, throughput) are blue; weather is white.
- Polls only while the page is visible: no background work on other pages.
- Missing or unsupported sensors degrade to an `n/a` key, never a crash.

## Non-goals

- Smart-home sensors (Hue sensors, Kasa/Tapo energy). None of the configured
  devices can supply them today; a later source can slot into the same tile model.
- Background alerting (tinting the nav key from other pages).
- History graphs, configurable thresholds, AMD/Intel GPU support, imperial units.
- Key presses that do anything beyond forcing a weather refresh.

## Layout

Approved via full-deck mockup (style A, network in Mbit/s).

| Key | Label | Value / unit | Source | Colour (warn / crit) |
|---|---|---|---|---|
| 6 | Monitor (nav) | new `monitor.png` icon; key 5 stays blank | — | — |
| 8 | CPU | `51°` / `°C` | `Tctl` from `zenpower` → `k10temp` → `coretemp` "Package id 0" | 75 / 90 |
| 9 | CPU load | `12` / `%` | `psutil.cpu_percent()` (delta since last tick) | 70 / 90 |
| 10 | CPU pwr | `42` / `W` | hwmon `zenpower` power label `RAPL_P_Package` | blue |
| 11 | GPU | `48°` / `°C` | `nvidia-smi` `temperature.gpu` | 75 / 85 |
| 12 | GPU load | `6` / `%` | `nvidia-smi` `utilization.gpu` | 70 / 90 |
| 13 | GPU pwr | `68` / `W` | `nvidia-smi` `power.draw` | blue |
| 14 | VRAM | `4.8` / `of 32 GB` | `nvidia-smi` `memory.used`, `memory.total` | % used: 80 / 92 |
| 15 | PC power | `214` / `W` | hwmon `corsairpsu` power label `power total` | blue |
| 16 | RAM | `32` / `%` | `psutil.virtual_memory().percent` | 80 / 92 |
| 17 | Disk `<name>` | `52` / `% full` | `psutil.disk_usage(path)`, 1st configured disk | 80 / 90 |
| 18 | Disk `<name>` | `76` / `% full` | 2nd configured disk (blank if none) | 80 / 90 |
| 19 | SSD | `61°` / `°C hottest` | max over `nvme` entries labelled `Composite` in `psutil.sensors_temperatures()` (all `nvme` entries if none are labelled) | 70 / 80 |
| 20 | Disk read | `8` / `kB/s` or `MB/s` | `psutil.disk_io_counters()` delta | blue |
| 21 | Disk write | `885` / `kB/s` or `MB/s` | same | blue |
| 22 | Net ↓ | `0.2` / `Mbit/s` | `psutil.net_io_counters(pernic=True)[iface]` delta | blue |
| 23 | Net ↑ | `0.1` / `Mbit/s` | same | blue |
| 24 | Now | condition icon, `12°`, `H 15° · L 6°` | Open-Meteo current + today | white |
| 25 | Feels like | `9°` / `°C` | `apparent_temperature` | white |
| 26 | Humidity | `78` / `%` | `relative_humidity_2m` | white |
| 27 | Wind `<SW>` | `18` / `km/h` | `wind_speed_10m`, `wind_direction_10m` → 8-point compass | white |
| 28 | Rain | `40` / `% today` | today's `precipitation_probability_max` | white |
| 29 | UV | `2` / `low` | current `uv_index`, WHO bands | <3 green, 3–7 amber, ≥8 red |
| 30 | Tomorrow | condition icon, `14° / 7°`, `80% rain` | tomorrow's daily values | white |
| 31 | Sunset / Sunrise | `16:52` / `rise 07:41` | next sun event (see below) | white |

**Number formatting**
- Temperatures and percentages are whole numbers. VRAM shows one decimal.
- Disk throughput: below 1 MB/s it shows whole kB/s, otherwise MB/s (one
  decimal under 10). Network: Mbit/s, one decimal under 10, whole numbers
  from 10, and Gbit/s with two decimals at 1000 Mbit/s or more.
- Throughput keys (20–23) and CPU load (9) show `—` whenever no rate is
  available, e.g. on the first tick, since they need two samples.
- UV band text: `low` (<3), `moderate` (3–5), `high` (6–7), `very high`
  (8–10), `extreme` (11+).

**Key 31 (next sun event)**, in the weather location's local time
(`utc_offset_seconds` from the response):
- Before today's sunrise: label `Sunrise`, value today's sunrise, detail `set <today's sunset>`.
- Between sunrise and sunset: label `Sunset`, value today's sunset, detail `rise <tomorrow's sunrise>`.
- After sunset: label `Sunrise`, value tomorrow's sunrise, detail `set <tomorrow's sunset>`.

**Weather condition icons** (WMO code → icon; day/night from `is_day`, and
tomorrow always uses the day icon):
0 → `weather_clear_{day,night}`, 1–2 → `weather_partly_{day,night}`,
3 → `weather_cloudy`, 45/48 → `weather_fog`, 51–67 and 80–82 → `weather_rain`,
71–77 and 85–86 → `weather_snow`, 95–99 → `weather_thunder`; anything else
→ `weather_cloudy`.

## Approaches considered

1. **In-process page with a sampler thread while active (chosen).** Mirrors
   `SpotifyPage`: `activate()` starts a thread, `deactivate()` stops and joins it.
   Sources are `psutil` + sysfs hwmon + `nvidia-smi`; weather uses stdlib
   `urllib` against Open-Meteo (no API key). The only new dependency is `psutil`.
2. **Read from an external agent** (Glances API, Prometheus node_exporter,
   `sensors -j`). This needs an extra service or tool running, and the
   PSU/RAPL power readings still need sysfs. Rejected.
3. **`pynvml` instead of `nvidia-smi`.** Faster (no process spawn), but it's
   another dependency, and `nvidia-smi` costs about 30 ms per 2 s tick. Rejected
   (YAGNI); it's an easy swap later because only one function parses GPU data.

## Architecture

A `pages/monitor/` subpackage keeps the feature self-contained. Each module
has one job and a small interface:

```
pages/monitor/
  __init__.py   MonitorPage(BasePage): lifecycle, poll thread, diff-render
  sources.py    SystemSampler -> SystemSample (pure data, None = unavailable)
  weather.py    Open-Meteo URL/fetch/parse -> Weather; icon + compass helpers
  tiles.py      build_tiles(sample, weather, now) -> {key: Tile}; render_tile(tile) -> Image
```

### `sources.py`

```python
@dataclass
class SystemSample:          # every field may be None (= sensor unavailable)
    cpu_temp: float | None; cpu_load: float | None; cpu_power: float | None
    gpu_temp: float | None; gpu_load: float | None; gpu_power: float | None
    vram_used_gb: float | None; vram_total_gb: float | None
    pc_power: float | None; ram_percent: float | None
    disks: list[tuple[str, float | None]]        # (name, percent full)
    ssd_temp: float | None
    disk_read: float | None; disk_write: float | None   # bytes/s
    net_down: float | None; net_up: float | None        # bytes/s
    pending: bool = False   # True only for SystemSample.placeholder(disk_names),
                            # the "—" state shown before the first real sample

class SystemSampler:
    def __init__(self, disks, net_interface=None,
                 hwmon_root="/sys/class/hwmon", route_file="/proc/net/route",
                 clock=time.monotonic, gpu_query=query_nvidia_smi): ...
    def sample(self) -> SystemSample: ...
```

Small pure helpers, each unit-tested: `read_hwmon_power(root, driver, label)`
(µW → W), `cpu_temp(sensors_temperatures_dict)`,
`default_route_interface(route_text)` (lowest-metric `00000000` destination;
re-resolved every tick so a changing default route is followed),
`parse_nvidia_smi(stdout)` (`[N/A]` → None), and a `Rate` helper whose
`update(counter, now)` turns cumulative counters into bytes/s (None on the
first call or after a counter reset). The sampler reads its clock once per
sample and passes the same `now` to all four rates.

Each source is wrapped individually: an exception or missing binary or sensor
gives `None` for that field only. The first failure per source is logged with
a traceback, and repeats are suppressed so a missing sensor doesn't spam the
log every 2 s. `nvidia-smi` runs with a 2 s timeout.

### `weather.py`

```python
@dataclass
class Day:     code: int; t_max: float; t_min: float; rain_chance: int | None
               sunrise: datetime; sunset: datetime        # naive, location-local
@dataclass
class Weather: temp: float; feels_like: float; humidity: int
               wind_speed: float; wind_dir: float; code: int; is_day: bool
               uv: float; utc_offset: timedelta; today: Day; tomorrow: Day

def build_url(lat, lon) -> str          # current + daily fields, timezone=auto, 2 days
def parse(payload: dict) -> Weather
def fetch(lat, lon, timeout=5) -> Weather
def condition_icon(code, is_day) -> str  # "weather_rain.png"
def compass(deg) -> str                  # "SW"
```

The request asks for `current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_direction_10m,weather_code,is_day,uv_index`
and `daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset`
(I checked these against a live response on 2026-11-10).

### `tiles.py`

```python
@dataclass(frozen=True)
class Tile:        label: str; value: str; unit: str; color: RGB
@dataclass(frozen=True)
class WeatherTile: label: str; icon: str; value: str; detail: str

def build_tiles(sample: SystemSample, weather: Weather | None,
                now_utc: datetime, weather_error: str | None = None
                ) -> dict[int, Tile | WeatherTile]
def render_tile(tile) -> PIL.Image.Image   # 144x144 RGB, style A
```

`build_tiles` holds all formatting, thresholds and the sun-event logic, so it
is pure and testable with literal expectations. It always returns all 24
keys (8–31); unavailable values become `Tile(label, "n/a", "", GREY)`, and
an unused disk slot (fewer than two disks configured) is `Tile("", "", "", GREY)`,
which renders as a plain black key.
`render_tile` draws at 144×144, the project's icon convention, and the Stream
Deck library downscales it as it does for icons. Fonts are DejaVu Sans
Bold/Regular with Pillow's default font as a fallback. The value's font
steps down until the text fits the key width. Weather tiles paste a
`weather_*.png` icon from `icons/`.

### `MonitorPage`

- `__init__(ctrl, sampler=None, fetch_weather=None, clock=time.monotonic,
  utcnow=...)`: reads `monitor` config. The optional arguments let tests
  inject fakes and fixed clocks; production passes nothing.
- `tick(stop=None)`: one poll. The thread calls it every 2 s and tests call
  it directly. A tick whose `stop` event is already set draws nothing, so a
  slow weather fetch that outlives `deactivate()` can't paint over the next page.
- `render()`: pushes every tile from the last data (all `—` before the first
  sample) and resets the diff cache. It's called by `switch_page` and makes
  no network or sensor calls, so it can't block the key callback.
- `activate()`: starts the poll thread. `deactivate()` sets the stop event,
  joins the thread (≤ 2.5 s) and keeps the last data for an instant redraw
  on return.
- Poll loop, every 2 s via `stop.wait(2.0)`: `sampler.sample()`, then fetch
  weather if due, then `build_tiles` and push only keys whose tile changed
  (dataclass equality against the last pushed tile). A lock guards the push,
  because `render()` can run on the key-callback thread at the same time
  (re-pressing the Monitor nav key).
- Weather is due 15 min after the last success, 60 s after a failure, or
  immediately when a weather key (24–31) is pressed (`on_key` sets a flag the
  poll thread picks up; the HTTP call never runs on the callback thread).
  The fetch runs on the poll thread with a 5 s timeout, so a slow API delays
  one tick at most. A failure prints one line (`monitor: weather fetch
  failed: ...`), not a traceback, since it repeats every 60 s while offline.
- Weather data is kept on failure. After 3 h without a successful fetch, or
  if no location is configured, key 24 shows `error.png` with detail
  `offline` / `no location` and keys 25–31 show `—`.

## Config

```yaml
monitor:
  disks:                      # up to 2, shown on keys 17-18; label "Disk <name>"
    - name: "/"
      path: "/"
    - name: "Home"
      path: "/home"
  # net_interface: "eth0"     # optional; default = interface on the default route
  weather:
    latitude: 52.52           # coordinates are sent to api.open-meteo.com
    longitude: 13.41
```

`config.yaml.dist` gets this example section (Open-Meteo's Berlin example).
The local `config.yaml` uses Münsbach, Luxembourg: `latitude: 49.63277`,
`longitude: 6.26459` (Open-Meteo geocoding, Europe/Luxembourg time zone),
with that place name as a comment.

## Related change: active nav-key highlight

Today `render_nav_bar` passes the active page's highlight as `color=`. That is
only the background for icon-less keys, and every nav icon is an opaque
tile, so the current page is never marked. The approved fix, style C
("label strip"):

- `set_key_image` gains `label_bg: RGB | None = None`. When it's set, after
  scaling, the bottom label strip (the same 20 px margin the icon is kept
  out of) is filled with `label_bg`, and the label is drawn in bold dark text
  (`(10, 20, 40)`, DejaVu Sans Bold 12) on top. The icon is untouched.
- `render_nav_bar` passes `label_bg=NAV_ACTIVE_COLOR` (`(110, 170, 255)`)
  for the active page's key and drops the ineffective `color=` argument.
- Test, in `tests/test_controller.py` with the existing `ImageDeck`
  stub: after switching pages, decode the active nav key's native JPEG,
  undo the XL's flip, and check that a pixel in the label strip away from
  the text is the accent colour while the same pixel on an inactive nav
  key is black. Switching pages moves the strip.

It ships as its own commit before the Monitor work.

## Changes to existing files

- `main.py`: `NAV_KEYS[6] = ("monitor", "monitor.png", "Monitor")`; register
  `MonitorPage` in `self.pages`.
- `generate_icons.py`: `monitor.png` (bar-chart tile) and the nine
  `weather_*.png` icons, at 144×144 like the rest.
- `requirements.txt`: add `psutil`.
- `config.yaml.dist`: `monitor` section.
- `README.md`, `CLAUDE.md`: key 6 is Monitor, key 5 stays reserved; page
  description; config section.
- `.gitignore`: add `.superpowers/` (brainstorm mockups).

## Testing

All tests run without hardware, network, `nvidia-smi` or real sensors.

- `test_monitor_sources.py`
  - `read_hwmon_power` against a fake hwmon tree in `tmp_path`.
  - `default_route_interface` on sample `/proc/net/route` text.
  - `parse_nvidia_smi`, including `[N/A]` and empty output.
  - `cpu_temp` driver preference order.
  - `Rate`: first call None, then the correct bytes/s with a stepped fake
    clock, None after a counter reset.
  - A missing `nvidia-smi` gives None GPU fields while the other fields are
    still filled in.
- `test_monitor_weather.py`
  - `parse` of a trimmed real Open-Meteo response saved in
    `tests/fixtures/openmeteo.json`, checked against hand-read literal values.
  - `condition_icon` and `compass` tables.
  - `build_url` contains the coordinates and the required fields.
- `test_monitor_tiles.py`
  - `build_tiles` with hand-built samples, checked against literal tiles:
    threshold colours at boundaries; Mbit/s, Gbit/s and kB/s/MB/s
    formatting; `n/a` for None; first-tick `—`; the second disk key is blank
    when only one disk is configured.
  - Key 31 before sunrise, between sunrise and sunset, and after sunset.
  - UV bands.
  - `render_tile` returns a 144×144 image for long values.
- `test_monitor_page.py`, using `FakeController` with an injected fake
  sampler and weather fetch:
  - `render()` pushes all 24 content keys without calling either source.
  - A poll tick re-pushes only the keys that changed.
  - A weather-key press triggers the fetch on the next tick, not in `on_key`.
  - `deactivate()` stops the thread.
  - Weather failure falls back to the error tile, with no location
    configured and after 3 h of failures.
