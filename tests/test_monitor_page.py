# tests/test_monitor_page.py
"""MonitorPage lifecycle, polling and weather scheduling with an injected
sampler, weather fetch and clocks. render_tile is swapped for identity so each
key's recorded "image" is the Tile it would show."""
import json
import os
import threading
import time
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
        self.resets = 0
        self.next = SystemSample(cpu_temp=50.0, ram_percent=30.0, disks=[("/", 50.0)])

    def reset(self):
        self.resets += 1

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
    # Run the weather fetch inline so these tests stay synchronous; the
    # "slow" fixture below exercises the real background thread.
    p.page = MonitorPage(ctrl, sampler=p.sampler, fetch_weather=p.weather,
                         clock=p.clock, utcnow=lambda: FIXED_NOW,
                         start_thread=lambda fn: fn())
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


def test_activate_resets_sampler_rates(p):
    p.page.activate()
    p.page.deactivate()
    assert p.sampler.resets == 1


def test_repeated_poll_failures_log_one_traceback(p, monkeypatch, capsys):
    monkeypatch.setattr(monitor, "POLL_SECONDS", 0.01)

    def boom():
        p.sampler.calls += 1
        raise OSError("deck unplugged")

    p.sampler.sample = boom
    p.page.activate()
    deadline = time.monotonic() + 2.0
    while p.sampler.calls < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    p.page.deactivate()

    assert p.sampler.calls >= 3
    assert capsys.readouterr().err.count("Traceback") == 1


# --- Weather fetch on its own thread: a stalled network must not hold up
# the 2 s metric ticks or deactivate().

class BlockingWeather(FakeWeather):
    """A fetch that blocks until released, like a stalled network."""

    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, lat, lon):
        self.calls.append((lat, lon))
        self.started.set()
        self.release.wait(1.0)
        return self.weather


def fetch_threads():
    return [t for t in threading.enumerate() if t.name == "monitor-weather" and t.is_alive()]


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.005)
    return condition()


@pytest.fixture
def slow(ctrl):
    """A page with real background threads and a blocking weather fetch."""
    ctrl.config = {"monitor": {"disks": [{"name": "/", "path": "/"}], "weather": LOCATION}}
    s = SimpleNamespace(sampler=FakeSampler(), weather=BlockingWeather(), clock=Clock(), ctrl=ctrl)
    s.page = MonitorPage(ctrl, sampler=s.sampler, fetch_weather=s.weather,
                         clock=s.clock, utcnow=lambda: FIXED_NOW)
    yield s
    s.weather.release.set()
    wait_until(lambda: not fetch_threads())


def test_tick_does_not_wait_for_a_slow_fetch(slow):
    started = time.monotonic()
    slow.page.tick()
    assert time.monotonic() - started < 0.5
    assert slow.weather.started.wait(1.0)  # the fetch runs in the background
    assert shown(slow.ctrl, 8) == Tile("CPU", "50°", "°C", GREEN)
    assert shown(slow.ctrl, 24) == WeatherTile("Now", "", "—", "")  # still pending


def test_only_one_fetch_runs_at_a_time(slow):
    slow.page.tick()
    assert slow.weather.started.wait(1.0)
    slow.clock.t += 3600  # long overdue, but the first fetch is still running
    slow.page.tick()
    assert len(slow.weather.calls) == 1


def test_fetched_weather_is_drawn_on_the_next_tick(slow):
    slow.page.tick()
    assert slow.weather.started.wait(1.0)
    slow.weather.release.set()
    assert wait_until(lambda: not fetch_threads())
    slow.page.tick()
    assert shown(slow.ctrl, 24).label == "Now"
    assert shown(slow.ctrl, 24).value != "—"


def test_deactivate_does_not_wait_for_a_slow_fetch(slow):
    slow.page.activate()
    assert slow.weather.started.wait(1.0)
    started = time.monotonic()
    slow.page.deactivate()
    assert time.monotonic() - started < 0.5
    assert poll_threads() == []


def test_weather_press_during_a_fetch_triggers_one_more(slow):
    slow.page.tick()
    assert slow.weather.started.wait(1.0)
    slow.page.on_key(26)  # pressed while the first fetch is still running
    slow.page.tick()
    assert len(slow.weather.calls) == 1

    slow.weather.release.set()
    assert wait_until(lambda: not fetch_threads())
    slow.page.tick()  # the remembered press starts a fresh fetch
    assert wait_until(lambda: len(slow.weather.calls) == 2 and not fetch_threads())
    slow.page.tick()  # not due and no new press: no third fetch
    assert wait_until(lambda: not fetch_threads())
    assert len(slow.weather.calls) == 2
