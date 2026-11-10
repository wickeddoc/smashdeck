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
