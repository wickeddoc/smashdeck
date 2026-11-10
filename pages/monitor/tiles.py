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
        return lambda v: level(round(v), warn, crit)  # as displayed

    def vram_color(used_gb):
        if not s.vram_total_gb:
            return BLUE
        return level(round(used_gb / s.vram_total_gb * 100), 80, 92)

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
