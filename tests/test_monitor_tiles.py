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
