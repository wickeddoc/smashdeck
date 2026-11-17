# pages/home.py
"""Home page: an at-a-glance overview plus deck brightness.

Row 2 shows CPU and GPU temperature and the current weather (the Monitor
page's own tiles); row 3 Spotify play/pause, the artist (its photo when
artist photos are on), and the song as its album artwork. The last column, under Restart, holds brightness 33/66/100 %.
Pressing a temperature or the weather opens the Monitor page; pressing the
artist or the song opens the Spotify page.

While visible, a home-poll thread samples the temperatures every POLL_SECONDS
and keeps the shared WeatherFeed fresh, and a SpotifyWatcher reports track
changes. Both redraw only the keys whose face changed.
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime

from pages import BasePage
from pages.faces import SPOTIFY_GREEN, PictureFace, render_face
from pages.monitor.sources import SystemSample, SystemSampler
from pages.monitor.tiles import CPU_TEMP_KEY, GPU_TEMP_KEY, WEATHER_NOW_KEY, build_tiles
from pages.monitor.weather_feed import WeatherFeed
from pages.spotify import PlayerSnapshot, SpotifyWatcher

POLL_SECONDS = 2.0
BRIGHTNESS_KEYS = {15: 33, 23: 66, 31: 100}  # last column, under Restart
CPU_KEY, GPU_KEY, WEATHER_KEY = 8, 9, 10
PLAY_KEY, ARTIST_KEY, SONG_KEY = 16, 17, 18
OPENS = {CPU_KEY: "monitor", GPU_KEY: "monitor", WEATHER_KEY: "monitor",
         ARTIST_KEY: "spotify", SONG_KEY: "spotify"}
BLACK = (0, 0, 0)
_UNSHOWN = object()


@dataclass(frozen=True)
class PlayFace:
    playing: bool


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HomePage(BasePage):
    def __init__(self, controller, weather=None, sampler=None,
                 watch_spotify=SpotifyWatcher, artist_photos=None, utcnow=_utcnow):
        """weather: the WeatherFeed shared with the Monitor page (one is built
        from config without it). artist_photos: the ArtistPhotos shared with
        the Spotify page, or None (off).
        watch_spotify(on_change, artist_photos=) makes the watcher."""
        super().__init__(controller)
        self.weather = weather or WeatherFeed.from_config(
            controller.config.get("monitor") or {})
        self.artist_photos = artist_photos
        self._sampler = sampler or SystemSampler()
        self._spotify = watch_spotify(self._on_spotify, artist_photos=artist_photos)
        self._utcnow = utcnow

        self._sample = SystemSample.placeholder([])
        self._music = (PlayerSnapshot(), None, None)  # (snapshot, cover, artist photo)
        self._shown = {}  # key -> face currently on the deck
        # Draws come from the poll, Spotify listener and key-callback threads.
        # _visible is True from render() until deactivate(); once it is False
        # (set under the lock, so an in-flight draw finishes first) nothing
        # draws, even a listener callback racing the page switch.
        self._lock = threading.Lock()
        self._visible = False
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    # --- BasePage ---

    def render(self):
        with self._lock:
            faces = self._faces()
            for key in range(8, self.ctrl.deck.key_count()):
                if key not in faces and key not in BRIGHTNESS_KEYS:
                    self.ctrl.set_key_image(key, color=BLACK)
            for key, pct in BRIGHTNESS_KEYS.items():
                self.ctrl.set_key_image(key, f"brightness_{pct}.png", f"{pct}%")
            self._shown = {}
            self._visible = True
            self._push_changes(faces)

    def on_key(self, key):
        pct = BRIGHTNESS_KEYS.get(key)
        if pct is not None:
            self.ctrl.deck.set_brightness(pct)
        elif key == PLAY_KEY:
            mpris = self._spotify.mpris
            if mpris is not None:
                mpris.play_pause()
                self._music = (self._spotify.snapshot(), self._spotify.art,
                               self._spotify.artist_photo)
                self._draw()  # at once; the listener reports it too
        elif key in OPENS:
            self.ctrl.switch_page(OPENS[key])

    def activate(self):
        self._sampler.reset()  # no rates averaged over the hidden period
        try:
            snap = self._spotify.start()
        except Exception as e:  # Home is the start page: never fail it
            print(f"home: Spotify unavailable: {e!r}")
            snap = PlayerSnapshot()
        self._music = (snap, self._spotify.art, self._spotify.artist_photo)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(self._stop,), name="home-poll", daemon=True)
        self._thread.start()

    def deactivate(self):
        with self._lock:
            self._visible = False
        if self._stop is not None:
            self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=POLL_SECONDS + 0.5)
        self._stop = None
        self._thread = None
        self._spotify.stop()
        self._music = (PlayerSnapshot(), None, None)

    # --- updates ---

    def _run(self, stop: threading.Event):
        failing = False  # log the first failure of a streak, not every tick
        while not stop.is_set():
            try:
                self.tick()
                if failing:
                    print("home: poll recovered")
                    failing = False
            except Exception:
                if not failing:
                    traceback.print_exc()
                    failing = True
            stop.wait(POLL_SECONDS)

    def tick(self):
        """One poll: sample the temperatures, refresh weather if due, redraw."""
        self._sample = self._sampler.sample()
        self.weather.refresh_if_due()
        self._draw()

    def _on_spotify(self, snap: PlayerSnapshot, art, artist_photo):
        """SpotifyWatcher callback, on its listener or artist-photo thread."""
        self._music = (snap, art, artist_photo)
        self._draw()

    # --- drawing ---

    def _faces(self) -> dict:
        """Every overview key -> what it should show (None: blank)."""
        weather, error = self.weather.view()
        tiles = build_tiles(self._sample, weather, self._utcnow(), weather_error=error)
        snap, art, photo = self._music
        return {
            CPU_KEY: tiles[CPU_TEMP_KEY],
            GPU_KEY: tiles[GPU_TEMP_KEY],
            WEATHER_KEY: tiles[WEATHER_NOW_KEY],
            PLAY_KEY: PlayFace(snap.status == "Playing"),
            ARTIST_KEY: PictureFace("Artist", snap.artist, photo) if snap.artist else None,
            SONG_KEY: PictureFace("Song", snap.title, art) if (snap.title or art) else None,
        }

    def _draw(self):
        with self._lock:
            if self._visible:
                self._push_changes(self._faces())

    def _push_changes(self, faces: dict):
        """Draw the keys whose face changed. Call with the lock held."""
        for key, face in faces.items():
            if self._shown.get(key, _UNSHOWN) == face:
                continue
            if face is None:
                self.ctrl.set_key_image(key, color=BLACK)
            elif isinstance(face, PlayFace):
                self.ctrl.set_key_image(
                    key, "pause.png" if face.playing else "play.png",
                    highlight=SPOTIFY_GREEN if face.playing else None)
            else:
                self.ctrl.set_key_image(key, pil_image=render_face(face))
            self._shown[key] = face
