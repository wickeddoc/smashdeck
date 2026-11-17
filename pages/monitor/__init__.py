# pages/monitor/__init__.py
"""Monitor page: live PC metrics (rows 2-3) and Open-Meteo weather (row 4).

Polls only while visible: activate() starts a thread that ticks every
POLL_SECONDS, deactivate() stops it. Each tick redraws only the keys whose
tile changed. Sensor reads never run on the Stream Deck's key-callback
thread. Weather comes from a WeatherFeed (shared with the Home page), which
fetches on its own short-lived thread so a slow network can't hold up the
metric ticks or deactivate(); the poll thread draws the result on its next
tick.
"""
from __future__ import annotations

import threading
import traceback
from datetime import UTC, datetime

from pages import BasePage
from pages.monitor.sources import SystemSample, SystemSampler
from pages.monitor.tiles import WEATHER_KEYS, build_tiles, render_tile
from pages.monitor.weather_feed import WeatherFeed

POLL_SECONDS = 2.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MonitorPage(BasePage):
    def __init__(self, controller, sampler=None, weather=None, utcnow=_utcnow,
                 **feed_kwargs):
        """weather: the shared WeatherFeed. Without one, the page builds its
        own from config; feed_kwargs (fetch, clock, start_thread) go to it."""
        super().__init__(controller)
        cfg = controller.config.get("monitor") or {}
        disks = (cfg.get("disks") or [])[:2]
        self._sampler = sampler or SystemSampler(
            disks=disks, net_interface=cfg.get("net_interface"))
        self.weather = weather or WeatherFeed.from_config(cfg, **feed_kwargs)
        self._utcnow = utcnow

        self._sample = SystemSample.placeholder([d["name"] for d in disks])
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
            self.weather.request()

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
        self.weather.refresh_if_due()
        self._draw(full=False, stop=stop)

    def _draw(self, full: bool, stop: threading.Event | None = None):
        weather, error = self.weather.view()
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
