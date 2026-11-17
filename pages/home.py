# pages/home.py
"""Home page: an at-a-glance overview plus deck brightness.

Row 2 shows CPU and GPU temperature and the current weather (the Monitor
page's own tiles); row 3 Spotify play/pause, the artist, and the song as its
album artwork. The last column, under Restart, holds brightness 33/66/100 %.
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

from PIL import Image, ImageDraw, ImageOps

from pages import BasePage
from pages.monitor.sources import SystemSample, SystemSampler
from pages.monitor.tiles import (
    BOLD,
    CPU_TEMP_KEY,
    FONT,
    GPU_TEMP_KEY,
    GREY,
    SIZE,
    WEATHER_NOW_KEY,
    WHITE,
    build_tiles,
    fit_font,
    render_tile,
)
from pages.monitor.weather_feed import WeatherFeed
from pages.spotify import PlayerSnapshot, SpotifyWatcher

POLL_SECONDS = 2.0
BRIGHTNESS_KEYS = {15: 33, 23: 66, 31: 100}  # last column, under Restart
CPU_KEY, GPU_KEY, WEATHER_KEY = 8, 9, 10
PLAY_KEY, ARTIST_KEY, SONG_KEY = 16, 17, 18
OPENS = {CPU_KEY: "monitor", GPU_KEY: "monitor", WEATHER_KEY: "monitor",
         ARTIST_KEY: "spotify", SONG_KEY: "spotify"}
SPOTIFY_GREEN = (30, 215, 96)
BLACK = (0, 0, 0)
MIN_TEXT = 16  # px at 144; smaller is unreadable once scaled to the XL's 96 px
_UNSHOWN = object()


@dataclass(frozen=True)
class PlayFace:
    playing: bool


@dataclass(frozen=True)
class TextFace:
    label: str
    text: str


@dataclass(frozen=True)
class SongFace:
    title: str
    art: Image.Image | None  # cover art; None until fetched (or none at all)


# --- drawing -------------------------------------------------------------------

def _ellipsize(text: str, font, width: int) -> str:
    if font.getlength(text) <= width:
        return text
    while text and font.getlength(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(text: str, font, width: int, max_lines: int) -> list[str]:
    """Greedy word wrap; a too-long last line ends in an ellipsis."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and font.getlength(trial) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(lines[-1] + "…", font, width)
    return lines


def _text_image(face: TextFace) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), "black")
    d = ImageDraw.Draw(img)
    mid = SIZE // 2
    d.text((mid, 21), face.label, font=fit_font(face.label, FONT, 19, SIZE - 8),
           fill=GREY, anchor="mm")
    width = SIZE - 12
    lines = _wrap(face.text, fit_font("", BOLD, 26, width), width, max_lines=3)
    top = 82 - (len(lines) - 1) * 16
    for i, line in enumerate(lines):
        font = fit_font(line, BOLD, 26, width, min_size=MIN_TEXT)
        d.text((mid, top + i * 32), _ellipsize(line, font, width), font=font,
               fill=SPOTIFY_GREEN, anchor="mm")
    return img


def _song_image(face: SongFace) -> Image.Image:
    if face.art is None:
        return _text_image(TextFace("Song", face.title))
    img = ImageOps.fit(face.art.convert("RGB"), (SIZE, SIZE))
    if face.title:
        d = ImageDraw.Draw(img, "RGBA")
        d.rectangle([(0, SIZE - 34), (SIZE, SIZE)], fill=(0, 0, 0, 190))
        font = fit_font(face.title, BOLD, 20, SIZE - 8, min_size=MIN_TEXT)
        d.text((SIZE // 2, SIZE - 17), _ellipsize(face.title, font, SIZE - 8),
               font=font, fill=WHITE, anchor="mm")
    return img


def render_face(face) -> Image.Image:
    """A 144 px key image for a monitor tile, text face or song face."""
    if isinstance(face, TextFace):
        return _text_image(face)
    if isinstance(face, SongFace):
        return _song_image(face)
    return render_tile(face)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- page ------------------------------------------------------------------------

class HomePage(BasePage):
    def __init__(self, controller, weather=None, sampler=None,
                 watch_spotify=SpotifyWatcher, utcnow=_utcnow):
        """weather: the WeatherFeed shared with the Monitor page (one is built
        from config without it). watch_spotify(on_change) makes the watcher."""
        super().__init__(controller)
        self.weather = weather or WeatherFeed.from_config(
            controller.config.get("monitor") or {})
        self._sampler = sampler or SystemSampler()
        self._spotify = watch_spotify(self._on_spotify)
        self._utcnow = utcnow

        self._sample = SystemSample.placeholder([])
        self._music = (PlayerSnapshot(), None)  # (snapshot, cover art)
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
                self._music = (self._spotify.snapshot(), self._spotify.art)
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
        self._music = (snap, self._spotify.art)
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
        self._music = (PlayerSnapshot(), None)

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

    def _on_spotify(self, snap: PlayerSnapshot, art):
        """SpotifyWatcher callback, on its listener thread."""
        self._music = (snap, art)
        self._draw()

    # --- drawing ---

    def _faces(self) -> dict:
        """Every overview key -> what it should show (None: blank)."""
        weather, error = self.weather.view()
        tiles = build_tiles(self._sample, weather, self._utcnow(), weather_error=error)
        snap, art = self._music
        return {
            CPU_KEY: tiles[CPU_TEMP_KEY],
            GPU_KEY: tiles[GPU_TEMP_KEY],
            WEATHER_KEY: tiles[WEATHER_NOW_KEY],
            PLAY_KEY: PlayFace(snap.status == "Playing"),
            ARTIST_KEY: TextFace("Artist", snap.artist) if snap.artist else None,
            SONG_KEY: SongFace(snap.title, art) if (snap.title or art) else None,
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
