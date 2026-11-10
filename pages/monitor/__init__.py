# pages/monitor/__init__.py
"""Monitor page: live PC metrics (rows 2-3) and Open-Meteo weather (row 4).

Polls only while visible: activate() starts a thread that ticks every
POLL_SECONDS, deactivate() stops it. Each tick redraws only the keys whose
tile changed. Sensor reads never run on the Stream Deck's key-callback
thread, and the weather HTTP call runs on its own short-lived thread so a
slow network can't hold up the metric ticks or deactivate(). That thread
only records the result; the poll thread draws it on its next tick.
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


def _start_daemon(fn):
    threading.Thread(target=fn, name="monitor-weather", daemon=True).start()


class MonitorPage(BasePage):
    def __init__(self, controller, sampler=None, fetch_weather=None,
                 clock=time.monotonic, utcnow=_utcnow, start_thread=_start_daemon):
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
        self._start_thread = start_thread

        self._sample = SystemSample.placeholder([d["name"] for d in disks])
        # Weather state is written by the fetch thread and read by the poll
        # and key-callback threads; _weather_lock is never held during I/O.
        self._weather_lock = threading.Lock()
        self._weather = None
        self._weather_at = 0.0  # clock() of the last successful fetch
        self._weather_due = 0.0  # clock() when the next fetch is due
        self._weather_failed = False
        self._weather_inflight = False
        self._weather_requested = False  # a weather key was pressed

        self._shown = {}  # key -> tile currently on the deck
        self._lock = threading.Lock()
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    # --- BasePage ---

    def render(self):
        self._draw(full=True)

    def on_key(self, key):
        if key in WEATHER_KEYS:
            # Picked up by the next tick, or after a fetch already running.
            with self._weather_lock:
                self._weather_requested = True

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
        """One poll: sample the system, start a weather fetch if due, redraw."""
        self._sample = self._sampler.sample()
        self._start_weather_fetch_if_due()
        self._draw(full=False, stop=stop)

    def _has_location(self) -> bool:
        return self._lat is not None and self._lon is not None

    def _start_weather_fetch_if_due(self):
        if not self._has_location():
            return
        with self._weather_lock:
            if self._weather_inflight:
                return  # one fetch at a time; a press is kept for afterwards
            if not (self._weather_requested or self._clock() >= self._weather_due):
                return
            self._weather_inflight = True
            self._weather_requested = False
        self._start_thread(self._fetch_weather_now)

    def _fetch_weather_now(self):
        """Runs on the fetch thread: fetch, then record the outcome. Never draws."""
        weather, failure = None, None
        try:
            weather = self._fetch_weather(self._lat, self._lon)
        except Exception as e:
            failure = e
        finally:
            with self._weather_lock:
                self._weather_inflight = False
                now = self._clock()
                if weather is not None:
                    self._weather = weather
                    self._weather_at = now
                    self._weather_failed = False
                    self._weather_due = now + WEATHER_EVERY
                else:
                    self._weather_failed = True
                    self._weather_due = now + WEATHER_RETRY
        if failure is not None:
            print(f"monitor: weather fetch failed: {failure!r}")

    def _weather_view(self):
        """(weather to show, error text for key 24)."""
        if not self._has_location():
            return None, "no location"
        with self._weather_lock:
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
