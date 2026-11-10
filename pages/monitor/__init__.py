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
        self._sampler.reset()  # no rates averaged over the hidden period
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
        failing = False  # log the first failure of a streak, not every tick
        while not stop.is_set():
            try:
                self.tick(stop)
                if failing:
                    print("monitor: poll recovered")
                    failing = False
            except Exception:
                if not failing:
                    traceback.print_exc()
                    failing = True
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
