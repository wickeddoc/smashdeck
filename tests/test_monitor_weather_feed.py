# tests/test_monitor_weather_feed.py
"""WeatherFeed: the weather reading Home and Monitor share. Fetches run
inline here (start_thread calls straight through); test_monitor_page.py
covers the real background thread."""
import json
import os

from pages.monitor.weather import parse
from pages.monitor.weather_feed import WeatherFeed

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "openmeteo.json")
MONITOR_CFG = {"weather": {"latitude": 49.63277, "longitude": 6.26459}}


class FakeFetch:
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


def make_feed(cfg=MONITOR_CFG):
    fetch, clock = FakeFetch(), Clock()
    feed = WeatherFeed.from_config(cfg, fetch=fetch, clock=clock,
                                   start_thread=lambda fn: fn())
    return feed, fetch, clock


def test_from_config_reads_the_location():
    feed, fetch, _ = make_feed()
    feed.refresh_if_due()
    assert fetch.calls == [(49.63277, 6.26459)]
    assert feed.view() == (fetch.weather, None)


def test_a_fresh_reading_is_not_fetched_again_until_15_minutes():
    feed, fetch, clock = make_feed()
    feed.refresh_if_due()
    clock.t += 14 * 60
    feed.refresh_if_due()
    assert len(fetch.calls) == 1
    clock.t += 60
    feed.refresh_if_due()
    assert len(fetch.calls) == 2


def test_request_fetches_on_the_next_refresh_even_when_fresh():
    feed, fetch, _ = make_feed()
    feed.refresh_if_due()
    feed.request()
    assert len(fetch.calls) == 1  # request() itself never does I/O
    feed.refresh_if_due()
    assert len(fetch.calls) == 2


def test_failure_shows_offline_and_retries_after_a_minute():
    feed, fetch, clock = make_feed()
    fetch.fail = True
    feed.refresh_if_due()
    assert feed.view() == (None, "offline")
    clock.t += 59
    feed.refresh_if_due()
    assert len(fetch.calls) == 1
    clock.t += 1
    feed.refresh_if_due()
    assert len(fetch.calls) == 2


def test_no_location_never_fetches():
    feed, fetch, _ = make_feed({})
    feed.refresh_if_due()
    feed.request()
    feed.refresh_if_due()
    assert fetch.calls == []
    assert feed.view() == (None, "no location")
