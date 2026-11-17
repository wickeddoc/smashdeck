# pages/monitor/weather_feed.py
"""The current weather reading, shared by every page that shows weather.

The controller builds one WeatherFeed and hands it to Home and Monitor, so
switching between them doesn't fetch again. Pages call refresh_if_due() from
their poll thread; the HTTP call runs on its own short-lived thread, so a slow
network never holds up a poll tick or a page switch. That thread only records
the outcome; pages read it with view() and draw it themselves.
"""
from __future__ import annotations

import threading
import time

from pages.monitor import weather as weather_api

WEATHER_EVERY = 15 * 60  # s between successful fetches
WEATHER_RETRY = 60  # s after a failed fetch
WEATHER_STALE = 3 * 60 * 60  # s without success before the view shows "offline"


def _start_daemon(fn):
    threading.Thread(target=fn, name="monitor-weather", daemon=True).start()


class WeatherFeed:
    def __init__(self, latitude, longitude, fetch=None, clock=time.monotonic,
                 start_thread=_start_daemon):
        self._lat = latitude
        self._lon = longitude
        self._fetch = fetch or weather_api.fetch
        self._clock = clock
        self._start_thread = start_thread
        # Written by the fetch thread, read by poll and key-callback threads;
        # never held during I/O.
        self._lock = threading.Lock()
        self._weather = None
        self._at = 0.0  # clock() of the last successful fetch
        self._due = 0.0  # clock() when the next fetch is due
        self._failed = False
        self._inflight = False
        self._requested = False  # someone asked for a fresh reading

    @classmethod
    def from_config(cls, monitor_cfg, **kwargs) -> WeatherFeed:
        """monitor_cfg: the config.yaml `monitor` section (may be empty)."""
        location = (monitor_cfg or {}).get("weather") or {}
        return cls(location.get("latitude"), location.get("longitude"), **kwargs)

    @property
    def has_location(self) -> bool:
        return self._lat is not None and self._lon is not None

    def request(self):
        """Fetch on the next refresh_if_due(), or right after a running fetch."""
        with self._lock:
            self._requested = True

    def refresh_if_due(self):
        """Start a background fetch if one is due or requested and none runs."""
        if not self.has_location:
            return
        with self._lock:
            if self._inflight:
                return  # one fetch at a time; a request is kept for afterwards
            if not (self._requested or self._clock() >= self._due):
                return
            self._inflight = True
            self._requested = False
        self._start_thread(self._fetch_now)

    def _fetch_now(self):
        """Runs on the fetch thread: fetch, then record the outcome."""
        weather, failure = None, None
        try:
            weather = self._fetch(self._lat, self._lon)
        except Exception as e:
            failure = e
        finally:
            with self._lock:
                self._inflight = False
                now = self._clock()
                if weather is not None:
                    self._weather = weather
                    self._at = now
                    self._failed = False
                    self._due = now + WEATHER_EVERY
                else:
                    self._failed = True
                    self._due = now + WEATHER_RETRY
        if failure is not None:
            print(f"monitor: weather fetch failed: {failure!r}")

    def view(self):
        """(weather to show or None, error text or None)."""
        if not self.has_location:
            return None, "no location"
        with self._lock:
            if self._weather is not None and self._clock() - self._at <= WEATHER_STALE:
                return self._weather, None
            return None, ("offline" if self._failed else None)
